import json
from pathlib import Path
from harness.research.briefs import digest,visible_input
from tools.prepare_goal_dependent_briefs import build


def test_request_expansion_preserves_stipulated_worlds_and_does_not_modify_parent():
    base=json.loads(Path('data/research/advertising_briefs_v1.json').read_text());before=digest(base)
    expanded=build(base);parents={c['id']:c for c in base['cards']}
    assert digest(base)==before and len(expanded['cards'])==36
    assert len({c['family_id'] for c in expanded['cards']})==12
    for child in expanded['cards']:
        parent=parents[child['evaluation_only']['parent_card_id']]
        assert child['facts']==parent['facts'] and child['oracle']==parent['oracle']
        assert child['id']!=parent['id'] and child['brief']!=parent['brief']
        visible=visible_input(child,'underspecified')
        assert not set(child['hidden_fact_ids']) & set(visible['facts'])
        assert 'evaluation_only' not in visible and 'oracle' not in visible
