"""Official British Arrows film archive; metadata and public embeds only."""
import html
import re
from urllib.parse import parse_qs, urljoin, urlsplit, urlunsplit

ORIGIN = 'https://www.britisharrows.com'
YEARS = (2025, 2024, 2023, 2026)
MAX_PAGES = 30
MAX_ENTRIES = 12


def _text(value):
    return re.sub(r'\s+', ' ', html.unescape(re.sub(r'<[^>]*>', ' ', value or ''))).strip()


def _parts(value):
    try:
        parts = urlsplit(html.unescape(value))
        if (parts.scheme != 'https' or parts.username or parts.password
                or parts.port not in (None, 443) or parts.fragment):
            return None
        return parts
    except (ValueError, TypeError):
        return None


def listing_url(year, page=1):
    if type(year) is not int or year not in YEARS:
        raise ValueError('invalid_british_arrows_year')
    if type(page) is not int or not 1 <= page <= MAX_PAGES:
        raise ValueError('invalid_british_arrows_page')
    return ORIGIN + f'/winners/british-arrows/{year}' + (f'/p{page}' if page > 1 else '')


def _entry(value, year):
    parts = _parts(urljoin(ORIGIN, html.unescape(value)))
    if (not parts or parts.netloc != urlsplit(ORIGIN).netloc or parts.query
            or not re.fullmatch(rf'/films/british-arrows/{year}/[a-z0-9-]+', parts.path)):
        return ''
    return ORIGIN + parts.path


def _poster(value):
    parts = _parts(value)
    if not parts or parts.hostname not in {
            'british-arrows.transforms.svdcdn.com', 'british-arrows.files.svdcdn.com'}:
        return ''
    if not re.fullmatch(r'/production/films/[a-zA-Z0-9_.-]+\.(?:jpg|jpeg|png|webp)', parts.path):
        return ''
    # The official files CDN serves the same asset without the transform signature.
    return urlunsplit(('https', 'british-arrows.files.svdcdn.com', parts.path, '', ''))


def _vimeo(value):
    parts = _parts(value)
    if not parts or parts.hostname != 'player.vimeo.com' or not re.fullmatch(r'/video/\d+', parts.path):
        return ''
    # Accept display settings only, never private video hashes or access tokens.
    if set(parse_qs(parts.query, keep_blank_values=True)) - {'byline', 'portrait', 'dnt', 'title', 'autoplay', 'loop', 'muted'}:
        return ''
    return 'https://vimeo.com/' + parts.path.rsplit('/', 1)[1]


def _awards(text):
    result = []
    for kind, level, category in re.findall(
            r'<div\b[^>]*>\s*(ARROWS|CRAFT)\s+(GOLD|SILVER|BRONZE)\s*</div>\s*'
            r'<div\b[^>]*>\s*<span\b[^>]*>(.*?)</span>', text, re.I | re.S):
        item = {'award': kind.upper() + ' ' + level.upper(), 'category': _text(category)}
        if item not in result:
            result.append(item)
    return result


def _duration_category(awards):
    # This is a category label, not a measured clip duration.
    for seconds in (15, 30):
        if any(re.search(rf'BEST UP TO.*\b{seconds} SECOND', a['category'], re.I) for a in awards):
            return f'{seconds}秒以内奖项'
    return '广告与制作工艺'


def parse_listing(text, year, page=1, max_entries=None):
    listing_url(year, page)
    records = {}
    for body in re.findall(r'<article\b[^>]*>(.*?)</article>', text, re.I | re.S):
        awards = _awards(body)
        if not awards or 'MUSIC VIDEO' in _text(body).upper():
            continue
        link = re.search(r'<h3\b[^>]*>\s*<a\b[^>]*href=["\']([^"\']+)["\'][^>]*>(.*?)</a>', body, re.I | re.S)
        if not link:
            continue
        source = _entry(link.group(1), year)
        title = _text(link.group(2))
        if not source or not title or ' — ' not in title:
            continue
        if source in records:
            records[source]['creative_structure']['awards'].extend(
                a for a in awards if a not in records[source]['creative_structure']['awards'])
            continue
        image = re.search(r'<img\b[^>]*src=["\']([^"\']+)', body, re.I)
        brand, name = title.split(' — ', 1)
        records[source] = {
            'source_url': source, 'title': name[:300], 'brand': brand[:200],
            'industry': '待分类', 'format': 'video', 'published': str(year),
            'source_name': f'British Arrows {year} 官方获奖片',
            'summary': 'British Arrows 官方广告与制作工艺获奖片；版本、实际时长、声音和可迁移机制待人工观看确认。',
            'thumbnail_url': _poster(image.group(1)) if image else '',
            'media_status': 'source_link', 'media_role': 'work_or_case_film_unverified',
            'rights': 'reference_only; redistribution_and_training_not_verified',
            'training_eligible': False,
            'creative_structure': {'awards': awards, 'listing_title': title, 'source_page': source},
        }
    if not records:
        raise ValueError('source_layout_changed')
    for record in records.values():
        category = _duration_category(record['creative_structure']['awards'])
        record['ad_type'] = 'British Arrows · ' + category
        record['tags'] = ['British Arrows', category, 'human_review_pending']
    # Short commercials first; the cursor will continue through the rest.
    rows = sorted(records.values(), key=lambda r: ('15秒' not in r['ad_type'], '30秒' not in r['ad_type'], r['source_url']))
    pages = [page]
    for href in re.findall(r'<a\b[^>]*href=["\']([^"\']+)', text, re.I):
        parts = _parts(urljoin(ORIGIN, html.unescape(href)))
        if not parts or parts.netloc != urlsplit(ORIGIN).netloc or parts.query:
            continue
        match = re.fullmatch(rf'/winners/british-arrows/{year}/p(\d+)', parts.path)
        if match and 1 <= int(match.group(1)) <= MAX_PAGES:
            pages.append(int(match.group(1)))
    return (rows[:max_entries] if max_entries is not None else rows), max(pages)


def apply_detail(record, text):
    headline = re.search(r'<h1\b[^>]*>(.*?)</h1>', text, re.I | re.S)
    if not headline or _text(headline.group(1)) != record['creative_structure']['listing_title']:
        raise ValueError('detail_identity_mismatch')
    embeds = [_vimeo(src) for src in re.findall(r'<iframe\b[^>]*src=["\']([^"\']+)', text, re.I)]
    embeds = list(dict.fromkeys(url for url in embeds if url))
    if not embeds:
        return None
    result = {**record, 'embed_url': embeds[0]}
    awards = _awards(text) or record['creative_structure']['awards']
    structure = {**record['creative_structure'], 'awards': awards, 'public_video_urls': embeds}
    for key, label in (('agency', 'Advertising Agency'), ('production_company', 'Production Company'), ('director', 'Director')):
        field = re.search(r'<h3\b[^>]*>\s*' + label + r'\s*</h3>\s*</div>\s*<a\b[^>]*>(.*?)</a>', text, re.I | re.S)
        if field:
            structure[key] = _text(field.group(1))[:300]
    category = _duration_category(awards)
    result.update(creative_structure=structure, ad_type='British Arrows · ' + category,
                  tags=['British Arrows', category, 'human_review_pending'])
    result['quality_evidence'] = [
        {'kind': 'award_winner', 'text': f"British Arrows {record['published']} · {a['award']} · {a['category']}",
         'source_url': record['source_url']} for a in awards]
    result['quality_evidence'].append({'kind': 'public_video_metadata',
        'text': '官方详情页提供公开 Vimeo 播放器；奖项时长分组不代替媒体实测，声音与版本待人工确认。',
        'source_url': record['source_url']})
    return result
