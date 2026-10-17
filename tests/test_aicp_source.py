from harness.models.reference_sources.aicp import parse_shortlist


def test_aicp_parser_drops_signed_media_and_keeps_stable_entry():
    html = '''<div class="vid_elem" data-entid="255"><div class="brand ">The Brand</div><span class="campaign">The Campaign</span></div>'''
    record = parse_shortlist(html, 38)[0]
    assert record['title'] == 'The Campaign'
    assert 'entry=255' in record['source_url']
    assert 'X-Amz' not in record['source_url']
    assert 'not_verified' in record['rights']
