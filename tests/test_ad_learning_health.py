import json,subprocess,sys
from pathlib import Path

def test_learning_health_reports_fresh_index_and_next_gate(tmp_path):
    index=tmp_path/'index.json';index.write_text(json.dumps({'schema':'visualagent.strategy-index.v1','generated_at':__import__('time').time(),'records':[{}]}))
    manifest=tmp_path/'manifest.json';manifest.write_text(json.dumps({'summary':{'projects':2,'versions':3,'training_eligible':0,'release_ready':False}}))
    result=subprocess.run([sys.executable,'tools/check_ad_learning.py','--index',str(index),'--manifest',str(manifest)],capture_output=True,text=True,check=True)
    report=json.loads(result.stdout);assert report['index']['state']=='fresh';assert report['next_action']=='complete_missing_release_gates'
    assert report['preference_queue']['state']=='not_configured'


def test_learning_health_reports_preference_queue(tmp_path):
    index=tmp_path/'index.json';index.write_text(json.dumps({'schema':'visualagent.strategy-index.v1','generated_at':__import__('time').time(),'records':[]}))
    manifest=tmp_path/'manifest.json';manifest.write_text(json.dumps({'summary':{}}))
    preferences=tmp_path/'preferences.json';preferences.write_text(json.dumps({'record_count':2,'training_eligible':False}))
    result=subprocess.run([sys.executable,'tools/check_ad_learning.py','--index',str(index),'--manifest',str(manifest),'--preferences',str(preferences)],capture_output=True,text=True,check=True)
    assert json.loads(result.stdout)['preference_queue']['records']==2


def test_learning_health_marks_manifest_stale_when_inputs_change(tmp_path, monkeypatch, capsys):
    index=tmp_path/'index.json';index.write_text(json.dumps({'schema':'visualagent.strategy-index.v1','generated_at':__import__('time').time(),'records':[]}))
    manifest=tmp_path/'manifest.json';manifest.write_text(json.dumps({'summary':{},'input_fingerprints':{'projects':'old'}}))
    import tools.check_ad_learning as health
    monkeypatch.setattr('harness.learning.inventory.input_fingerprints', lambda: {'projects':'new'})
    monkeypatch.setattr(sys,'argv',['check_ad_learning.py','--index',str(index),'--manifest',str(manifest)])
    try: health.main()
    except SystemExit as exit_status: assert exit_status.code==2
    report=json.loads(capsys.readouterr().out);assert report['preparation']['state']=='stale';assert report['preparation']['changed_inputs']==['projects'];assert report['next_action']=='refresh_preparation_manifest'


def test_learning_health_reports_pending_reference_analysis_queue(tmp_path):
    import time
    index=tmp_path/'index.json';index.write_text(json.dumps({'schema':'visualagent.strategy-index.v1','generated_at':time.time(),'records':[]}))
    manifest=tmp_path/'manifest.json';manifest.write_text(json.dumps({'summary':{}}))
    queue=tmp_path/'queue.json';queue.write_text(json.dumps({'state':'ready','total_pending':2768,'count':200,'training_eligible':False}))
    result=subprocess.run([sys.executable,'tools/check_ad_learning.py','--index',str(index),'--manifest',str(manifest),'--review-queue',str(queue)],capture_output=True,text=True,check=True)
    report=json.loads(result.stdout)
    assert report['analysis_review_queue']=={'state':'ready','pending':2768,'listed':200,'training_eligible':False}
    assert report['next_action']=='complete_reference_analysis_review'


def test_bounded_fingerprint_reader_fails_closed_on_slow_storage():
    import time
    from tools.check_ad_learning import bounded_input_fingerprints, FingerprintTimeout
    started=time.monotonic()
    try:
        bounded_input_fingerprints(lambda: time.sleep(2), seconds=1)
    except FingerprintTimeout:
        pass
    else:
        raise AssertionError('slow fingerprint reader must time out')
    assert time.monotonic()-started < 1.8
