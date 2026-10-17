import hashlib
import json
import sqlite3
import pytest
from tools.prepare_relation_source_review import build


def fixture(tmp_path):
    root=tmp_path/'library';root.mkdir()
    media=root/'a.mp4';media.write_bytes(b'fixture-media')
    sha=hashlib.sha256(media.read_bytes()).hexdigest()
    with sqlite3.connect(root/'library.sqlite3') as c:
        c.execute('create table assets(item text,path text,sha256 text)')
        c.execute('insert into assets values (?,?,?)',('private-item','a.mp4',sha))
    selection=tmp_path/'selection.json'
    selection.write_text(json.dumps({'selected':[{'review_id':'R1','item':'private-item','sha256':sha,'duration':2,'has_audio_stream':True}]}))
    config=tmp_path/'candidates.json'
    config.write_text(json.dumps({'schema':'visualagent.relation-candidates.v1','pairs':[{'candidate_reference':'R1','contrast_reference':'R1','hypothesis':'HIDDEN_SUGGESTION'}]}))
    return root,selection,config,tmp_path/'out'


def test_verified_media_packet_excludes_candidate_hints(tmp_path,monkeypatch):
    monkeypatch.setattr('tools.prepare_relation_source_review.media_duration',lambda p, binary:2.8)
    args=fixture(tmp_path);report=build(*args)
    assert report['clip_count']==1 and report['media_bytes_verified']
    assert report['independent_reviews_completed']==0
    html=(args[-1]/'review.html').read_text()
    assert 'HIDDEN_SUGGESTION' not in html and 'private-item' not in html
    assert 'R1' not in html
    packet=json.loads((args[-1]/'packet.json').read_text())
    assert not packet['training_eligible']
    assert packet['clips'][0]['duration']==2.8 and packet['clips'][0]['stored_duration']==2
    assert (args[-1]/'S01.mp4').read_bytes()==b'fixture-media'
    with pytest.raises(FileExistsError):build(*args)


def test_changed_media_rejected_before_packet_creation(tmp_path):
    args=fixture(tmp_path);(args[0]/'a.mp4').write_bytes(b'changed')
    with pytest.raises(ValueError,match='media_bytes_mismatch'):build(*args)
    assert not args[-1].exists()


def test_outside_media_path_rejected(tmp_path):
    args=fixture(tmp_path)
    with sqlite3.connect(args[0]/'library.sqlite3') as c:c.execute("update assets set path='../outside.mp4'")
    with pytest.raises(ValueError,match='asset_outside_root'):build(*args)
    assert not args[-1].exists()
