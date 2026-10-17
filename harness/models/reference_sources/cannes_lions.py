"""Public Cannes Lions winner-spotlight metadata.

The pages are official editorial selections and expose public Vimeo links in
their server-rendered Next.js data.  We retain only stable Vimeo URLs and the
official page as evidence; the clips are not asserted to be the original ad,
and they are not downloaded automatically.
"""
import json
import re
from html import unescape
from urllib.parse import urlsplit, urlunsplit


ORIGIN = 'https://www.canneslions.com'
PAGES = (
    ORIGIN + '/awards/winners-spotlight/winners-interviews',
    ORIGIN + '/awards/winners-spotlight/sports',
)


def _text(value):
    return re.sub(r'\s+', ' ', unescape(str(value or ''))).strip()


def _vimeo_url(value):
    """Return a query-free public Vimeo URL, or an empty string."""
    parts = urlsplit(_text(value))
    if parts.scheme != 'https' or parts.hostname not in {'vimeo.com', 'www.vimeo.com'}:
        return ''
    if not re.fullmatch(r'/\d+', parts.path or ''):
        return ''
    return urlunsplit(('https', 'vimeo.com', parts.path, '', ''))


def _image_url(fields):
    image = fields.get('image')
    if not isinstance(image, dict):
        return ''
    file_info = image.get('fields', {}).get('file', {})
    value = file_info.get('url', '') if isinstance(file_info, dict) else ''
    if isinstance(value, str) and value.startswith('//'):
        return 'https:' + value
    return value if isinstance(value, str) else ''


def _walk(value):
    if isinstance(value, dict):
        sys = value.get('sys', {})
        content_type = sys.get('contentType', {}) if isinstance(sys, dict) else {}
        content_type = content_type.get('sys', {}) if isinstance(content_type, dict) else {}
        fields = value.get('fields')
        if content_type.get('id') == 'videoCard' and isinstance(fields, dict):
            yield fields
        for child in value.values():
            yield from _walk(child)
    elif isinstance(value, list):
        for child in value:
            yield from _walk(child)


def parse_page(html_text, page_url, year=2025):
    """Parse unique 2025 winner-spotlight cards from one official page."""
    match = re.search(r'<script id="__NEXT_DATA__"[^>]*>(.*?)</script>', html_text, re.S | re.I)
    if not match:
        raise ValueError('source_layout_changed')
    try:
        payload = json.loads(match.group(1))
    except json.JSONDecodeError as exc:
        raise ValueError('source_layout_changed') from exc
    records = []
    seen = set()
    for fields in _walk(payload):
        title = _text(fields.get('title'))
        description = _text(fields.get('description'))
        media_url = _vimeo_url(fields.get('videoUrl'))
        if not title or not media_url or not re.search(rf'\b{int(year)}\b', description):
            continue
        if media_url in seen:
            continue
        seen.add(media_url)
        image_url = _image_url(fields)
        records.append({
            'source_url': media_url,
            'title': title[:300],
            'source_name': 'Cannes Lions 官方 Winners Spotlight',
            'published': str(year),
            'industry': '待分类',
            'ad_type': 'Winner Spotlight / case film',
            'summary': 'Cannes Lions 官方获奖专题视频，公开卡片含作品标题与制作/品牌署名；未确认是否为原始广告片，等待人工观看与标注。',
            'quality_evidence': [{
                'kind': 'award_winner_spotlight',
                'text': description,
                'source_url': page_url,
            }],
            'creative_structure': {
                'credit_line': description,
                'spotlight_page': page_url,
            },
            'embed_url': media_url,
            'thumbnail_url': image_url,
            'media_status': 'source_link',
            'media_role': 'winner_spotlight_unverified',
            'rights': 'reference_only; redistribution_and_training_not_verified',
            'tags': ['Cannes Lions Winner Spotlight'],
        })
    return records
