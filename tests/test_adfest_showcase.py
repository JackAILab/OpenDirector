import fcntl
import json

import httpx
import pytest

from harness.library import store
from harness.models.reference_download import validate_url
from harness.models.reference_sources import adfest_showcase as source
from harness.tools import adfest_showcase as action
from tools import collect_adfest_showcase as runner, cache_ad_reference_media


def listing(page=1, identities=None, category=11, pages=2):
    identities = identities or ([1, 2] if page == 1 else [3, 4])
    prefix = source.CATEGORIES[category][1]
    cards = []
    for identity in identities:
        code = f'{prefix}01_{identity:03}'
        cards.append(f'''<div class="showcase_item">
          <div class="showcase_item_award"><img alt="{'GRANDE' if identity == 1 else 'FINALIST'}"></div>
          <div class="showcase_item_thumb"><a class="toDetail" href="{source.DETAIL_PATH}?id={identity}&amp;code={code}">
          <img src="{source.MEDIA_BASE}{code}_DI01T.jpg"/></a></div>
          <div class="showcase_item_content"><span class="winners_font02">Film &amp; Story {identity}</span>
          <div class="showcase_item_meta"><div>Brand</div><div>Agency</div></div></div></div>''')
    pagination = ''.join(f'<a class="showcase_page_number {"winners_font02" if n==page else "page_2"}" href="{source.listing_url(category,n)}">{n}</a>' for n in range(1, pages+1))
    return f'''<h1>ADFEST 2027</h1><script>var worksBase = '{source.MEDIA_BASE}';</script>
       <select class="mobile_right_menu"><option value="{category}" selected>FILM LOTUS</option></select>
       <select class="mobile_ws_menu"><option value="all" selected>ALL</option></select>
       {''.join(cards)}{pagination}'''


def detail(identity=1, files=None):
    return json.dumps({'code': 0, 'data': [
        {'keyword': 'TITLE', 'content': f'Film &amp; Story {identity}'},
        {'keyword': 'BRAND', 'content': 'Brand'},
        {'keyword': 'SUB CATEGORY', 'content': 'VIRAL FILM'},
        {'keyword': 'DIRECTOR', 'content': 'PRIVATE CREDIT MUST NOT PERSIST'},
        {'keyword': 'ENGLISH SYNOPSIS', 'content': 'LONG SOURCE PROSE MUST NOT PERSIST'},
        {'keyword': 'URL 1', 'content': 'https://example.org/?token=DO_NOT_STORE'},
    ], 'files2': files if files is not None else [{'name': f'F01_{identity:03}.mp4', 'type': 'mp4'}]})


def test_source_edition_beats_masthead_and_preserves_award_levels_and_privacy():
    parsed = source.parse_listing(listing(), 11)
    assert parsed['page'] == 1 and parsed['pages'] == 2
    assert [r['quality_evidence'][0]['kind'] for r in parsed['records']] == ['award_winner', 'award_finalist']
    record = source.apply_detail(parsed['records'][0], detail())
    assert record['title'] == 'Film & Story 1'
    assert record['published'] == '2026'
    assert record['source_url'].endswith('showcase.html?id=1')
    assert record['creative_structure']['public_video_url'] == source.MEDIA_BASE + 'F01_001.mp4'
    assert record['media_role'] == 'work_or_case_film_unverified'
    encoded = json.dumps(record)
    for private in ('PRIVATE CREDIT', 'LONG SOURCE PROSE', 'DO_NOT_STORE', 'detail_url'):
        assert private not in encoded
    assert 'audio' not in record


@pytest.mark.parametrize('mutation,error', [
    (lambda s: s.replace('works2026', 'works2027'), 'source_edition_changed'),
    (lambda s: s.replace('value="11" selected', 'value="10" selected'), 'source_category_mismatch'),
    (lambda s: s.replace('page_number winners_font02', 'page_number page_2'), 'source_page_mismatch'),
    (lambda s: s.replace('F01_001_DI01T.jpg', 'F01_999_DI01T.jpg'), 'source_edition_changed'),
])
def test_changed_edition_category_pagination_or_identity_stops(mutation, error):
    with pytest.raises(ValueError, match=error):
        source.parse_listing(mutation(listing()), 11)


