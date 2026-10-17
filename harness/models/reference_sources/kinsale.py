"""Public Kinsale Shark Awards advertising-film metadata.

The public AwardsEngine pages expose bounded winner cards and detail pages with
BubbleVault MP4 files.  We keep those URLs as source evidence only; the
collector never downloads or republishes the source media.
"""
import html
import re
from harness.models.reference_sources.award_evidence import award_evidence_kind
from html.parser import HTMLParser
from urllib.parse import urljoin, urlsplit, urlunsplit

ORIGIN = 'https://kinsalesharks.awardsengine.com'
YEARS = (2026, 2025, 2024, 2023)
LISTING_PATH = '/winners/2025'
MAX_ENTRIES = 12
MEDIUMS = {
    'ADVERTISING FILM',
    'FILM CRAFT',
    'FILM CRAFT - ANIMATION / CGI / VFX',
    'MUSIC & SOUND CRAFT',
}


def _text(value):
    return re.sub(r'\s+', ' ', html.unescape(re.sub(r'<[^>]*>', ' ', value or ''))).strip()


class _WinnerBlocks(HTMLParser):
    """Capture bounded ``div.winners`` blocks without a DOM dependency."""
    _void = {'area', 'base', 'br', 'col', 'embed', 'hr', 'img', 'input',
             'link', 'meta', 'param', 'source', 'track', 'wbr'}

    def __init__(self):
        super().__init__(convert_charrefs=False)
        self.depth = 0
        self.buffer = []
        self.blocks = []

    def handle_starttag(self, tag, attrs):
        raw = self.get_starttag_text() or ''
        attrs = dict(attrs)
        classes = set((attrs.get('class') or '').split())
        if not self.depth and tag == 'div' and 'winners' in classes:
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


def _field(pattern, body):
    match = re.search(pattern, body, re.I | re.S)
    return _text(match.group(1)) if match else ''


def _safe_video(value):
    if not isinstance(value, str):
        return ''
    parts = urlsplit(html.unescape(value.strip()))
    if (parts.scheme != 'https' or parts.username or parts.password
            or parts.port not in (None, 443) or parts.query or parts.fragment):
        return ''
    host = (parts.hostname or '').lower()
    if not re.fullmatch(r'bv-[a-z0-9-]+\.bubblevault\.com', host):
        return ''
    if not re.fullmatch(r'/(?:[^?#]+/){1,3}mp4/[^?#]+/[^?#]+\.mp4', parts.path, re.I):
        return ''
    return urlunsplit(('https', host, parts.path, '', ''))


def _safe_poster(value):
    if not isinstance(value, str):
        return ''
    parts = urlsplit(html.unescape(value.strip()))
    if (parts.scheme != 'https' or parts.username or parts.password
            or parts.port not in (None, 443) or parts.query or parts.fragment):
        return ''
    host = (parts.hostname or '').lower()
    if not re.fullmatch(r'bv-[a-z0-9-]+\.bubblevault\.com', host):
        return ''
    if not re.fullmatch(r'/(?:[^?#]+/){1,3}jpg/[^?#]+/[^?#]+\.jpg', parts.path, re.I):
        return ''
    return urlunsplit(('https', host, parts.path, '', ''))


def listing_url(year):
    if type(year) is not int or year not in YEARS:
        raise ValueError('invalid_kinsale_year')
    return ORIGIN + f'/winners/{year}'


