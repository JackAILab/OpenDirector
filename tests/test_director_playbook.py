import asyncio,json
from harness.agents import creative_director


def test_playbook_is_versioned_and_sent_as_generic_guidance(monkeypatch):
 monkeypatch.setenv('AD_STRATEGY_INDEX','/nonexistent/test-index.json')
 calls=[]
 class Model:
  async def complete(self,messages):
   calls.append(messages);return {'reply':'ok','brief':{'product':'p','audience':'a','message':'m','style':'s','cta':'c'},'assumptions':[],'decisions':[],'questions':[{'id':'x','question':'q','why':'w','options':[]}],'shots':[]}
 monkeypatch.setattr(creative_director,'CreativeDirectorModel',Model)
 async def run():
  return await creative_director.direct({'duration':15,'provider':'kling','aspect':'16:9','messages':[{'role':'user','content':'商品'}],'brief':{},'canvas':{'nodes':[],'edges':[]}},'interview')
 asyncio.run(run());payload=json.loads(calls[0][1]['content']);assert payload['evidence_backed_playbook']['version']=='ad-director-playbook-v1';assert payload['evidence_backed_playbook']['evidence_summary']['analysis_count']==349;assert payload['evidence_backed_playbook']['evidence_summary']['mechanism_coverage']['observable_task']==323;assert 'usage_policy' in payload['evidence_backed_playbook'];assert '商品' in json.dumps(payload,ensure_ascii=False)
 assert 'raw_provider' not in json.dumps(payload)
 assert payload['mechanism_report']['schema']=='visualagent.ad-mechanism-report.v1'
 assert payload['mechanism_report']['training_eligible'] is False
 assert len(payload['evidence_backed_playbook']['mechanism_vocabulary'])==8
 contract=payload['strategy_context_contract']
 assert contract['schema']=='visualagent.strategy-context-contract.v1'
 assert contract['provenance']=='external_reference_strategy_observation'
 assert any('复制品牌、人物、文案、原音轨' in item for item in contract['forbidden_use'])


def test_playbook_uses_safe_fresh_snapshot(tmp_path,monkeypatch):
 import time
 from harness.library.playbook import compact
 path=tmp_path/'index.json';monkeypatch.setenv('AD_STRATEGY_INDEX',str(path))
 path.write_text(json.dumps({'schema':'visualagent.strategy-index.v1','generated_at':time.time(),
  'analysis_summary':{'analysis_count':2,'audio_semantics_reviewed':0,'full_motion_reviewed':0,
   'media_roles':{'original_ad':2,'private-user':1},'confidence':{'high':2},
   'mechanism_coverage':{'pressure_test':1},'raw_provider':'secret'}}))
 result=compact()['evidence_summary']
 assert result['analysis_count']==2 and result['snapshot_status']=='fresh'
 assert 'private-user' not in str(result) and 'secret' not in str(result)
