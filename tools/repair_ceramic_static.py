#!/usr/bin/env python3
"""Explicit ceramic static-reference retry; waits for the seven-case repair batch."""
import argparse
import json
from pathlib import Path
import subprocess
import time
import httpx

ROOT=Path(__file__).resolve().parents[1]
PRIVATE=Path('/var/lib/visualstation-local')
STATE=PRIVATE/'recommendation20-ceramic-static-state.json'
CASES={c['id']:c for c in json.loads((ROOT/'productions/recommendation_20_v1/cases.json').read_text())['cases']}
DIRECTIONS={
 'sneakers':'以参考图中静置台阶上的单只白橙运动鞋为唯一商品，全程没有人、脚、裤腿、穿鞋或走路动作。保持鞋帮、鞋舌、鞋带、橙色鞋底、后跟橙色装饰条及中底几何形状，固定同一侧面。两个镜头分别沿鞋面细节极缓推近与小幅拉远，黄昏城市灯光形成背景层次，不旋转商品、不增加另一只鞋。',
 'bag':'固定参考图中的无标识焦糖棕帆布包，静置在雨后咖啡馆石墙旁。禁止人和车辆经过前景遮挡商品，不做肩背或拿起动作，不生成文字或标志。两个镜头分别细节轻推和小幅拉远；湿地反光、窗内暖光形成层次。保持包形、提手与桌面/地面接触关系。',
 'headphones':'耳机必须保持参考图中的固定形状、耳罩与头梁连接结构，以及原有桌面接触方式。禁止新增支架、悬浮、旋转耳罩、出现人手、拿起或放下。两个镜头只做不超过百分之五的平移或推近，保持同一可见侧面和真实接触阴影。',
 'morning-coffee':'展示已经泡好的咖啡。陶杯中咖啡液面始终固定，分享壶、滤杯和水壶全程静置；禁止注水、冲煮、填充或凭空出现液体。第一镜微距缓推，第二镜轻微拉远，保持同样成品状态。',
 'tea':'展示已经泡好的青瓷杯清茶。全程固定液位、杯形与茶叶数量，不注水、不增减茶叶。第一镜缓慢推进，第二镜轻微拉远；窗外竹影和雨滴形成环境变化。',
 'ceramic':'展示图中的米白陶杯。固定杯口宽度、高度、收底、釉面旋纹与双手位置。不捧起、不捏握、不旋转杯子。第一镜极缓推近，第二镜横移不超过画面百分之五，光影细腻。'}


def save(value):
 p=STATE.with_suffix('.tmp');p.write_text(json.dumps(value,ensure_ascii=False,indent=2));p.replace(STATE)


def wait_for_main():
 while True:
  proc=subprocess.run(['systemctl','is-active','visualagent-recommendation20-repair-v5'],capture_output=True,text=True)
  s=json.loads((PRIVATE/'recommendation20-repair-state.json').read_text())
  if proc.stdout.strip() not in ('active','activating','deactivating'):
   if len(s['cases'])!=7 or any(v['state'] not in ('completed','failed','planning_failed') for v in s['cases'].values()):
    raise RuntimeError('Main batch stopped unexpectedly; reconcile before repairs')
   return s
  time.sleep(20)


def main():
 parser=argparse.ArgumentParser()
 parser.add_argument('--prepare-only',action='store_true',help='Prepare plans without submitting video generation')
 args=parser.parse_args()
 prior=json.loads((PRIVATE/'recommendation20-repair-state.json').read_text()) if args.prepare_only else wait_for_main()
 state=json.loads(STATE.read_text()) if STATE.exists() else {'cases':{},'new_revision_credit_cap':4,'total_account_cap':138,'training_eligible':False}
 refs=json.loads((PRIVATE/'template-reference-images/references.json').read_text())
 key=json.loads((PRIVATE/'recommendation20-account.json').read_text())['api_key']
 with httpx.Client(base_url='http://127.0.0.1:30080',headers={'Authorization':'Bearer '+key},timeout=180,trust_env=False) as c:
  def request(method,path,**kwargs):
   r=c.request(method,path,**kwargs)
   if not r.is_success:raise RuntimeError(f'Studio response {r.status_code}')
   return r.json()
  for slug in ['ceramic']:
   case=CASES[slug];credits=case['approved_credits'];assert credits in (4,6)
   record=state['cases'].setdefault(slug,{'state':'not_started','attempt':prior['cases'][slug]['attempt']+(0 if slug=='sparkling' else 1),'retry_of_run':(prior['cases'][slug].get('run_id') or prior['cases'][slug].get('retry_of_run'))})
   if record['state']=='completed':continue
   if not record.get('project'):
    if slug=='sparkling':
     p=request('GET','/creative/api/projects/'+prior['cases'][slug]['project']);assert p['state']=='ready' and not p.get('run_id')
     record.update(project=p['id'],state='planned');save(state)
    else:
     p=request('POST','/creative/api/projects',json={k:case[k] for k in ('provider','model','aspect','duration')}|{'message':f"修订广告《{case['title']}》。{'米白陶杯独立静置在木桌上，无人无手。杯口、外鼓杯身、收底和足圈全程刚性不变，保持接地阴影。镜头固定，暖色日光与背景树影缓慢变化。两段分别较近景与稍宽环境景，杯子和书本均不移动。禁止旋转、伸缩、挤压杯子，不添加物体。'} 两个五秒镜头用同一参考图；保持商品几何结构，所有可读文字由后期添加。字幕分别为：{case['captions'][0]} / {case['captions'][1]}。brief.cta使用第二条字幕作为情绪行动收束，不另加未出现在字幕里的行动文案。不编造品牌、价格或功效。直接给完整两镜方案。"})
     record.update(project=p['id'],state='created');save(state)
   route='/creative/api/projects/'+record['project'];p=request('GET',route)
   if record['state']=='created':
    reference=json.loads((PRIVATE/'template-reference-repairs/ceramic-v4/result.json').read_text())['path']
    if not p.get('reference'):p=request('POST',route+'/reference',params={'revision':p['revision']},content=Path(reference).read_bytes())
    record['state']='planning_requested';save(state)
    p=request('POST',route+'/message',json={'revision':p['revision'],'mode':'plan','text':''})
    assert p['state']=='ready';record['state']='planned';save(state)
   if record['state']=='planning_requested':
    if p['state']!='ready':raise RuntimeError('Planning needs reconciliation; no automatic retry')
    record['state']='planned';save(state)
   if args.prepare_only:
    if record['state']!='planned' or p['state']!='ready' or p.get('run_id'):
     raise RuntimeError('Preparation requires an unsubmitted ready plan')
    assert p['quote']['credits']==credits
    print(slug,'prepared_without_generation',flush=True)
    continue
   if record['state']=='planned':
    assert p['quote']['credits']==credits
    record['state']='execution_requested';save(state)
    p=request('POST',route+'/execute',json={'revision':p['revision'],'approved_credits':credits})
    record.update(state='observing',run_id=p['run_id']);save(state)
   while True:
    try:p=request('GET',route)
    except (httpx.HTTPError,RuntimeError):time.sleep(15);continue
    if p['state']=='completed':
     record.update(state='completed',run_id=p['run_id'],technical=p['qa']['technical']);save(state);print(slug,'repair_completed',flush=True);break
    if p['state'] not in ('running','rendering'):
     record.update(state='needs_reconciliation',project_state=p['state']);save(state);raise RuntimeError('Repair stopped; no automatic retry')
    time.sleep(15)

if __name__=='__main__':main()
