from harness.models.reference_sources.cannes_corporate import parse_listing
import json

import httpx
import pytest

from harness.library import store
from harness.library.browse_groups import group_ids
from harness.models.reference_sources import cannes_corporate as source
from harness.models.reference_download import validate_url
from harness.tools import award_archive
from tools import collect_cannes_corporate as collector


def card(category, host='winners.cannescorporate.com', award=8):
    return f'''<a href="https://{host}/single-entry/123?award_id={award}"><p class="film-category">{category}</p><h4 class="film-title">Title &amp; Story</h4><p><span>CLIENT:</span> Brand</p><img src="https://winners.cannescorporate.com/still.jpg"></a>'''


def test_category_filter_and_award_deduplication():
    records = parse_listing(card('Marketing Communication – B2C') + card('Marketing Communication – B2C', award=9) + card('Documentaries'))
    assert len(records) == 1
    assert records[0]['title'] == 'Title & Story'
    assert records[0]['brand'] == 'Brand'
    assert records[0]['source_url'] == 'https://winners.cannescorporate.com/single-entry/123'
    assert 'not_verified' in records[0]['rights']


def test_foreign_links_are_rejected():
    assert parse_listing(card('Product and Launch Videos', host='example.org')) == []


def test_conflicting_titles_cannot_share_award_evidence():
    with pytest.raises(ValueError, match='identity_conflict'):
        parse_listing(card('Product and Launch Videos') + card('Product and Launch Videos').replace('Title &amp; Story', 'Another Film'))


def listing(ids=(123,), year=2025, category=4):
    header = f'<h1>Winners {year}</h1><select name="main_category"><option value="{category}" selected="selected">Category</option></select>'
    cards = ''.join(card('B23 Product and Launch Videos').replace('/123?', f'/{i}?').replace(
        '<p class="film-category">', '<div class="award-badge">Silver Award</div><p class="film-category">') for i in ids)
    return header + cards


def detail(identity=123, year=2025):
    return f'''<h1>Title &amp; Story</h1><span class="detail-label">CLIENT:</span><span class="detail-value">Brand</span>
        <span>PRODUCER: PERSONAL CREDIT EXCLUDED</span><video><source src="{source.ORIGIN}/external_drive/{year}/{identity}/{identity}_{year}_05_09_18_43_26_comp.mp4"></video>'''


def test_detail_adds_exact_public_video_and_award_evidence_without_credits():
    candidate = source.parse_archive_listing(listing(), 2025, 4)[0]
    result = source.apply_detail(candidate, source.parse_detail(detail(), candidate['source_url']))
    assert result['published'] == '2025'
    assert result['creative_structure']['award_year'] == 2025
    assert result['quality_evidence'][0]['kind'] == 'award_winner'
    assert 'PERSONAL CREDIT' not in json.dumps(result)
    assert validate_url(result['creative_structure']['public_video_url'])
    assert group_ids('B19 Product and Launch Videos') == group_ids('B23 Product and Launch Videos') == ('product',)


def test_finalist_is_not_promoted_to_winner():
    candidate = source.parse_archive_listing(listing().replace('Silver Award', 'Finalist Diploma'), 2025, 4)[0]
    assert candidate['quality_evidence'][0]['kind'] == 'award_finalist'


@pytest.mark.parametrize('html,year,category', [(listing(), 2026, 4), (listing(), 2025, 1),
    (listing().replace(' selected="selected"', ''), 2025, 4)])
def test_wrong_year_or_ignored_category_is_rejected(html, year, category):
    with pytest.raises(ValueError):
        source.parse_archive_listing(html, year, category)


@pytest.mark.parametrize('year,category', [(2022, 4), (2025, 9), (True, 4), (2025, True)])
def test_unsupported_directory_is_rejected_before_network(year, category):
    with pytest.raises(ValueError):
        source.listing_url(year, category)


@pytest.mark.parametrize('change', ['title', 'client', 'year', 'identity', 'ambiguous'])
def test_detail_must_match_listing_identity_and_year(change):
    candidate = source.parse_archive_listing(listing(), 2025, 4)[0]
    html = detail()
    if change == 'title':html = html.replace('Title &amp; Story', 'Another Film')
    if change == 'client':html = html.replace('>Brand<', '>Another Client<')
    if change == 'year':html = detail(year=2024)
    if change == 'identity':html = detail(identity=456)
    if change == 'ambiguous':html += detail().replace('_18_43_26_', '_18_43_27_').split('<video>')[1]
    with pytest.raises(ValueError):
        source.apply_detail(candidate, source.parse_detail(html, candidate['source_url']))


@pytest.mark.parametrize('suffix', ['?token=secret', '#fragment', '/../x.mp4'])
def test_media_query_fragments_and_unsupported_path_are_not_downloadable(suffix):
    url = source.ORIGIN + '/external_drive/2025/123/123_2025_05_09_18_43_26_comp.mp4' + suffix
    with pytest.raises(ValueError):
        validate_url(url)


def test_media_year_and_entry_cannot_disagree_with_filename():
    for url in [source.ORIGIN + '/external_drive/2025/123/456_2025_05_09_18_43_26_comp.mp4',
                source.ORIGIN + '/external_drive/2025/123/123_2024_05_09_18_43_26_comp.mp4',
                'http://winners.cannescorporate.com/external_drive/2025/123/123_2025_05_09_18_43_26_comp.mp4']:
        with pytest.raises(ValueError):validate_url(url)


