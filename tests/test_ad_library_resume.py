import hashlib
import json
import subprocess
import time
from pathlib import Path

import httpx
import pytest

from harness.models.reference_download import download_mp4, checkpoint_info
from harness.tools.reference_media_cache import PartialCache
from harness.library import store
from tools import cache_ad_reference_media as media

URL = 'https://media.dandad.org/film.mp4'
ETAG = '"version-one"'


def seed(directory, prefix=b'abcd', complete=b'abcdefgh'):
    directory.mkdir(parents=True, exist_ok=True)
    (directory/'source.mp4').write_bytes(prefix)
    (directory/'checkpoint.json').write_text(json.dumps({
        'source_hash': hashlib.sha256(URL.encode()).hexdigest(), 'etag': ETAG,
        'size': len(complete), 'bytes': len(prefix), 'sha256': hashlib.sha256(prefix).hexdigest()}))


def fetch(client, directory, **kwargs):
    return download_mp4(client, URL, directory, max_bytes=32, timeout=60, resume=True, **kwargs)


def test_timeout_keeps_prefix_and_same_version_resumes_without_new_full_request(tmp_path):
    calls = []
    class Interrupted(httpx.SyncByteStream):
        def __iter__(self):
            yield b'abcd'
            raise httpx.ReadTimeout('synthetic transport timeout')
    def request(req):
        calls.append(dict(req.headers))
        if len(calls) == 1:
            return httpx.Response(200, headers={'Content-Length': '8', 'ETag': ETAG}, stream=Interrupted())
        return httpx.Response(206, headers={'Content-Range': 'bytes 4-7/8', 'ETag': ETAG}, content=b'efgh')
    with httpx.Client(transport=httpx.MockTransport(request)) as client:
        with pytest.raises(httpx.ReadTimeout): fetch(client, tmp_path)
        info = checkpoint_info(tmp_path, 32)
        assert info['bytes'] == 4 and URL not in (tmp_path/'checkpoint.json').read_text()
        assert fetch(client, tmp_path).read_bytes() == b'abcdefgh'
        assert calls[1]['range'] == 'bytes=4-' and calls[1]['if-range'] == ETAG
        assert calls[1]['accept-encoding'] == 'identity'
        assert fetch(client, tmp_path).read_bytes() == b'abcdefgh'
        assert len(calls) == 2  # a checked, complete source can be reused for local remux


@pytest.mark.parametrize('replacement', ['changed_version', 'range_ignored'])
def test_full_response_to_range_restarts_at_zero(tmp_path, replacement):
    seed(tmp_path)
    def request(req):
        assert req.headers['range'] == 'bytes=4-'
        return httpx.Response(200, headers={'ETag': '"version-two"' if replacement == 'changed_version' else ETAG}, content=b'12345678')
    with httpx.Client(transport=httpx.MockTransport(request)) as client:
        assert fetch(client, tmp_path).read_bytes() == b'12345678'


@pytest.mark.parametrize('headers', [
    {'Content-Range': 'bytes 3-6/8', 'ETag': ETAG},
    {'Content-Range': 'bytes 4-7/9', 'ETag': ETAG},
    {'Content-Range': 'bytes 4-7/8', 'ETag': '"changed"'},
    {'Content-Range': 'bytes 4-7/8', 'ETag': ETAG, 'Content-Length': '5'},
])
def test_mismatched_range_or_version_never_appends_to_prefix(tmp_path, headers):
    seed(tmp_path)
    with httpx.Client(transport=httpx.MockTransport(lambda req: httpx.Response(206, headers=headers, content=b'efgh'))) as client:
        with pytest.raises(ValueError, match='invalid_media_range'): fetch(client, tmp_path)
    assert not (tmp_path/'checkpoint.json').exists() and not (tmp_path/'source.mp4').exists()


@pytest.mark.parametrize('fault', ['corrupt_prefix', 'corrupt_metadata', 'changed_source'])
def test_bad_local_checkpoint_starts_a_fresh_download(tmp_path, fault):
    seed(tmp_path)
    if fault == 'corrupt_prefix': (tmp_path/'source.mp4').write_bytes(b'xxxx')
    elif fault == 'corrupt_metadata': (tmp_path/'checkpoint.json').write_text('{broken')
    else:
        p=tmp_path/'checkpoint.json';d=json.loads(p.read_text());d['source_hash']='f'*64;p.write_text(json.dumps(d))
    def request(req):
        assert 'range' not in req.headers
        return httpx.Response(200, headers={'ETag': ETAG}, content=b'abcdefgh')
    with httpx.Client(transport=httpx.MockTransport(request)) as client:
        assert fetch(client, tmp_path).read_bytes() == b'abcdefgh'


