import json,subprocess,sys

def test_review_cli_writes_immutable_receipt(tmp_path):
    queue={'schema':'visualagent.training-candidate-queue.v1','source_manifest_sha256':'a'*64,'records':[{'sample_id':'b'*64,'record_sha256':'c'*64,'creator_token':'creator'}]}
    q=tmp_path/'queue.json';out=tmp_path/'review.json';q.write_text(json.dumps(queue))
    command=[sys.executable,'tools/review_training_candidate.py','--queue',str(q),'--candidate','b'*64,'--reviewer-id','admin','--reviewer-token','other','--note','已经核对脱敏后的确切候选内容。','--privacy','--rights','--sanitized-context','--output',str(out)]
    result=subprocess.run(command,capture_output=True,text=True,check=True);assert 'receipt_sha256' in result.stdout
    receipt=json.loads(out.read_text());assert receipt['independent'] and all(receipt['decisions'].values())
    again=subprocess.run(command,capture_output=True,text=True);assert again.returncode!=0
