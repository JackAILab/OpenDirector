import json

import pytest

from harness.models.reference_sources import mother_london as source


def project(**updates):
    return {'_type': 'project', 'title': 'Example Brand', 'tagline': 'A visible result',
            'slug': 'visible-result', 'filters': {'year': 2026},
            'slideshow': [{'mediaType': 'video', 'video': {'id': '1234567890'}}],
            'featuredImage': {'url': 'https://cdn.sanity.io/images/test/production/abcd1234-1920x1080.png'},
            'content': [{'private_note': 'do not retain'}], **updates}


def page(data):
    return '<script type="application/json" id="__NEXT_DATA__">' + json.dumps({
        'props': {'pageProps': {'data': data, 'previewToken': 'must-not-escape'}}}) + '</script>'


def listing(*projects):
    return page({'modules': [{'projects': list(projects)}]})


def test_actual_portfolio_year_deduplication_primary_video_and_private_fields():
    old = project(slug='prior-year', filters={'year': 2025})
    data = listing(project(), old, project())
    rows = source.parse_listing(data, year=2026, max_entries=None)
    assert len(rows) == 1
    row = rows[0]
    assert row['title'] == 'A visible result' and row['brand'] == 'Example Brand'
    assert row['published'] == '2026'
    assert not row.get('embed_url')
    assert row['creative_structure']['source_video_urls'] == ['https://vimeo.com/1234567890']
    assert row['creative_structure']['preview_mode'] == 'official_source_only'
    assert row['media_status'] == 'source_link' and row['training_eligible'] is False
    assert row['media_role'] == 'work_or_case_film_unverified'
    assert row['quality_evidence'][0]['kind'] == 'official_portfolio'
    assert 'public_video_url' not in row['creative_structure']  # no direct-download claim
    assert 'must-not-escape' not in json.dumps(row) and 'do not retain' not in json.dumps(row)
    assert source.parse_listing(data, year=2025)[0]['source_url'].endswith('/prior-year')


@pytest.mark.parametrize('identity', ['123456?token=secret', 'https://vimeo.com/123456',
                                      '../123456', 123456, '0', None])
def test_rejects_nonpublic_or_malformed_video_identities(identity):
    p = project(slideshow=[{'mediaType': 'video', 'video': {'id': identity}}])
    assert source.parse_listing(listing(p)) == []
    assert source.parse_detail(page(p), source.ORIGIN + '/work/visible-result') == {'has_video': False}


def test_rejects_image_only_projects_and_unsigned_poster_boundaries():
    assert source.parse_listing(listing(project(slideshow=[{'mediaType': 'image'}]))) == []
    for url in ['http://cdn.sanity.io/images/test/production/abcd-1x1.png',
                'https://cdn.sanity.io.evil.test/images/test/production/abcd-1x1.png',
                'https://cdn.sanity.io/images/test/production/abcd-1x1.png?token=secret']:
        row = source.parse_listing(listing(project(featuredImage={'url': url})))[0]
        assert row['thumbnail_url'] == '' and row['creative_structure']['source_video_urls']


def test_detail_identity_and_year_must_match_listing():
    p = project()
    row = source.parse_listing(listing(p))[0]
    detail = source.parse_detail(page(p), row['source_url'])
    assert source.apply_detail(row, detail) == row
    with pytest.raises(ValueError, match='detail_identity_mismatch'):
        source.parse_detail(page(project(slug='another')), row['source_url'])
    moved = source.parse_detail(page(project(filters={'year': 2025})), row['source_url'])
    with pytest.raises(ValueError, match='detail_identity_mismatch'):
        source.apply_detail(row, moved)


def test_listing_limits_and_url_encoding_never_accept_external_paths():
    rows = [project(slug=f'project-{n}') for n in range(20)]
    assert len(source.parse_listing(listing(*rows))) == 12
    assert len(source.parse_listing(listing(*rows), max_entries=None)) == 20
    p = project(slug="Brand's-new&work")
    assert source.parse_listing(listing(p))[0]['source_url'].endswith('/Brand%27s-new%26work')
    for slug in ['../escape', '//evil.test', 'a?token=secret', 'a%2fb', '..']:
        assert source.parse_listing(listing(project(slug=slug))) == []
    with pytest.raises(ValueError, match='invalid_mother_london_year'):
        source.listing_url(True)


@pytest.mark.parametrize('text', ['no JSON here', page([]), '<script id="__NEXT_DATA__">{</script>', page({})])
def test_source_layout_failures_are_explicit(text):
    with pytest.raises(ValueError, match='source_layout_changed'):
        source.parse_listing(text)


def test_runner_reuses_bounded_archive_action_without_generating(monkeypatch):
    from tools import collect_mother_london as runner
    calls = []
    monkeypatch.setattr(runner, 'collect_archive', lambda *args: calls.append(args) or {'state': 'completed'})
    assert runner.run(2026)['state'] == 'completed'
    assert calls == [(source, runner.SOURCE, 'mother_london', 2026, None, 10)]