def test_pdf_only_entry_is_skipped_and_multiple_public_versions_are_kept():
    parsed = source.parse_listing(listing().replace('F01_001_DI01T.jpg', 'pdfT.jpg'), 11)
    row = parsed['records'][0]
    assert row['thumbnail_url'] == ''
    assert source.apply_detail(row, detail(files=[{'name': 'F01_001.pdf', 'type': 'pdf'}])) is None
    record = source.apply_detail(row, detail(files=[{'name': 'F01_001.mp4', 'type': 'mp4'},
        {'name': 'F01_001_AV02.mp4', 'type': 'mp4'}]))
    assert record['creative_structure']['public_video_count'] == 2
    assert record['creative_structure']['preview_selection'] == 'first_published_public_video'


@pytest.mark.parametrize('bad_detail', [detail(2), detail(files=[{'name': 'F01_002.mp4', 'type': 'mp4'}]),
    detail(files=[{'name': '../private.mp4?token=hidden', 'type': 'mp4'}])])
def test_wrong_work_cannot_supply_a_video(bad_detail):
    with pytest.raises(ValueError, match='identity_mismatch'):
        source.apply_detail(source.parse_listing(listing(), 11)['records'][0], bad_detail)


def test_parenthesis_spacing_can_differ_but_subtitle_words_must_match():
    record = source.parse_listing(listing(), 11)['records'][0]
    record['title'] += ' (Part A)'
    raw = json.loads(detail())
    raw['data'][0]['content'] += '(Part A)'
    result = source.apply_detail(record, json.dumps(raw))
    assert result['title'] == 'Film & Story 1 (Part A)'
    raw['data'][0]['content'] = raw['data'][0]['content'].replace('Part A', 'Part B')
    with pytest.raises(ValueError, match='identity_mismatch'):
        source.apply_detail(record, json.dumps(raw))


@pytest.mark.parametrize('suffix', ['?token=hidden', '#fragment', '/../private.mp4'])
def test_media_url_cannot_include_credentials_or_extra_path(suffix):
    with pytest.raises(ValueError, match='unsupported_media_locator'):
        validate_url(source.MEDIA_BASE + 'F01_001.mp4' + suffix)


@pytest.mark.parametrize('url', [
    'http://adfest.d-energy.cn/adfest/works2026/F01_001.mp4',
    'https://adfest.d-energy.cn.evil.test/adfest/works2026/F01_001.mp4',
    'https://name@adfest.d-energy.cn/adfest/works2026/F01_001.mp4',
    'https://adfest.d-energy.cn/adfest/works2027/F01_001.mp4',
    'https://adfest.d-energy.cn/admin/F01_001.mp4',
])
def test_media_allowlist_keeps_the_exact_public_host_and_edition(url):
    with pytest.raises(ValueError, match='unsupported_media_locator'):
        validate_url(url)


def test_official_mp4_uses_the_existing_bounded_downloader(tmp_path):
    with httpx.Client(transport=httpx.MockTransport(lambda request: httpx.Response(200, content=b'public video'))) as client:
        output = cache_ad_reference_media.direct_media(client, source.MEDIA_BASE + 'F01_001.mp4', tmp_path)
    assert output.read_bytes() == b'public video'


@pytest.fixture
def collector(tmp_path, monkeypatch):
    monkeypatch.setattr(store, 'ROOT', tmp_path)
    monkeypatch.setenv('AD_LIBRARY_METADATA_OVERLAP', '1')
    delays, requests = [], []
    options = {'fail': set(), 'repeat': False, 'disallow': False, 'edition': 2026, 'reverse': False}
    monkeypatch.setattr(action.time, 'sleep', delays.append)
    original = httpx.Client
    def respond(request):
        requests.append(str(request.url))
        if request.url.path == '/robots.txt':
            if request.url.host == 'adfest.d-energy.cn':
                return httpx.Response(404)
            return httpx.Response(200, text='User-agent: *\nCrawl-delay: 3\nDisallow: ' + (source.DETAIL_PATH if options['disallow'] else '') + '\n')
        if request.url.path == source.SHOWCASE_PATH:
            page = int(request.url.params['page'])
            identities = [2, 1] if page == 1 and options['reverse'] else [1, 2] if page == 2 and options['repeat'] else None
            html = listing(page, identities)
            return httpx.Response(200, text=html.replace('works2026', 'works' + str(options['edition'])))
        assert request.url.path == source.DETAIL_PATH
        identity = int(request.url.params['id'])
        return httpx.Response(503 if identity in options['fail'] else 200, text=detail(identity))
    monkeypatch.setattr(action.httpx, 'Client', lambda **kw: original(transport=httpx.MockTransport(respond), **kw))
    return options, requests, delays


