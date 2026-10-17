"""Bounded public award metadata; no claim of viewing or redistribution rights."""
import re
from html import unescape
from urllib.parse import urlsplit, parse_qsl, urljoin
from types import SimpleNamespace

from harness.models.reference_download import validate_url

ORIGIN = 'https://winners.cannescorporate.com'
YEARS = (2026, 2025, 2024, 2023)
CATEGORIES = (4, 1)


def text(value):
    return unescape(re.sub(r'<[^>]*>', ' ', value)).strip()


def _normalized(value):
    return re.sub(r'\s+', ' ', text(value)).strip()


def listing_url(year, category=4):
    if type(year) is not int or year not in YEARS:
        raise ValueError('invalid_corporate_year')
    if type(category) is not int or category not in CATEGORIES:
        raise ValueError('invalid_corporate_category')
    return ORIGIN + f'/?year={year}&main_category={category}'


def _entry(value):
    try:
        parts = urlsplit(urljoin(ORIGIN, unescape(value)))
        if (parts.scheme != 'https' or parts.netloc != 'winners.cannescorporate.com'
                or parts.fragment or not re.fullmatch(r'/single-entry/[1-9][0-9]{0,7}', parts.path)
                or any(k not in ('award_id', 'category_id') or not v.isdigit()
                       for k, v in parse_qsl(parts.query, keep_blank_values=True))):
            return ''
        return ORIGIN + parts.path
    except (ValueError, TypeError):
        return ''


def _poster(value, year, identity):
    parts = urlsplit(unescape(value))
    if (parts.scheme == 'https' and parts.netloc == 'winners.cannescorporate.com'
            and not parts.query and not parts.fragment
            and re.fullmatch(rf'/external_drive/{year}/{identity}/[A-Za-z0-9_.-]+\.(?:jpg|png|jpeg|webp)', parts.path)):
        return ORIGIN + parts.path
    return ''


def parse_listing(html, year=None, max_entries=None):
    if year is not None:
        listing_url(year)
        headings = [_normalized(h) for h in re.findall(r'<h1\b[^>]*>(.*?)</h1>', html, re.S | re.I)]
        if headings != [f'Winners {year}']:
            raise ValueError('corporate_year_mismatch')
    records = []
    for link, body in re.findall(r'<a\b[^>]*href="([^"]*/single-entry/[^\"]+)"[^>]*>(.*?)</a>', html, re.S):
        source = _entry(link)
        if not source:
            continue
        category = re.search(r'<p class="film-category">(.*?)</p>', body, re.S)
        title = re.search(r'<h4 class="film-title">(.*?)</h4>', body, re.S)
        if not category or not title:
            continue
        category = text(category[1])
        if not any(k in category for k in ('Marketing Communication', 'Product and Launch')):
            continue
        client = re.search(r'<p><span>CLIENT:</span>(.*?)</p>', body, re.S)
        poster = re.search(r'<img[^>]*src="([^"]+)"', body)
        level = re.search(r'<div\b[^>]*class="award-badge"[^>]*>(.*?)</div>', body, re.S)
        award = _normalized(level[1]) if level else ''
        kind = ('award_winner' if award in ('Gold Award', 'Silver Award', 'Grand Prix')
                else 'award_finalist' if award == 'Finalist Diploma' else 'award_archive')
        identity = source.rsplit('/', 1)[1]
        records.append({'source_url': source, 'title': text(title[1])[:300],
                        'brand': text(client[1])[:200] if client else '',
                        'source_name': 'Cannes Corporate 官方获奖档案',
                        'published': str(year or ''),
                        'ad_type': category[:100], 'industry': '待分类',
                        'summary': '官方获奖页面收录。未完整观看；创作策略与声音质量等待人工标注。',
                        'quality_evidence': [{'kind': kind, 'text': ' · '.join(v for v in (str(year or ''), award, category) if v),
                                              'source_url': unescape(link)}],
                        'thumbnail_url': _poster(poster[1], year, identity) if poster and year else '',
                        'media_status': 'source_link', 'media_role': 'work_or_case_film_unverified',
                        'rights': 'reference_only; redistribution_and_training_not_verified',
                        'tags': [category]})
    unique = {}
    for record in records:
        source = record['source_url']
        if source not in unique:
            unique[source] = record
        else:
            if any(_normalized(unique[source][key]) != _normalized(record[key]) for key in ('title', 'brand')):
                raise ValueError('corporate_listing_identity_conflict')
            for evidence in record['quality_evidence']:
                if evidence not in unique[source]['quality_evidence']:
                    unique[source]['quality_evidence'].append(evidence)
    rows = list(unique.values())
    return rows if max_entries is None else rows[:max_entries]


