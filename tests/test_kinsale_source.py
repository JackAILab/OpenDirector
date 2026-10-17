from harness.models.reference_sources import kinsale


LISTING = '''
<div class="winners prettybird automotive_including_auto_products_and_services gold">
<h4 class='title'>ADVERTISING FILM 2025</h4>
<a href="/?action=ows:entries.details&amp;e=196048&amp;project_year=2025"><img data-original="https://images.bubblevault.com/unsafe/poster.jpg"></a>
<div class="prize"><h3>Gold</h3></div><p>INTERNATIONAL</p><strong>Automotive</strong>
<div class="credits"><h4>Thank You, Lewis</h4><p>Mercedes</p></div>
<div class="company-details">Entrant Co: <span>PRETTYBIRD</span><p>United Kingdom</p></div>
</div>
<div class="winners other"><h4 class='title'>DESIGN 2025</h4></div>
'''


DETAIL = '''
<h3 class="title"><strong>Thank You, Lewis</strong></h3>
<table><tr><th>Brand:</th><td>Mercedes</td></tr><tr><th>Client:</th><td>Mercedes</td></tr>
<tr><th>Production Company:</th><td>PRETTYBIRD</td></tr><tr><th>Agency:</th><td>AMV DDBO</td></tr>
<tr><th>Director:</th><td>Melina Matsoukas</td></tr></table>
<img data-type="video" data-video-src="https://bv-04.bubblevault.com/id/mp4/720x480/film.mp4" src="https://bv-04.bubblevault.com/id/jpg/720x480/poster.jpg">
<small class="mp4-duration">1m:50s</small>
'''


def test_listing_restricts_to_advertising_film_and_is_bounded():
    rows = kinsale.parse_listing(LISTING * 20, year=2025, max_entries=3)
    assert len(rows) == 1
    assert rows[0]['title'] == 'Thank You, Lewis'
    assert rows[0]['source_url'].startswith(kinsale.ORIGIN + '/?action=ows:entries.details')


def test_detail_extracts_public_video_duration_and_credits():
    detail = kinsale.parse_detail(DETAIL, 'https://example.test/entry')
    assert detail['has_video'] is True
    assert detail['duration'] == 110.0
    record = kinsale.apply_detail(kinsale.parse_listing(LISTING, year=2025)[0], detail)
    assert record['creative_structure']['public_video_url'] == detail['video_url']
    assert record['creative_structure']['director'] == 'Melina Matsoukas'


def test_rejects_untrusted_video_url():
    bad = DETAIL.replace('https://bv-04.bubblevault.com/id/mp4/720x480/film.mp4', 'https://evil.example/film.mp4?token=x')
    assert kinsale.parse_detail(bad, 'https://example.test/entry')['has_video'] is False


def test_year_rotation_accepts_historical_listing_year():
    historical = LISTING.replace('2025', '2024').replace('project_year=2025', 'project_year=2024')
    assert kinsale.parse_listing(historical, year=2024)[0]['published'] == '2024'
    assert kinsale.listing_url(2024).endswith('/winners/2024')


def test_award_evidence_preserves_unknown_and_nomination_levels():
    for award, kind in [('Winner', 'award_winner'), ('Shortlist', 'award_shortlist'), ('Finalist', 'award_finalist'), ('', 'award_listing')]:
        listing = LISTING.replace('<h3>Gold</h3>', '<h3>' + award + '</h3>')
        record = kinsale.parse_listing(listing, year=2025)[0]
        assert record['quality_evidence'][0]['kind'] == kind
        assert '官方获奖片' not in record['source_name']
        if not award:
            assert '奖项级别待核实' in record['quality_evidence'][0]['text']
