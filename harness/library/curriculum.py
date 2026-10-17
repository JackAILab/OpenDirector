"""Turn validated reference mechanisms into a reusable director curriculum."""
CURRICULUM_SCHEMA = 'visualagent.ad-agent-curriculum.v1'


def _count(summary, key):
    summary = summary or {}
    # The runtime playbook exposes ``mechanism_coverage`` while the private
    # aggregate report uses ``mechanism_taxonomy_counts``. Accept both so a
    # fresh curriculum cannot silently lose evidence counts when materialized
    # directly from the aggregate report.
    coverage = summary.get('mechanism_coverage') or summary.get('mechanism_taxonomy_counts') or {}
    value = coverage.get(key, 0)
    return value if type(value) is int and value >= 0 else 0


def build_curriculum(summary):
    """Build bounded stage guidance without copying any reference content."""
    if not isinstance(summary, dict):
        raise ValueError('Playbook summary is required')
    total = summary.get('analysis_count', 0)
    if type(total) is not int or total < 0:
        raise ValueError('Invalid analysis count')
    stages = [
        {'id': 'fact_boundary', 'order': 1, 'goal': '确认商品事实、限制和可证明的单一主张',
         'agent_action': '先追问事实与限制，再允许写分镜', 'evidence': _count(summary, 'truth_constraints'),
         'pass': ['claim_is_single', 'facts_are_source_bound', 'unsupported_benefit_is_flagged']},
        {'id': 'observable_proof', 'order': 2, 'goal': '把主张转成观众能看见的任务和结果变化',
         'agent_action': '每个节拍写动作、结果和因果，不只写氛围', 'evidence': _count(summary, 'visible_proof'),
         'pass': ['task_is_visible', 'result_has_before_after', 'product_causes_action']},
        {'id': 'controlled_conflict', 'order': 3, 'goal': '只保留一条压力、对照或反转',
         'agent_action': '删掉第二卖点和无关支线', 'evidence': _count(summary, 'contrast_or_reversal'),
         'pass': ['one_conflict', 'reversal_is_explainable', 'no_reference_copying']},
        {'id': 'reaction_attribution', 'order': 4, 'goal': '用人物或环境反应收束，再完成品牌归因',
         'agent_action': '结果之后安排反应、商品识别和可证实行动',
         'evidence': _count(summary, 'human_reaction') + _count(summary, 'brand_attribution'),
         'pass': ['reaction_follows_result', 'product_is_identified', 'cta_is_fact_safe']},
        {'id': 'native_sound', 'order': 5, 'goal': '让声音承担节奏、因果或记忆点',
         'agent_action': '为每段分别写旁白、音乐、环境声和动作音，并标注审阅状态',
         'evidence': _count(summary, 'audio_dependency'),
         'pass': ['audio_prompt_exists', 'audio_is_not_inferred_from_stills', 'semantic_audio_review_pending_until_heard']},
        {'id': 'release_gates', 'order': 6, 'goal': '把技术、语义、人工和授权门禁分开',
         'agent_action': '所有证据齐备前保持不可训练', 'evidence': 0,
         'pass': ['technical_qa', 'independent_review', 'privacy_rights_sanitization', 'human_approval', 'explicit_consent']},
    ]
    for stage in stages:
        if stage['evidence'] > total:
            stage['evidence'] = total
    return {
        'schema': CURRICULUM_SCHEMA,
        'source_scope': 'bounded mechanism coverage from validated sampled-frame analyses',
        'analysis_count': total,
        'stages': stages,
        'training_policy': {'training_eligible': False, 'requires_all_release_gates': True},
        'prohibitions': ['copy reference brand, person, wording, shot sequence, product or audio',
                         'treat heuristic coverage as a quality score',
                         'infer sound meaning or full motion from sampled frames'],
    }
