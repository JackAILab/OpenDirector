from harness.models.reference_sources import berlin_commercial


LISTING = '''
<div class="winners park_pictures cat_commercials_and_branded_content_short gold winner" id="214043" data-entry-id="214043">
<h4 class='title'><br>COMMERCIALS AND BRANDED CONTENT - SHORT</h4>
<div class="prize"><h3>Winner</h3></div><strong>COMMERCIALS AND BRANDED CONTENT - SHORT</strong>
<div class="credits"><h4>Love Hurts</h4><p>Vaseline</p><p>Park Pictures</p></div>
<div class="company-details"><span>Savanah Leaf</span></div></div>
<div class="winners cat_music_videos" data-entry-id="214044"><h4 class='title'>MUSIC VIDEOS</h4></div>
'''


DETAIL = '''
<h1 class="entry-details"><span class="title">Love Hurts</span></h1>
<video poster="https://bv-04.bubblevault.com/id/poster/jpg/720x480/poster.jpg"><source src="https://bv-04.bubblevault.com/id/film/mp4/720x480/film.mp4" type="video/mp4"></video>
<div class="credits-container"><h2><span class="left">CLIENT/BRAND</span><span class="right">VASELINE</span></h2>
<h2><span class="left">PRODUCTION COMPANY</span><span class="right">PARK PICTURES</span></h2>
<h2><span class="left">DIRECTOR(S)</span><span class="right">SAVANAH LEAF</span></h2>
<h2><span class="left">AGENCY</span><span class="right">OGILVY SINGAPORE</span></h2></div>
'''


def test_listing_restricts_to_commercial_and_craft_and_is_bounded():
    rows = berlin_commercial.parse_listing(LISTING * 20, year=2026, max_entries=3)
    assert len(rows) == 1
    assert rows[0]['title'] == 'Love Hurts'
    assert rows[0]['source_url'].endswith('project_year=2026&e=214043')


def test_detail_extracts_public_video_and_credits():
    detail = berlin_commercial.parse_detail(DETAIL, 'https://example.test/entry')
    assert detail['has_video'] is True
    record = berlin_commercial.apply_detail(berlin_commercial.parse_listing(LISTING, year=2026)[0], detail)
    assert record['creative_structure']['public_video_url'] == detail['video_url']
    assert record['creative_structure']['director'] == 'SAVANAH LEAF'


def test_rejects_untrusted_video_url():
    bad = DETAIL.replace('https://bv-04.bubblevault.com/id/film/mp4/720x480/film.mp4', 'https://evil.example/film.mp4?token=x')
    assert berlin_commercial.parse_detail(bad, 'https://example.test/entry')['has_video'] is False


def test_year_rotation_accepts_historical_listing_year():
    historical = LISTING.replace('2026', '2024')
    assert berlin_commercial.parse_listing(historical, year=2024)[0]['published'] == '2024'
    assert berlin_commercial.listing_url(2024).endswith('/winners/2024')


def test_award_evidence_preserves_unknown_and_nomination_levels():
    for award, kind in [('Winner', 'award_winner'), ('Shortlist', 'award_shortlist'), ('Finalist', 'award_finalist'), ('', 'award_listing')]:
        listing = LISTING.replace('<h3>Winner</h3>', '<h3>' + award + '</h3>')
        record = berlin_commercial.parse_listing(listing, year=2026)[0]
        assert record['quality_evidence'][0]['kind'] == kind
        assert '官方获奖片' not in record['source_name']
        if not award:
            assert '奖项级别待核实' in record['quality_evidence'][0]['text']


def test_detail_restores_medium_hidden_by_flat_craft_listing():
    from harness.library.browse_groups import group_ids
    import copy
    listing = LISTING.replace('COMMERCIALS AND BRANDED CONTENT - SHORT', 'Craft: Idea')
    record = berlin_commercial.parse_listing(listing, year=2026)[0]
    before = copy.deepcopy(record)
    for section, groups in [('Music Videos', ('sound', 'craft')),
                            ('Personal Work', ('craft', 'visual')),
                            ('Commercials and Branded Content', ('film', 'branded', 'craft'))]:
        header = ('<h1 class="entry-details"><span class="title">Film</span>'
                  '<span class="category">'+section+': </span>'
                  '<span class="subcategory">Craft: Idea</span></h1>')
        html = DETAIL.replace('<h1 class="entry-details"><span class="title">Love Hurts</span></h1>', header)
        # Unrelated navigation labels must not change the entry's own medium.
        html = '<nav><span class="category">Commercials and Branded Content</span></nav>'+html
        detail = berlin_commercial.parse_detail(html, record['source_url'])
        actual = berlin_commercial.apply_detail(record, detail)
        assert group_ids(actual['ad_type']) == groups
        assert actual['creative_structure']['section'] == section
        assert actual['creative_structure']['listing_category'] == 'Craft: Idea'
        assert actual['quality_evidence'][-1]['text'] == '官方详情页类别：'+section+' / Craft: Idea'
        assert actual['quality_evidence'][0] == record['quality_evidence'][0]
        assert actual['media_role'] == 'work_or_case_film_unverified'
        assert record == before


def test_missing_detail_section_does_not_guess_medium_from_title():
    listing = LISTING.replace('COMMERCIALS AND BRANDED CONTENT - SHORT', 'Craft: Idea')
    record = berlin_commercial.parse_listing(listing, year=2026)[0]
    detail = berlin_commercial.parse_detail(DETAIL.replace('Love Hurts', 'Artist - Music Video'), record['source_url'])
    actual = berlin_commercial.apply_detail(record, detail)
    assert actual['ad_type'] == 'Berlin Commercial · Craft: Idea'
    assert 'section' not in actual['creative_structure']


def test_historical_commercial_section_survives_ingest_and_film_filter(tmp_path, monkeypatch):
    """Actual 2024 header naming must be discoverable without promoting music."""
    from harness.library import store
    monkeypatch.setattr(store, 'ROOT', tmp_path)
    ids = []
    for n, section in enumerate(('Commercial Work', 'Music Videos')):
        listing = LISTING.replace('214043', str(159298 + n)).replace(
            'COMMERCIALS AND BRANDED CONTENT - SHORT', 'Craft: Colour Grading')
        record = berlin_commercial.parse_listing(listing, year=2024)[0]
        header = ('<h1 class="entry-details"><span class="title">Love Hurts</span>'
                  '<span class="category">' + section + ': </span>'
                  '<span class="subcategory">Craft: Colour Grading</span></h1>')
        detail = berlin_commercial.parse_detail(DETAIL.replace(
            '<h1 class="entry-details"><span class="title">Love Hurts</span></h1>', header), record['source_url'])
        ids.append(store.ingest(berlin_commercial.apply_detail(record, detail))[0])
    with store.connection() as db:
        before = [tuple(r) for r in db.execute('SELECT * FROM items ORDER BY id')]
    result = store.list_items(0, ad_group='film')
    assert [item['id'] for item in result['items']] == [ids[0]]
    assert result['items'][0]['ad_type'] == 'Berlin Commercial · Commercial Work / Craft: Colour Grading'
    assert result['items'][0]['review']['state'] == 'pending'
    assert result['items'][0]['training_eligible'] is False
    assert [item['id'] for item in store.list_items(0, ad_group='sound')['items']] == [ids[1]]
    assert {item['id'] for item in store.list_items(0, ad_group='craft')['items']} == set(ids)
    with store.connection() as db:
        assert before == [tuple(r) for r in db.execute('SELECT * FROM items ORDER BY id')]
        assert db.execute('SELECT COUNT(*) FROM reviews').fetchone()[0] == 0