def parse_archive_listing(html, year, category, max_entries=None):
    listing_url(year, category)
    selected = re.search(r'<select\b[^>]*name="main_category"[^>]*>(.*?)</select>', html, re.S)
    if not selected or not re.search(rf'<option\b[^>]*value="{category}"[^>]*selected(?:\s|=|>)', selected[1]):
        raise ValueError('corporate_category_mismatch')
    rows = parse_listing(html, year, max_entries)
    if not rows:
        # A complete category can contain films outside our narrow scope
        # (the 2023 online archive contains only a brand-image film). A blank
        # or changed layout must not be mistaken for a confirmed empty result.
        cards = re.findall(r'<a\b[^>]*href="([^"]*/single-entry/[^\"]+)"[^>]*>(.*?)</a>', html, re.S)
        if not any(_entry(link) and re.search(r'<p class="film-category">', body)
                   and re.search(r'<h4 class="film-title">', body) for link, body in cards):
            raise ValueError('corporate_listing_missing')
    return rows


def parse_detail(html, source_url):
    if _entry(source_url) != source_url:
        raise ValueError('invalid_corporate_source')
    headings = re.findall(r'<h1\b[^>]*>(.*?)</h1>', html, re.S | re.I)
    if len(headings) != 1 or not _normalized(headings[0]):
        raise ValueError('corporate_detail_missing')
    client = re.search(r'<span\b[^>]*class="detail-label"[^>]*>\s*CLIENT:\s*</span>\s*<span\b[^>]*class="detail-value"[^>]*>(.*?)</span>', html, re.S)
    videos = []
    identity = source_url.rsplit('/', 1)[1]
    for element in re.findall(r'<source\b[^>]*>', html, re.S | re.I):
        src = re.search(r'\bsrc=["\']([^"\']+)', element)
        if not src:
            continue
        url = unescape(src[1])
        validate_url(url)
        parts = urlsplit(url)
        if parts.netloc != 'winners.cannescorporate.com' or parts.path.split('/')[3] != identity:
            raise ValueError('corporate_video_identity_mismatch')
        if url not in videos:
            videos.append(url)
    if len(videos) > 12:
        raise ValueError('corporate_video_limit')
    primary = videos[0] if len(videos) == 1 else ''
    if len(videos) > 1:
        # Official campaign pages can contain several cuts. Use only the
        # explicitly active carousel video as the preview, keeping every
        # validated variant visible as provenance, not downloading them all.
        active = re.findall(r'<div\b[^>]*class="carousel-item active"[^>]*>(.*?)</div>', html, re.S)
        defaults = [unescape(url) for body in active for url in
                    re.findall(r'<source\b[^>]*\bsrc=["\']([^"\']+)', body)]
        if len(defaults) != 1 or defaults[0] not in videos:
            raise ValueError('corporate_video_ambiguous')
        primary = defaults[0]
    return {'title': _normalized(headings[0]), 'brand': _normalized(client[1]) if client else '',
            'video_url': primary, 'video_variants': videos}


def apply_detail(record, detail):
    if (_normalized(record['title']) != detail['title']
            or _normalized(record['brand']) != detail['brand']):
        raise ValueError('corporate_detail_identity_mismatch')
    video = detail['video_url']
    if any(urlsplit(url).path.split('/')[2] != record['published'] for url in detail['video_variants']):
        raise ValueError('corporate_video_year_mismatch')
    result = {**record, 'format': 'video', 'creative_structure': {
        'award_year': int(record['published']), 'category': record['ad_type'],
        'source_page': record['source_url'], 'public_video_url': video,
        'public_video_variants': [{'label': f'官网版本 {index + 1}', 'url': url,
                                   'default': url == video}
                                  for index, url in enumerate(detail['video_variants'])],
    }}
    if len(detail['video_variants']) > 1:
        result['summary'] += f" 官网提供{len(detail['video_variants'])}个视频版本，预览采用官网默认展示版本；版本内容仍待人工确认。"
    return result


def archive_adapter(category):
    return SimpleNamespace(ORIGIN=ORIGIN, ALLOW_EMPTY_LISTING=True,
        listing_url=lambda year: listing_url(year, category),
        parse_listing=lambda html, year, max_entries=None: parse_archive_listing(html, year, category, max_entries),
        parse_detail=parse_detail, apply_detail=apply_detail)
