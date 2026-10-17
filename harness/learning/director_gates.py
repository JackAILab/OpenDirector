"""Evidence gates derived from the reference-ad curriculum.

This is a bounded contract check, not an aesthetic, conversion, or training
approval. It deliberately reports missing evidence instead of inventing it.
"""
import re

SCHEMA = 'visualagent.director-stage-gates.v1'


def _text(value):
    return str(value or '').lower()


def _contains(text, terms):
    return any(term in text for term in terms)


def evaluate_director_gates(plan):
    if not isinstance(plan, dict):
        raise ValueError('Director plan is required')
    brief = plan.get('brief') or {}
    shots = [shot for shot in (plan.get('shots') or []) if isinstance(shot, dict)]
    brief_text = ' '.join(_text(brief.get(key)) for key in ('message', 'claim', 'product', 'audience'))
    shot_text = [' '.join(_text(shot.get(key)) for key in ('prompt', 'rationale', 'caption')) for shot in shots]
    audio_text = [_text(shot.get('audio_prompt')) for shot in shots]
    all_visual = ' '.join(shot_text)

    stages = []
    stages.append({
        'id': 'fact_boundary',
        'evidence': bool(_text(brief.get('message')).strip()) and bool(plan.get('assumptions') is not None),
        'observed': ['brief.message', 'assumptions'] if _text(brief.get('message')).strip() and plan.get('assumptions') is not None else [],
        'missing': [] if _text(brief.get('message')).strip() and plan.get('assumptions') is not None else ['brief.message_or_assumptions'],
    })

    proof = _contains(all_visual, ('show', 'demonstrat', 'reveal', 'result', 'action', '展示', '证明', '结果', '动作'))
    stages.append({
        'id': 'observable_proof', 'evidence': proof,
        'observed': ['shot.action_or_result_language'] if proof else [],
        'missing': [] if proof else ['shot.action_or_result_language'],
    })

    conflict = bool(plan.get('strategy_selection')) or _contains(all_visual, ('contrast', 'reversal', 'before', 'after', '对比', '反转', '之前', '之后'))
    stages.append({
        'id': 'controlled_conflict', 'evidence': conflict,
        'observed': ['strategy_selection_or_contrast_language'] if conflict else [],
        'missing': [] if conflict else ['strategy_selection_or_contrast_language'],
    })

    attribution = bool(_text(brief.get('product')).strip()) and _contains(all_visual, ('product', 'brand', 'logo', '商品', '品牌', '产品'))
    stages.append({
        'id': 'reaction_attribution', 'evidence': attribution,
        'observed': ['brief.product', 'product_attribution_language'] if attribution else [],
        'missing': [] if attribution else ['brief.product_or_attribution_language'],
    })

    native_audio = bool(audio_text) and all(bool(item.strip()) for item in audio_text) and _contains(' '.join(audio_text), ('music', 'sound', 'audio', 'voice', '音乐', '声音', '音效', '旁白'))
    stages.append({
        'id': 'native_sound', 'evidence': native_audio,
        'observed': ['per_shot.audio_prompt'] if native_audio else [],
        'missing': [] if native_audio else ['per_shot.audio_prompt_with_sound_detail'],
    })

    stages.append({
        'id': 'release_gates', 'evidence': False,
        'observed': [],
        'missing': ['technical_qa', 'independent_review', 'privacy_rights_sanitization', 'human_approval', 'explicit_consent'],
    })
    return {
        'schema': SCHEMA,
        'stages': stages,
        'passed_stage_count': sum(1 for stage in stages if stage['evidence']),
        'training_eligible': False,
        'quality_score': None,
        'limitations': ['heuristics are evidence presence checks, not aesthetic or conversion labels',
                        'release gates remain closed until independent review and consent'],
    }
