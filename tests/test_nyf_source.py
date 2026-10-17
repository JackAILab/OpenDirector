import httpx
from unittest.mock import patch

from harness.models.reference_sources import nyf


def card(award='Grand', title='Film One', company='Studio', brand='Brand', medium='FILM', category='Best Use', detail='11111111-1111-4111-8111-111111111111'):
    return f'''<div class="grid-item" data-award="{award}">
      <div class="overlay-country"><a href="/Winners/WinnerDetailsNew/{detail}"><label class="badge">Video</label>
      <div class="image-crop lazyload" data-bg="url(https://nyfstorageprod.blob.core.windows.net/thumbnail/thumb.jpg"></div></a></div>
      <div class="grid-info"><h5>{title}</h5><ul>
      <li><label>COMPANY</label> <span>{company}</span></li>
      <li><label>Brand</label> <span>{brand}</span></li>
      <li><label>Category</label> <span>{category}</span></li></ul></div>
      <div class="cat-bar"><span>{medium}: {category}</span></div>
      </div>'''


def html(*cards):
    return '<select id="id"><option value="56f6454a-72bb-42e8-8847-f77d053e4c4f" selected="selected">2025</option></select>' + ''.join(cards)


def test_parse_listing_groups_same_work_and_preserves_award_evidence():
    rows = nyf.parse_listing(html(
        card(detail='11111111-1111-4111-8111-111111111111'),
        card(award='Gold', detail='22222222-2222-4222-8222-222222222222'),
        card(medium='STUDENT', detail='33333333-3333-4333-8333-333333333333'),
        card(award='Finalist', detail='44444444-4444-4444-8444-444444444444'),
    ), 2025)
    assert len(rows) == 1
    assert rows[0]['creative_structure']['award_entry_count'] == 2
    assert {e['text'].split(' · ')[1] for e in rows[0]['quality_evidence']} == {'Grand', 'Gold'}
    assert rows[0]['source_url'].startswith('https://www.nyfadvertising.com/Winners/WinnerDetailsNew/')
    assert rows[0]['media_status'] == 'source_link'


def test_parse_listing_rejects_changed_archive_selection():
    try:
        nyf.parse_listing('<select id="id"><option selected="selected">2024</option></select>', 2025)
    except ValueError as exc:
        assert str(exc) == 'source_layout_changed'
    else:
        raise AssertionError('expected source_layout_changed')


def test_collector_is_idempotent_and_bounded(tmp_path, monkeypatch):
    from harness.library import store
    from tools import collect_nyf as collector
    monkeypatch.setattr(store, 'ROOT', tmp_path)
    monkeypatch.setattr(collector.nyf, 'ARCHIVES', {2025: 'archive-id'})
    source = html(card()).replace('56f6454a-72bb-42e8-8847-f77d053e4c4f', 'archive-id')

    def respond(request):
        if request.url.path == '/robots.txt':
            return httpx.Response(404)
        return httpx.Response(200, text=source)

    real_client = httpx.Client
    monkeypatch.setattr(collector.httpx, 'Client', lambda **kw: real_client(transport=httpx.MockTransport(respond), **kw))
    first = collector.run(2025)
    second = collector.run(2025)
    assert first['state'] == 'completed' and first['discovered'] == 1 and first['inserted'] == 1
    assert second['state'] == 'completed' and second['discovered'] == 1 and second['inserted'] == 0


def test_scheduled_collector_rotates_archive_years():
    from tools import collect_nyf as collector
    with patch.object(collector.nyf, 'ARCHIVES', {2025: 'a', 2024: 'b', 2023: 'c'}), \
         patch.object(collector.time, 'time', return_value=0):
        assert collector._year(None) == 2025
    with patch.object(collector.nyf, 'ARCHIVES', {2025: 'a', 2024: 'b', 2023: 'c'}), \
         patch.object(collector.time, 'time', return_value=3 * 3600):
        assert collector._year(None) == 2024
    with patch.object(collector.nyf, 'ARCHIVES', {2025: 'a'}):
        try:
            collector._year(2024)
        except ValueError as exc:
            assert str(exc) == 'invalid_nyf_year'
        else:
            raise AssertionError('expected invalid_nyf_year')
