import pytest
from harness.models.reference_sources import ciclope

LISTING='''<div class="video-container all grand_prix" id="200155" data-entry-id="200155"><p class="title">No Project Without Drama - HORNBACH</p><h3 class="prize Grand Prix"><span>Grand Prix</span></h3><h4 class="category"><span data-category-1="PRODUCTION">PRODUCTION</span></h4><video src="https://bv-04.bubblevault.com/clips/id/clip/id_clip.mp4"></video></div><div class="video-container all gold" id="200156" data-entry-id="200156"><p class="title">Music - Artist</p><h3 class="prize"><span>Gold</span></h3><h4 class="category"><span data-category-1="MUSIC VIDEO">MUSIC VIDEO</span></h4></div>'''
DETAIL='''<p class="entry-title">No Project Without Drama</p><video poster="https://bv-04.bubblevault.com/id/poster/jpg/720x480/poster.jpg"><source src="https://bv-04.bubblevault.com/id/film/mp4/720x480/film.mp4" type="video/mp4"></video><table><tr><th><strong><small>Client</small></strong></th></tr><tr><td>HORNBACH</td></tr><tr><th><strong><small>Director</small></strong></th></tr><tr><td>Lope Serrano</td></tr></table>'''

def test_listing_excludes_music_video():
    rows=ciclope.parse_listing(LISTING,year=2025,max_entries=3)
    assert len(rows)==1 and rows[0]['title']=='No Project Without Drama'


def test_category_attributes_do_not_leak_into_visible_text():
    listing = LISTING.replace(
        '<span data-category-1="PRODUCTION">PRODUCTION</span>',
        '<span data-category-1="CICLOPE CRAFT" '
        'title="CICLOPE Craft > FASHION &amp; LUXURY">'
        'DIRECTION &gt; <strong>FASHION &amp; LUXURY</strong></span>')
    record = ciclope.parse_listing(listing, year=2026)[0]
    assert record['creative_structure']['category'] == 'DIRECTION > FASHION & LUXURY'
    assert record['creative_structure']['section'] == 'CICLOPE CRAFT'
    assert record['title'] == 'No Project Without Drama'
    assert record['brand'] == 'HORNBACH'


@pytest.mark.parametrize('category,expected_count', [
    ('CICLOPE Entertainment - MUSIC VIDEO > DIRECTION', 1),
    ('CICLOPE Craft - SOUND &amp; MUSIC > ORIGINAL MUSIC', 2),
])
def test_nested_music_video_category_is_excluded_but_ad_music_is_kept(category, expected_count):
    listing = LISTING.replace(
        '<span data-category-1="MUSIC VIDEO">MUSIC VIDEO</span>',
        f'<span data-category-1="CICLOPE ENTERTAINMENT">{category}</span>')
    assert len(ciclope.parse_listing(listing, year=2026)) == expected_count

def test_detail_extracts_video_and_credits():
    detail=ciclope.parse_detail(DETAIL,'https://example.test')
    assert detail['has_video'] and detail['client']=='HORNBACH'
    record=ciclope.apply_detail(ciclope.parse_listing(LISTING,year=2025)[0],detail)
    assert record['creative_structure']['director']=='Lope Serrano'

def test_rejects_untrusted_video():
    bad=DETAIL.replace('https://bv-04.bubblevault.com/id/film/mp4/720x480/film.mp4','https://evil.example/x.mp4?token=x')
    assert not ciclope.parse_detail(bad,'x')['has_video']

def test_year_validation():
    assert ciclope.listing_url(2024).endswith('/winners/2024')


@pytest.mark.parametrize('award,kind', [('Finalist','award_finalist'),('Shortlist','award_shortlist'),('', 'award_listing'),('Gold','award_winner')])
def test_listing_preserves_actual_award_level(award, kind):
    listing=LISTING.replace('Grand Prix',award)
    record=ciclope.parse_listing(listing,year=2025)[0]
    assert record['quality_evidence'][0]['kind']==kind
    assert '官方获奖片' not in record['source_name']
    if not award:assert 'winner' not in record['quality_evidence'][0]['text']
