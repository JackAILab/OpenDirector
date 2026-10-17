import json
import httpx
import pytest

from harness.library import store
from harness.models.reference_download import validate_url
from harness.models.reference_sources import kyoorius_current as source
from harness.tools import award_archive
from tools import collect_kyoorius_current, cache_ad_reference_media

VIDEO = 'https://kyoorius-prod2-resized-media.awards-360.com/companies/455/media/22af752d-850f-441e-fc8c-08de9ea08308.mp4'


def entry(identity=14550, discipline='Film', award='First List'):
    return {'id': identity, 'title': f'Film & Story {identity}', 'year': '2026',
        'brand': 'Brand', 'awardLevel': award,
        'hierarchy': [{'programName': discipline, 'currentLabel': 'Discipline'}],
        'media': [{'mediaType': 'video', 'videoResizePath': VIDEO, 'adminFieldName': 'Content AV'}],
        'individualCredits': [{'personal_detail': 'MUST NOT STORE'}]}


def page(field, value, split=False):
    stream = 'e:' + json.dumps(['$', 'section', None, {field: value}]) + '\n'
    chunks = [stream[:80], stream[80:]] if split else [stream]
    return ''.join('<script>self.__next_f.push(' + json.dumps([1, chunk]) + ')</script>' for chunk in chunks)


def test_listing_handles_chunk_boundaries_filters_films_and_preserves_award_levels():
    rows = [entry(), entry(2, 'Film Craft', 'Blue Elephant'), entry(3, 'Regional Film'), entry(4, 'Press')]
    records = source.parse_listing(page('entries', rows, split=True), max_entries=None)
    assert len(records) == 3
    assert records[0]['quality_evidence'][0]['kind'] == 'award_shortlist'
    assert records[1]['quality_evidence'][0]['kind'] == 'award_winner'
    assert 'individualCredits' not in json.dumps(records)
    assert 'MUST NOT STORE' not in json.dumps(records)
    assert len(source.parse_listing(page('entries', rows), max_entries=1)) == 1


def test_detail_preserves_variants_and_prefers_the_work_over_case_study():
    row = entry()
    case_url = VIDEO.replace('22af752d', 'aaaaaaaa')
    row['media'].insert(0, {'mediaType': 'video', 'videoResizePath': case_url, 'adminFieldName': 'Case Study Video'})
    record = source.parse_listing(page('entries', [row]))[0]
    detail = source.parse_detail(page('entry', row), record['source_url'])
    result = source.apply_detail(record, detail)
    assert result['creative_structure']['public_video_url'] == VIDEO
    assert result['creative_structure']['public_video_count'] == 2
    assert result['creative_structure']['public_video_variants'][1]['url'] == case_url
    assert result['media_role'] == 'work_or_case_film_unverified'
    assert 'individualCredits' not in json.dumps(result)


def test_wrong_detail_identity_fails_instead_of_attaching_another_film():
    with pytest.raises(ValueError, match='identity_mismatch'):
        source.parse_detail(page('entry', entry(2)), source._source_url(entry(1)))


def test_title_update_keeps_the_actual_fetched_url_as_evidence():
    row = entry()
    fetched = source._source_url(row)
    row['title'] = 'Updated title'
    detail = source.parse_detail(page('entry', row), fetched)
    assert detail['record']['source_url'] == fetched
    assert detail['record']['creative_structure']['source_page'] == fetched
    assert detail['record']['quality_evidence'][0]['source_url'] == fetched


@pytest.mark.parametrize('title, slug', [
    ("Confidence on slippery roads | It's easy on an Ather",
     'confidence-on-slippery-roads-its-easy-on-an-ather'),
    ('Don’t Waste Water', 'dont-waste-water'),
])
def test_source_slug_matches_public_gallery_route(title, slug):
    row = entry(13498)
    row['title'] = title
    assert source._source_url(row).endswith('/13498-' + slug + '/')


