import json
from pathlib import Path
import pytest
from tools.prepare_relation_candidates import active_pairs


def test_screened_candidates_exclude_held_pairs():
    d=json.loads(Path('data/research/relation_transfer_candidates_v2.json').read_text())
    assert [p['family_id'] for p in active_pairs(d)]==['glass']


def test_unknown_or_all_held_fails_closed():
    with pytest.raises(ValueError):active_pairs({'schema':'unknown'})
    d={'schema':'visualagent.relation-candidates.v2','pairs':[{'screening_status':'approved'}]}
    with pytest.raises(ValueError):active_pairs(d)
    d['pairs'][0]['screening_status']='hold_source_relation_unestablished'
    with pytest.raises(ValueError):active_pairs(d)
