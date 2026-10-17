"""Materialize safe, explainable mechanism coverage for the director UI."""

SCHEMA = 'visualagent.ad-mechanism-report.v1'

DIMENSIONS = (
    ('visible_proof', '可观察证明', '把主张变成观众能看见的任务和结果变化', '要求每个节拍写动作、结果和因果'),
    ('attention_task', '注意力任务', '让观众寻找、辨认或等待一个关键结果', '先说明观众要关注什么，再安排揭示'),
    ('contrast_or_reversal', '对照或反转', '用一条可读冲突重新解释前面的画面', '只保留一条冲突，删掉第二卖点'),
    ('human_reaction', '人物反应', '让结果通过人物或环境反应变成情绪', '结果之后补反应，再完成归因'),
    ('brand_attribution', '品牌归因', '把已理解的结果明确归给商品或品牌', '在理解结果之后安排事实安全的 CTA'),
    ('audio_dependency', '声音依赖', '让音乐、环境声、动作音或旁白承担节奏与因果', '逐段设计声音，但未听审前保持待确认'),
    ('truth_constraints', '真实性约束', '把限制、条件和可证明边界带入创作', '先追问事实和限制，拒绝补造功效'),
)


def build_mechanism_report(summary):
    if not isinstance(summary, dict):
        raise ValueError('Aggregate summary is required')
    total = summary.get('analysis_count')
    if type(total) is not int or total <= 0:
        raise ValueError('Invalid analysis count')
    counts = summary.get('mechanism_taxonomy_counts') or summary.get('mechanism_coverage') or {}
    if not isinstance(counts, dict):
        raise ValueError('Mechanism counts are required')
    dimensions = []
    for key, label, meaning, action in DIMENSIONS:
        value = counts.get(key, 0)
        if type(value) is not int or value < 0 or value > total:
            raise ValueError('Invalid mechanism count')
        dimensions.append({'id': key, 'label': label, 'count': value,
                           'coverage_rate': round(value / total, 4),
                           'why_it_matters': meaning, 'agent_action': action})
    return {'schema': SCHEMA, 'analysis_count': total, 'dimensions': dimensions,
            'method': 'bounded taxonomy coverage; not a quality or conversion score',
            'evidence_scope': 'timecoded sampled frames and source metadata',
            'limitations': ['audio semantics and full motion may remain pending',
                            'coverage does not prove causal effectiveness',
                            'reference mechanisms must not copy brand, people, wording, shots or audio'],
            'training_eligible': False}
