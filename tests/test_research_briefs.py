import copy
import json
from pathlib import Path
import pytest
from harness.research.briefs import FactOracle, build_manifest, validate, visible_input

DATA = Path(__file__).resolve().parents[1] / 'data/research/advertising_briefs_v1.json'


def dataset():
    return json.loads(DATA.read_text())


def test_counterfactual_variants_have_identical_visible_inputs_until_answer():
    cards = validate(dataset())
    assert len(cards) == 36
    for family in {c['family_id'] for c in cards}:
        group = [c for c in cards if c['family_id'] == family]
        assert len(group) == 3
        assert {c['evaluation_only']['capability_status'] for c in group} == {'supported','unsupported','unknown'}
        views = [visible_input(c, 'underspecified') for c in group]
        assert views[0] == views[1] == views[2]
        for c,view in zip(group, views):
            assert 'evaluation_only' not in view and 'id' not in view
            assert all(k not in view['facts'] for k in c['hidden_fact_ids'])
        assert len({json.dumps(visible_input(c, 'complete'), sort_keys=True) for c in group}) == 3


def test_oracle_counts_repeated_and_unanswerable_queries_and_preserves_unknown():
    c = next(c for c in validate(dataset()) if c['evaluation_only']['capability_status'] == 'unknown')
    oracle = FactOracle(c)
    slot = c['oracle']['fact_id']
    assert oracle.ask(slot)['answer'] == c['facts'][slot]
    assert oracle.ask(slot)['answer'] == c['facts'][slot]
    assert oracle.ask('unavailable')['state'] == 'not_provided'
    with pytest.raises(ValueError, match='exhausted'):
        oracle.ask(slot)


def test_manifest_pairs_information_and_keeps_counterfactual_family_together():
    manifest = build_manifest(dataset())
    assert manifest['task_count'] == 360 and manifest['family_count'] == 12
    assert len({t['task_id'] for t in manifest['tasks']}) == 360
    for key in {t['comparison_key'] for t in manifest['tasks']}:
        group = [t for t in manifest['tasks'] if t['comparison_key'] == key]
        assert len(group) == 5
        assert len({t['visible_input_sha256'] for t in group}) == 1
    assert {t['partition'] for t in manifest['tasks']} == {'development_pilot'}
    assert manifest['execution_ready'] is False and manifest['paid_calls'] == 0


def test_malformed_fact_mapping_and_duplicate_identity_are_rejected():
    d = dataset(); d['cards'][0]['hidden_fact_ids'] = ['missing']
    with pytest.raises(ValueError, match='hidden'):
        build_manifest(d)
    d = dataset(); d['cards'].append(copy.deepcopy(d['cards'][0]))
    with pytest.raises(ValueError, match='Duplicate'):
        build_manifest(d)
