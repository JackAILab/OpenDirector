"""Public Cresta Awards moving-image and film-craft winner metadata."""
import html
import re
from html.parser import HTMLParser
from urllib.parse import parse_qs, urljoin, urlsplit, urlunsplit
from harness.models.reference_sources.award_evidence import award_evidence_kind

ORIGIN = 'https://www.cresta-awards.com'
YEARS = (2026, 2025, 2024, 2023)
MAX_ENTRIES = 12
ALLOWED_SECTIONS = ('1: MOVING IMAGE', '16: FILM CRAFT')


def _text(value):
    return re.sub(r'\s+', ' ', html.unescape(re.sub(r'<[^>]*>', ' ', value or ''))).strip()


class _WinnerBlocks(HTMLParser):
    _void = {'area', 'base', 'br', 'col', 'embed', 'hr', 'img', 'input',
             'link', 'meta', 'param', 'source', 'track', 'wbr'}

    def __init__(self):
        super().__init__(convert_charrefs=False)
        self.depth, self.buffer, self.blocks = 0, [], []

    def handle_starttag(self, tag, attrs):
        raw = self.get_starttag_text() or ''
        attrs = dict(attrs)
        if not self.depth and tag == 'div' and 'winners' in (attrs.get('class') or '').split():
            self.depth, self.buffer = 1, [raw]
            return
        if self.depth:
            self.buffer.append(raw)
            if tag not in self._void:
                self.depth += 1

    def handle_startendtag(self, tag, attrs):
        if self.depth:
            self.buffer.append(self.get_starttag_text() or '')

    def handle_endtag(self, tag):
        if not self.depth:
            return
        self.buffer.append(f'</{tag}>')
        if tag not in self._void:
            self.depth -= 1
        if self.depth == 0:
            self.blocks.append(''.join(self.buffer))
            self.buffer = []

    def handle_data(self, data):
        if self.depth:
            self.buffer.append(data)

    def handle_entityref(self, name):
        if self.depth:
            self.buffer.append(f'&{name};')

    def handle_charref(self, name):
        if self.depth:
            self.buffer.append(f'&#{name};')


def _winner_blocks(text):
    parser = _WinnerBlocks()
    parser.feed(text)
    if parser.blocks:
        return parser.blocks
    return re.findall(r'(?is)<div\s+class=["\']winners\b.*?(?=<div\s+class=["\']winners\b|\Z)', text)


def _field(pattern, body):
    match = re.search(pattern, body, re.I | re.S)
    return _text(match.group(1)) if match else ''


def _safe_media(value, ext):
    if not isinstance(value, str):
        return ''
    parts = urlsplit(html.unescape(value.strip()))
    if (parts.scheme != 'https' or parts.username or parts.password
            or parts.port not in (None, 443) or parts.query or parts.fragment):
        return ''
    host = (parts.hostname or '').lower()
    if not re.fullmatch(r'bv-[a-z0-9-]+\.bubblevault\.com', host):
        return ''
    if not re.fullmatch(rf'/(?:[^?#]+/)+{ext}/[^?#]+/[^?#]+\.{ext}', parts.path, re.I):
        return ''
    return urlunsplit(('https', host, parts.path, '', ''))


def listing_url(year):
    if type(year) is not int or year not in YEARS:
        raise ValueError('invalid_cresta_year')
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
    return (origin + '/?action=ows:entries.details&e=' + query['e'][0]
            + f'&project_year={year}')


