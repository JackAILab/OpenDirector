from copy import deepcopy

import pytest

from harness.tools.creative_edit_ripple import move_many, ripple_delete, ripple_delete_many


def document():
    return {
        'clips': [
            {'source': 'a', 'start': 0, 'end': 3, 'transition': {'kind': 'cut', 'duration': 0}},
            {'source': 'b', 'start': 0, 'end': 3, 'transition': {'kind': 'cut', 'duration': 0}},
            {'source': 'c', 'start': 0, 'end': 3, 'transition': {'kind': 'cut', 'duration': 0}},
        ],
        'captions': [
            {'start': 0.4, 'end': 2.0, 'text': '前段', 'track': 0},
            {'start': 3.4, 'end': 4.4, 'text': '删掉', 'track': 0},
            {'start': 6.5, 'end': 8.5, 'text': '后段', 'track': 0,
             'words': [
                 {'text': '后', 'start': 0.0, 'end': 0.7},
                 {'text': '段', 'start': 0.7, 'end': 2.0},
             ]},
        ],
        'rhythm': [{'start': 6.2, 'end': 8.2, 'label': '收束'}],
        'audio': [{'source': 'music', 'at': 0, 'start': 0, 'end': 8,
                   'gain': 0.5, 'fade_in': 0.2, 'fade_out': 0.3}],
        'volume': 1,
        'duration': 9,
        'training_eligible': False,
    }


def test_ripple_delete_retimes_all_tracks_and_keeps_source_immutable():
    original = document()
    result = ripple_delete(original, 1)
    spec, receipt = result['spec'], result['receipt']

    assert original == document()
    assert [clip['source'] for clip in spec['clips']] == ['a', 'c']
    assert spec['duration'] == 6
    assert receipt['start'] == 3
    assert receipt['end'] == 6
    assert receipt['removed_seconds'] == 3
    assert receipt['duration_after'] == 6
    assert spec['captions'][0]['start'] == 0.4
    assert spec['captions'][1]['start'] == 3.5
    assert spec['captions'][1]['end'] == 5.5
    assert [word['start'] for word in spec['captions'][1]['words']] == [0.0, 0.7]
    assert spec['rhythm'][0]['start'] == 3.2
    assert spec['rhythm'][0]['end'] == 5.2
    assert len(spec['audio']) == 2
    assert [item['at'] for item in spec['audio']] == [0, 3]
    assert [item['end'] - item['start'] for item in spec['audio']] == [3, 2]
    assert receipt['split_audio'] == 1
    assert receipt['removed_captions'] == 1
    assert receipt['training_eligible'] is False


def test_ripple_delete_cuts_transition_and_rejects_invalid_selection():
    source = document()
    source['clips'][0]['transition'] = {'kind': 'dissolve', 'duration': 0.5}
    source['clips'][1]['transition'] = {'kind': 'dissolve', 'duration': 0.5}
    output = ripple_delete(source, 1)
    assert output['spec']['clips'][0]['transition'] == {'kind': 'cut', 'duration': 0}
    assert output['receipt']['cleared_transitions'] == 2

    with pytest.raises(ValueError, match='至少保留一个画面'):
        ripple_delete({'clips': []}, 0)
    with pytest.raises(ValueError, match='至少保留一个画面'):
        ripple_delete({'clips': document()['clips'][:1]}, 0)


def test_ripple_delete_many_uses_original_indices_and_leaves_one_clip():
    source = document()
    result = ripple_delete_many(source, [0, 2])
    spec, receipt = result['spec'], result['receipt']
    assert [clip['source'] for clip in spec['clips']] == ['b']
    assert spec['duration'] == 3
    assert receipt['removed_seconds'] == 6
    assert receipt['duration_after'] == 3
    assert receipt['training_eligible'] is False
    assert source == document()
    with pytest.raises(ValueError, match='至少保留一个画面'):
        ripple_delete_many(source, [0, 1, 2])


def test_move_many_preserves_block_order_and_rejects_non_contiguous_selection():
    clips = document()['clips']
    earlier = move_many(clips, [1, 2], -1)
    assert [clip['source'] for clip in earlier['clips']] == ['b', 'c', 'a']
    assert earlier['indexes'] == [0, 1]
    later = move_many(clips, [0, 1], 1)
    assert [clip['source'] for clip in later['clips']] == ['c', 'a', 'b']
    assert later['indexes'] == [1, 2]
    with pytest.raises(ValueError, match='连续画面'):
        move_many(clips, [0, 2], 1)
