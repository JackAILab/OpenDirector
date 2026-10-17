"""Exercise persisted progress through real Kyoorius parsers and SQLite."""
import httpx
import pytest

from harness.library import store
from harness.models.reference_sources import kyoorius
from harness.tools import award_archive
from tools import collect_kyoorius


@pytest.fixture
def archive(tmp_path, monkeypatch):
    monkeypatch.setattr(store, 'ROOT', tmp_path)
    delays, requests, failing = [], [], set()
    monkeypatch.setattr(award_archive.time, 'sleep', delays.append)
    cards = ''.join(f'''<div class="winners cat_film">
        <h4 class="title">Film</h4>
        <a href="/?action=ows:entries.details&amp;e={identity}&amp;project_year=2025">View</a>
        <div class="prize"><h3>Blue Elephant</h3></div>
        <div class="credits"><h4>Film {identity}</h4><p>Brand</p></div></div>'''
        for identity in range(10000, 10025))
    detail = '''<img data-type="video"
        data-video-src="https://bv-04.bubblevault.com/id/mp4/720x480/film.mp4">
        <small class="mp4-duration">20s</small>'''

    def respond(request):
        if request.url.path == '/robots.txt':
            return httpx.Response(200, text='User-agent: *\nCrawl-delay: 12\n')
        if request.url.path in kyoorius.LISTING_PATHS:
            return httpx.Response(200, text=cards)
        identity = request.url.params['e']
        requests.append(identity)
        return httpx.Response(503 if identity in failing else 200, text=detail)

    original = httpx.Client
    monkeypatch.setattr(award_archive.httpx, 'Client',
                        lambda **kw: original(transport=httpx.MockTransport(respond), **kw))
    return cards, delays, requests, failing


def test_default_annual_listing_advances_past_first_twelve_and_stops_at_end(archive):
    cards, delays, requests, _ = archive
    assert len(kyoorius.parse_listing(cards)) == 12
    assert len(kyoorius.parse_listing(cards, max_entries=None)) == 25
    receipts = []
    first = collect_kyoorius.run()
    second = collect_kyoorius.run()
    tail = collect_kyoorius.run(batches=8, on_batch=receipts.append)
    assert first['path'] == '/winners/2025'
    assert (first['offset'], first['next_offset'], first['inserted']) == (0, 12, 12)
    assert (second['offset'], second['next_offset'], second['inserted']) == (12, 24, 12)
    assert (tail['batches'], tail['inserted'], tail['stop_reason']) == (1, 1, 'year_scan_complete')
    assert receipts[0]['path'] == first['path']
    assert requests == [str(i) for i in range(10000, 10025)]
    assert len(delays) == 25 and min(delays) == 12
    with store.connection() as db:
        assert db.execute('SELECT COUNT(*) FROM items').fetchone()[0] == 25
        assert db.execute('SELECT COUNT(*) FROM reviews').fetchone()[0] == 0


def test_section_cursor_is_independent_and_preferences_survive_rediscovery(archive):
    collect_kyoorius.run()
    with store.connection() as db:
        identity = db.execute('SELECT id FROM items ORDER BY id LIMIT 1').fetchone()[0]
    store.review_item(identity, 7, 0, 'selected', {'craft': 4}, ['visual'], 'My own preference')
    before = store.get_item(identity, 7)
    section = collect_kyoorius.run(paths=['/winners/2025/craft'])
    assert section['offset'] == 0 and section['next_offset'] == 12
    assert section['inserted'] == 0
    with store.connection() as db:
        offsets = {row['source']: row['offset'] for row in db.execute('SELECT source,offset FROM archive_cursors')}
    assert offsets == {'kyoorius:/winners/2025': 12, 'kyoorius:/winners/2025/craft': 12}
    after = store.get_item(identity, 7)
    assert before['review'] == after['review']
    assert after['training_eligible'] is False


def test_failed_detail_keeps_cursor_and_stops_burst(archive):
    _, _, requests, failing = archive
    collect_kyoorius.run()
    failing.add('10012')
    interrupted = collect_kyoorius.run(batches=8)
    assert interrupted['state'] == 'partial' and interrupted['batches'] == 1
    assert interrupted['last_batch']['next_offset'] == 12
    assert requests.count('10012') == 1
    failing.clear()
    resumed = collect_kyoorius.run()
    assert resumed['offset'] == 12 and resumed['next_offset'] == 24
    assert resumed['inserted'] == 1


@pytest.mark.parametrize('args', [
    ['--batches', '33'],
    ['--path', '/winners/2025', '--path', '/winners/2025/craft', '--batches', '2'],
])
def test_ambiguous_or_unbounded_cli_does_not_collect(monkeypatch, args):
    monkeypatch.setattr(collect_kyoorius, 'run', lambda *a, **kw: pytest.fail('Must reject before collecting'))
    with pytest.raises(SystemExit) as exc:
        collect_kyoorius.main(args)
    assert exc.value.code == 2
