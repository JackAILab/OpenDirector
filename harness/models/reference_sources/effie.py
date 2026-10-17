"""Effie Worldwide case-film metadata from the public case archive.

Effie entries explain effectiveness and may be case films rather than the
original advertisement. Keep that distinction explicit and preserve only
stable public source links; the collector never downloads or republishes the
video files.
"""
import html
import re
from html.parser import HTMLParser
from urllib.parse import urlencode, urljoin, urlsplit

ORIGIN = 'https://effie.org'
ARCHIVE_PAGES = 1842
MAX_CASES = 10
MAX_PAGE_BYTES = 4 * 1024 * 1024


def archive_url(page):
    """Use the same public, anonymous pagination action as the site's UI."""
    if type(page) is not int or not 1 <= page <= ARCHIVE_PAGES:
        raise ValueError('invalid_effie_page')
    return ORIGIN + '/wp-admin/admin-ajax.php?' + urlencode({
        'action': 'get_filtered_posts', 'post_type': 'cases',
        'paged': page, 'per_page': MAX_CASES, 'form_data[keyword]': '',
    })


def read_page(client, url):
    """Bound decoded response bytes, including chunked archive/detail HTML."""
    with client.stream('GET', url) as response:
        response.raise_for_status()
        chunks, size = [], 0
        for chunk in response.iter_bytes():
            size += len(chunk)
            if size > MAX_PAGE_BYTES:
                raise ValueError('source_too_large')
            chunks.append(chunk)
        return b''.join(chunks).decode(response.encoding or 'utf-8', errors='replace')


def _text(value):
    value = re.sub(r'<[^>]*>', ' ', value or '')
    return re.sub(r'\s+', ' ', html.unescape(value)).strip()


class _Cards(HTMLParser):
    """Capture complete ``card case-card`` blocks without a DOM dependency."""

    def __init__(self):
        super().__init__(convert_charrefs=False)
        self.depth = 0
        self.buffer = []
        self.cards = []

    def handle_starttag(self, tag, attrs):
        raw = self.get_starttag_text() or ''
        classes = dict(attrs).get('class', '') or ''
        if self.depth == 0 and tag == 'div' and {'card', 'case-card'} <= set(classes.split()):
            self.depth = 1
            self.buffer = [raw]
        elif self.depth:
            self.buffer.append(raw)
            # HTMLParser does not emit an end tag for void elements such as
            # img/input, so they must not change the nesting depth.
            if tag not in {'area', 'base', 'br', 'col', 'embed', 'hr', 'img', 'input', 'link', 'meta', 'param', 'source', 'track', 'wbr'}:
                self.depth += 1

    def handle_startendtag(self, tag, attrs):
        if self.depth:
            self.buffer.append(self.get_starttag_text() or '')

    def handle_endtag(self, tag):
        if not self.depth:
            return
        self.buffer.append(f'</{tag}>')
        self.depth -= 1
        if self.depth == 0:
            self.cards.append(''.join(self.buffer))
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


def parse_archive(html_text, origin=ORIGIN):
    parser = _Cards()
    parser.feed(html_text)
    records = []
    for card in parser.cards[:MAX_CASES]:
        href = re.search(r'<a\s+href=["\']([^"\']+)["\'][^>]*>\s*Explore\s+this\s+case', card, re.I | re.S)
        title = re.search(r'<h4[^>]*>(.*?)</h4>', card, re.I | re.S)
        image = re.search(r'<img[^>]+src=["\']([^"\']+)["\'][^>]*>', card, re.I | re.S)
        if not href or not title:
            continue
        fields = {}
        for key, value in re.findall(
                r'<div\s+class=["\']nc["\'][^>]*>\s*<strong>([^<:]+):</strong>\s*(.*?)</div>',
                card, re.I | re.S):
            fields[_text(key).lower().replace(' ', '_')] = _text(value)
        source_url = urljoin(origin + '/', html.unescape(href.group(1)))
        source = urlsplit(source_url)
        if (source.scheme != 'https' or source.netloc != urlsplit(origin).netloc
                or not source.path.startswith('/cases/') or source.path == '/cases/'
                or source.query or source.fragment):
            continue
        records.append({
            'source_url': source_url,
            'title': _text(title.group(1))[:300],
            'brand': fields.get('brand', '')[:200],
            'industry': '待分类',
            'ad_type': 'Effie case · ' + fields.get('category', '获奖案例'),
            'format': 'video',
            'language': 'en',
            'summary': 'Effie 官方有效性案例；页面中的视频可能是案例说明片，不等同于原始广告，等待人工确认。',
            'quality_evidence': [{
                'kind': 'award_case',
                'text': 'Effie 官方案例 · ' + ' · '.join(
                    value for value in (fields.get('award_level', ''), fields.get('category', ''),
                                        fields.get('program', ''), fields.get('year', '')) if value),
                'source_url': source_url,
            }],
            'source_name': 'Effie Worldwide 官方案例库',
            'published': fields.get('year', ''),
            'media_status': 'source_link',
            'media_role': 'case_film_unverified',
            'rights': 'reference_only; redistribution_and_training_not_verified',
            'thumbnail_url': urljoin(origin + '/', html.unescape(image.group(1))) if image else '',
            'tags': ['Effie', 'case-film', 'human_review_pending'],
            'creative_structure': {
                'award_level': fields.get('award_level', ''),
                'category': fields.get('category', ''),
                'program': fields.get('program', ''),
            },
        })
    return records


def parse_detail(html_text, source_url):
    video = re.search(r'<source\s+src=["\']([^"\']+)["\'][^>]*type=["\']video/mp4["\']', html_text, re.I | re.S)
    poster = re.search(r'<video[^>]+data-poster=["\']([^"\']+)["\']', html_text, re.I | re.S)
    return {
        'embed_url': urljoin(source_url, html.unescape(video.group(1))) if video else '',
        'thumbnail_url': urljoin(source_url, html.unescape(poster.group(1))) if poster else '',
        'has_video': bool(video),
    }
