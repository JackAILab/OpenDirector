"""Versioned, generic director checks distilled from validated ad analyses."""
PLAYBOOK_VERSION='ad-director-playbook-v1'
PLAYBOOK={
 'version':PLAYBOOK_VERSION,
 'source_scope':'validated sampled-frame strategy candidates; not original author reasoning or training labels',
 'mechanism_vocabulary':[
  {'id':'pressure_test','label':'压力测试','use':'把单一卖点放入一个会暴露限制的环境或障碍中。'},
  {'id':'observable_task','label':'可观察任务','use':'让产品完成一个观众能看见结果的动作，而不是只说功能。'},
  {'id':'misdirection_reveal','label':'误导后揭示','use':'先建立品类或因果预期，再用揭示重新解释前面的画面。'},
  {'id':'contrast_reversal','label':'对照反转','use':'只保留一条易懂的前后或意义反转，制造记忆点。'},
  {'id':'human_reaction','label':'人物反应','use':'用人物、群体或关系反应承接产品结果与情绪。'},
  {'id':'accumulation','label':'连续累积','use':'用重复实例逐步放大容量、规模或情感价值。'},
  {'id':'product_as_action','label':'产品成为动作','use':'让商品或功能推动关键情节，而不是充当道具。'},
  {'id':'brand_reveal','label':'品牌归因','use':'在观众理解结果后完成产品、品牌和行动的明确归因。'},
 ],
 'evidence_summary':{
  'analysis_count':349,'distinct_items':349,'distinct_media':348,
  'confidence':{'high':298,'medium':50,'low':1},
  'mechanism_coverage':{'observable_task':323,'product_as_action':197,'brand_reveal':181,'accumulation':182,'pressure_test':127,'human_reaction':231,'misdirection_reveal':126,'contrast_reversal':134},
  'method':'substring heuristic over validated principle/mechanism fields; counts are coverage signals, not quality scores',
  'limits':['sampled frames and source metadata only','audio and full motion remain unverified','award or reference status is not a user preference label']
 },
 'principles':[
  {'id':'single_claim','check':'先确认一个可证实的单一主张，列出支持它的真实商品事实和限制。','prompt_effect':'让每个节拍都服务同一主张，缺少事实时先追问。'},
  {'id':'observable_proof','check':'把主张转成观众能看见的任务、压力或对照，并安排结果变化。','prompt_effect':'画面必须写清动作、结果和因果，不能只写氛围。'},
  {'id':'controlled_contrast','check':'只保留一条冲突或反转，让观众能在15秒内理解。','prompt_effect':'删除无关支线和第二个卖点。'},
  {'id':'reaction_and_attribution','check':'给结果一个人物/环境反应，再完成商品与品牌归因。','prompt_effect':'结尾同时写结果、商品和可证实行动号召。'},
  {'id':'native_sound','check':'为每个时间窗设计原创音乐、环境声、动作音和必要旁白。','prompt_effect':'不能从静帧推断原片声音，也不能用声音补造未经证实的功效。'},
  {'id':'truth_boundary','check':'标出地域、设备、条件、资质和功效边界。','prompt_effect':'把限制写进假设与追问，不编造承诺。'},
 ],
 'timing_grammar':[
  {'id':'opening_task','window':'0–3s','job':'给出一个可读的目标、异常或阻力；让观众知道要关注什么。'},
  {'id':'proof_action','window':'3–8s','job':'让商品通过一个具体动作改变状态或结果；画面写清因果，不只写氛围。'},
  {'id':'reframe_reaction','window':'8–12s','job':'必要时只保留一条反转或重释，再用人物/环境反应把结果变成情绪。'},
  {'id':'attribution_close','window':'12–15s','job':'在结果已被理解后完成商品/品牌归因和单一事实安全的行动号召。'},
  {'id':'native_audio','window':'全片','job':'每个时段同时给原创音乐变化、环境声、动作音和短旁白；一次提交整片，不拼接独立镜头。'},
 ],
 'usage_policy':['借鉴机制，不复制品牌、人物、文案、商品、具体镜头序列或原音轨。','当前商品事实优先于案例策略；案例只能帮助提出问题和选择结构。','采样帧只证明采样帧中可见的内容；未审阅音频/完整运动时保持不确定。']
}

def compact():
 return {'version':PLAYBOOK['version'],'source_scope':PLAYBOOK['source_scope'],'evidence_summary':_snapshot_summary(),'mechanism_vocabulary':PLAYBOOK['mechanism_vocabulary'],'principles':PLAYBOOK['principles'],'timing_grammar':PLAYBOOK['timing_grammar'],'usage_policy':PLAYBOOK['usage_policy']}

def _snapshot_summary():
 """Read bounded aggregate metrics, never raw index text or a live database."""
 import json,os,time
 from pathlib import Path
 from harness.library.mechanisms import MECHANISMS
 fallback=dict(PLAYBOOK['evidence_summary'],snapshot_status='historical_baseline')
 from harness.library.index_paths import strategy_index_path
 path=strategy_index_path()
 try:
  if not path.is_file() or path.stat().st_size>2_000_000:return fallback
  index=json.loads(path.read_text(encoding='utf-8'))
  generated=index.get('generated_at')
  if index.get('schema')!='visualagent.strategy-index.v1' or type(generated) not in (int,float) or not 0<=time.time()-generated<=7*86400:return fallback
  summary=index.get('analysis_summary')
  if not isinstance(summary,dict):return fallback
  output={'snapshot_status':'fresh','method':'bounded heuristic coverage; not quality or conversion labels'}
  for key in ('analysis_count','audio_semantics_reviewed','full_motion_reviewed'):
   value=summary.get(key)
   if type(value) is not int or value<0:return fallback
   output[key]=value
  for key,allowed in (('media_roles',('original_ad','case_film','music_video','mixed','unknown')),('confidence',('low','medium','high')),('mechanism_coverage',MECHANISMS)):
   counts=summary.get(key,{})
   if not isinstance(counts,dict):return fallback
   output[key]={name:value for name,value in counts.items() if name in allowed and type(value) is int and 0<=value<=output['analysis_count']}
  return output
 except (OSError,ValueError,TypeError,AttributeError):return fallback
