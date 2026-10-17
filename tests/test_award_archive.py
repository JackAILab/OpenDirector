from types import SimpleNamespace

import httpx
import fcntl
import pytest

from harness.library import store
from harness.tools.award_archive import collect_archive, collect_archive_batches


def _adapter():
    adapter = SimpleNamespace(ORIGIN='https://awards.example')
    adapter.listing_url = lambda year: f'https://awards.example/winners/{year}'
    adapter.parse_listing = lambda text, year, max_entries=None: [
        {'source_url': f'https://awards.example/detail/{n}', 'title': f'Film {n}', 'brand': 'Brand'}
        for n in range(25)
    ]
    adapter.parse_detail = lambda text, url: {'has_video': True, 'video_url': url, 'thumbnail_url': ''}
    adapter.apply_detail = lambda record, detail: {
        **record,
        'source_name': 'test award', 'industry': 'consumer', 'ad_type': 'film',
        'media_status': 'source_link', 'quality_evidence': [],
    }
    return adapter


def test_archive_cursor_advances_and_is_resumable(tmp_path, monkeypatch):
    monkeypatch.setattr(store, 'ROOT', tmp_path)
    monkeypatch.setattr('harness.tools.award_archive.time.sleep', lambda _: None)

    def respond(request):
        if request.url.path == '/robots.txt':
            return httpx.Response(404)
        return httpx.Response(200, text='listing')

    real_client = httpx.Client
    monkeypatch.setattr('harness.tools.award_archive.httpx', SimpleNamespace(
        Client=lambda **kw: real_client(transport=httpx.MockTransport(respond), **kw),
        HTTPError=httpx.HTTPError,
    ))
    adapter = _adapter()
    first = collect_archive(adapter, 'Test awards', 'test_awards', 2025, request_delay=0)
    second = collect_archive(adapter, 'Test awards', 'test_awards', 2025, request_delay=0)
    assert first['state'] == second['state'] == 'completed'
    assert first['offset'] == 0 and first['next_offset'] == 12
    assert second['offset'] == 12 and second['next_offset'] == 24
    with store.connection() as db:
        assert db.execute('select offset from archive_cursors where source=? and year=?', ('test_awards', 2025)).fetchone()[0] == 24


def test_archive_cursor_does_not_advance_on_detail_failure(tmp_path, monkeypatch):
    monkeypatch.setattr(store, 'ROOT', tmp_path)
    monkeypatch.setattr('harness.tools.award_archive.time.sleep', lambda _: None)
    adapter = _adapter()

    def respond(request):
        if request.url.path == '/robots.txt':
            return httpx.Response(404)
        if request.url.path == '/detail/0':
            return httpx.Response(503)
        return httpx.Response(200, text='ok')

    real_client = httpx.Client
    monkeypatch.setattr('harness.tools.award_archive.httpx', SimpleNamespace(
        Client=lambda **kw: real_client(transport=httpx.MockTransport(respond), **kw),
        HTTPError=httpx.HTTPError,
    ))
    result = collect_archive(adapter, 'Test awards', 'test_awards', 2025, request_delay=0)
    assert result['state'] == 'partial' and result['error_code'] == 'source_unavailable'
    with store.connection() as db:
        assert db.execute('select count(*) from archive_cursors').fetchone()[0] == 0


def test_archive_startup_write_failure_is_bounded_and_makes_no_requests(tmp_path,monkeypatch):
    monkeypatch.setattr(store,'ROOT',tmp_path)
    with store.connection() as db:
        db.execute("CREATE TRIGGER busy BEFORE INSERT ON collection_runs BEGIN SELECT RAISE(ABORT,'simulated busy database'); END")
    def no_network(**kw):raise AssertionError('Must not fetch without a committed receipt')
    monkeypatch.setattr('harness.tools.award_archive.httpx',SimpleNamespace(Client=no_network,HTTPError=httpx.HTTPError))
    result=collect_archive(_adapter(),'Test awards','test_awards',2025)
    assert result=={'state':'failed','error_code':'database_unavailable','year':2025,'discovered':0,'inserted':0}
    with store.connection() as db:
        assert db.execute('SELECT COUNT(*) FROM collection_runs').fetchone()[0]==0
        assert db.execute('SELECT COUNT(*) FROM items').fetchone()[0]==0


@pytest.mark.parametrize('failure', ['status', 'timeout'])
def test_archive_listing_failure_diagnostics_are_bounded(tmp_path, monkeypatch, failure):
    monkeypatch.setattr(store, 'ROOT', tmp_path)
    requests = []

    def respond(request):
        requests.append(request.url.path)
        if request.url.path == '/robots.txt':
            return httpx.Response(404)
        if failure == 'timeout':
            raise httpx.ReadTimeout('private provider payload and URL', request=request)
        return httpx.Response(502, text='private provider payload and URL')

    real_client = httpx.Client
    monkeypatch.setattr('harness.tools.award_archive.httpx', SimpleNamespace(
        Client=lambda **kw: real_client(transport=httpx.MockTransport(respond), **kw),
        HTTPError=httpx.HTTPError,
    ))
    result = collect_archive(_adapter(), 'Test awards', 'test_awards', 2025, request_delay=0)
    expected = {'phase': 'listing', 'error_code': 'timeout' if failure == 'timeout' else 'http_status'}
    if failure == 'status':
        expected['http_status'] = 502
    assert result['state'] == 'failed'
    assert result['failure_details'] == [expected]
    assert result['offset'] == result['next_offset'] == 0
    assert requests == ['/robots.txt', '/winners/2025']
    assert 'private provider' not in str(result)
    assert 'https://' not in str(result)
    with store.connection() as db:
        assert db.execute('SELECT COUNT(*) FROM archive_cursors').fetchone()[0] == 0
        assert db.execute('SELECT COUNT(*) FROM items').fetchone()[0] == 0