@pytest.mark.parametrize('etag', [None, 'W/"weak"'])
def test_unversioned_partial_is_not_reused(tmp_path, etag):
    class Interrupted(httpx.SyncByteStream):
        def __iter__(self):
            yield b'abcd'
            raise httpx.ReadTimeout('synthetic timeout')
    headers={'Content-Length':'8', **({'ETag':etag} if etag else {})}
    with httpx.Client(transport=httpx.MockTransport(lambda req: httpx.Response(200, headers=headers, stream=Interrupted()))) as client:
        with pytest.raises(httpx.ReadTimeout): fetch(client, tmp_path)
    assert checkpoint_info(tmp_path, 32) is None and not (tmp_path/'source.mp4').exists()


def test_short_body_is_checkpointed_but_not_reported_complete(tmp_path):
    with httpx.Client(transport=httpx.MockTransport(lambda req: httpx.Response(200, headers={'Content-Length':'8','ETag':ETAG}, content=b'abcd'))) as client:
        with pytest.raises(ValueError, match='incomplete_media'): fetch(client, tmp_path)
    assert checkpoint_info(tmp_path, 32)['bytes'] == 4


def test_crash_tail_is_removed_before_range_request(tmp_path):
    seed(tmp_path)
    with (tmp_path/'source.mp4').open('ab') as output: output.write(b'unchecked-tail')
    def request(req):
        assert req.headers['range'] == 'bytes=4-'
        assert (tmp_path/'source.mp4').read_bytes() == b'abcd'
        return httpx.Response(206, headers={'Content-Range':'bytes 4-7/8','ETag':ETAG}, content=b'efgh')
    with httpx.Client(transport=httpx.MockTransport(request)) as client:
        assert fetch(client, tmp_path).read_bytes() == b'abcdefgh'


def test_periodic_checkpoint_survives_process_interruption(tmp_path):
    prefix=b'x'*(4*1024*1024);size=len(prefix)+8
    class Crash(httpx.SyncByteStream):
        def __iter__(self):
            yield prefix
            yield b'tail'
            raise KeyboardInterrupt()
    with httpx.Client(transport=httpx.MockTransport(lambda req: httpx.Response(200, headers={'Content-Length':str(size),'ETag':ETAG}, stream=Crash()))) as client:
        with pytest.raises(KeyboardInterrupt):
            download_mp4(client,URL,tmp_path,max_bytes=size,timeout=60,resume=True)
    assert checkpoint_info(tmp_path,size)['bytes']==len(prefix)
    def request(req):
        assert req.headers['range']==f'bytes={len(prefix)}-'
        return httpx.Response(206,headers={'Content-Range':f'bytes {len(prefix)}-{size-1}/{size}','ETag':ETAG},content=b'abcdefgh')
    with httpx.Client(transport=httpx.MockTransport(request)) as client:
        assert download_mp4(client,URL,tmp_path,max_bytes=size,timeout=60,resume=True).read_bytes()==prefix+b'abcdefgh'


def test_resumable_download_retains_same_deadline_and_size_limit(tmp_path):
    seed(tmp_path);now=[0]
    class Slow(httpx.SyncByteStream):
        def __iter__(self):
            now[0]=59;yield b'e'
            now[0]=61;yield b'fgh'
    with httpx.Client(transport=httpx.MockTransport(lambda req: httpx.Response(206,headers={'Content-Range':'bytes 4-7/8','ETag':ETAG},stream=Slow()))) as client:
        with pytest.raises(ValueError,match='download_timeout'):fetch(client,tmp_path,clock=lambda:now[0])
    assert checkpoint_info(tmp_path,32)['bytes']==5
    with httpx.Client(transport=httpx.MockTransport(lambda req:httpx.Response(200,headers={'Content-Length':'8','ETag':ETAG},content=b'abcdefgh'))) as client:
        with pytest.raises(ValueError,match='media_limit'):
            download_mp4(client,URL,tmp_path,max_bytes=4,timeout=60,resume=True)
    assert not (tmp_path/'source.mp4').exists()


