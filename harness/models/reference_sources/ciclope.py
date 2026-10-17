"""Public CICLOPE Festival advertising and craft winner metadata."""
import html
from html.parser import HTMLParser
import re
from urllib.parse import parse_qs, urljoin, urlsplit, urlunsplit
from harness.models.reference_sources.award_evidence import award_evidence_kind

ORIGIN = 'https://awards.ciclopefestival.com'
YEARS = (2026, 2025, 2024, 2023)
MAX_ENTRIES = 12
EXCLUDED_SECTIONS = {'MUSIC VIDEO'}


class _TextContent(HTMLParser):
    """Read visible text without treating '>' inside attributes as tag endings."""

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.parts = []

    def handle_data(self, data):
        self.parts.append(data)


def _text(value):
    parser = _TextContent()
    parser.feed(value or '')
    parser.close()
    return re.sub(r'\s+', ' ', ' '.join(parser.parts)).strip()


def _field(pattern, body):
    match = re.search(pattern, body, re.I | re.S)
    return _text(match.group(1)) if match else ''


def _blocks(text):
    return re.findall(r'(?is)<div\s+class=["\']video-container\b.*?(?=<div\s+class=["\']video-container\b|\Z)', text)


def _safe_url(value, kind):
    if not isinstance(value, str):
        return ''
    parts = urlsplit(html.unescape(value.strip()))
    if (parts.scheme != 'https' or parts.username or parts.password
            or parts.port not in (None, 443) or parts.query or parts.fragment):
        return ''
    host = (parts.hostname or '').lower()
    if not re.fullmatch(r'bv-[a-z0-9-]+\.bubblevault\.com', host):
        return ''
    if kind == 'mp4':
        pattern = r'/(?:[^?#]+/){1,3}mp4/[^?#]+/[^?#]+\.mp4'
    else:
        pattern = r'/(?:[^?#]+/){1,3}jpg/[^?#]+/[^?#]+\.jpg'
    if not re.fullmatch(pattern, parts.path, re.I):
        return ''
    return urlunsplit(('https', host, parts.path, '', ''))


def listing_url(year):
    if type(year) is not int or year not in YEARS:
        raise ValueError('invalid_ciclope_year')
    return ORIGIN + f'/winners/{year}'


def _trusted_entry(value, year, origin=ORIGIN):
    parts = urlsplit(urljoin(origin + '/', html.unescape(value or '')))
    if parts.scheme != 'https' or parts.netloc != urlsplit(origin).netloc or parts.path != '/':
        return ''
    query = parse_qs(parts.query, keep_blank_values=True)
    if query.get('action') != ['ows:entries.details'] or query.get('project_year') != [str(year)]:
        return ''
    if len(query.get('e', [])) != 1 or not re.fullmatch(r'\d+', query['e'][0]):
        return ''
    return (origin + '/?action=ows:entries.details&isNotAjax=true&project_year='
            + str(year) + '&e=' + query['e'][0])


def parse_listing(text, year=2025, origin=ORIGIN, max_entries=MAX_ENTRIES):
    listing_url(year)
    records, seen = [], set()
    for block in _blocks(text):
        section = _field(r'data-category-1=["\']([^"\']+)', block).upper()
        category = _field(r'<h4\b[^>]*class=["\']category["\'][^>]*>(.*?)</h4>', block)
        category_parts = set(re.split(r'\s+(?:-|>)\s+', category.upper()))
        if EXCLUDED_SECTIONS.intersection({section, *category_parts}):
            continue
        entry_id = re.search(r'data-entry-id=["\'](\d+)["\']', block, re.I)
        title_line = _field(r'<p\b[^>]*class=["\']title["\'][^>]*>(.*?)</p>', block)
        award = _field(r'<h3\b[^>]*class=["\']prize[^>]*>.*?<span>(.*?)</span>', block)
        if not entry_id or not title_line:
            continue
        source_url = _trusted_entry(f'/?action=ows:entries.details&e={entry_id.group(1)}&project_year={year}', year, origin)
        if not source_url or source_url in seen:
            continue
        seen.add(source_url)
        pieces = re.split(r'\s+-\s+', title_line, maxsplit=1)
        title, brand = pieces[0].strip(), (pieces[1].strip() if len(pieces) > 1 else '')
        records.append({
            'source_url': source_url, 'title': title[:300], 'brand': brand[:200],
            'industry': '待分类', 'ad_type': 'CICLOPE · ' + (section.title() or 'Film Craft'),
            'format': 'video', 'language': 'en', 'source_name': f'CICLOPE Festival {year} 官方案例',
            'published': str(year),
            'summary': 'CICLOPE 官方广告与制作工艺案例；奖项级别以来源为准，详情页 MP4、声音、版本和版权仍待人工确认。',
            'quality_evidence': [{'kind': award_evidence_kind(award), 'text': f'CICLOPE Festival {year} · {award or "奖项级别待核实"} · {section or category}', 'source_url': source_url}],
            'thumbnail_url': '', 'media_status': 'source_link',
            'media_role': 'work_or_case_film_unverified',
            'rights': 'reference_only; redistribution_and_training_not_verified',
            'tags': ['CICLOPE', 'film', section.casefold() or 'craft', 'human_review_pending'],
            'creative_structure': {'section': section, 'category': category, 'award': award, 'source_page': source_url},
        })
        if max_entries is not None and len(records) >= max_entries:
            break
    return records


def parse_detail(text, source_url):
    source = re.search(r'<source\b[^>]*src=["\']([^"\']+)["\'][^>]*type=["\']video/mp4["\']', text, re.I | re.S)
    media = _safe_url(source.group(1), 'mp4') if source else ''
    poster_match = re.search(r'<video\b[^>]*poster=["\']([^"\']+)', text, re.I | re.S)
    poster = _safe_url(poster_match.group(1), 'jpg') if poster_match else ''
    fields = {}
    for label, value in re.findall(r'<tr>\s*<th[^>]*>.*?<small>(.*?)</small>.*?</th>\s*</tr>\s*<tr>\s*<td[^>]*>(.*?)</td>', text, re.I | re.S):
        fields[_text(label).casefold()] = _text(value)
    return {'has_video': bool(media), 'video_url': media, 'thumbnail_url': poster,
            'title': fields.get('title', _field(r'<p\b[^>]*class=["\']entry-title["\'][^>]*>(.*?)</p>', text)),
            'brand': fields.get('client', ''), 'client': fields.get('client', ''),
            'production_company': fields.get('production company', ''),
            'agency': fields.get('advertising agency', ''),
            'director': fields.get('director', ''), 'entrant_company': fields.get('entrant company', '')}


def apply_detail(record, detail):
    if not detail.get('has_video'):
        return None
    result = dict(record)
    if detail.get('title'):
        result['title'] = detail['title'][:300]
    if detail.get('brand'):
        result['brand'] = detail['brand'][:200]
    if detail.get('thumbnail_url'):
        result['thumbnail_url'] = detail['thumbnail_url']
    result['creative_structure'] = {**record.get('creative_structure', {}),
        'public_video_url': detail['video_url'], 'client': detail.get('client', ''),
        'production_company': detail.get('production_company', ''), 'agency': detail.get('agency', ''),
        'director': detail.get('director', ''), 'entrant_company': detail.get('entrant_company', '')}
    result['quality_evidence'] = [*record['quality_evidence'], {'kind': 'public_video_metadata',
        'text': '官方详情页公开 MP4 与海报；片长、声音、版本和品牌事实待人工确认。',
        'source_url': record['source_url']}]
    return result
