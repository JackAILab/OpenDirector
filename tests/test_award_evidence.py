import pytest

from harness.library import store
from harness.models.reference_sources.award_evidence import award_evidence_kind
from harness.tools.award_evidence import corrected_evidence, repair_award_evidence


@pytest.mark.parametrize('level,kind', [
    ('Finalist', 'award_finalist'), ('Gold Finalist', 'award_finalist'),
    ('Shortlisted', 'award_shortlist'), ('Short List', 'award_shortlist'),
    ('Grand Prix', 'award_winner'), ('Silver', 'award_winner'),
    ('Gold Winner', 'award_winner'), ('Winner', 'award_winner'),
    ('', 'award_listing'), ('Special mention', 'award_listing'),
])
def test_source_levels_never_promote_finalists_or_unknowns(level, kind):
    assert award_evidence_kind(level) == kind


def test_repair_preserves_preferences_and_is_idempotent(tmp_path, monkeypatch):
    monkeypatch.setattr(store, 'ROOT', tmp_path)
    # Ingestion sorts query arguments while evidence retains the source's
    # original order; they still identify the same official entry.
    url = 'https://awards.ciclopefestival.com/?project_year=2024&e=1'
    data = {'source_url': url, 'title': 'Reference', 'ad_type': 'CICLOPE · Production',
            'source_name': 'CICLOPE 官方获奖片', 'summary': '官方获奖条目',
            'creative_structure': {'award': 'Finalist'},
            'quality_evidence': [{'kind': 'award_winner', 'source_url': url, 'text': 'Finalist'}]}
    identity, _ = store.ingest(data)
    store.review_item(identity, 7, 0, 'selected', {'craft': 4}, ['visual'], 'My own preference')
    initial = store.get_item(identity, 7)
    assert repair_award_evidence()['would_correct'] == 1
    assert store.get_item(identity, 7)['revision'] == initial['revision']
    assert repair_award_evidence(apply=True)['corrected'] == 1
    current = store.get_item(identity, 7)
    assert current['quality_evidence'][0]['kind'] == 'award_finalist'
    assert current['review'] == initial['review']
    assert current['revision'] == initial['revision'] + 1
    assert current['training_eligible'] is False
    assert repair_award_evidence(apply=True)['corrected'] == 0
    assert corrected_evidence('https://example.org', data) == data


def test_different_or_signed_source_evidence_is_not_relabelled():
    url='https://awards.ciclopefestival.com/?e=1&project_year=2024'
    data={'creative_structure':{'award':'Finalist'},'quality_evidence':[
        {'kind':'award_winner','source_url':'https://awards.ciclopefestival.com/?e=2&project_year=2024'},
        {'kind':'award_winner','source_url':url+'&token=private'},
    ]}
    assert all(e['kind']=='award_winner' for e in corrected_evidence(url,data)['quality_evidence'])


def test_unknown_source_level_removes_old_winner_fallback():
    url = 'https://www.cresta-awards.com/?e=2'
    data = {'creative_structure': {'award': ''},
            'quality_evidence': [{'kind': 'award_winner', 'source_url': url,
                                  'text': 'Cresta · winner · Craft'}]}
    result = corrected_evidence(url, data)
    assert result['quality_evidence'][0]['kind'] == 'award_listing'
    assert 'winner' not in result['quality_evidence'][0]['text']
    assert data['quality_evidence'][0]['kind'] == 'award_winner'
