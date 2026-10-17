from harness.library.learning import summarize_analysis_rows


def test_analysis_summary_is_aggregate_only():
    result=summarize_analysis_rows([{
        'media_role':'original_ad','confidence':'high','evidence_scope':'sampled',
        'principle':'极端环境制造反转，品牌落版','mechanism':'人物完成任务',
        'transfer_rules':['保留一个结果'],'avoid':['不要复制品牌'],
        'audio_semantics_reviewed':False,'full_motion_reviewed':False,
        'source_item':'secret-id','media_sha256':'secret-sha'}])
    assert result['analysis_count']==1
    assert result['media_roles']=={'original_ad':1}
    assert result['audio_semantics_reviewed']==0
    assert 'source_item' not in str(result) and 'secret-sha' not in str(result)


def test_summary_counts_latest_current_media_only(tmp_path,monkeypatch):
    import json,sqlite3
    from harness.library import learning,store
    monkeypatch.setattr(store,'ROOT',tmp_path)
    with sqlite3.connect(tmp_path/'library.sqlite3') as db:
        db.execute('CREATE TABLE assets(item TEXT,sha256 TEXT)')
        db.executemany('INSERT INTO assets VALUES(?,?)',[('a','current'),('b','new')])
    with learning.connection() as db:
        for item,sha,version,role in [('a','current',1,'case_film'),('a','current',2,'original_ad'),('b','old',1,'case_film')]:
            db.execute('INSERT INTO analyses VALUES(?,?,?,?,?,?,?)',
                       (item,sha,version,1,'test',json.dumps({'media_role':role}),0))
    result=learning.analysis_summary()
    assert result['analysis_count']==1
    assert result['media_roles']=={'original_ad':1}
