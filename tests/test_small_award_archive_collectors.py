"""Real provider parsers must progress beyond the first twelve annual entries."""
import importlib
import httpx
import pytest
from harness.library import store
from harness.tools import award_archive


@pytest.mark.parametrize('source', ['berlin_commercial', 'kinsale'])
def test_annual_collector_advances_through_real_parser(tmp_path, monkeypatch, source):
    adapter = importlib.import_module('harness.models.reference_sources.' + source)
    collector = importlib.import_module('tools.collect_' + source)
    monkeypatch.setattr(store, 'ROOT', tmp_path)
    delays = []
    monkeypatch.setattr(award_archive.time, 'sleep', delays.append)
    medium = 'COMMERCIALS AND BRANDED CONTENT - SHORT' if source == 'berlin_commercial' else 'ADVERTISING FILM 2025'
    cards = []
    for identity in range(10000, 10025):
        cards.append(f'''<div class="winners" data-entry-id="{identity}">
        <h4 class="title">{medium}</h4>
        <a href="/?action=ows:entries.details&amp;e={identity}&amp;project_year=2025">View</a>
        <div class="prize"><h3>Gold</h3></div><strong>Automotive</strong>
        <div class="credits"><h4>Film {identity}</h4><p>Brand</p></div></div>''')
    listing = ''.join(cards)
    assert len(adapter.parse_listing(listing, year=2025)) == 12
    assert len(adapter.parse_listing(listing, year=2025, max_entries=None)) == 25
    detail = '''<h3 class="title"><strong>Film</strong></h3>
    <video><source src="https://bv-04.bubblevault.com/id/mp4/720x480/film.mp4" type="video/mp4"></video>
    <img data-type="video" data-video-src="https://bv-04.bubblevault.com/id/mp4/720x480/film.mp4">'''
    detail_ids = []

    def respond(request):
        if request.url.path == '/robots.txt':
            return httpx.Response(200, text='User-agent: *\nCrawl-delay: 10\n')
        if request.url.path == '/winners/2025':
            return httpx.Response(200, text=listing)
        detail_ids.append(request.url.params['e'])
        return httpx.Response(200, text=detail)

    original_client = httpx.Client
    monkeypatch.setattr(award_archive.httpx, 'Client', lambda **kw: original_client(transport=httpx.MockTransport(respond), **kw))
    first = collector.run(year=2025)
    second = collector.run(year=2025)
    tail = collector.run(year=2025, batches=10)
    assert first['offset'] == 0 and first['next_offset'] == 12 and first['inserted'] == 12
    assert second['offset'] == 12 and second['next_offset'] == 24 and second['inserted'] == 12
    assert tail['stop_reason'] == 'year_scan_complete' and tail['batches'] == 1 and tail['inserted'] == 1
    assert detail_ids == [str(n) for n in range(10000, 10025)]
    assert len(delays) == 25 and all(delay >= 10 for delay in delays)
    with store.connection() as db:
        assert db.execute('SELECT COUNT(*) FROM items').fetchone()[0] == 25
        assert db.execute('SELECT offset FROM archive_cursors WHERE source=? AND year=2025', (source,)).fetchone()[0] == 0
        assert db.execute('SELECT COUNT(*) FROM reviews').fetchone()[0] == 0


@pytest.mark.parametrize('source', ['berlin_commercial', 'kinsale'])
@pytest.mark.parametrize('args', [['--batches','2'], ['--year','2025','--batches','33']])
def test_archive_cli_rejects_unbounded_or_implicit_burst(monkeypatch, source, args):
    collector = importlib.import_module('tools.collect_' + source)
    monkeypatch.setattr(collector, 'run', lambda *a, **kw: pytest.fail('Invalid CLI input must not collect'))
    with pytest.raises(SystemExit) as error:
        collector.main(args)
    assert error.value.code == 2