def parse_listing(html_text, year=2025, origin=ORIGIN, max_entries=MAX_ENTRIES):
    listing_url(year)
    parser = _WinnerBlocks()
    parser.feed(html_text)
    records, seen = [], set()
    for block in parser.blocks:
        title_block = _field(r'<h4\b[^>]*class=["\']title["\'][^>]*>(.*?)</h4>', block)
        match = re.fullmatch(r'(.+?)\s+(20\d{2})', title_block)
        if not match or int(match.group(2)) != year:
            continue
        medium = match.group(1).strip().upper()
        if medium not in MEDIUMS:
            continue
        href = re.search(r'<a\b[^>]+href=["\']([^"\']*action=ows:entries\.details[^"\']*)', block, re.I)
        entry = _field(r'<div\b[^>]*class=["\']credits["\'][^>]*>.*?<h4\b[^>]*>(.*?)</h4>', block)
        brand = _field(r'<div\b[^>]*class=["\']credits["\'][^>]*>.*?<p\b[^>]*>(.*?)</p>', block)
        agency = _field(r'<div\b[^>]*class=["\']company-details["\'][^>]*>.*?<span\b[^>]*>(.*?)</span>', block)
        award = _field(r'<div\b[^>]*class=["\']prize["\'][^>]*>.*?<h3\b[^>]*>(.*?)</h3>', block)
        category = _field(r'<strong\b[^>]*>(.*?)</strong>', block)
        if not href or not entry or not brand:
            continue
        source_url = urljoin(origin + '/', html.unescape(href.group(1)))
        parts = urlsplit(source_url)
        if (parts.scheme != 'https' or parts.netloc != urlsplit(origin).netloc
                or parts.path != '/' or not re.fullmatch(rf'action=ows:entries\.details&e=\d+&project_year={year}', parts.query)):
            continue
        if source_url in seen:
            continue
        seen.add(source_url)
        records.append({
            'source_url': source_url,
            'title': entry[:300],
            'brand': brand[:200],
            'industry': '待分类',
            'ad_type': 'Kinsale · ' + medium.title(),
            'format': 'video',
            'language': 'en',
            'source_name': f'Kinsale Shark Awards {year} 官方案例',
            'published': str(year),
            'summary': 'Kinsale 官方广告 Film / Film Craft 案例；奖项级别以来源为准，详情页公开视频版本、声音与版权仍待人工确认。',
            'quality_evidence': [{
                'kind': award_evidence_kind(award),
                'text': f'Kinsale Shark Awards {year} · {award or "奖项级别待核实"} · {medium} · {category}',
                'source_url': source_url,
            }],
            'thumbnail_url': '',
            'media_status': 'source_link',
            'media_role': 'work_or_case_film_unverified',
            'rights': 'reference_only; redistribution_and_training_not_verified',
            'tags': ['Kinsale Sharks', 'film', medium.casefold(), 'human_review_pending'],
            'creative_structure': {
                'agency_or_entrant': agency,
                'award': award,
                'category': category,
                'medium': medium,
                'source_page': source_url,
            },
        })
        if max_entries is not None and len(records) >= max_entries:
            break
    return records


def _duration(value):
    value = _text(value)
    match = re.fullmatch(r'(?:(\d+)m:)?(\d+(?:\.\d+)?)s', value, re.I)
    if not match:
        return None
    return int(match.group(1) or 0) * 60 + float(match.group(2))


def parse_detail(html_text, source_url):
    video = re.search(r'<[^>]+data-type=["\']video["\'][^>]+data-video-src=["\']([^"\']+)', html_text, re.I | re.S)
    if not video:
        return {'has_video': False}
    media = _safe_video(video.group(1))
    poster_match = re.search(r'<[^>]+data-type=["\']video["\'][^>]+src=["\']([^"\']+)', html_text, re.I | re.S)
    poster = _safe_poster(poster_match.group(1)) if poster_match else ''
    duration = _field(r'<small\b[^>]*class=["\']mp4-duration["\'][^>]*>(.*?)</small>', html_text)
    fields = {key.casefold(): _text(value) for key, value in re.findall(
        r'<th>\s*(Title|Brand|Client|Production Company|Entrant Company|Agency|Director):\s*</th>\s*<td>(.*?)</td>',
        html_text, re.I | re.S)}
    return {
        'has_video': bool(media),
        'video_url': media,
        'thumbnail_url': poster,
        'duration': _duration(duration),
        'title': fields.get('title', ''),
        'brand': fields.get('brand', ''),
        'client': fields.get('client', ''),
        'production_company': fields.get('production company', ''),
        'entrant_company': fields.get('entrant company', ''),
        'agency': fields.get('agency', ''),
        'director': fields.get('director', ''),
    }


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
    result['creative_structure'] = {
        **record.get('creative_structure', {}),
        'public_video_url': detail['video_url'],
        'duration_seconds': detail.get('duration'),
        'client': detail.get('client', ''),
        'production_company': detail.get('production_company', ''),
        'entrant_company': detail.get('entrant_company', ''),
        'agency': detail.get('agency', ''),
        'director': detail.get('director', ''),
    }
    if detail.get('duration') is not None:
        result['quality_evidence'] = [*record['quality_evidence'], {
            'kind': 'public_video_metadata',
            'text': f"官方详情页公开 MP4，标示时长 {detail['duration']:g} 秒；片型、版本和声音待人工确认。",
            'source_url': record['source_url'],
        }]
    return result