def test_pagination_failure_resumes_without_skipping_or_changing_preferences(collector):
    options, requests, delays = collector
    first = runner.run(11)
    assert (first['inserted'], first['next_page']) == (2, 2)
    with store.connection() as db:
        identity = db.execute('SELECT id FROM items ORDER BY id LIMIT 1').fetchone()[0]
    store.review_item(identity, 88, 0, 'selected', {'craft': 5}, [], 'keep this review')
    options['fail'].add(4)
    second = runner.run(11, batches=4)
    assert second['state'] == 'partial' and second['batches'] == 1
    assert second['last_batch']['next_page'] == 2 and second['inserted'] == 1
    options['fail'].clear()
    third = runner.run(11, batches=4)
    assert third['stop_reason'] == 'category_scan_complete' and third['inserted'] == 1
    assert min(delays) == 3
    with store.connection() as db:
        assert db.execute('SELECT COUNT(*) FROM items').fetchone()[0] == 4
        assert db.execute('SELECT page FROM adfest_showcase_cursors').fetchone()[0] == 1
        assert db.execute('SELECT note FROM reviews').fetchone()[0] == 'keep this review'
        assert all(json.loads(r[0])['training_eligible'] is False for r in db.execute('SELECT data FROM items'))
    assert len([u for u in requests if source.DETAIL_PATH in u]) == 6


def test_repeated_page_does_not_advance_cursor_or_create_duplicate_work(collector):
    options, requests, _ = collector
    runner.run(11)
    options['repeat'] = True
    before = len(requests)
    result = runner.run(11)
    assert result['state'] == 'failed' and result['error_code'] == 'page_repeated'
    assert result['next_page'] == 2 and result['attempted'] == 0
    assert not any(source.DETAIL_PATH in url for url in requests[before:])


def test_reordered_first_page_resets_cursor_without_losing_existing_review(collector):
    options, _, _ = collector
    runner.run(11)
    with store.connection() as db:
        identity = db.execute('SELECT id FROM items ORDER BY id LIMIT 1').fetchone()[0]
    store.review_item(identity, 88, 0, 'selected', {}, [], 'human choice')
    options['reverse'] = True
    result = runner.run(11)
    assert result['cursor_reset'] is True and result['page'] == 1
    assert result['next_page'] == 2 and result['inserted'] == 0
    with store.connection() as db:
        assert db.execute('SELECT COUNT(*) FROM items').fetchone()[0] == 2
        assert tuple(db.execute('SELECT state,note FROM reviews WHERE item=?', (identity,)).fetchone()) == ('selected', 'human choice')


@pytest.mark.parametrize('change,error', [('disallow', 'source_unavailable'), ('edition', 'source_edition_changed')])
def test_policy_and_edition_changes_leave_no_partial_new_records(collector, change, error):
    options, _, _ = collector
    options[change] = True if change == 'disallow' else 2027
    result = runner.run(11)
    assert result['state'] == 'failed' and result['error_code'] == error
    with store.connection() as db:
        assert db.execute('SELECT COUNT(*) FROM items').fetchone()[0] == 0
        assert db.execute('SELECT COUNT(*) FROM adfest_showcase_cursors').fetchone()[0] == 0


def test_active_collector_is_never_interrupted(collector, tmp_path):
    _, requests, _ = collector
    with (tmp_path / '.collector.lock').open('a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        assert runner.run(11)['state'] == 'already_running'
    assert requests == []


def test_streams_are_bounded_before_parsing(monkeypatch):
    monkeypatch.setattr(source, 'MAX_BYTES', 32)
    with httpx.Client(transport=httpx.MockTransport(lambda request: httpx.Response(200, content=b'x' * 33))) as client:
        with pytest.raises(ValueError, match='source_page_too_large'):
            action._read(client, source.ORIGIN)
