"""Build bounded, privacy-safe review packets for sampled ad references."""
import json

PACKET_SCHEMA = 'visualagent.ad-media-review-packets.v1'

AUDIO_CHECKS = (
    'audio_stream_presence',
    'speech_language_and_transcript',
    'music_structure',
    'sound_effect_sync',
    'brand_sound_or_silence',
)
MOTION_CHECKS = (
    'shot_boundary_and_timing',
    'product_identity_continuity',
    'causal_motion_readability',
    'camera_motion_and_occlusion',
    'end_card_or_brand_transition',
)


def build_packets(queue, limit=200, only_semantic=False):
    """Convert the operator queue into review tasks without analysis text or paths."""
    if not isinstance(queue, dict) or queue.get('schema') != 'visualagent.ad-analysis-review-queue.v1':
        raise ValueError('Invalid review queue')
    if type(limit) is not int or not 1 <= limit <= 2000:
        raise ValueError('Invalid packet limit')
    items = []
    source_items=queue.get('items', [])
    if only_semantic:
        source_items=[row for row in source_items if isinstance(row,dict) and 'analysis' not in (row.get('missing') or [])]
    for row in source_items[:limit]:
        if not isinstance(row, dict) or not isinstance(row.get('item'), str):
            continue
        missing = row.get('missing', [])
        if not isinstance(missing, list):
            continue
        packet = {
            'item': row['item'],
            'media_sha256': row.get('media_sha256'),
            'analysis_version': row.get('analysis_version'),
            'duration_seconds': row.get('duration'),
            'audio_present': row.get('audio_present'),
            'missing': [x for x in missing if x in ('analysis', 'audio_semantics', 'full_motion')],
            'audio_review': {'status': 'pending', 'checks': list(AUDIO_CHECKS)},
            'motion_review': {'status': 'pending', 'checks': list(MOTION_CHECKS)},
            'training_eligible': False,
        }
        if 'analysis' in packet['missing']:
            packet['audio_review']['status'] = 'blocked_by_missing_analysis'
            packet['motion_review']['status'] = 'blocked_by_missing_analysis'
        items.append(packet)
    return {
        'schema': PACKET_SCHEMA,
        'source_schema': queue['schema'],
        'state': queue.get('state', 'unknown'),
        'total_pending': queue.get('total_pending'),
        'analysis_pending': queue.get('analysis_pending'),
        'semantic_review_pending': queue.get('semantic_review_pending'),
        'count': len(items),
        'only_semantic': bool(only_semantic),
        'items': items,
        'policy': 'technical probes and semantic reviews remain separate; completing this packet never grants training eligibility',
        'training_eligible': False,
    }


def dumps(packet):
    return json.dumps(packet, ensure_ascii=False, indent=2) + '\n'
