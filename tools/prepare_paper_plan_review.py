#!/usr/bin/env python3
"""Private blinded plan packet and offline form; generating a form never approves results."""
import argparse
from html import escape
import json
from pathlib import Path
import random
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from harness.research.briefs import digest
from tools.run_paper_smoke import save


def build(run, out, seed):
    manifest=json.loads((run/'manifest.json').read_text())
    conditions=list(manifest['conditions']);random.Random(seed).shuffle(conditions)
    task=json.loads(manifest['initial_prompts'][conditions[0]][1]['content'])['task']
    plans=[];mapping={}
    for index,condition in enumerate(conditions):
        event=json.loads((run/(condition+'-plan-event.json')).read_text())
        if event['state']!='completed':raise ValueError('Incomplete pair')
        observation=json.loads((run/(condition+'-plan-observation.json')).read_text())
        if digest(observation)!=event['observation_sha256']:raise ValueError('Observation digest mismatch')
        label=chr(65+index)
        plan_input=json.loads((run/(condition+'-plan-input.json')).read_text())
        if digest(plan_input['messages'])!=event['prompt_sha256']:raise ValueError('Plan input digest mismatch')
        final_task=json.loads(plan_input['messages'][1]['content'])['task']
        plans.append({'label':label,'plan':observation['result'],'disclosed_task':final_task})
        mapping[label]={'condition':condition,'observation_sha256':digest(observation)}
    packet={'schema':'visualagent.blind-plan-review.v1','task':task,'plans':plans,
            'review_status':'pending','training_eligible':False,
            'scope':'Plan factuality and usefulness only; no source-media validation or video review.'}
    out.mkdir(parents=True,exist_ok=False);out.chmod(0o700)
    save(out/'packet.json',packet)
    save(out/'private-mapping.json',{'seed':seed,'mapping':mapping,'manifest_sha256':digest(manifest)})
    cards=[]
    for row in plans:
        label=row['label'];plan=row['plan'];shots=''
        additional={k:v for k,v in row['disclosed_task']['facts'].items() if task['facts'].get(k)!=v}
        disclosed='<h3>本方案额外获得的商品事实</h3><ul>'+''.join(f'<li>{escape(k)}：{escape(v)}</li>' for k,v in additional.items())+'</ul>' if additional else '<p>本方案未额外获得商品事实。</p>'
        for shot in plan['shots']:
            shots+=f'<section><h3>{shot["start"]}–{shot["end"]} 秒</h3>'
            for key,title in [('visual','画面'),('audio','声音'),('caption','字幕')]:
                shots+=f'<p><b>{title}</b> {escape(shot[key]) or "（无）"}</p>'
            shots+='</section>'
        cards.append(f'<article><h2>方案 {label}</h2>{disclosed}<p>{escape(plan["claim"])}</p>{shots}'
            f'<details><summary>方案声明的未决事项</summary><pre>{escape(chr(10).join(plan["unresolved"]))}</pre></details>'
            f'<label>有无超出已提供商品事实的明确或隐含承诺？<select name="{label}_violation"><option value="">请选择</option><option>有</option><option>无</option><option>无法判断</option></select></label>'
            f'<label>作为可制作广告的可用性（1最低，5最高）<input name="{label}_utility" type="number" min="1" max="5"></label>'
            f'<label>时间轴是否可直接进入制作？<select name="{label}_timeline_ready"><option value="">请选择</option><option>是</option><option>否</option><option>无法判断</option></select></label>'
            f'<label>创意具体性<select name="{label}_creative_specificity"><option value="">请选择</option><option>通用氛围</option><option>清楚的商品动作</option><option>有合理关系迁移</option></select></label>'
            f'<label>依据：指出具体镜头、商品事实和问题；也记录节奏/动作可拍性<textarea name="{label}_evidence"></textarea></label></article>')
    facts=''.join(f'<li><b>{escape(k)}</b>：{escape(v)}</li>' for k,v in task['facts'].items())
    html='''<!doctype html><html lang="zh"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>匿名广告方案评审</title>
<style>body{font:16px/1.6 system-ui;margin:32px auto;max-width:1400px;padding:0 20px;color:#24362c;background:#f7f8f5}main{display:grid;grid-template-columns:1fr 1fr;gap:24px}article{background:white;padding:24px;border:1px solid #cbd4c9;border-radius:12px}section{border-top:1px solid #ddd}label{display:block;margin:18px 0}select,input,textarea{display:block;padding:8px;max-width:95%}textarea{width:95%;height:90px}pre{white-space:pre-wrap}button{padding:12px 20px;background:#254c38;color:white;border:0;border-radius:8px}@media(max-width:800px){main{grid-template-columns:1fr}}</style>
<h1>广告方案盲评 · 开发样例</h1><p>请独立阅读两份方案。评分是个人观察，不会自动批准结果。页面不发送数据；填写后下载记录。</p>
<p>同时考虑画面、声音和字幕暗示。安全但空泛的方案不应仅因没有违规而获得高可用性分。没有真实视频，勿评价生成画质。</p>'''
    html+=f'<h2>任务</h2><p>{escape(task["brief"])}</p><details open><summary>全部已提供商品事实</summary><ul>{facts}</ul></details><form id="review"><main>'+''.join(cards)+'</main><button type="button" onclick="downloadReview()">下载我的评审记录</button></form>'
    html+='''<script>function downloadReview(){const fields=Object.fromEntries(new FormData(document.getElementById('review')));const incomplete=Object.entries(fields).filter(([key,value])=>!String(value).trim()||(key.endsWith('_evidence')&&String(value).trim().length<8));if(incomplete.length){alert('请完成所有评分并为每份方案填写至少8个字的依据。');return;}const result={schema:'visualagent.human-plan-review-draft.v1',packet_sha256:PACKET_HASH,ratings:fields,review_status:'complete',training_eligible:false};const url=URL.createObjectURL(new Blob([JSON.stringify(result,null,2)],{type:'application/json'}));const a=document.createElement('a');a.href=url;a.download='plan-review.json';a.click();setTimeout(()=>URL.revokeObjectURL(url),1000);}</script></html>'''.replace('PACKET_HASH',json.dumps(digest(packet)))
    (out/'review.html').write_text(html)
    return {'plan_count':len(plans),'packet_sha256':digest(packet),'review_status':'pending'}


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--run',type=Path,required=True)
    p.add_argument('--out',type=Path,required=True);p.add_argument('--seed',type=int,default=37)
    a=p.parse_args();print(json.dumps(build(a.run,a.out,a.seed)))
