import pytest
from unittest.mock import patch

from harness.models.reference_sources import webby


def listing(items):
    return {'Success': True, 'Data': items}


def item(item_id=336154, title="Winning Isn't Comfortable", awards=None, winner=True):
    return {
        'ItemId': item_id,
        'Year': 2025,
        'MediaTypeId': 1,
        'Title': title,
        'Organization': 'Wieden+Kennedy',
        'Awards': awards or ['Webby Winner'],
        'Categories': [{'CategoryId': 46, 'Category': 'Best Video Campaign', 'IsWinner': winner}],
    }


def detail(item_id=336154, urls='https://www.youtube.com/watch?v=abc|https://example.com/private'):
    return {'Success': True, 'Data': {'PieceID': item_id, 'Url': urls}}


def test_parse_listing_keeps_only_winners_and_is_bounded():
    rows = [item(i, f'Case {i}', ['Nominee'], False) for i in range(1, 4)]
    rows += [item(10, 'Winner A'), item(11, 'Winner B'), item(12, 'Winner C')]
    records = webby.parse_listing(listing(rows), 2025, 1)
    assert [r['item_id'] for r in records] == [10, 11]
    assert records[0]['source_url'].endswith('/10/winner-a')


def test_enrich_keeps_only_permanent_public_video_hosts():
    record = webby.parse_listing(listing([item()]), 2025)[0]
    enriched = webby.enrich(record, detail(urls='https://www.youtube.com/watch?v=abc12345678|https://example.com/private'))
    assert enriched['embed_url'] == 'https://www.youtube.com/watch?v=abc12345678'
    assert enriched['creative_structure']['public_video_links'] == ['https://www.youtube.com/watch?v=abc12345678']
    assert enriched['media_role'] == 'work_or_case_film_unverified'
    assert enriched['quality_evidence'][0]['kind'] == 'award_winner'


def test_invalid_payload_or_year_does_not_fabricate_records():
    with pytest.raises(ValueError, match='invalid_webby_year'):
        webby.listing_payload(2022)
    with pytest.raises(ValueError, match='source_layout_changed'):
        webby.parse_listing({'Success': False, 'Data': []}, 2025)
    record = webby.parse_listing(listing([item()]), 2025)[0]
    with pytest.raises(ValueError, match='source_layout_changed'):
        webby.enrich(record, detail(999))


def test_scheduled_collector_rotates_supported_years():
    from tools import collect_webby
    with patch.object(collect_webby.time, 'time', return_value=0):
        assert collect_webby._year(None) == 2025
    with patch.object(collect_webby.time, 'time', return_value=3 * 3600):
        assert collect_webby._year(None) == 2024
    with pytest.raises(ValueError, match='invalid_webby_year'):
        collect_webby._year(2022)
