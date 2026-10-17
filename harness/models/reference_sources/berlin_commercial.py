"""Public Berlin Commercial advertising-film winner metadata.

Berlin Commercial publishes bounded winner listings through AwardsEngine.  The
listing cards carry an entry id and the detail view exposes a public BubbleVault
MP4 and poster.  We retain those URLs as review evidence only; the collector
does not download or republish source media.
"""
import html
import re
from harness.models.reference_sources.award_evidence import award_evidence_kind
from html.parser import HTMLParser
from urllib.parse import parse_qs, urljoin, urlsplit, urlunsplit

ORIGIN = 'https://berlincommercial.awardsengine.com'
YEARS = (2026, 2025, 2024, 2023)
MAX_ENTRIES = 12


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


def _winner_blocks(html_text):
    """Return card fragments even when AwardsEngine emits unbalanced markup.

    The current Berlin Commercial export contains legacy tags that keep a
    depth-based HTML parser open across the whole page.  Cards are still
    unambiguously delimited by the next outer ``div.winners`` marker, so the
    fallback stays bounded to that public listing structure.
    """
    parser = _WinnerBlocks()
    parser.feed(html_text)
    if parser.blocks:
        return parser.blocks
    return re.findall(
        r'(?is)<div\s+class=["\']winners\b.*?(?=<div\s+class=["\']winners\b|\Z)',
        html_text,
    )


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
        raise ValueError('invalid_berlin_commercial_year')
    return ORIGIN + f'/winners/{year}'


def _entry_url(entry_id, year, origin=ORIGIN):
    if not re.fullmatch(r'\d+', str(entry_id or '')):
        return ''
    return (origin + '/?action=ows:entries.details&isNotAjax=true&'
            f'project_year={year}&e={entry_id}')


def _trusted_entry_url(value, year, origin=ORIGIN):
    parts = urlsplit(urljoin(origin + '/', html.unescape(value or '')))
    if parts.scheme != 'https' or parts.netloc != urlsplit(origin).netloc or parts.path != '/':
        return ''
    query = parse_qs(parts.query, keep_blank_values=True)
    if query.get('action') != ['ows:entries.details'] or query.get('project_year') != [str(year)]:
        return ''
    if query.get('isNotAjax') != ['true'] or len(query.get('e', [])) != 1:
        return ''
    if not re.fullmatch(r'\d+', query['e'][0]):
        return ''
    return _entry_url(query['e'][0], year, origin)


def parse_listing(html_text, year=2025, origin=ORIGIN, max_entries=MAX_ENTRIES):
    listing_url(year)
    records, seen = [], set()
    for block in _winner_blocks(html_text):
        category = _field(r'<h4\b[^>]*class=["\']title["\'][^>]*>(.*?)</h4>', block)
        # The listing flattens craft categories across commercial, music and
        # personal-work sections. The detail header restores that distinction;
        # a bare Craft label is never evidence of an advertising-film format.
        if not (category.upper().startswith('COMMERCIALS AND BRANDED CONTENT')
                or category.upper().startswith('CRAFT:')):
            continue
        entry_id = re.search(r'data-entry-id=["\'](\d+)["\']', block, re.I)
        entry = _field(r'<div\b[^>]*class=["\']credits["\'][^>]*>.*?<h4\b[^>]*>(.*?)</h4>', block)
        brand = _field(r'<div\b[^>]*class=["\']credits["\'][^>]*>.*?<p\b[^>]*>(.*?)</p>', block)
        agency = _field(r'<div\b[^>]*class=["\']company-details["\'][^>]*>.*?<span\b[^>]*>(.*?)</span>', block)
        award = _field(r'<div\b[^>]*class=["\']prize["\'][^>]*>.*?<h3\b[^>]*>(.*?)</h3>', block)
        production = _field(r'<div\b[^>]*class=["\']credits["\'][^>]*>.*?<p\b[^>]*>.*?</p>\s*<p\b[^>]*>(.*?)</p>', block)
        if not entry_id or not entry or not brand:
            continue
        source_url = _trusted_entry_url(_entry_url(entry_id.group(1), year, origin), year, origin)
        if not source_url or source_url in seen:
            continue
        seen.add(source_url)
        records.append({
            'source_url': source_url,
            'title': entry[:300],
            'brand': brand[:200],
            'industry': '待分类',
            'ad_type': 'Berlin Commercial · ' + (category or 'Commercial Film'),
            'format': 'video',
            'language': 'en',
            'source_name': f'Berlin Commercial {year} 官方案例',
            'published': str(year),
            'summary': 'Berlin Commercial 官方商业与制作工艺案例；奖项级别以来源为准，详情页公开视频版本、声音与版权仍待人工确认。',
            'quality_evidence': [{
                'kind': award_evidence_kind(award),
                'text': f'Berlin Commercial {year} · {award or "奖项级别待核实"} · {category}',
                'source_url': source_url,
            }],
            'thumbnail_url': '',
            'media_status': 'source_link',
            'media_role': 'work_or_case_film_unverified',
            'rights': 'reference_only; redistribution_and_training_not_verified',
            'tags': ['Berlin Commercial', 'film', category.casefold(), 'human_review_pending'],
            'creative_structure': {
                'agency_or_entrant': agency,
                'production_company': production,
                'award': award,
                'category': category,
                'source_page': source_url,
            },
        })
        if max_entries is not None and len(records) >= max_entries:
            break
    return records


