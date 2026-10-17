"""Private message-time configuration snapshots, separate from model conversation and trajectories."""
from harness.models.video_catalog import model_spec


def record_message_context(project):
    index = len(project.get('messages', [])) - 1
    if index < 0 or project['messages'][index].get('role') != 'user':
        return
    contexts = project.setdefault('message_contexts', {})
    if str(index) in contexts:
        return
    try:
        model_label = model_spec(project['provider'], project.get('model'))['label']
    except (KeyError, ValueError):
        model_label = project.get('model', '')
    skill = project.get('skill') or {}
    inputs = project.get('video_inputs')
    reference = project.get('reference') or {}
    references = []
    nodes = project.get('canvas', {}).get('nodes', [])
    assets = project.get('canvas_assets', {})
    pending = False
    if inputs is not None:
        mode = inputs.get('mode', 'text')
        selected = inputs.get('references', []) if mode != 'text' else []
        pending = bool(inputs.get('model') != project.get('model') or
                       selected and project.get('video_inputs_product') != project.get('brief', {}).get('product', ''))
        for item in selected[:7]:
            aid = item.get('asset')
            if assets.get(aid, {}).get('kind') != 'image':
                pending = True
                continue
            label = next((n.get('label') for n in nodes if n.get('asset') == aid and n.get('label')), '')
            references.append({'asset': aid, 'label': str(label or '参考图片')[:80],
                               'role': item.get('role', 'reference')})
    elif reference.get('id'):
        mode = 'first_frame'
        pending = bool(project.get('reference_needs_review') or
                       project.get('reference_product') != project.get('brief', {}).get('product', ''))
        # Legacy uploads are immutable copies; keep their identity, not the latest reference.
        references.append({'reference_id': reference['id'], 'label': '商品参考图', 'role': 'product'})
    else:
        mode = 'text'
    snapshot = {
        'schema_version': 1, 'revision': project.get('revision', 0),
        'model': {'id': project.get('model', ''), 'label': model_label},
        'skill': {'id': project.get('skill_id', ''), 'title': project.get('skill_title', ''),
                  'version': skill.get('version', 1)},
        'approval_mode': project.get('approval_mode', 'manual'),
        'aspect': project.get('aspect'), 'duration': project.get('duration'),
        'video_input_mode': mode, 'references': references, 'needs_review': pending,
    }
    contexts[str(index)] = snapshot
