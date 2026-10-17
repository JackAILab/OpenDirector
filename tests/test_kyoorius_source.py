import pytest
from harness.models.reference_sources import kyoorius


LISTING = '''
<div class="winners cat_all cat_film blue_elephant">
<h4 class='title'>Film<br>Online &amp; Social Films &gt; 15 to 30 Seconds</h4>
<a href="/?action=ows:entries.details&amp;e=184650&amp;project_year=2025"><img data-original="https://cdn1.bubblevault.com/poster.jpg"></a>
<div class="prize"><h3>Blue Elephant</h3></div>
<div class="credits"><h4>Rishabh Pant x Swiggy Bolt</h4><p>Swiggy</p></div>
<div class="company-details"><span>Swiggy</span></div>
</div>
'''


DETAIL = '''
<h3 class="title"><strong>Rishabh Pant x Swiggy Bolt</strong></h3>
<img data-type="video" data-video-src="https://bv-04.bubblevault.com/id/mp4/720x480/film.mp4" src="https://bv-04.bubblevault.com/id/jpg/720x480/poster.jpg">
<small class="mp4-duration">20s</small>
<strong>Brand:</strong> Swiggy<br><strong>Client:</strong> Swiggy<br><strong>Entrant:</strong> Swiggy<br>
'''


def test_parse_listing_is_bounded_and_film_only():
    rows = kyoorius.parse_listing(LISTING * 20, max_entries=3)
    assert len(rows) == 1
    assert rows[0]['title'] == 'Rishabh Pant x Swiggy Bolt'
    assert rows[0]['source_url'].startswith(kyoorius.ORIGIN + '/?action=ows:entries.details')
    assert rows[0]['media_status'] == 'source_link'


def test_parse_detail_validates_public_video_and_duration():
    detail = kyoorius.parse_detail(DETAIL, 'https://example.test/entry')
    assert detail['has_video'] is True
    assert detail['duration'] == 20.0
    assert detail['video_url'].endswith('/film.mp4')
    record = kyoorius.apply_detail(kyoorius.parse_listing(LISTING)[0], detail)
    assert record['creative_structure']['public_video_url'] == detail['video_url']
    assert record['creative_structure']['duration_seconds'] == 20.0


def test_rejects_signed_or_untrusted_video_urls():
    bad = DETAIL.replace('https://bv-04.bubblevault.com/id/mp4/720x480/film.mp4',
                         'https://evil.example/film.mp4?token=x')
    assert kyoorius.parse_detail(bad, 'https://example.test/entry')['has_video'] is False


def test_craft_page_is_in_the_bounded_rotation():
    assert '/winners/2025/craft' in kyoorius.LISTING_PATHS


def test_year_landing_page_is_in_the_bounded_rotation():
    assert '/winners/2025' in kyoorius.LISTING_PATHS


@pytest.mark.parametrize('level,kind', [
    ('The First List', 'award_shortlist'), ('First List', 'award_shortlist'),
    ('Blue Elephant', 'award_winner'), ('Baby Blue Elephant', 'award_winner'),
    ('Baby Black Elephant', 'award_winner'),
    ('', 'award_listing'), ('Unrecognized award', 'award_listing'),
])
def test_preserves_first_round_and_specific_elephant_recognition(level, kind):
    record = kyoorius.parse_listing(LISTING.replace('<h3>Blue Elephant</h3>', f'<h3>{level}</h3>'))[0]
    assert record['quality_evidence'][0]['kind'] == kind
    assert '官方获奖片' not in record['source_name']
    if level:
        assert level in record['quality_evidence'][0]['text']
    else:
        assert '奖项级别待核实' in record['quality_evidence'][0]['text']
