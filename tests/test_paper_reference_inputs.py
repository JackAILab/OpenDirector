import pytest
from tools.prepare_paper_reference_inputs import reference_input
from tools.prepare_paper_reference_review import digest


def fixture():
    analysis = {'media_sha256': 'media', 'beats': [{'start': 0, 'end': 5,
        'observation': 'A turns around.', 'purpose': 'Potential surprise.', 'frames': [0]}],
        'principle': 'Pressure test', 'audio_semantics_reviewed': False,
        'full_motion_reviewed': False, 'source_url': 'excluded', 'human_review': 'approved'}
    return {'review_id': 'R008', 'sha256': 'media', 'analysis_sha256': digest(analysis)}, analysis


def test_separates_observation_from_interpretation_without_promoting_review():
    row, analysis = fixture()
    result = reference_input(row, analysis)
    assert result['evidence']['events'][0]['visual_observation'] == 'A turns around.'
    assert 'purpose' not in result['evidence']['events'][0]
    assert result['interpretation']['event_functions'][0]['narrative_function'] == 'Potential surprise.'
    assert result['evidence']['independent_review'] == 'pending'
    assert result['training_eligible'] is False
    assert 'source_url' not in result


def test_changed_analysis_and_media_are_rejected():
    row, analysis = fixture()
    analysis['principle'] = 'Changed'
    with pytest.raises(ValueError, match='frozen_analysis_mismatch'):
        reference_input(row, analysis)
    row['analysis_sha256'] = digest(analysis)
    row['sha256'] = 'other-media'
    with pytest.raises(ValueError, match='frozen_media_mismatch'):
        reference_input(row, analysis)
