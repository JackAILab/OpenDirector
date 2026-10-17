from urllib.parse import parse_qs

import httpx
import pytest

from harness.library import store
from harness.models.reference_sources import effie
from tools import collect_effie as collector


def card(slug):
    return f'''<div class="card case-card"><h4>{slug}</h4>
      <a href="https://effie.org/cases/{slug}/">Explore this case</a></div>'''


VIDEO = '<video><source src="/public-film.mp4" type="video/mp4"></video>'
# Put the specific permission first for urllib's conservative rule evaluator.
ROBOTS = 'User-agent: *\nAllow: /wp-admin/admin-ajax.php\nDisallow: /wp-admin/\nCrawl-delay: 10\n'


@pytest.fixture
def source(tmp_path, monkeypatch):
    monkeypatch.setattr(store, 'ROOT', tmp_path / 'library')
    monkeypatch.setenv('AD_LIBRARY_METADATA_OVERLAP', '1')
    requests, delays = [], []
    monkeypatch.setattr(collector.time, 'sleep', delays.append)
    real_client = httpx.Client

    def install(*, second=None, first=None, robots=ROBOTS, no_video=()):
        def handler(request):
            requests.append(request)
            if request.url.path == '/robots.txt':
                return httpx.Response(200, text=robots)
            if request.url.path == '/wp-admin/admin-ajax.php':
                query = parse_qs(request.url.query.decode(), keep_blank_values=True)
                assert query == {
                    'action': ['get_filtered_posts'], 'post_type': ['cases'],
                    'paged': [query['paged'][0]], 'per_page': ['10'],
                    'form_data[keyword]': [''],
                }
                assert request.headers['X-Requested-With'] == 'XMLHttpRequest'
                body = first if query['paged'] == ['1'] else second
                return httpx.Response(200, text=body if body is not None else card('first'))
            if request.url.path.startswith('/cases/'):
                slug = request.url.path.split('/')[2]
                return httpx.Response(200, text='' if slug in no_video else VIDEO)
            raise AssertionError('Unexpected source request')

        monkeypatch.setattr(collector.httpx, 'Client', lambda **kw: real_client(
            transport=httpx.MockTransport(handler), **kw))
        return requests, delays

    return install


def test_collects_actual_second_page_with_video_and_respects_delay(source):
    requests, delays = source(second=card('second') + card('text-only'), no_video=('text-only',))
    result = collector.run(2)
    assert (result['state'], result['discovered'], result['inserted']) == ('completed', 1, 1)
    assert [r.url.path for r in requests] == [
        '/robots.txt', '/wp-admin/admin-ajax.php', '/wp-admin/admin-ajax.php',
        '/cases/second/', '/cases/text-only/',
    ]
    assert delays == [10, 10, 10, 10]
    with store.connection() as db:
        row = db.execute('SELECT id FROM items').fetchone()
    item = store.get_item(row['id'], 0)
    assert item['source_url'] == 'https://effie.org/cases/second/'
    assert item['media_role'] == 'case_film_unverified'
    assert item['training_eligible'] is False
    assert item['review']['state'] == 'pending'


def test_repeated_ajax_page_is_partial_and_does_not_fetch_details(source):
    requests, _ = source(second=card('first'))
    result = collector.run(2)
    assert result['state'] == 'partial' and result['error_code'] == 'page_repeated'
    assert result['discovered'] == result['inserted'] == 0
    assert len(requests) == 3


def test_ajax_disallowed_by_robots_is_not_requested(source):
    requests, _ = source(robots='User-agent: *\nDisallow: /wp-admin/\n')
    result = collector.run(2)
    assert result['state'] == 'failed'
    assert [r.url.path for r in requests] == ['/robots.txt']


def test_detail_disallowed_by_robots_is_not_requested(source):
    requests, delays = source(second=card('blocked'), robots=ROBOTS + 'Disallow: /cases/blocked/\n')
    result = collector.run(2)
    assert result['state'] == 'failed' and result['inserted'] == 0
    assert len(requests) == 3 and delays == [10, 10]


@pytest.mark.parametrize('first,second', [('', card('second')), (card('first'), '')])
def test_empty_or_unrecognized_ajax_response_is_not_success(source, first, second):
    source(first=first, second=second)
    result = collector.run(2)
    assert result['state'] == 'failed' and result['inserted'] == 0


def test_second_visit_preserves_human_preference_and_deduplicates(source):
    source(second=card('second'))
    assert collector.run(2)['inserted'] == 1
    with store.connection() as db:
        identity = db.execute('SELECT id FROM items').fetchone()[0]
    store.review_item(identity, 7, 0, 'selected', {'story': 4}, [], 'Human preference')
    result = collector.run(2)
    assert result['state'] == 'completed' and result['inserted'] == 0
    assert store.get_item(identity, 7)['review']['note'] == 'Human preference'


def test_collector_lock_still_prevents_a_second_worker(source):
    import fcntl
    requests, _ = source()
    store.ROOT.mkdir(parents=True)
    with (store.ROOT / '.collector.lock').open('a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        assert collector.run(2)['state'] == 'already_running'
    assert requests == []


@pytest.mark.parametrize('page', [True, 0, -1, 1843, '2'])
def test_invalid_page_rejected_before_requests(source, page):
    requests, _ = source()
    with pytest.raises(ValueError, match='invalid_effie_page'):
        collector.run(page)
    assert requests == []


def test_decoded_stream_larger_than_limit_is_rejected(monkeypatch):
    monkeypatch.setattr(effie, 'MAX_PAGE_BYTES', 5)

    class Chunks(httpx.SyncByteStream):
        def __iter__(self):
            yield b'123'
            yield b'456'
            raise AssertionError('Reader must stop after crossing the bound')

    with httpx.Client(transport=httpx.MockTransport(
            lambda request: httpx.Response(200, stream=Chunks()))) as client:
        with pytest.raises(ValueError, match='source_too_large'):
            effie.read_page(client, effie.archive_url(2))


@pytest.mark.parametrize('target', ['https://example.org/cases/film/',
                                  'http://effie.org/cases/film/',
                                  'https://effie.org/private/',
                                  'https://effie.org/cases/film/?token=fixture'])
def test_archive_ignores_non_public_case_locators(target):
    html = card('film').replace('https://effie.org/cases/film/', target)
    assert effie.parse_archive(html) == []
