from harness.models.reference_sources import british_arrows


LISTING = '''
<article><div><img src="https://british-arrows.transforms.svdcdn.com/production/films/attABC.jpg?w=800&amp;s=temporary"></div>
<div><div>ARROWS GOLD</div><div><span>BEST UP TO &amp; INCLUDING 15 SECOND COMMERCIAL</span></div></div>
<h3><a href="/films/british-arrows/2025/teenage-cat-temptations">Temptations — Teenage Cat</a></h3><p>BA2025</p></article>
<article><div><div>SPECIAL</div><div><span>PRODUCTION COMPANY OF THE YEAR</span></div></div>
<h3><a href="/films/british-arrows/2025/production-company">Production Company of the Year</a></h3></article>
'''

DETAIL = '''
<h1>Temptations — Teenage Cat</h1>
<iframe src="https://player.vimeo.com/video/1063216406?byline=0&amp;portrait=0&amp;dnt=1&amp;title=0"></iframe>
<div><h3>Advertising Agency</h3></div><a>adam&amp;eveDDB</a>
<div><h3>Production Company</h3></div><a>SMUGGLER</a>
<div><h3>Director</h3></div><a>Randy Krallman</a>
<div>ARROWS GOLD</div><div><span>BEST UP TO &amp; INCLUDING 15 SECOND COMMERCIAL</span></div>
'''


def test_listing_keeps_commercial_and_rejects_special():
    rows, pages = british_arrows.parse_listing(LISTING, 2025)
    assert pages == 1
    assert len(rows) == 1
    assert rows[0]['title'] == 'Teenage Cat'
    assert rows[0]['ad_type'].endswith('15秒以内奖项')
    assert rows[0]['thumbnail_url'].endswith('/production/films/attABC.jpg')


def test_detail_extracts_vimeo_and_credits():
    rows, _ = british_arrows.parse_listing(LISTING, 2025)
    result = british_arrows.apply_detail(rows[0], DETAIL)
    assert result['embed_url'] == 'https://vimeo.com/1063216406'
    assert result['creative_structure']['production_company'] == 'SMUGGLER'
    assert result['creative_structure']['director'] == 'Randy Krallman'


def test_rejects_untrusted_embed():
    rows, _ = british_arrows.parse_listing(LISTING, 2025)
    bad = DETAIL.replace('https://player.vimeo.com/video/1063216406?byline=0&amp;portrait=0&amp;dnt=1&amp;title=0',
                         'https://player.vimeo.com/video/1063216406?h=private')
    try:
        british_arrows.apply_detail(rows[0], bad)
    except ValueError:
        return
    assert british_arrows.apply_detail(rows[0], bad) is None


def test_year_and_page_validation():
    assert british_arrows.listing_url(2025, 2).endswith('/2025/p2')
    try:
        british_arrows.listing_url(2022)
    except ValueError as exc:
        assert str(exc) == 'invalid_british_arrows_year'
    else:
        raise AssertionError('invalid year accepted')
