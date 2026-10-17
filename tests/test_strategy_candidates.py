import json,sqlite3,time
from harness.library import learning

def test_strategy_candidates_are_current_media_bound_and_diverse(tmp_path,monkeypatch):
    root=tmp_path/'library';root.mkdir()
    index=root/'index.json';index.write_text(json.dumps({'schema':'visualagent.strategy-index.v1','generated_at':time.time(),'records':[{'source_item':'a','confidence':'high','principle':'证明'},{'source_item':'b','confidence':'high','principle':'反转'}]}),encoding='utf-8')
    monkeypatch.setenv('AD_STRATEGY_INDEX',str(index))
    result=learning.strategy_candidates(3)
    assert [r['source_item'] for r in result]==['a','b']
    assert all('raw_provider' not in json.dumps(r) for r in result)


def test_expired_strategy_index_fails_open(tmp_path,monkeypatch):
    index=tmp_path/'expired.json';index.write_text(json.dumps({'schema':'visualagent.strategy-index.v1','generated_at':time.time()-8*86400,'records':[{'source_item':'a'}]}),encoding='utf-8');monkeypatch.setenv('AD_STRATEGY_INDEX',str(index))
    assert learning.strategy_candidates(3)==[]


def test_strategy_candidates_use_brief_relevance_but_keep_default_order(tmp_path,monkeypatch):
    index=tmp_path/'index.json';index.write_text(json.dumps({'schema':'visualagent.strategy-index.v1','generated_at':time.time(),'records':[
        {'source_item':'a','confidence':'high','principle':'用反转证明价值','mechanism':'人物误判后纠正'},
        {'source_item':'b','confidence':'high','principle':'把续航变成可见结果','mechanism':'电量决定任务能否完成'}]}),encoding='utf-8')
    monkeypatch.setenv('AD_STRATEGY_INDEX',str(index))
    assert [r['source_item'] for r in learning.strategy_candidates(3)]==['a','b']
    selected=learning.strategy_candidates(1,query='续航 电量')[0]
    assert selected['source_item']=='b' and selected['relevance_score']>0
    assert '关键词匹配' in selected['selection_reason']


def test_strategy_candidate_limit_allows_wider_offline_index(tmp_path,monkeypatch):
    index=tmp_path/'index.json';index.write_text(json.dumps({'schema':'visualagent.strategy-index.v1','generated_at':time.time(),
        'records':[{'source_item':str(i),'principle':str(i)} for i in range(10)]}),encoding='utf-8')
    monkeypatch.setenv('AD_STRATEGY_INDEX',str(index))
    assert len(learning.strategy_candidates(10))==10


def test_strategy_candidates_pick_newest_private_snapshot_without_explicit_path(tmp_path,monkeypatch):
    import harness.library.index_paths as paths
    old=tmp_path/'strategy-candidates.json';new=tmp_path/'strategy-candidates-v2.json'
    payload=lambda item:{'schema':'visualagent.strategy-index.v1','generated_at':time.time(),'records':[{'source_item':item,'principle':'机制'}]}
    old.write_text(json.dumps(payload('old')));new.write_text(json.dumps(payload('new')))
    old.touch();time.sleep(0.01);new.touch()
    monkeypatch.delenv('AD_STRATEGY_INDEX',raising=False);monkeypatch.setattr(paths,'DEFAULT_DIR',tmp_path)
    assert learning.strategy_candidates(1)[0]['source_item']=='new'


def test_sampled_evidence_survives_index_retrieval_and_sanitization(tmp_path,monkeypatch):
    from harness.library.mechanisms import annotate
    from harness.learning.training_records import sanitize_plan
    record=annotate({'source_item':'example','principle':'展示真实结果','beats':[
        {'start':1,'end':4,'purpose':'建立注意','observation':'商品进入场景'},
        {'start':5,'end':8,'purpose':'证明结果','observation':'用户看到变化'},
    ]})
    index=tmp_path/'index.json'
    index.write_text(json.dumps({'schema':'visualagent.strategy-index.v1',
        'generated_at':time.time(),'records':[record]}))
    monkeypatch.setenv('AD_STRATEGY_INDEX',str(index))
    selected=learning.strategy_candidates(1)
    assert len(selected[0]['shooting_grammar']['windows'])==2
    clean=sanitize_plan({'strategy_candidates':selected})
    assert clean['strategy_candidates'][0]['shooting_grammar']['windows'][1]['role']=='proof_or_reframe'
    assert 'source_item' not in json.dumps(clean)

