"""Public Kyoorius Creative Awards film winner metadata.

The AwardsEngine pages expose a public entry page, poster, MP4 locator and
duration for film winners.  We retain those as review evidence only; the
collector never downloads or republishes the media.
"""
import html
import re
from html.parser import HTMLParser
from urllib.parse import urljoin, urlsplit, urlunsplit

ORIGIN = 'https://kyooriuscreative2025.awardsengine.com'
LISTING_PATH = '/winners/2025/advertising'
# The annual listing contains the union of the Advertising and Craft entries.
# Keep discipline paths available for explicit scans of an individual section.
LISTING_PATHS = ('/winners/2025', LISTING_PATH, '/winners/2025/craft')
MAX_ENTRIES = 12


def _text(value):
    return re.sub(r'\s+', ' ', html.unescape(re.sub(r'<[^>]*>', ' ', value or ''))).strip()


def _award_kind(value):
    # Kyoorius distinguishes its first judging round from Elephant awards:
    # https://www.kyoorius.com/kca (Results & Winning).
    level = _text(value).casefold()
    if level in ('first list', 'the first list'):
        return 'award_shortlist'
    if level in ('blue elephant', 'baby blue elephant', 'baby black elephant',
                 'black elephant', 'purple elephant'):
        return 'award_winner'
    return 'award_listing'


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
    if not re.fullmatch(r'/[^?#]+/mp4/[^?#]+\.mp4', parts.path, re.I):
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
    if not re.fullmatch(r'/[^?#]+/jpg/[^?#]+\.jpg', parts.path, re.I):
        return ''
    return urlunsplit(('https', host, parts.path, '', ''))


def parse_listing(html_text, origin=ORIGIN, max_entries=MAX_ENTRIES):
    parser = _WinnerBlocks()
    parser.feed(html_text)
    records = []
    seen = set()
    for block in parser.blocks:
        # Restrict this source to film entries; other Kyoorius disciplines are
        # useful later but do not belong in the video template pool.
        if 'cat_film' not in block:
            continue
        href = re.search(r'<a\b[^>]+href=["\']([^"\']*action=ows:entries\.details[^"\']*)', block, re.I)
        entry = _field(r'<div\b[^>]*class=["\']credits["\'][^>]*>.*?<h4\b[^>]*>(.*?)</h4>', block)
        brand = _field(r'<div\b[^>]*class=["\']credits["\'][^>]*>.*?<p\b[^>]*>(.*?)</p>', block)
        agency = _field(r'<div\b[^>]*class=["\']company-details["\'][^>]*>.*?<span\b[^>]*>(.*?)</span>', block)
        award = _field(r'<div\b[^>]*class=["\']prize["\'][^>]*>.*?<h3\b[^>]*>(.*?)</h3>', block)
        category = _field(r'<h4\b[^>]*class=["\']title["\'][^>]*>(.*?)</h4>', block)
        poster = re.search(r'data-original=["\']([^"\']+)', block, re.I)
        if not href or not entry or not brand:
            continue
        source_url = urljoin(origin + '/', html.unescape(href.group(1)))
        if source_url in seen:
            continue
        seen.add(source_url)
        records.append({
            'source_url': source_url,
            'title': entry[:300],
            'brand': brand[:200],
            'industry': '待分类',
            'ad_type': 'Kyoorius · ' + (category or 'Film'),
            'format': 'video',
            'language': 'en',
            'source_name': 'Kyoorius Creative Awards 2025 官方案例',
            'published': '2025',
            'summary': 'Kyoorius 官方 Film 案例；奖项级别以来源为准，详情页公开视频可能是参赛版本，原片身份、声音和品牌事实仍待人工确认。',
            'quality_evidence': [{
                'kind': _award_kind(award),
                'text': f'Kyoorius Creative Awards 2025 · {award or "奖项级别待核实"} · {category or "Film"}',
                'source_url': source_url,
            }],
            'thumbnail_url': '',
            'media_status': 'source_link',
            'media_role': 'work_or_case_film_unverified',
            'rights': 'reference_only; redistribution_and_training_not_verified',
            'tags': ['Kyoorius', 'film', 'human_review_pending'],
            'creative_structure': {
                'agency': agency,
                'award': award,
                'category': category,
                'source_page': source_url,
            },
        })
        if max_entries is not None and len(records) >= max_entries:
            break
    return records


def parse_detail(html_text, source_url):
    video = re.search(r'<[^>]+data-type=["\']video["\'][^>]+data-video-src=["\']([^"\']+)', html_text, re.I | re.S)
    if not video:
        return {'has_video': False}
    media = _safe_video(video.group(1))
    poster_match = re.search(r'<[^>]+data-type=["\']video["\'][^>]+src=["\']([^"\']+)', html_text, re.I | re.S)
    poster = _safe_poster(poster_match.group(1)) if poster_match else ''
    duration = _field(r'<small\b[^>]*class=["\']mp4-duration["\'][^>]*>(.*?)</small>', html_text)
    seconds = None
    match = re.fullmatch(r'(\d+(?:\.\d+)?)\s*s', duration or '', re.I)
    if match:
        seconds = float(match.group(1))
    title = _field(r'<h3\b[^>]*class=["\']title[^>]*>.*?<strong>(.*?)</strong>', html_text)
    fields = {}
    for key, value in re.findall(r'<strong>(Brand|Client|Entrant):</strong>\s*([^<]+)', html_text, re.I):
        fields[key.casefold()] = _text(value)
    return {
        'has_video': bool(media),
        'video_url': media,
        'thumbnail_url': poster,
        'duration': seconds,
        'title': title,
        'brand': fields.get('brand', ''),
        'client': fields.get('client', ''),
        'entrant': fields.get('entrant', ''),
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
        'entrant': detail.get('entrant', ''),
    }
    if detail.get('duration') is not None:
        result['quality_evidence'] = [*record['quality_evidence'], {
            'kind': 'public_video_metadata',
            'text': f"官方详情页公开 MP4，标示时长 {detail['duration']:g} 秒；身份和版本待人工确认。",
            'source_url': record['source_url'],
        }]
    return result


class ArchiveListing:
    """Adapt one vetted 2025 listing to the shared durable archive action."""
    ORIGIN = ORIGIN

    def __init__(self, path):
        if path not in LISTING_PATHS:
            raise ValueError('invalid_kyoorius_selection')
        self.path = path
        self.cursor_key = 'kyoorius:' + path

    def listing_url(self, year):
        if type(year) is not int or year != 2025:
            raise ValueError('invalid_kyoorius_year')
        return self.ORIGIN + self.path

    def parse_listing(self, text, year, max_entries=None):
        self.listing_url(year)
        return parse_listing(text, max_entries=max_entries)

    parse_detail = staticmethod(parse_detail)
    apply_detail = staticmethod(apply_detail)
