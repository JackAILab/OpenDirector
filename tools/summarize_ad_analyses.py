#!/usr/bin/env python3
"""Aggregate evidence-backed ad analysis into safe mechanism statistics."""
import argparse,json,os,statistics,sys,sqlite3
from collections import Counter
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from harness.library import learning,store

TAXONOMY={
 'visible_proof':['可见结果','结果变化','功能证明','证明','动作验证','演示','压力测试','性能'],
 'attention_task':['寻找','搜索','看不见','难以辨认','等待','悬念','疑惑','猜','任务'],
 'contrast_or_reversal':['反转','对照','误判','意外','冲突','重释','反差','揭示'],
 'human_reaction':['反应','表情','人物反应','停顿','笑点','情绪'],
 'brand_attribution':['品牌归因','落版','品牌揭示','品牌承接','归因'],
 'single_claim':['单一卖点','单一能力','唯一主张','单一利益'],
 'audio_dependency':['音轨','声音','旁白','音效','音乐'],
 'truth_constraints':['真实','限定','证据','不能编造','功效边界','资格']}

def aggregate(output):
 rows=[]
 with sqlite3.connect(f'file:{store.ROOT / "library.sqlite3"}?mode=ro',uri=True,timeout=2) as source:
  current=dict(source.execute('SELECT item,sha256 FROM assets'))
 with learning.connection() as c:
  raw=c.execute('SELECT item,media_sha256,version,source_revision,model,data FROM analyses ORDER BY item,media_sha256,version DESC').fetchall()
  seen=set()
  for row in raw:
   if current.get(row[0]) != row[1]: continue
   key=(row[0],row[1])
   if key in seen: continue
   seen.add(key)
   data=json.loads(row[5]);rows.append((row,data))
 if not rows:raise ValueError('No analyses found')
 roles=Counter(d.get('media_role','unknown') for _,d in rows)
 confidence=Counter(d.get('confidence','unknown') for _,d in rows)
 scope=Counter(d.get('evidence_scope','unknown') for _,d in rows)
 beats=[];questions=[];rules=[];avoids=[];durations=[];taxonomy=Counter();guidance_taxonomy=Counter();coverage=[]
 for _,d in rows:
  bs=d.get('beats',[]);beats.append(len(bs));questions.append(len(d.get('grill_questions',[])));rules.append(len(d.get('transfer_rules',[])));avoids.append(len(d.get('avoid',[])))
  if bs:
   durations.append(sum(max(0,float(b['end'])-float(b['start'])) for b in bs));coverage.append(len({i for b in bs for i in b.get('frames',[])}))
  text=' '.join(str(d.get(k,'')) for k in ('principle','mechanism'))
  guidance=' '.join(str(d.get(k,'')) for k in ('grill_questions','transfer_rules','avoid'))
  for label,terms in TAXONOMY.items():
   # Static sampled frames cannot establish an audio dependency. Keep that
   # dimension at zero until an independent listening review is recorded.
   if label == 'audio_dependency':
    if d.get('audio_semantics_reviewed') is True and any(term in text for term in terms): taxonomy[label] += 1
   elif any(term in text for term in terms):taxonomy[label]+=1
   if any(term in guidance for term in terms):guidance_taxonomy[label]+=1
 digest={'schema':'visualagent.ad-analysis-aggregate.v1','analysis_count':len(rows),
  'distinct_items':len({r[0][0] for r in rows}),'distinct_media':len({r[0][1] for r in rows}),
  'latest_only':True,'roles':dict(roles),'confidence':dict(confidence),'evidence_scope':dict(scope),
  'structure':{'beats':{'min':min(beats),'median':statistics.median(beats),'max':max(beats)},
   'grill_questions':{'min':min(questions),'median':statistics.median(questions),'max':max(questions)},
   'transfer_rules':{'min':min(rules),'median':statistics.median(rules),'max':max(rules)},
   'avoid_conditions':{'min':min(avoids),'median':statistics.median(avoids),'max':max(avoids)},
   'covered_seconds':{'min':min(durations),'median':statistics.median(durations),'max':max(durations)},
   'unique_evidence_frames':{'min':min(coverage),'median':statistics.median(coverage),'max':max(coverage)}},
  'mechanism_taxonomy_counts':dict(taxonomy),'guidance_taxonomy_counts':dict(guidance_taxonomy),'taxonomy_method':'substring heuristic; mechanism counts use only validated principle/mechanism, guidance counts use questions/rules/avoid; neither is a semantic label or quality score',
  'learning_use':{'use_for_director':True,'use_for_training':False,'reason':'candidates are sampled-frame evidence with pending human/audio/motion/rights review'},
  'privacy':{'raw_provider_payloads':False,'media_paths':False,'user_content':False}}
 path=Path(output)
 if path.exists() or path.is_symlink():raise FileExistsError('Refusing to overwrite aggregate')
 path.parent.mkdir(parents=True,exist_ok=True,mode=0o700)
 fd=os.open(path,os.O_CREAT|os.O_EXCL|os.O_WRONLY,0o600)
 with os.fdopen(fd,'w',encoding='utf-8') as f:json.dump(digest,f,ensure_ascii=False,indent=2);f.write('\n')
 return digest

if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('--output',type=Path,required=True);a=p.parse_args();print(json.dumps(aggregate(a.output),ensure_ascii=False))
