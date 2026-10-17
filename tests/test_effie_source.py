from harness.models.reference_sources import effie


ARCHIVE = '''
<div class="card case-card">
  <div class="card-image landscape"><img src="https://cdn.example.test/hero.jpg" alt="Picture a Win"></div>
  <div class="card-content"><h4 class="nc">Picture a Win</h4><div class="meta">
    <div class="nc"><strong>Brand:</strong> New York Lottery</div>
    <div class="nc"><strong>Award Level:</strong> Bronze</div>
    <div class="nc"><strong>Category:</strong> Artificial Intelligence (AI)</div>
    <div class="nc"><strong>Program:</strong> United States</div>
    <div class="nc"><strong>Year:</strong> 2024</div>
  </div><a href="https://effie.org/cases/picture-a-win/" class="btn">Explore this case</a></div>
</div>
'''


DETAIL = '''
<div class="intro-video"><video data-poster="/poster.jpg"><source src="/film.mp4" type="video/mp4" /></video></div>
'''


def test_parse_archive_keeps_official_case_fields_and_source_link():
    records = effie.parse_archive(ARCHIVE)
    assert len(records) == 1
    record = records[0]
    assert record['title'] == 'Picture a Win'
    assert record['brand'] == 'New York Lottery'
    assert record['source_url'] == 'https://effie.org/cases/picture-a-win/'
    assert record['media_role'] == 'case_film_unverified'
    assert 'training_eligible' not in record  # store.ingest adds the closed gate


def test_parse_detail_resolves_only_stable_public_media_links():
    media = effie.parse_detail(DETAIL, 'https://effie.org/cases/picture-a-win/')
    assert media == {
        'embed_url': 'https://effie.org/film.mp4',
        'thumbnail_url': 'https://effie.org/poster.jpg',
        'has_video': True,
    }


def test_archive_parser_is_bounded_to_one_page():
    records = effie.parse_archive(ARCHIVE * 20)
    assert len(records) <= effie.MAX_CASES