def test_strategy_candidates_expose_media_role_without_promoting_it_to_quality(monkeypatch, tmp_path):
    import json
    from harness.library import learning
    path=tmp_path/'strategy.json'
    path.write_text(json.dumps({'schema':'visualagent.strategy-index.v1','generated_at':__import__('time').time(),'records':[{'source_item':'a','media_role':'music_video','principle':'节奏','mechanism':'动作','confidence':'high'}]}))
    monkeypatch.setenv('AD_STRATEGY_INDEX',str(path))
    result=learning.strategy_candidates(1)
    assert result[0]['media_role']=='music_video'
    assert result[0].get('training_eligible') is not True
    assert result[0]['confidence']=='high'


def test_transfer_guidance_matches_new_benefit_but_avoid_does_not(tmp_path, monkeypatch):
    index=tmp_path/'index.json'
    index.write_text(json.dumps({'schema':'visualagent.strategy-index.v1','generated_at':time.time(),'records':[
        {'source_item':'negative','principle':'颜色反差','avoid':['不适合续航演示']},
        {'source_item':'transfer','principle':'压力决定结果','transfer_rules':['让续航决定最后一步能否完成']},
    ]}))
    monkeypatch.setenv('AD_STRATEGY_INDEX',str(index))
    selected=learning.strategy_candidates(2,query='续航')
    assert selected[0]['source_item']=='transfer'
    assert selected[0]['relevance_score']>0
    assert selected[1]['relevance_score']==0
    assert '不代表原片证明' in selected[0]['selection_reason']


def test_query_terms_are_not_joined_into_spurious_chinese_bigrams():
    assert learning._relevance({'principle':'甲乙'},'灯甲 乙灯')==0
    assert learning._relevance({'principle':'续航'},'续航 续航')==learning._relevance({'principle':'续航'},'续航')


def test_original_ads_are_preferred_when_relevance_ties(tmp_path, monkeypatch):
    index=tmp_path/'index.json'
    index.write_text(json.dumps({'schema':'visualagent.strategy-index.v1','generated_at':time.time(),'records':[
        {'source_item':'music','media_role':'music_video','principle':'节奏'},
        {'source_item':'ad','media_role':'original_ad','principle':'节奏'},
    ]}))
    monkeypatch.setenv('AD_STRATEGY_INDEX',str(index))
    assert learning.strategy_candidates(2)[0]['source_item']=='ad'


def test_offline_scan_does_not_use_item_id_prefix(tmp_path, monkeypatch):
    """A later, uniquely tagged mechanism must be eligible for the bounded index."""
    import sqlite3
    from harness.library import store
    root=tmp_path/'data';(root/'learning').mkdir(parents=True)
    library=root/'library.sqlite3';analysis=root/'learning'/'analyses.sqlite3'
    with sqlite3.connect(library) as db:
        db.execute('CREATE TABLE assets(item TEXT,sha256 TEXT)')
        db.executemany('INSERT INTO assets VALUES(?,?)',[('early','sha-early'),('late','sha-late')])
    with sqlite3.connect(analysis) as db:
        db.execute('CREATE TABLE analyses(item TEXT,media_sha256 TEXT,version INTEGER,data TEXT)')
        common={'confidence':'high','grill_questions':['q'],'transfer_rules':['r'],'avoid':['a'],'beats':[{'start':0,'end':1,'observation':'o','purpose':'p','frames':[0]}]}
        db.execute('INSERT INTO analyses VALUES(?,?,?,?)',('early','sha-early',1,json.dumps({**common,'media_role':'original_ad','principle':'证明结果','mechanism':'动作证明'})))
        db.execute('INSERT INTO analyses VALUES(?,?,?,?)',('late','sha-late',1,json.dumps({**common,'media_role':'original_ad','principle':'误读后反转','mechanism':'反转揭示'})))
    monkeypatch.setattr(store,'ROOT',root)
    result=learning._scan_strategy_candidates(2)
    assert {r['source_item'] for r in result}=={'early','late'}
