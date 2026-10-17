"""Publish a completed edit and its frozen video sources to the same project canvas."""
import copy
import json
import re
import secrets
import shutil
from harness.studio import store
from harness.tools.creative_canvas import save_asset, next_position, asset_directory
from harness.tools.creative_edit_media import digest, describe, MAX_EDIT_UPLOAD
from harness.tools.creative_edit_timing import schedule
from harness.tools.creative_edit import validate_edit


def publish_export(project,job):
    if job.get('state')!='completed' or job.get('qa',{}).get('technical')!='passed':raise ValueError('只有技术检查通过的剪辑版本可加入画布')
    if not re.fullmatch('[a-f0-9]{32}',job['id']):raise ValueError('导出版本无效')
    directory=store.DATA/'edits'/project['id']/job['id'];output=directory/'final.mp4'
    if job.get('artifact_sha256') and digest(output)!=job['artifact_sha256']:raise ValueError('导出文件已变化')
    document=json.loads((directory/'edit.json').read_text())
    if job.get('document_sha256') and digest(directory/'edit.json')!=job['document_sha256']:raise ValueError('导出剪辑记录已变化')
    sources={};paths={}
    for i,(sid,sha) in enumerate(document['sources'].items()):
        candidates=list(directory.glob(f'source-{i}.*'))
        if len(candidates)!=1:raise ValueError('导出来源文件不完整')
        path=candidates[0];meta=describe(path)
        if meta['sha256']!=sha:raise ValueError('导出来源文件已变化')
        sources[sid]=meta;paths[sid]=path
    document=validate_edit(document,catalog=sources)
    # Use copied source bytes, so later re-generation or source removal cannot rewrite history.
    result=copy.deepcopy(project);assets=result.setdefault('canvas_assets',{});graph=result.setdefault('canvas',{'nodes':[],'edges':[]})
    existing=next((aid for aid,a in assets.items() if a.get('provenance',{}).get('export_id')==job['id']),None)
    if existing:
        placed=any(n.get('asset')==existing for n in graph['nodes'])
        if not placed:
            if len(graph['nodes'])>=16:raise ValueError('画布已满，请先整理素材')
            graph['nodes'].append(dict(id='n'+secrets.token_hex(16),kind='video',asset=existing,label='剪辑成片',text='',role='story',**next_position(graph)))
        return result,existing,not placed
    new=[];mapping={}
    needed=[sid for sid,meta in sources.items() if meta['kind']=='video']
    for sid in needed:
        sha=sources[sid]['sha256']
        match=next((aid for aid,a in assets.items() if a['kind']=='video' and a.get('sha256')==sha and (asset_directory(project,aid)/a['filename']).is_file() and digest(asset_directory(project,aid)/a['filename'])==sha),None)
        if match:mapping[sid]=match
    missing=len(needed)-len(mapping)
    nodes_needed=sum(not any(n.get('asset')==aid for n in graph['nodes']) for aid in set(mapping.values()))+missing+1
    if len(graph['nodes'])+nodes_needed>16:raise ValueError('画布空间不足，请先为成片及来源整理节点')
    if len(assets)+missing+1>32:raise ValueError('项目素材空间不足，请先整理素材')
    for path in [output]+[paths[sid] for sid in needed if sid not in mapping]:
        if path.stat().st_size>MAX_EDIT_UPLOAD:raise ValueError('此视频超过 60 MB，请先导出较短片段')
    try:
        for sid in needed:
            if sid not in mapping:
                asset=save_asset(project,paths[sid].read_bytes(),'video',max_bytes=MAX_EDIT_UPLOAD,max_duration=120);new.append(asset['id'])
                asset['provenance']={'kind':'edit_source','sources':[],'source_id':sid,'source_sha256':sources[sid]['sha256']}
                # Preserve the bounded retake receipt when this source is an immutable candidate.
                source_meta=project.get('edit_assets',{}).get(sid.removeprefix('edit_'),{}) if sid.startswith('edit_') else {}
                receipt=source_meta.get('provenance',{})
                if source_meta.get('sha256')==sources[sid]['sha256'] and receipt.get('kind')=='video_retake':
                    asset['provenance']['retake']={k:copy.deepcopy(receipt[k]) for k in
                        ('job_id','model','source','source_sha256','source_start','source_end','input_sha256','raw_sha256','audio','training_eligible') if k in receipt}
                assets[asset['id']]=asset;mapping[sid]=asset['id']
            aid=mapping[sid]
            if not any(n.get('asset')==aid for n in graph['nodes']):
                graph['nodes'].append(dict(id='n'+secrets.token_hex(16),kind='video',asset=aid,label='剪辑来源 '+str(needed.index(sid)+1),text='',role='reference',**next_position(graph)))
        asset=save_asset(project,output.read_bytes(),'video',max_bytes=MAX_EDIT_UPLOAD,max_duration=document['duration']+.2);new.append(asset['id'])
        asset['provenance']={'kind':'video_edit','sources':list(dict.fromkeys(mapping.values())),'export_id':job['id'],
            'clips':[dict(asset=mapping[c['source']],start=c['start'],end=c['end'],at=t['at'],transition=c['transition']) for c,t in zip(document['clips'],schedule(document['clips']))],
            'audio':[dict(source_sha256=document['sources'][a['source']],start=a['start'],end=a['end'],at=a['at']) for a in document['audio']],
            'document_sha256':digest(directory/'edit.json'),'artifact_sha256':digest(output)}
        assets[asset['id']]=asset
        parents=[n for n in graph['nodes'] if n.get('asset') in mapping.values()]
        # Direct sources are placed first, and the derived video is added in the next free column.
        parent=parents[0]['asset'] if parents else None
        graph['nodes'].append(dict(id='n'+secrets.token_hex(16),kind='video',asset=asset['id'],label='剪辑成片 · '+str(document['duration'])+'s',text='',role='story',**next_position(graph,parent)))
        return result,asset['id'],True
    except Exception:
        for aid in new:shutil.rmtree(asset_directory(project,aid),ignore_errors=True)
        raise
