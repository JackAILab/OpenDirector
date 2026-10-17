import json
from pathlib import Path
import pytest
from harness.studio import store
from harness.tools import creative_edit_publish as publish
from harness.tools.creative_edit_media import digest
from harness.tools.creative_edit import validate_edit
from test_creative_edit import client,source_project


def test_publish_frozen_sources_lineage_idempotence_and_owner_scope(client,monkeypatch):
    p=source_project(client,monkeypatch);job_id='a'*32;folder=store.DATA/'edits'/p['id']/job_id;folder.mkdir(parents=True)
    (folder/'source-0.mp4').write_bytes(b'old-source');(folder/'final.mp4').write_bytes(b'final')
    sha=digest(folder/'source-0.mp4');spec=validate_edit(dict(source_sha256=sha,clips=[dict(start=1,end=3)]),15,sha)
    (folder/'edit.json').write_text(json.dumps(spec));job=dict(id=job_id,state='completed',revision=p['revision'],qa={'technical':'passed'},artifact_sha256=digest(folder/'final.mp4'),document_sha256=digest(folder/'edit.json'))
    p['edit_versions']=[job];p['canvas']={'nodes':[],'edges':[]};store.save(p,1);counter=[]
    monkeypatch.setattr(publish,'describe',lambda path:dict(sha256=digest(path),duration=15,kind='video',has_audio=True))
    def asset(project,raw,kind,**kwargs):
        aid=str(len(counter)+1)*32;counter.append(aid);directory=store.DATA/'canvas'/p['id']/aid;directory.mkdir(parents=True)
        (directory/'source.mp4').write_bytes(raw)
        return dict(id=aid,kind=kind,filename='source.mp4',sha256=digest(directory/'source.mp4'),frames=1,duration=2)
    monkeypatch.setattr(publish,'save_asset',asset)
    base='/creative/api/projects/'+p['id']+'/edit/exports/'+job_id+'/canvas'
    assert client.post(base,json={'revision':p['revision']},headers={'Authorization':'Bearer two'}).status_code==404
    response=client.post(base,json={'revision':p['revision']});assert response.status_code==200,response.text
    current=store.load(p['id'],1);assert current['state']=='completed' and current['artifact']==p['artifact']
    assert current['canvas']['edges']==[] and len(current['canvas']['nodes'])==2
    origin=current['canvas_assets'][response.json()['asset']]['provenance'];assert origin['clips'][0]['start']==1 and len(origin['sources'])==1
    source=current['canvas_assets'][origin['sources'][0]];assert (store.DATA/'canvas'/p['id']/source['id']/'source.mp4').read_bytes()==b'old-source'
    again=client.post(base,json={'revision':current['revision']});assert again.json()['revision']==current['revision'] and len(counter)==2
    assert client.post(base,json={'revision':p['revision']}).status_code==409
    (folder/'final.mp4').write_bytes(b'tampered')
    assert client.post(base,json={'revision':current['revision']}).status_code==422