def parse_listing(text, year=2025, origin=ORIGIN, max_entries=MAX_ENTRIES):
    listing_url(year)
    records, seen = [], set()
    for block in _winner_blocks(text):
        heading = _field(r'<h4\b[^>]*class=["\']title["\'][^>]*>(.*?)</h4>', block)
        heading_upper = heading.upper()
        section = next((s for s in ALLOWED_SECTIONS if heading_upper.startswith(s)), '')
        if not section:
            continue
        href = re.search(r'<a\b[^>]+href=["\']([^"\']*action=ows:entries\.details[^"\']*)', block, re.I)
        title = _field(r'<div\b[^>]*class=["\']credits["\'][^>]*>.*?<h4\b[^>]*>(.*?)</h4>', block)
        brand = _field(r'<div\b[^>]*class=["\']credits["\'][^>]*>.*?<p\b[^>]*>(.*?)</p>', block)
        entrant = _field(r'<div\b[^>]*class=["\']company-details["\'][^>]*>.*?<span\b[^>]*>(.*?)</span>', block)
        award = _field(r'<div\b[^>]*class=["\']prize["\'][^>]*>.*?<h3\b[^>]*>(.*?)</h3>', block)
        category = _field(r'<strong\b[^>]*>(.*?)</strong>', block)
        source_url = _trusted_entry(href.group(1), year, origin) if href else ''
        if not source_url or not title or not brand or source_url in seen:
            continue
        seen.add(source_url)
        records.append({
            'source_url': source_url, 'title': title[:300], 'brand': brand[:200],
            'industry': '待分类', 'ad_type': 'Cresta · ' + section.title(),
            'format': 'video', 'language': 'en', 'source_name': f'Cresta Awards {year} 官方案例',
            'published': str(year),
            'summary': 'Cresta 官方 Moving Image / Film Craft 案例；奖项级别以来源为准，片型、版本、声音和版权待人工确认。',
            'quality_evidence': [{'kind': award_evidence_kind(award), 'text': f'Cresta Awards {year} · {award or "奖项级别待核实"} · {category}', 'source_url': source_url}],
            'thumbnail_url': '', 'media_status': 'source_link',
            'media_role': 'work_or_case_film_unverified',
            'rights': 'reference_only; redistribution_and_training_not_verified',
            'tags': ['Cresta Awards', 'film', section.casefold(), 'human_review_pending'],
            'creative_structure': {'entrant_company': entrant, 'award': award, 'section': section, 'category': category, 'source_page': source_url},
        })
        if max_entries is not None and len(records) >= max_entries:
            break
    return records


def _table_field(label, body):
    return _field(r'<tr>\s*<th[^>]*>\s*' + re.escape(label) + r'\s*</th>\s*<td[^>]*>(.*?)</td>', body)


def _duration(value):
    value = _text(value)
    match = re.fullmatch(r'(?:(\d+)m:)?(\d+(?:\.\d+)?)s', value, re.I)
    return int(match.group(1) or 0) * 60 + float(match.group(2)) if match else None


def parse_detail(text, source_url):
    video = re.search(r'<[^>]+data-type=["\']video["\'][^>]+data-video-src=["\']([^"\']+)', text, re.I | re.S)
    media = _safe_media(video.group(1), 'mp4') if video else ''
    poster_match = re.search(r'<[^>]+data-type=["\']video["\'][^>]+src=["\']([^"\']+)', text, re.I | re.S)
    poster = _safe_media(poster_match.group(1), 'jpg') if poster_match else ''
    duration = _field(r'<small\b[^>]*class=["\']mp4-duration["\'][^>]*>(.*?)</small>', text)
    title = _field(r'<h3\b[^>]*class=["\']title[^>]*>\s*<strong>(.*?)</strong>', text)
    return {'has_video': bool(media), 'video_url': media, 'thumbnail_url': poster,
            'duration': _duration(duration), 'title': title,
            'brand': _table_field('Brand:', text), 'client': _table_field('Client:', text),
            'entrant_company': _table_field('Entrant Company:', text),
            'product': _table_field('Product/Service:', text)}


def apply_detail(record, detail):
    if not detail.get('has_video'):
        return None
    result = dict(record)
    for key, limit in (('title', 300), ('brand', 200)):
        if detail.get(key):
            result[key] = detail[key][:limit]
    if detail.get('thumbnail_url'):
        result['thumbnail_url'] = detail['thumbnail_url']
    result['creative_structure'] = {**record.get('creative_structure', {}),
        'public_video_url': detail['video_url'], 'duration_seconds': detail.get('duration'),
        'client': detail.get('client', ''), 'entrant_company': detail.get('entrant_company', ''),
        'product': detail.get('product', '')}
    result['quality_evidence'] = [*record['quality_evidence'], {
        'kind': 'public_video_metadata',
        'text': f"官方详情页公开 MP4，标示时长 {detail['duration']:g} 秒；作品身份、声音和版本待人工确认。" if detail.get('duration') is not None else '官方详情页公开 MP4；片长、声音和版本待人工确认。',
        'source_url': record['source_url']}]
    return result
