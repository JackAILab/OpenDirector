import json

from harness.library import learning, store


def test_review_queue_is_current_media_bound_and_fail_closed(tmp_path, monkeypatch):
    monkeypatch.setattr(store, 'ROOT', tmp_path)
    first, _ = store.ingest({'title': 'one', 'source_url': 'https://example.invalid/one'})
    second, _ = store.ingest({'title': 'two', 'source_url': 'https://example.invalid/two'})
    with store.connection() as c:
        c.execute('INSERT INTO assets VALUES(?,?,?,?,?,?,?,?,?)', (first, 'assets/one.mp4', 'a'*64, 15, 15, 1, 100, 100, 0))
        c.execute('INSERT INTO assets VALUES(?,?,?,?,?,?,?,?,?)', (second, 'assets/two.mp4', 'b'*64, 20, 20, 0, 100, 100, 0))
    raw={
        'media_role':'original_ad','confidence':'high','principle':'把动作变成结果',
        'mechanism':'可见结果','beats':[{'start':0,'end':5,'observation':'a','purpose':'建立注意','frames':[0]}],
        'grill_questions':['事实？'],'transfer_rules':['重新设计'],'avoid':['不复制'],
    }
    clean=learning.validate(raw,15,[1])
    learning.save_analysis(first, 'a'*64, 1, 'model', clean, [1])
    queue=learning.analysis_review_queue()
    assert queue['state']=='ready'
    assert queue['total_pending']==2
    by_item={item['item']:item for item in queue['items']}
    assert by_item[first]['missing']==['audio_semantics','full_motion']
    assert by_item[second]['missing']==['analysis']
    assert all(item['training_eligible'] is False for item in queue['items'])
    # Replacing the analyzed asset makes the old analysis ineligible for this queue.
    with store.connection() as c:
        c.execute('UPDATE assets SET sha256=? WHERE item=?', ('c'*64, first))
    changed=learning.analysis_review_queue()
    assert next(item for item in changed['items'] if item['item']==first)['missing']==['analysis']


def test_review_queue_never_exposes_analysis_text(tmp_path, monkeypatch):
    monkeypatch.setattr(store, 'ROOT', tmp_path)
    item, _ = store.ingest({'title': 'one', 'source_url': 'https://example.invalid/one'})
    with store.connection() as c:
        c.execute('INSERT INTO assets VALUES(?,?,?,?,?,?,?,?,?)', (item, 'assets/one.mp4', 'a'*64, 15, 15, 1, 100, 100, 0))
    raw={'media_role':'original_ad','confidence':'high','principle':'秘密说明','mechanism':'动作',
         'beats':[{'start':0,'end':5,'observation':'private@example.com','purpose':'建立注意','frames':[0]}],
         'grill_questions':['事实？'],'transfer_rules':['重新设计'],'avoid':['不复制']}
    learning.save_analysis(item,'a'*64,1,'model',learning.validate(raw,15,[1]),[1])
    text=json.dumps(learning.analysis_review_queue(),ensure_ascii=False)
    assert 'private@example.com' not in text and '秘密说明' not in text
