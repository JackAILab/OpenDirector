import pytest
from harness.models.reference_sources import cresta

LISTING='''<div class="winners tv_or_cinema grand"><h4 class="title">1: MOVING IMAGE <span class="year">2025</span></h4><a href="/?action=ows:entries.details&amp;e=192336&amp;project_year=2025"><img></a><div class="prize"><h3>Grand Prix</h3></div><strong>TV or Cinema Commercial over 60 seconds</strong><div class="credits"><h4>Never Just A Period</h4><p>Essity</p></div><div class="company-details"><span>AMVBBDO</span></div></div><div class="winners"><h4 class="title">2: DIGITAL <span class="year">2025</span></h4></div>'''
DETAIL='''<h3 class="title"><strong>Never Just A Period</strong></h3><div class="details-media"><img data-type="video" data-video-src="https://bv-04.bubblevault.com/id/film/mp4/720x480/film.mp4" src="https://bv-04.bubblevault.com/id/poster/jpg/720x480/poster.jpg"><small class="mp4-duration">2m:25s</small></div><table><tr><th>Brand:</th><td>Essity</td></tr><tr><th>Client:</th><td>Essity</td></tr><tr><th>Entrant Company:</th><td>AMVBBDO</td></tr></table>'''

def test_listing_limits_to_video_sections():
    rows=cresta.parse_listing(LISTING,year=2025,max_entries=3)
    assert len(rows)==1 and rows[0]['title']=='Never Just A Period'

def test_detail_extracts_video_duration_and_fields():
    detail=cresta.parse_detail(DETAIL,'https://example.test')
    assert detail['has_video'] and detail['duration']==145.0
    record=cresta.apply_detail(cresta.parse_listing(LISTING,year=2025)[0],detail)
    assert record['creative_structure']['public_video_url']==detail['video_url']

def test_rejects_untrusted_video():
    assert not cresta.parse_detail(DETAIL.replace('https://bv-04.bubblevault.com/id/film/mp4/720x480/film.mp4','https://evil.example/a.mp4?x=1'),'x')['has_video']

def test_year_validation():
    assert cresta.listing_url(2024).endswith('/winners/2024')


@pytest.mark.parametrize('award,kind', [('Finalist','award_finalist'),('Shortlist','award_shortlist'),('', 'award_listing'),('Gold','award_winner')])
def test_listing_preserves_actual_award_level(award, kind):
    listing=LISTING.replace('Grand Prix',award)
    record=cresta.parse_listing(listing,year=2025)[0]
    assert record['quality_evidence'][0]['kind']==kind
    assert '官方获奖片' not in record['source_name']
    if not award:assert 'winner' not in record['quality_evidence'][0]['text']
