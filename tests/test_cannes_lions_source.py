import json

from harness.models.reference_sources.cannes_lions import parse_page


def page(cards):
    payload = {
        'props': {'pageProps': {'content': [{
            'sys': {'contentType': {'sys': {'id': 'group'}}},
            'fields': {'content': cards},
        }]}}
    }
    return '<script id="__NEXT_DATA__" type="application/json">' + json.dumps(payload) + '</script>'


def card(title, description, url, image='//images.ctfassets.net/x/thumb.jpg'):
    return {
        'sys': {'contentType': {'sys': {'id': 'videoCard'}}},
        'fields': {
            'title': title,
            'description': description,
            'videoUrl': url,
            'image': {'fields': {'file': {'url': image}}},
        },
    }


def test_parse_page_keeps_stable_vimeo_and_official_evidence():
    rows = parse_page(page([card('Night Fishing', 'INNOCEAN, SEOUL / HYUNDAI / 2025', 'https://vimeo.com/123?share=copy')]),
                      'https://www.canneslions.com/awards/winners-spotlight/winners-interviews')
    assert len(rows) == 1
    assert rows[0]['source_url'] == 'https://vimeo.com/123'
    assert rows[0]['embed_url'] == 'https://vimeo.com/123'
    assert rows[0]['quality_evidence'][0]['source_url'].startswith('https://www.canneslions.com/')
    assert rows[0]['media_status'] == 'source_link'
    assert rows[0]['rights'].startswith('reference_only;')
    assert rows[0]['thumbnail_url'] == 'https://images.ctfassets.net/x/thumb.jpg'


def test_parse_page_filters_year_invalid_hosts_and_deduplicates():
    rows = parse_page(page([
        card('Keep', 'AGENCY / BRAND / 2025', 'https://vimeo.com/1'),
        card('Duplicate', 'AGENCY / BRAND / 2025', 'https://vimeo.com/1?share=copy'),
        card('Old', 'AGENCY / BRAND / 2024', 'https://vimeo.com/2'),
        card('Bad host', 'AGENCY / BRAND / 2025', 'https://example.com/3'),
    ]), 'https://www.canneslions.com/awards/winners-spotlight/sports')
    assert [row['title'] for row in rows] == ['Keep']


def test_collector_is_bounded_and_idempotent(tmp_path, monkeypatch):
    import httpx
    from harness.library import store
    from tools import collect_cannes_lions as collector

    monkeypatch.setattr(store, 'ROOT', tmp_path)
    html = page([card('Keep', 'AGENCY / BRAND / 2025', 'https://vimeo.com/1')])

    def respond(request):
        if request.url.path == '/robots.txt':
            return httpx.Response(404)
        return httpx.Response(200, text=html)

    real_client = httpx.Client
    monkeypatch.setattr(collector.httpx, 'Client', lambda **kw: real_client(transport=httpx.MockTransport(respond), **kw))
    selected = ('https://www.canneslions.com/awards/winners-spotlight/test',)
    first = collector.run(pages=selected)
    second = collector.run(pages=selected)
    assert first['state'] == 'completed' and first['discovered'] == 1 and first['inserted'] == 1
    assert second['state'] == 'completed' and second['discovered'] == 1 and second['inserted'] == 0
