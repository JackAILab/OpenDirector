import shutil
import os
import subprocess
import pytest
from PIL import Image
from harness.studio import store
from harness.tools.creative_canvas import save_asset
from test_creative_studio import client, ready


def test_extract_owned_video_frame_and_preserve_source(client, monkeypatch, tmp_path):
    ffmpeg, ffprobe = os.getenv('CREATIVE_FFMPEG') or shutil.which('ffmpeg'), os.getenv('CREATIVE_FFPROBE') or shutil.which('ffprobe')
    if not ffmpeg or not ffprobe:
        pytest.skip('ffmpeg and ffprobe required')
    monkeypatch.setenv('CREATIVE_FFMPEG', ffmpeg)
    monkeypatch.setenv('CREATIVE_FFPROBE', ffprobe)
    source=tmp_path/'fixture.mp4'
    subprocess.run([ffmpeg,'-v','error','-f','lavfi','-i','color=red:s=320x180:r=24',
                    '-t','1','-vf',"drawbox=color=blue:t=fill:enable='gte(t,0.5)'",'-pix_fmt','yuv420p','-threads','1',str(source)],check=True)
    p=ready(client); p=store.load(p['id'],1)
    asset=save_asset(p,source.read_bytes(),'video')
    p['canvas_assets']={asset['id']:asset}
    p['canvas']={'nodes':[dict(id='source',kind='video',asset=asset['id'],label='Source',x=0,y=0)],'edges':[]}
    store.save(p,1)
    url=f"/creative/api/projects/{p['id']}/canvas/assets/{asset['id']}/frame"
    params={'revision':p['revision'],'at':.5}
    assert client.post(url,params=params,headers={'Authorization':'Bearer two'}).status_code==404
    assert client.post(url,params={**params,'at':1.5}).status_code==422
    assert client.post(url,params={**params,'revision':-1}).status_code==409
    r=client.post(url,params=params)
    assert r.status_code==200, r.text
    result=r.json(); updated=result['project']; frame=result['asset']
    assert frame['kind']=='image'
    assert updated['canvas_lineage'][frame['id']]['sources']==[asset['id']]
    assert updated['canvas_lineage'][frame['id']]['source_time']==.5
    assert updated['canvas']['edges']==[]  # Derivation never grants Director input.
    assert len(updated['canvas']['nodes'])==2
    assert store.load(p['id'],1)['canvas_assets'][asset['id']]==asset
    assert client.post(url,params=params).status_code==409  # No duplicate on stale retry.
    assert source.read_bytes()==(store.DATA/'canvas'/p['id']/asset['id']/'source.mp4').read_bytes()

    # Verify actual decoded endpoints, not a guessed timestamp near duration.
    for position,channel in [('last',2),('first',0)]:
        response=client.post(url,params={'revision':updated['revision'],'position':position})
        assert response.status_code==200, response.text
        updated=response.json()['project']; still=response.json()['asset']
        receipt=updated['canvas_lineage'][still['id']]
        assert receipt['source_position']==position
        assert receipt['sources']==[asset['id']]
        path=store.DATA/'canvas'/p['id']/still['id']/still['filename']
        with Image.open(path) as image:
            pixel=image.convert('RGB').getpixel((160,90))
            assert pixel[channel]>200 and sum(pixel)-pixel[channel]<80
        if position=='last': assert 'source_time' not in receipt