def test_partial_storage_is_bounded_and_final_assets_are_untouched(tmp_path):
    cache=PartialCache(tmp_path)
    sentinel=tmp_path/'assets'/'complete.mp4';sentinel.parent.mkdir();sentinel.write_bytes(b'final media')
    for n in (1,2):seed(cache.root/f'{n:024x}',b'abcdef')
    target=cache.reserve('3'*24,max_bytes=8,budget=16)
    assert target is not None
    assert sum((p/'source.mp4').stat().st_size for p in cache.entries() if (p/'source.mp4').exists())+8<=16
    assert sentinel.read_bytes()==b'final media'
    assert cache.reserve('4'*24,max_bytes=8,budget=4) is None
    for n in range(30,48):seed(cache.root/f'{n:024x}',b'a')
    cache.reserve('5'*24,max_bytes=8,budget=1024)
    assert len(cache.entries())<=16


def test_partial_storage_never_follows_a_symlink_root(tmp_path):
    target=tmp_path/'external'
    target.mkdir();(tmp_path/'.media-partials').symlink_to(target,target_is_directory=True)
    cache=PartialCache(tmp_path)
    assert cache.ready_ids(32)==[]
    with pytest.raises(ValueError,match='invalid_partial_identity'):cache.reserve('a'*24,32,128)
    with pytest.raises(ValueError,match='invalid_partial_identity'):cache.discard('a'*24)


def test_checked_prefix_gets_priority_only_after_existing_cooldown(tmp_path,monkeypatch):
    monkeypatch.setattr(store,'ROOT',tmp_path)
    old,_=store.ingest({'source_url':'https://example.org/old','title':'old'})
    fresh,_=store.ingest({'source_url':'https://example.org/fresh','title':'fresh'})
    seed(PartialCache(tmp_path).root/old)
    with store.connection() as db:db.execute("INSERT INTO media_jobs VALUES(?,'failed',1,'download_timeout',?)",(old,time.time()))
    assert [r['id'] for r in media.recover_candidates(1)[0]]==[fresh]
    with store.connection() as db:db.execute('UPDATE media_jobs SET updated=? WHERE item=?',(time.time()-7*3600,old))
    assert [r['id'] for r in media.recover_candidates(1)[0]]==[old]


def test_real_codec_pipeline_publishes_only_after_resumed_download(tmp_path,monkeypatch):
    if not Path(media.FFMPEG).is_file():pytest.skip('FFmpeg runtime unavailable')
    fixture=tmp_path/'synthetic.mp4'
    subprocess.run([media.FFMPEG,'-nostdin','-v','error','-f','lavfi','-i','color=c=blue:s=160x90:d=1',
        '-f','lavfi','-i','sine=frequency=500:duration=1','-shortest','-c:v','libx264','-c:a','aac',str(fixture)],check=True,capture_output=True)
    content=fixture.read_bytes();offset=len(content)//2;calls=[]
    root=tmp_path/'library';monkeypatch.setattr(store,'ROOT',root);monkeypatch.setattr(media,'MAX_FILE',2*1024*1024)
    monkeypatch.setenv('AD_LIBRARY_MAX_GIB','1')
    identity,_=store.ingest({'source_url':'https://example.org/codec-fixture','title':'Synthetic codec fixture',
        'creative_structure':{'public_video_url':URL}})
    class Interrupted(httpx.SyncByteStream):
        def __iter__(self):
            yield content[:offset]
            raise httpx.ReadTimeout('synthetic timeout')
    def request(req):
        calls.append(dict(req.headers))
        if len(calls)==1:return httpx.Response(200,headers={'Content-Length':str(len(content)),'ETag':ETAG},stream=Interrupted())
        assert req.headers['range']==f'bytes={offset}-'
        return httpx.Response(206,headers={'Content-Range':f'bytes {offset}-{len(content)-1}/{len(content)}','ETag':ETAG},content=content[offset:])
    original=httpx.Client
    monkeypatch.setattr(media.httpx,'Client',lambda **kw:original(transport=httpx.MockTransport(request),**kw))
    assert media.run(1)=={'state':'partial','cached':0,'failed':1}
    with store.connection() as db:
        assert db.execute('SELECT COUNT(*) FROM assets').fetchone()[0]==0
        db.execute('UPDATE media_jobs SET updated=0 WHERE item=?',(identity,))
    assert media.run(1)=={'state':'completed','cached':1,'failed':0}
    with store.connection() as db:
        asset=db.execute('SELECT * FROM assets WHERE item=?',(identity,)).fetchone()
        assert asset['audio']==1 and asset['duration']>=0.9
        assert hashlib.sha256((root/asset['path']).read_bytes()).hexdigest()==asset['sha256']
    assert len(calls)==2 and not (PartialCache(root).root/identity).exists()
