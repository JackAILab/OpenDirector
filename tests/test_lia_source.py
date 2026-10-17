from harness.models.reference_sources.lia import parse_winners


def test_parse_winners_keeps_stable_entry_and_drops_media_url():
    html = '''<div class="medium-entry"><div class="medium-entry-title medium-entry-award-gold">Gold</div>
      <div class="medium-entry-content"><em class="text-pink">TV &amp; CINEMA<br />Humor</em>
      <h3><strong>Studio</strong></h3><a href="?id_entry=12&amp;id_medium=6&amp;id_submedium=1&amp;view=details&amp;page=1">Brand: <strong>Brand X</strong></a>
      <a href="?id_entry=12&amp;id_medium=6&amp;id_submedium=1&amp;view=details&amp;page=1">Title: <strong>Funny Film</strong></a></div></div>'''
    row = parse_winners(html, 6, year=2024, origin='https://2024.liaentries.com')[0]
    assert row['title'] == 'Funny Film'
    assert '2024.liaentries.com' in row['source_url'] and 'id_entry=12' in row['source_url'] and 'page=' not in row['source_url']
    assert 'media_url' not in row and row['quality_evidence'][0]['kind'] == 'award_winner'


def test_collector_stops_repeated_listing_pages(tmp_path, monkeypatch):
    import httpx
    from harness.library import store
    from tools import collect_lia as collector
    monkeypatch.setattr(store, 'ROOT', tmp_path)
    monkeypatch.setattr(collector, 'YEARS', (2025,))
    monkeypatch.setattr(collector, 'MEDIUMS', ((6, 'TV & Cinema'),))
    monkeypatch.setattr(collector.time, 'sleep', lambda _: None)
    calls = []
    def respond(request):
        calls.append(str(request.url))
        if request.url.path == '/robots.txt':
            return httpx.Response(404)
        return httpx.Response(200, text='<div class="medium-entry"><a href="?id_entry=12&view=details">Title: <strong>Film</strong></a></div></div>')
    real_client = httpx.Client
    monkeypatch.setattr(collector.httpx, 'Client', lambda **kw: real_client(transport=httpx.MockTransport(respond), **kw))
    result = collector.run()
    assert result['state'] == 'completed' and result['inserted'] == 1
    assert len([url for url in calls if '/winners/' in url]) == 2


def test_collector_supports_bounded_deep_page_backfill(tmp_path, monkeypatch):
    import httpx
    from harness.library import store
    from tools import collect_lia as collector
    monkeypatch.setattr(store, 'ROOT', tmp_path)
    monkeypatch.setattr(collector, 'YEARS', (2025,))
    monkeypatch.setattr(collector, 'MEDIUMS', ((6, 'TV & Cinema'),))
    monkeypatch.setattr(collector.time, 'sleep', lambda _: None)
    calls = []
    def respond(request):
        calls.append(str(request.url))
        if request.url.path == '/robots.txt': return httpx.Response(404)
        page = request.url.params.get('page')
        title = f'Film {page}'
        return httpx.Response(200, text=f'<div class="medium-entry"><a href="?id_entry={page}&view=details">Title: <strong>{title}</strong></a></div></div>')
    real_client = httpx.Client
    monkeypatch.setattr(collector.httpx, 'Client', lambda **kw: real_client(transport=httpx.MockTransport(respond), **kw))
    result = collector.run(years=(2025,), medium_ids=(6,), page_start=5)
    assert result['state'] == 'completed' and result['inserted'] == 4
    assert any('page=5' in url for url in calls)


def test_default_mediums_cover_moving_image_and_branded_formats():
    from tools import collect_lia as collector
    ids = {medium_id for medium_id, _label in collector.MEDIUMS}
    assert {2, 3, 6, 7, 24, 25, 27, 29, 36, 45}.issubset(ids)
    assert len(ids) == len(collector.MEDIUMS)


def test_partial_collection_preserves_records_and_reports_safe_failure(tmp_path, monkeypatch):
    import json
    import httpx
    from harness.library import store
    from tools import collect_lia as collector
    monkeypatch.setattr(store, 'ROOT', tmp_path)
    monkeypatch.setattr(collector.time, 'sleep', lambda _: None)
    def respond(request):
        if request.url.path == '/robots.txt':
            return httpx.Response(404)
        if request.url.params.get('id_medium') == '36':
            return httpx.Response(503, text='private-provider-payload')
        return httpx.Response(200, text='<div class="medium-entry"><a href="?id_entry=12&view=details">Title: <strong>Film</strong></a></div></div>')
    real_client = httpx.Client
    monkeypatch.setattr(collector.httpx, 'Client', lambda **kw: real_client(transport=httpx.MockTransport(respond), **kw))
    result = collector.run(years=(2025,), medium_ids=(6, 36))
    assert result['state'] == 'partial' and result['inserted'] == 1
    assert result['failures'] == [{'year': 2025, 'phase': 'listing', 'medium_id': 36,
                                  'page': 1, 'error_code': 'http_status', 'http_status': 503}]
    assert 'private-provider-payload' not in json.dumps(result)
    assert 'https://' not in json.dumps(result)
    with store.connection() as db:
        assert db.execute('SELECT COUNT(*) FROM items').fetchone()[0] == 1


def test_robots_timeout_reports_scope_without_exception_details(tmp_path, monkeypatch):
    import json
    import httpx
    from harness.library import store
    from tools import collect_lia as collector
    monkeypatch.setattr(store, 'ROOT', tmp_path)
    def respond(request):
        raise httpx.ReadTimeout('private-request-details', request=request)
    real_client = httpx.Client
    monkeypatch.setattr(collector.httpx, 'Client', lambda **kw: real_client(transport=httpx.MockTransport(respond), **kw))
    result = collector.run(years=(2025,), medium_ids=(6,))
    assert result['state'] == 'failed' and result['inserted'] == 0
    assert result['failures'] == [{'year': 2025, 'phase': 'robots', 'error_code': 'timeout'}]
    assert 'private-request-details' not in json.dumps(result)
