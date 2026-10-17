from test_creative_studio import client, ready
from harness.studio import media_access, store
from harness.tools.creative_canvas import asset_directory


def test_grant_tamper_scope_and_expiry(monkeypatch):
    monkeypatch.setattr(media_access.time,'time',lambda:1000)
    token=media_access.issue(1,'p','a')
    assert media_access.verify(token,'p','a')==1
    assert media_access.verify(token+'x','p','a') is None
    assert media_access.verify(token,'other','a') is None
    assert media_access.verify(token,'p','other') is None
    for invalid in ('', 'bad', 'a.b.c', '.', 'x'*2049):
        assert media_access.verify(invalid,'p','a') is None
    monkeypatch.setattr(media_access.time,'time',lambda:1900)
    assert media_access.verify(token,'p','a') is None


def test_native_range_grant_is_asset_only_and_owner_checked(client,monkeypatch):
    client.base_url='https://testserver'
    p=ready(client);p=store.load(p['id'],1)
    aid='a'*32
    p['canvas_assets']={aid:{'id':aid,'kind':'video','filename':'source.mp4'}}
    store.save(p,1)
    folder=asset_directory(p,aid);folder.mkdir(parents=True)
    (folder/'source.mp4').write_bytes(b'0123456789abcdef')
    url=f'/creative/api/projects/{p["id"]}/canvas/assets/{aid}'
    assert client.post(url+'/preview-session',headers={'Authorization':'Bearer two'}).status_code==404
    r=client.post(url+'/preview-session');assert r.status_code==200
    assert r.json()=={'source':url+'/source'}
    cookie=r.headers['set-cookie'];assert all(x in cookie for x in ('HttpOnly','Secure','SameSite=strict','Max-Age=900','Path='+url+'/source'))
    del client.headers['Authorization']
    r=client.get(url+'/source',headers={'Range':'bytes=2-5'})
    assert r.status_code==206 and r.content==b'2345'
    assert r.headers['content-range']=='bytes 2-5/16'
    assert r.headers['accept-ranges']=='bytes'
    assert client.get(url+'/metadata').status_code==401
    assert client.get('/creative/api/projects/'+p['id']).status_code==401
    assert client.get(url+'/source',headers={'Authorization':'Bearer two'}).status_code==404
    # An issued grant never bypasses current project ownership.
    monkeypatch.setattr(media_access.time,'time',lambda:10**12)
    assert client.get(url+'/source').status_code==401