@pytest.fixture
def batch_transport(tmp_path, monkeypatch):
    monkeypatch.setattr(store, 'ROOT', tmp_path)
    monkeypatch.setattr('harness.tools.award_archive.time.sleep', lambda _: None)
    requests, failing = [], set()

    def respond(request):
        requests.append(request.url.path)
        if request.url.path == '/robots.txt':
            return httpx.Response(404)
        return httpx.Response(503 if request.url.path in failing else 200, text='ok')

    real_client = httpx.Client
    monkeypatch.setattr('harness.tools.award_archive.httpx', SimpleNamespace(
        Client=lambda **kw: real_client(transport=httpx.MockTransport(respond), **kw),
        HTTPError=httpx.HTTPError,
    ))
    return requests, failing


def test_batches_resume_from_database_and_stop_before_year_wrap(batch_transport):
    adapter, receipts = _adapter(), []
    collect_archive(adapter, 'Test awards', 'test_awards', 2025, request_delay=0)
    result = collect_archive_batches(adapter, 'Test awards', 'test_awards', 2025,
                                     max_batches=10, request_delay=0, on_batch=receipts.append)
    assert result['state'] == 'completed'
    assert result['stop_reason'] == 'year_scan_complete'
    assert result['batches'] == 2 and result['inserted'] == 13
    assert [r['offset'] for r in receipts] == [12, 24]
    assert batch_transport[0].count('/detail/0') == 1
    with store.connection() as db:
        assert db.execute('SELECT COUNT(*) FROM items').fetchone()[0] == 25
        assert db.execute('SELECT offset FROM archive_cursors').fetchone()[0] == 0


def test_batches_respect_limit_and_apply_explicit_offset_only_once(batch_transport):
    result = collect_archive_batches(_adapter(), 'Test awards', 'test_awards', 2025,
                                     max_batches=2, offset=1, request_delay=0)
    assert result['batches'] == 2 and result['inserted'] == 24
    assert result['last_batch']['offset'] == 13
    assert result['stop_reason'] == 'year_scan_complete'
    assert '/detail/0' not in batch_transport[0]


def test_batch_budget_keeps_remaining_candidates_for_next_invocation(batch_transport):
    result = collect_archive_batches(_adapter(), 'Test awards', 'test_awards', 2025,
                                     max_batches=1, request_delay=0)
    assert result['stop_reason'] == 'batch_limit'
    assert result['inserted'] == 12
    assert '/detail/12' not in batch_transport[0]
    with store.connection() as db:
        assert db.execute('SELECT offset FROM archive_cursors').fetchone()[0] == 12


def test_batches_stop_on_partial_without_retry_or_skipping_failed_detail(batch_transport):
    batch_transport[1].add('/detail/12')
    result = collect_archive_batches(_adapter(), 'Test awards', 'test_awards', 2025,
                                     max_batches=10, request_delay=0)
    assert result['state'] == result['stop_reason'] == 'partial'
    assert result['batches'] == 2 and result['inserted'] == 23
    assert batch_transport[0].count('/detail/12') == 1
    assert '/detail/24' not in batch_transport[0]
    with store.connection() as db:
        assert db.execute('SELECT offset FROM archive_cursors').fetchone()[0] == 12


def test_batches_yield_to_other_collector_between_batches(batch_transport, tmp_path):
    with (tmp_path / '.collector.lock').open('a') as other:
        def acquire_after_batch(batch):
            if batch['state'] == 'completed':
                fcntl.flock(other, fcntl.LOCK_EX | fcntl.LOCK_NB)
        result = collect_archive_batches(_adapter(), 'Test awards', 'test_awards', 2025,
                                         max_batches=10, request_delay=0, on_batch=acquire_after_batch)
    assert result['state'] == result['stop_reason'] == 'already_running'
    assert result['inserted'] == 12
    assert '/detail/12' not in batch_transport[0]


@pytest.mark.parametrize('limit', [0, 33, True])
def test_invalid_batch_budget_does_not_start_network(batch_transport, limit):
    with pytest.raises(ValueError, match='invalid_archive_batch_limit'):
        collect_archive_batches(_adapter(), 'Test awards', 'test_awards', 2025, max_batches=limit)
    assert batch_transport[0] == []


def test_ciclope_cli_requires_fixed_year_for_multiple_batches(batch_transport):
    from tools.collect_ciclope import main
    with pytest.raises(SystemExit) as exc:
        main(['--batches', '2'])
    assert exc.value.code == 2
    assert batch_transport[0] == []
