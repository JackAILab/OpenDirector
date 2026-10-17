import json
import types
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient
from harness.studio import store, templates


def test_catalog_gate_owned_adoption_and_media_allowlist(tmp_path,monkeypatch):
    monkeypatch.setattr(store,'DATA',tmp_path)
    directory=tmp_path/'templates'/'coffee';directory.mkdir(parents=True)
    (directory/'final.mp4').write_bytes(b'fixture-media');(directory/'poster.jpg').write_bytes(b'fixture-poster')
    template={'id':'coffee','title':'咖啡','provider':'kling','model':'kling-video-v2_5','aspect':'16:9','duration':10,'storyboard':[{'title':'细节','caption':'早安','rationale':'开启清晨'}]}
    (tmp_path/'templates'/'catalog.json').write_text(json.dumps({'templates':[template]}))
    app=FastAPI()
    def auth(value):
        if value!='Bearer own':raise HTTPException(401)
        return {'id':42}
    def gate(request):
        if request.cookies.get('access')!='yes':raise HTTPException(403)
    templates.install(types.SimpleNamespace(app=app,require_session=auth,require_site_access=gate))
    with TestClient(app) as c:
        assert c.get('/creative/api/templates').status_code==403
        assert c.get('/creative/api/templates/coffee/video').status_code==403
        c.cookies.set('access','yes')
        assert c.get('/creative/api/templates').json()['templates'][0]['id']=='coffee'
        assert c.get('/creative/api/templates/coffee/private-key').status_code==404
        assert c.get('/creative/api/templates/unknown/video').status_code==404
        assert c.post('/creative/api/templates/coffee/use',json={'product':'茶杯'}).status_code==401
        result=c.post('/creative/api/templates/coffee/use',json={'product':'茶杯','requirements':'自然光'},headers={'Authorization':'Bearer own'})
        assert result.status_code==200
        p=result.json();saved=store.load(p['id'],42)
        assert saved['model']=='kling-video-v3_0' and saved['aspect']=='16:9'
        assert saved['state']=='intake' and not saved['shots'] and saved['training_eligible']==False
        assert 'run_id' not in saved and 'artifact' not in saved
        assert '茶杯' in saved['messages'][0]['content']
        assert saved['canvas']['edges'][0]['target']=='director'
        assert p['quote']['credits']==0  # no planned generation or paid task inherited
        try:store.load(p['id'],43);assert False
        except HTTPException as e:assert e.status_code==404

        chosen=c.post('/creative/api/templates/coffee/use',json={
            'product':'茶杯','model':'kling-video-v3_0_omni','aspect':'9:16'
        },headers={'Authorization':'Bearer own'})
        assert chosen.status_code==200
        selected=store.load(chosen.json()['id'],42)
        assert selected['model']=='kling-video-v3_0_omni' and selected['aspect']=='9:16'
        assert selected['duration']==15 and selected['generation_mode']=='single_native'
        assert 'Kling O3' in selected['messages'][0]['content']
        assert not selected['shots'] and not selected.get('film')
        for invalid in [{'model':'kling-video-v2_5'},{'model':'MiniMax-H3'},
                        {'model':'unknown-model'},{'model':''},{'aspect':'4:3'}]:
            assert c.post('/creative/api/templates/coffee/use',json={'product':'茶杯',**invalid},
                          headers={'Authorization':'Bearer own'}).status_code==422
        with store.connection() as db:
            assert db.execute('SELECT COUNT(*) FROM projects').fetchone()[0]==2

        private=c.post('/creative/api/skills',headers={'Authorization':'Bearer own'},json={'content':{
            'title':'私人方法','description':'仅我可见','inputs':['商品图'],'steps':['拍摄细节'],'checks':['商品一致']}}).json()
        assert private['id'] not in {s['id'] for s in c.get('/creative/api/skills').json()['skills']}
        assert private['id'] in {s['id'] for s in c.get('/creative/api/skills',headers={'Authorization':'Bearer own'}).json()['skills']}
        assert c.get('/creative/api/skills',headers={'Authorization':'Bearer invalid'}).status_code==401


def test_parallel_publication_retains_both_and_is_idempotent(tmp_path,monkeypatch):
    from concurrent.futures import ThreadPoolExecutor
    monkeypatch.setattr(store,'DATA',tmp_path)
    source=tmp_path/'source.mp4';source.write_bytes(b'video')
    poster=tmp_path/'poster.jpg';poster.write_bytes(b'poster')
    p={'provider':'kling','model':'kling-video-v2_5','qa':{'technical':'passed'},'shots':[{'title':'镜头','caption':'字幕','rationale':'质感'}]}
    def publish(tid):
        case={'id':tid,'title':tid,'category':'家居','product':'杯','scene':'桌面','provider':'kling','model':'kling-video-v2_5','aspect':'16:9','duration':10}
        return templates.publish_template(case,p,source,poster,False,'抽帧检查通过，待人审')
    with ThreadPoolExecutor(max_workers=2) as pool:
        assert all(pool.map(publish,['one','two']))
    assert {t['id'] for t in templates.catalog()['templates']}=={'one','two'}
    assert publish('one') is False
    assert len(templates.catalog()['templates'])==2
    assert all(t['training_eligible']==False for t in templates.catalog()['templates'])
