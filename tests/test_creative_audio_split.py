import copy
import os
import subprocess
import pytest
from harness.studio import store
from harness.tools.creative_canvas import save_asset, asset_directory, asset_metadata, validate_graph
from harness.tools.creative_audio_split import split_audio
from test_creative_studio import client, ready


def test_separate_real_tracks_auth_revision_and_source(client, tmp_path):
    source=tmp_path/'source.mp4'
    subprocess.run([os.environ['CREATIVE_FFMPEG'],'-v','error','-f','lavfi','-i','color=blue:s=320x180:r=24',
                    '-f','lavfi','-i','sine=frequency=440:sample_rate=48000','-t','1','-c:a','aac',
                    '-pix_fmt','yuv420p','-threads','1',str(source)],check=True)
    p=store.load(ready(client)['id'],1)
    asset=save_asset(p,source.read_bytes(),'video');aid=asset['id']
    p['canvas_assets']={aid:asset}
    p['canvas']={'nodes':[dict(id='source',kind='video',asset=aid,label='原片',text='',x=0,y=0)],'edges':[]}
    store.save(p,1)
    url=f"/creative/api/projects/{p['id']}/canvas/assets/{aid}/split-audio"
    assert client.post(url,params={'revision':p['revision']},headers={'Authorization':'Bearer two'}).status_code==404
    assert client.post(url,params={'revision':-1}).status_code==409
    r=client.post(url,params={'revision':p['revision']});assert r.status_code==200,r.text
    result=r.json();updated=store.load(p['id'],1)
    assert len(updated['canvas']['nodes'])==3
    assert updated['canvas']['edges']==[]
    muted,audio=result['assets']
    assert not asset_metadata(updated,muted['id'])['has_audio']
    assert asset_metadata(updated,audio['id'])['sample_rate']==48000
    assert .95 <= asset_metadata(updated,audio['id'])['duration'] <= 1.1
    assert (asset_directory(updated,aid)/asset['filename']).read_bytes()==source.read_bytes()
    for a in result['assets']:
        assert result['project']['canvas_lineage'][a['id']]['sources']==[aid]
        response=client.get(f"/creative/api/projects/{p['id']}/canvas/assets/{a['id']}/source")
        assert response.status_code==200
        assert response.headers['content-type'].startswith('audio/mp4' if a['kind']=='audio' else 'video/mp4')
    # Extracted canvas audio is an owned, hash-bound edit source, never a picture.
    from harness.tools.creative_edit import validate_edit
    document=client.get(f"/creative/api/projects/{p['id']}/edit").json()
    sid='canvas_'+audio['id']
    assert document['sources'][sid]['kind']=='audio'
    assert document['sources'][sid]['has_audio'] is True
    response=client.get(f"/creative/api/projects/{p['id']}/edit/sources/{sid}")
    assert response.status_code==200
    assert response.headers['content-type'].startswith('audio/mp4')
    assert client.get(f"/creative/api/projects/{p['id']}/edit/sources/{sid}",headers={'Authorization':'Bearer two'}).status_code==404
    spec=copy.deepcopy(document['spec'])
    spec['sources'][sid]=document['sources'][sid]['sha256']
    spec['audio']=[{'source':sid,'start':0,'end':.8,'at':0,'gain':1}]
    assert validate_edit(spec,catalog=document['sources'])['audio'][0]['source']==sid
    wrong=copy.deepcopy(spec);wrong['sources'][sid]='wrong'
    with pytest.raises(ValueError,match='源素材已变化'):validate_edit(wrong,catalog=document['sources'])
    wrong=copy.deepcopy(spec);wrong['clips']=[{'source':sid,'start':0,'end':.8}]
    with pytest.raises(ValueError,match='不支持该轨道'):validate_edit(wrong,catalog=document['sources'])
    assert client.post(url,params={'revision':p['revision']}).status_code==409
    with pytest.raises(ValueError,match='无音轨'): split_audio(updated,muted['id'])
    validate_graph(updated['canvas'],updated['canvas_assets'])
    graph=copy.deepcopy(updated['canvas']);graph['edges']=[{'source':result['nodes'][1]['id'],'target':'director'}]
    with pytest.raises(ValueError,match='音频理解'): validate_graph(graph,updated['canvas_assets'])


def test_partial_output_failure_cleans_assets(client,monkeypatch,tmp_path):
    import harness.tools.creative_audio_split as module
    p={'id':'a'*24,'canvas_assets':{'b'*32:{'id':'b'*32,'kind':'video','filename':'source.mp4'}},'canvas':{'nodes':[],'edges':[]}}
    directory=asset_directory(p,'b'*32);directory.mkdir(parents=True);(directory/'source.mp4').write_bytes(b'original')
    before=copy.deepcopy(p)
    monkeypatch.setattr(module,'asset_metadata',lambda *a:{'has_audio':True,'duration':1})
    def run(args,**kwargs):
        from pathlib import Path
        Path(args[-1]).write_bytes(b'processed')
    monkeypatch.setattr(module.subprocess,'run',run)
    def save(project,raw,kind,**kwargs):
        if kind=='audio':raise ValueError('test failure')
        out=asset_directory(p,'c'*32);out.mkdir();(out/'source.mp4').write_bytes(raw)
        return {'id':'c'*32,'kind':'video'}
    monkeypatch.setattr(module,'save_asset',save)
    with pytest.raises(ValueError,match='test failure'):split_audio(p,'b'*32)
    assert p==before
    assert not asset_directory(p,'c'*32).exists()
    assert (directory/'source.mp4').read_bytes()==b'original'
