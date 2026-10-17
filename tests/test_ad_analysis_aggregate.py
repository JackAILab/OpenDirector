import json,pytest
from harness.library import learning,store
from tools.summarize_ad_analyses import aggregate

def test_aggregate_is_safe_and_structural(tmp_path,monkeypatch):
 monkeypatch.setattr(store,'ROOT',tmp_path)
 identity,_=store.ingest({'title':'x','source_url':'https://example.invalid/private'})
 with store.connection() as c:c.execute('INSERT INTO assets VALUES(?,?,?,?,?,?,?,?,?)',(identity,'assets/x.mp4','a'*64,15,15,1,100,100,0))
 raw={'media_role':'original_ad','confidence':'high','principle':'用反转把功能证明变成可见结果','mechanism':'先制造寻找任务，再用动作验证和品牌归因收束','beats':[{'start':0,'end':5,'observation':'a','purpose':'建立悬念','frames':[0]},{'start':5,'end':15,'observation':'b','purpose':'结果变化','frames':[1]}],'grill_questions':['真实证据？'],'transfer_rules':['保持单一卖点'],'avoid':['不能编造功效']}
 clean=learning.validate(raw,15,[1,10]);learning.save_analysis(identity,'a'*64,1,'model',clean,[1,10]);out=tmp_path/'aggregate.json';r=aggregate(out)
 assert r['analysis_count']==1 and r['mechanism_taxonomy_counts']['visible_proof']==1 and r['guidance_taxonomy_counts']['truth_constraints']==1 and r['learning_use']['use_for_training'] is False
 assert 'private' not in out.read_text() and 'https://' not in out.read_text()
 with pytest.raises(FileExistsError):aggregate(out)
 # Historical analyses and replaced media must not inflate current coverage.
 learning.save_analysis(identity,'a'*64,1,'model',clean,[1,10])
 assert aggregate(tmp_path/'latest.json')['analysis_count']==1
 with store.connection() as c:c.execute('UPDATE assets SET sha256=? WHERE item=?',('b'*64,identity))
 with pytest.raises(ValueError,match='No analyses found'):aggregate(tmp_path/'replaced.json')
 learning.save_analysis(identity,'b'*64,1,'model',clean,[1,10])
 assert aggregate(tmp_path/'current.json')['analysis_count']==1
