from harness.library.curriculum import build_curriculum


def test_curriculum_orders_mechanisms_and_keeps_release_closed():
    curriculum = build_curriculum({'analysis_count': 10, 'mechanism_coverage': {
        'truth_constraints': 8, 'visible_proof': 9, 'contrast_or_reversal': 7,
        'human_reaction': 4, 'brand_attribution': 3, 'audio_dependency': 10}})
    assert curriculum['schema'] == 'visualagent.ad-agent-curriculum.v1'
    assert [stage['order'] for stage in curriculum['stages']] == [1, 2, 3, 4, 5, 6]
    assert curriculum['stages'][1]['evidence'] == 9
    assert curriculum['training_policy']['training_eligible'] is False
    assert 'copy reference brand' in curriculum['prohibitions'][0]


def test_curriculum_fails_closed_on_bad_summary():
    try:
        build_curriculum({'analysis_count': -1})
    except ValueError:
        pass
    else:
        raise AssertionError('invalid summary should fail closed')


def test_curriculum_accepts_private_aggregate_taxonomy_counts():
    curriculum = build_curriculum({'analysis_count': 12, 'mechanism_taxonomy_counts': {
        'truth_constraints': 11, 'visible_proof': 10,
        'contrast_or_reversal': 9, 'human_reaction': 8,
        'brand_attribution': 7, 'audio_dependency': 12}})
    assert [stage['evidence'] for stage in curriculum['stages'][:5]] == [11, 10, 9, 12, 12]