def _detail_field(label, body):
    pattern = (r'<h2[^>]*>\s*<span[^>]*class=["\']left["\'][^>]*>\s*'
               + re.escape(label) + r'\s*</span>\s*<span[^>]*class=["\']right["\'][^>]*>(.*?)</span>\s*</h2>')
    return _field(pattern, body)


def parse_detail(html_text, source_url):
    source = re.search(r'<source\b[^>]*src=["\']([^"\']+)["\'][^>]*type=["\']video/mp4["\']', html_text, re.I | re.S)
    media = _safe_video(source.group(1)) if source else ''
    poster_match = re.search(r'<video\b[^>]*poster=["\']([^"\']+)', html_text, re.I | re.S)
    poster = _safe_poster(poster_match.group(1)) if poster_match else ''
    title = _field(r'<span\b[^>]*class=["\']title["\'][^>]*>(.*?)</span>', html_text)
    heading = re.search(r'<h1\b[^>]*class=["\']entry-details["\'][^>]*>(.*?)</h1>', html_text, re.I | re.S)
    header = heading.group(1) if heading else ''
    return {
        'has_video': bool(media),
        'video_url': media,
        'thumbnail_url': poster,
        'title': title,
        # Read the entry's own header, not navigation or related entries.
        'section': _field(r'<span\b[^>]*class=["\']category["\'][^>]*>(.*?)</span>', header).rstrip(':： '),
        'subcategory': _field(r'<span\b[^>]*class=["\']subcategory["\'][^>]*>(.*?)</span>', header),
        'brand': _detail_field('CLIENT/BRAND', html_text),
        'production_company': _detail_field('PRODUCTION COMPANY', html_text),
        'director': _detail_field('DIRECTOR(S)', html_text),
        'agency': _detail_field('AGENCY', html_text),
        'synopsis': _detail_field('SHORT SYNOPSIS', html_text),
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
        'client': detail.get('brand', ''),
        'production_company': detail.get('production_company', ''),
        'director': detail.get('director', ''),
        'agency': detail.get('agency', ''),
        'short_synopsis': detail.get('synopsis', ''),
    }
    result['quality_evidence'] = [*record['quality_evidence'], {
        'kind': 'public_video_metadata',
        'text': '官方详情页公开 MP4 与海报；片长、声音、版本和品牌身份待人工确认。',
        'source_url': record['source_url'],
    }]
    if detail.get('section'):
        category = ' / '.join(value for value in (detail['section'], detail.get('subcategory', '')) if value)
        result['ad_type'] = 'Berlin Commercial · ' + category
        result['creative_structure'].update(
            listing_category=record.get('creative_structure', {}).get('listing_category',
                record.get('creative_structure', {}).get('category', '')),
            section=detail['section'], subcategory=detail.get('subcategory', ''), category=category)
        result['quality_evidence'].append({
            'kind': 'source_category', 'text': '官方详情页类别：' + category,
            'source_url': record['source_url'],
        })
        if detail['section'].casefold() in ('music videos', 'personal work'):
            result['summary'] = ('Berlin Commercial 官方' +
                ('音乐视频' if detail['section'].casefold() == 'music videos' else '个人作品') +
                '参考，可用于研究摄影、制作与表达；具体媒体版本、声音与版权仍待人工确认。')
    return result
