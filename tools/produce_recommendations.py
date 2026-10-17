#!/usr/bin/env python3
"""Bounded first-attempt template production via the existing studio API.

No provider calls live here: the authenticated Studio Runner owns generation.
A stopped/uncertain attempt is observed, never automatically submitted again.
"""
import argparse
import json
import os
from pathlib import Path
import time
import httpx


def write(path, value):
    temporary = path.with_suffix('.tmp')
    temporary.write_text(json.dumps(value,ensure_ascii=False,indent=2)+'\n')
    temporary.replace(path)


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--manifest',required=True)
    parser.add_argument('--state',required=True)
    parser.add_argument('--key-file',required=True)
    parser.add_argument('--references')
    parser.add_argument('--prior-state')
    args=parser.parse_args()
    manifest=json.loads(Path(args.manifest).read_text())
    cases=manifest['cases']
    assert len(cases)==20 and len({c['id'] for c in cases})==20
    assert sum(c['approved_credits'] for c in cases)==manifest['max_first_attempt_credits']==92
    path=Path(args.state);path.parent.mkdir(parents=True,exist_ok=True,mode=0o700)
    state=json.loads(path.read_text()) if path.exists() else {'cases':{},'training_eligible':False}
    key=json.loads(Path(args.key_file).read_text())['api_key']
    with httpx.Client(base_url=os.getenv('CREATIVE_BATCH_URL','http://127.0.0.1:30080'),headers={'Authorization':'Bearer '+key},timeout=180,trust_env=False) as client:
        def request(method,url,**kwargs):
            r=client.request(method,url,**kwargs)
            if not r.is_success: raise RuntimeError(f'Studio response {r.status_code}')
            return r.json()
        for case in cases:
            record=state['cases'].setdefault(case['id'],{'state':'not_started','attempt':1})
            if args.prior_state:
                prior=json.loads(Path(args.prior_state).read_text())['cases'].get(case['id'],{})
                if prior.get('run_id'):
                    record.update(attempt=2,retry_of_run=prior['run_id'])
            if record['state'] in ('completed','failed','planning_failed'): continue
            reference=None
            if args.references:
                while True:
                    refs=json.loads(Path(args.references).read_text())
                    reference=refs.get(case['id'],{})
                    if reference.get('state')=='completed':break
                    if reference.get('state')=='failed_no_retry':
                        raise RuntimeError('Reference generation failed; explicit new attempt required')
                    time.sleep(15)
            if not record.get('project'):
                message=(f"制作一支可用于首页模板参考的10秒广告。标题：{case['title']}。产品：{case['product']}。"
                    f"视觉场景：{case['scene']}。两个镜头必须重复完全相同的产品外观约束，分别以细节吸引和场景价值收束；"
                    f"两个字幕原样使用：{case['captions'][0]} / {case['captions'][1]}。"
                    "brief.cta使用第二条字幕作为情绪行动收束，不另加未出现在字幕里的行动文案。"
                    "成年消费者，真实可感的生活体验。丰富前中后景，精致商业摄影，不能空洞。"
                    "不要编造品牌、价格、折扣、功效、认证；不生成可读文字或标志。商品一致性必须审阅。"
                    "参考图已是商品展示状态，不演示反复注水、灌注、凭空填满或改变物体形状。"
                    "两段都会从同一参考图开始，因此设计成两个独立展示视角，不延续需要累积状态的动作。"
                    "以轻缓运镜、景深和合理环境细节形成变化，保持商品尺寸与结构；避免复杂手部操作。直接形成完整方案。")
                p=request('POST','/creative/api/projects',json={k:case[k] for k in ('provider','model','aspect','duration')}|{'message':message})
                record.update(project=p['id'],state='created');write(path,state)
            pid=record['project'];route='/creative/api/projects/'+pid
            p=request('GET',route)
            if record['state']=='planning_requested':
                # Recover a response lost after planning finished, without another model call.
                while p['state']=='planning':
                    time.sleep(10);p=request('GET',route)
                if p['state']=='ready' and len(p['shots'])==2:
                    assert p['quote']['credits']==case['approved_credits']
                    record['state']='planned';write(path,state)
                else:
                    raise RuntimeError('Interrupted planning requires reconciliation before continuation')
            if reference and record['state']=='created' and not p.get('reference'):
                image=Path(reference['path']).read_bytes()
                p=request('POST',route+'/reference',params={'revision':p['revision']},content=image)
                record['reference_sha256']=p['reference']['sha256'];write(path,state)
            if record['state']=='created':
                record['state']='planning_requested';write(path,state)
                try:p=request('POST',route+'/message',json={'revision':p['revision'],'mode':'plan','text':''})
                except Exception:
                    record['state']='planning_failed';write(path,state);print(case['id'],'planning_failed',flush=True);continue
                assert p['state']=='ready' and len(p['shots'])==2
                assert p['quote']['credits']==case['approved_credits']
                record['state']='planned';write(path,state)
            if record['state']=='planned':
                assert p['quote']['credits']==case['approved_credits']
                record['state']='execution_requested';write(path,state)
                # Persist intent before POST. An interrupted call cannot lead to a second POST.
                p=request('POST',route+'/execute',json={'revision':p['revision'],'approved_credits':case['approved_credits']})
                record['run_id']=p['run_id'];record['state']='observing';write(path,state)
            if record['state']=='planning_requested':
                raise RuntimeError('Interrupted planning requires reconciliation before continuation')
            while True:
                try:p=request('GET',route)
                except (httpx.HTTPError,RuntimeError):time.sleep(15);continue
                if p['state']=='completed':
                    record.update(state='completed',run_id=p['run_id'],technical=p.get('qa',{}).get('technical'),training_eligible=False)
                    write(path,state);print(case['id'],'completed',flush=True);break
                if p['state']=='failed':
                    record.update(state='failed',run_id=p.get('run_id'));write(path,state);print(case['id'],'failed_no_retry',flush=True);break
                if p['state'] not in ('running','rendering'):
                    record.update(state='needs_reconciliation',project_state=p['state']);write(path,state)
                    raise RuntimeError('Production paused; inspect the saved project, do not resubmit')
                record.update(state='observing',project_state=p['state'],completed_shots=sum(s['state']=='completed' for s in p['shots']))
                write(path,state);time.sleep(15)
    print('First-attempt batch finished; inspect reviews before publishing.',flush=True)

if __name__=='__main__':main()
