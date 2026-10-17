"""Bounded image action; generated assets belong to one project and one attempt."""
from harness.models.studio_image import generate
from harness.tools.creative_reference import reference_path
from harness.tools.creative_canvas import save_asset, asset_directory
from harness.studio import store
from harness.tools.creative_image_inputs import checked_paths


def create_image(project, task):
    reference=None
    prepared=task.get('prepared')
    if prepared:
        paths=checked_paths(project,prepared['references'])
        reference=paths[0] if len(paths)==1 else paths or None
    elif task.get('source_asset'):
        asset=project['canvas_assets'][task['source_asset']]
        reference=asset_directory(project,asset['id'])/asset['filename']
    elif task['model']=='hunyuan-image-v2.0-general-edit':
        reference=reference_path(project)
    if prepared and prepared.get('region',{}).get('shape')=='brush':
        import hashlib
        from harness.tools.creative_image_region import brush_mask
        region=prepared['region'];mask=brush_mask(tuple(region['dimensions']),region['strokes'])
        if hashlib.sha256(mask.tobytes()).hexdigest()!=region['mask_sha256']:raise ValueError('已确认选区发生变化，本次不会提交生成')
        guide_dir=store.DATA/'image-inputs'/project['id']/task['id'];guide_dir.mkdir(parents=True,exist_ok=False,mode=0o700)
        guide=guide_dir/'selection.png';mask.save(guide,'PNG');guide.chmod(0o600)
        reference=[paths[0],guide]
    raw=generate(task['model'],task['prompt'],prepared['aspect'] if prepared else project['aspect'],
                 store.DATA/'image-generations'/project['id']/task['id'],reference)
    region_receipt=None
    if prepared and prepared.get('region'):
        from harness.tools.creative_image_region import compose_region
        raw,region_receipt=compose_region(paths[0],raw,prepared['region'])
    asset=save_asset(project,raw,'image',preserve_pixels=True)
    source=task.get('source_asset') or task.get('reference_asset')
    sources=[r['asset'] for r in prepared['references'] if r.get('asset')] if prepared else [source] if source else []
    asset['provenance']={'kind':'image_composite' if len(sources)>1 else 'image_edit' if reference else 'image_generated',
                         'sources':sources,'request_id':task['id'],'model':task['model']}
    if region_receipt:asset['provenance']['region_edit']=region_receipt
    if task.get('adjustments'):
        asset['provenance']['adjustments']={k:task['adjustments'][k] for k in ('angle','light') if k in task['adjustments']}
    if task.get('transform_draft_id'):
        asset['provenance']['transform_draft_id']=task['transform_draft_id']
    if prepared:
        if prepared.get('control_parameters'):
            asset['provenance']['control_parameters']=dict(prepared['control_parameters'])
        asset['provenance'].update(inputs=prepared['references'],input_hash=prepared['input_hash'],training_eligible=False)
    if task.get('reference_id'): asset['provenance']['reference_id']=task['reference_id']
    return asset