def test_campaign_variants_keep_official_active_preview_without_merging_films():
    candidate = source.parse_archive_listing(listing(), 2025, 4)[0]
    first = detail().replace('<video>', '<div class="carousel-item active"><video>').replace('</video>', '</video></div>')
    second = '<div class="carousel-item"><video>' + detail().split('<video>')[1].replace('_18_43_26_', '_18_43_27_') + '</div>'
    result = source.apply_detail(candidate, source.parse_detail(first + second, candidate['source_url']))
    variants = result['creative_structure']['public_video_variants']
    assert len(variants) == 2 and [v['default'] for v in variants] == [True, False]
    assert result['creative_structure']['public_video_url'] == variants[0]['url']
    assert '2个视频版本' in result['summary']
    with pytest.raises(ValueError, match='ambiguous'):
        source.parse_detail(first + second.replace('carousel-item', 'carousel-item active'), candidate['source_url'])


def test_official_original_mp4_variants_preserve_campaign_and_default():
    candidate = source.parse_archive_listing(listing(year=2026), 2026, 4)[0]
    first = detail(year=2026).replace('_comp.mp4','_og.mp4').replace(
        '<video>','<div class="carousel-item active"><video>').replace('</video>','</video></div>')
    second = '<div class="carousel-item"><video>' + detail(year=2026).split('<video>')[1].replace(
        '_18_43_26_comp.mp4','_18_43_27_og.mp4') + '</div>'
    result = source.apply_detail(candidate,source.parse_detail(first+second,candidate['source_url']))
    variants = result['creative_structure']['public_video_variants']
    assert len(variants)==2 and [v['default'] for v in variants]==[True,False]
    assert all(validate_url(v['url']).endswith('_og.mp4') for v in variants)
    valid=variants[0]['url']
    for invalid in (valid+'?token=secret',valid+'#fragment',valid.replace('/123/123_','/123/456_'),
                    valid.replace('_og.mp4','_other.mp4'),valid.replace('https:','http:')):
        with pytest.raises(ValueError):validate_url(invalid)


def test_full_category_cursor_reaches_later_product_films_and_preserves_review(tmp_path, monkeypatch):
    monkeypatch.setattr(store, 'ROOT', tmp_path)
    monkeypatch.setenv('AD_LIBRARY_METADATA_OVERLAP', '1')
    monkeypatch.setattr(award_archive.time, 'sleep', lambda _: None)
    requests = []
    def respond(request):
        requests.append(request.url.path)
        if request.url.path == '/robots.txt':return httpx.Response(404)
        if request.url.path == '/':return httpx.Response(200, text=listing(range(101, 114)))
        identity = int(request.url.path.rsplit('/', 1)[1])
        return httpx.Response(200, text=detail(identity))
    original = httpx.Client
    monkeypatch.setattr(award_archive.httpx, 'Client', lambda **kw: original(transport=httpx.MockTransport(respond), **kw))
    first = collector.run(2025, 4)
    assert first['inserted'] == first['attempted'] == 12 and first['next_offset'] == 12
    with store.connection() as db:first_id = db.execute('SELECT id FROM items LIMIT 1').fetchone()[0]
    store.review_item(first_id, 77, 0, 'selected', {'craft': 4}, [], 'My preference')
    second = collector.run(2025, 4)
    assert second['inserted'] == second['attempted'] == 1 and second['year_scan_complete']
    assert len([p for p in requests if p.startswith('/single-entry/')]) == 13
    with store.connection() as db:
        assert db.execute('SELECT COUNT(*) FROM items').fetchone()[0] == 13
        assert tuple(db.execute('SELECT state,note FROM reviews').fetchone()) == ('selected', 'My preference')
        assert all(json.loads(r[0])['training_eligible'] is False for r in db.execute('SELECT data FROM items'))
        assert db.execute('SELECT COUNT(*) FROM assets').fetchone()[0] == 0


def test_cli_requires_explicit_year_and_category_for_multi_batch():
    with pytest.raises(SystemExit):collector.main(['--batches', '2'])


def test_verified_category_without_product_entries_completes_without_detail_requests(tmp_path, monkeypatch):
    monkeypatch.setattr(store, 'ROOT', tmp_path)
    monkeypatch.setenv('AD_LIBRARY_METADATA_OVERLAP', '1')
    requests = []
    def respond(request):
        requests.append(request.url.path)
        if request.url.path == '/robots.txt':return httpx.Response(404)
        assert request.url.path == '/'
        return httpx.Response(200, text=listing(year=2023).replace('B23 Product and Launch Videos', 'B18 Brand Image Videos'))
    original = httpx.Client
    monkeypatch.setattr(award_archive.httpx, 'Client', lambda **kw: original(transport=httpx.MockTransport(respond), **kw))
    result = collector.run(2023, 4, batches=2)
    assert result['state'] == 'completed' and result['stop_reason'] == 'year_scan_complete'
    assert result['batches'] == 1 and result['inserted'] == 0
    assert requests == ['/robots.txt', '/']
    with store.connection() as db:
        assert db.execute('SELECT offset FROM archive_cursors').fetchone()[0] == 0


def test_missing_directory_cards_is_not_confirmed_empty():
    with pytest.raises(ValueError, match='listing_missing'):
        source.parse_archive_listing(listing(ids=(), year=2023), 2023, 4)