@pytest.mark.parametrize('bad', [
    VIDEO + '?token=secret', VIDEO + '#fragment',
    VIDEO.replace('https:', 'http:'), VIDEO.replace('awards-360.com', 'awards-360.com.evil.test'),
    VIDEO.replace('/companies/455/media/', '/admin/'), VIDEO.replace('.mp4', '.m3u8'),
    VIDEO.replace('https://', 'https://name@'),
])
def test_unsigned_official_mp4_only(bad):
    with pytest.raises(ValueError):
        validate_url(bad)
    row = entry(); row['media'][0]['videoResizePath'] = bad
    assert not source.parse_detail(page('entry', row), source._source_url(row))['has_video']


def test_official_video_passes_the_existing_bounded_downloader(tmp_path):
    with httpx.Client(transport=httpx.MockTransport(lambda request: httpx.Response(200, content=b'public video'))) as client:
        target = cache_ad_reference_media.direct_media(client, VIDEO, tmp_path)
    assert target.read_bytes() == b'public video'


def test_scripts_are_not_executed_and_oversized_pages_are_rejected():
    with pytest.raises(ValueError, match='unrecognized'):
        source.parse_listing('<script>self.__next_f.push([1, getPrivateData()])</script>')
    with pytest.raises(ValueError, match='too_large'):
        source.parse_listing(' ' * (source.LISTING_MAX_BYTES + 1))


def test_durable_cursor_with_real_parser_and_failed_detail(tmp_path, monkeypatch):
    monkeypatch.setattr(store, 'ROOT', tmp_path)
    delays, requested, fail = [], [], {13}
    monkeypatch.setattr(award_archive.time, 'sleep', delays.append)
    rows = [entry(i) for i in range(1, 26)]
    def respond(request):
        if request.url.path == '/robots.txt':
            return httpx.Response(200, text='User-agent: *\nCrawl-delay: 12\n')
        if request.url.path == '/winners/2026/kca/':
            # The real listing exceeds the default detail-page allowance.
            return httpx.Response(200, text=page('entries', rows) + ' ' * award_archive.MAX_BYTES)
        identity = int(request.url.path.split('/')[-2].split('-')[0])
        requested.append(identity)
        return httpx.Response(503 if identity in fail else 200, text=page('entry', entry(identity)))
    original = httpx.Client
    monkeypatch.setattr(award_archive.httpx, 'Client', lambda **kw: original(transport=httpx.MockTransport(respond), **kw))
    first = collect_kyoorius_current.run()
    assert (first['inserted'], first['next_offset']) == (12, 12)
    failed = collect_kyoorius_current.run(batches=4)
    assert failed['state'] == 'partial' and failed['batches'] == 1
    assert failed['last_batch']['next_offset'] == 12
    fail.clear()
    resumed = collect_kyoorius_current.run(batches=4)
    assert resumed['inserted'] == 2 and resumed['stop_reason'] == 'year_scan_complete'
    assert len(delays) == 37 and min(delays) == 12
    with store.connection() as db:
        assert db.execute('SELECT count(*) FROM items').fetchone()[0] == 25
        assert db.execute('SELECT count(*) FROM reviews').fetchone()[0] == 0
        assert db.execute("SELECT offset FROM archive_cursors WHERE source='kyoorius:current'").fetchone()[0] == 0
        assert all(json.loads(row['data'])['training_eligible'] is False for row in db.execute('SELECT data FROM items'))


def test_listing_allowance_does_not_relax_details_and_is_still_bounded():
    with httpx.Client(transport=httpx.MockTransport(lambda request: httpx.Response(200, content=b'x' * (award_archive.MAX_BYTES + 1)))) as client:
        with pytest.raises(ValueError, match='too_large'):
            award_archive._read_page(client, source.ORIGIN)
    with httpx.Client(transport=httpx.MockTransport(lambda request: httpx.Response(200, content=b'x' * (source.LISTING_MAX_BYTES + 1)))) as client:
        with pytest.raises(ValueError, match='too_large'):
            award_archive._read_page(client, source.ORIGIN, source.LISTING_MAX_BYTES)


def test_invalid_batch_does_not_start_collection(monkeypatch):
    monkeypatch.setattr(collect_kyoorius_current, 'run', lambda *a: pytest.fail('No collection'))
    with pytest.raises(SystemExit) as exc:
        collect_kyoorius_current.main(['--batches', '33'])
    assert exc.value.code == 2
