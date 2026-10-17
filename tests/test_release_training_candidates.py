import json,subprocess,sys
from pathlib import Path
from harness.learning.candidate_review import make_receipt,queue_digest

def test_release_command_requires_confirmation_and_is_non_overwriting(tmp_path):
    queue={'schema':'visualagent.training-candidate-queue.v1','source_manifest_sha256':'a'*64,
           'records':[{'sample_id':'b'*64,'record_sha256':'c'*64,'training_eligible':False,'limitations':['review'],
                       'provenance':{'plan':'actual_agent_plan_snapshot','strategy_context':'external_reference_strategy_observation','trajectory':'actual_agent_observed_events','policy':'reference observations and user episodes must never be mixed as supervision'}} ]}
    receipt=make_receipt(queue,'b'*64,'reviewer',{g:True for g in ('privacy_review','rights_review','sanitized_context_review')},'已逐项核对转换后的候选内容与授权边界。')
    q=tmp_path/'queue.json';r=tmp_path/'reviews.json';out=tmp_path/'release.json'
    q.write_text(json.dumps(queue),encoding='utf-8');r.write_text(json.dumps({'queue_sha256':queue_digest(queue),'receipts':[receipt]}),encoding='utf-8')
    command=[sys.executable,'tools/release_training_candidates.py','--queue',str(q),'--reviews',str(r),'--output',str(out)]
    rejected=subprocess.run(command,capture_output=True,text=True);assert rejected.returncode!=0 and not out.exists()
    accepted=subprocess.run(command+['--confirm-release'],capture_output=True,text=True);assert accepted.returncode==0
    payload=json.loads(out.read_text());assert payload['training_eligible'] and payload['records'][0]['public_release'];assert 'limitations' not in payload['records'][0]
    again=subprocess.run(command+['--confirm-release'],capture_output=True,text=True);assert again.returncode!=0
