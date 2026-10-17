import sqlite3


def test_library_fingerprint_ignores_sqlite_header_changes(tmp_path, monkeypatch):
    from harness.learning import inventory
    from harness.library import store as library_store
    data=tmp_path/'data';(data/'learning').mkdir(parents=True)
    (data/'projects.sqlite3').write_bytes(b'projects')
    (data/'learning'/'episodes.sqlite3').write_bytes(b'episodes')
    db=data/'library.sqlite3'
    with sqlite3.connect(db) as c:
        c.executescript('CREATE TABLE items(id TEXT,source_url TEXT,title TEXT,brand TEXT,industry TEXT,ad_type TEXT,data TEXT,revision INTEGER,created REAL,updated REAL); CREATE TABLE assets(item TEXT,path TEXT,sha256 TEXT,bytes INTEGER,duration REAL,audio INTEGER,width INTEGER,height INTEGER,created REAL); INSERT INTO items VALUES("i","https://example.test","T","","","","{}",1,1,1);')
    analyses=data/'learning'/'analyses.sqlite3'
    with sqlite3.connect(analyses) as c:c.execute('CREATE TABLE analyses(item TEXT,media_sha256 TEXT,version INTEGER,source_revision INTEGER,model TEXT,data TEXT)')
    monkeypatch.setattr(inventory.store,'DATA',data);monkeypatch.setattr(library_store,'ROOT',data)
    first=inventory.input_fingerprints()
    with sqlite3.connect(db) as c:c.execute('PRAGMA user_version=7')
    second=inventory.input_fingerprints()
    assert first==second


def test_feedback_changes_episode_fingerprint(tmp_path,monkeypatch):
    from harness.learning import inventory,feedback
    monkeypatch.setattr(inventory.store,'DATA',tmp_path)
    connection=feedback.connection();connection.commit();connection.close()
    first=inventory.input_fingerprints()['episodes']
    feedback.record({'id':'p','revision':1},1,'keep',4,[],[])
    assert inventory.input_fingerprints()['episodes']!=first
