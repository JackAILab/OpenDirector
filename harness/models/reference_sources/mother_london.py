"""Mother London's public campaign portfolio; source evidence, not quality labels."""
import html
from html.parser import HTMLParser
import json
import re
from urllib.parse import quote, urlsplit

ORIGIN = 'https://www.motherlondon.com'
YEARS = (2026, 2025, 2024, 2023)
MAX_ENTRIES = 12


class _NextData(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=False)
        self.active = False
        self.payloads = []

    def handle_starttag(self, tag, attrs):
        if tag == 'script' and dict(attrs).get('id') == '__NEXT_DATA__':
            self.active = True
            self.payloads.append('')

    def handle_endtag(self, tag):
        if tag == 'script':
            self.active = False

    def handle_data(self, data):
        if self.active:
            self.payloads[-1] += data


def _data(text):
    parser = _NextData()
    parser.feed(text)
    try:
        if len(parser.payloads) != 1:
            raise ValueError('source_layout_changed')
        data = json.loads(parser.payloads[0])['props']['pageProps']['data']
        if not isinstance(data, dict):
            raise ValueError('source_layout_changed')
        return data
    except (ValueError, KeyError, TypeError):
        raise ValueError('source_layout_changed') from None


def _text(value, limit):
    if not isinstance(value, str):
        return ''
    return re.sub(r'\s+', ' ', html.unescape(re.sub(r'<[^>]*>', ' ', value))).strip()[:limit]


def _entry(slug):
    if not isinstance(slug, str) or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_&' -]{0,179}", slug):
        return ''
    return ORIGIN + '/work/' + quote(slug, safe='-_')


def _poster(value):
    if not isinstance(value, str):
        return ''
    try:
        u = urlsplit(value)
        if (u.scheme != 'https' or u.netloc != 'cdn.sanity.io' or u.query or u.fragment
                or not re.fullmatch(r'/images/[a-z0-9]+/[a-z0-9_-]+/[a-f0-9]+-\d+x\d+\.(?:png|jpg|jpeg|webp)', u.path)):
            return ''
        return value
    except ValueError:
        return ''


def listing_url(year):
    if type(year) is not int or year not in YEARS:
        raise ValueError('invalid_mother_london_year')
    return ORIGIN + '/work'


def _project(project):
    if not isinstance(project, dict) or project.get('_type') != 'project':
        return None
    source = _entry(project.get('slug'))
    brand = _text(project.get('title'), 200)
    title = _text(project.get('tagline'), 300)
    filters = project.get('filters') or {}
    year = filters.get('year') if isinstance(filters, dict) else None
    if not source or not brand or not title or type(year) is not int or year not in YEARS:
        return None
    videos = []
    for slide in project.get('slideshow') or []:
        if not isinstance(slide, dict) or slide.get('mediaType') != 'video':
            continue
        video = slide.get('video') or {}
        identity = video.get('id') if isinstance(video, dict) else None
        # Vimeo identities only: do not retain preview tokens, private hashes,
        # player configuration, arbitrary video URLs or provider payloads.
        if isinstance(identity, str) and re.fullmatch(r'[1-9]\d{0,11}', identity):
            url = 'https://vimeo.com/' + identity
            if url not in videos:
                videos.append(url)
    if not videos:
        return None
    image = project.get('featuredImage') or {}
    return {
        'source_url': source, 'title': title, 'brand': brand,
        'published': str(year), 'source_name': f'Mother London {year} 官方作品',
        'industry': '待分类', 'ad_type': 'Mother London · 品牌创意作品',
        'format': 'video', 'language': '待核实',
        'summary': 'Mother London 官方品牌创意项目；官网所列影片可能为广告、品牌内容或案例介绍，片型、声音、时长与可迁移机制待实际观看确认。',
        'quality_evidence': [{'kind': 'official_portfolio',
            'text': f'Mother London 官网作品目录及项目详情，官网年份分类 {year}；来源收录不代替人工质量评价。',
            'source_url': source}],
        'thumbnail_url': _poster(image.get('url')) if isinstance(image, dict) else '',
        'media_status': 'source_link',
        'media_role': 'work_or_case_film_unverified',
        'rights': 'reference_only; redistribution_and_training_not_verified',
        'training_eligible': False,
        'tags': ['Mother London', 'official_portfolio', 'human_review_pending'],
        # IDs in the agency's metadata do not prove that Vimeo permits an
        # off-site player. Keep the official case entry, not a broken iframe.
        'creative_structure': {'source_page': source, 'portfolio_year': year,
                               'source_video_urls': videos[:8],
                               'preview_mode': 'official_source_only'},
    }


def parse_listing(text, year=2026, max_entries=MAX_ENTRIES):
    listing_url(year)
    data = _data(text)
    modules = data.get('modules')
    if not isinstance(modules, list):
        raise ValueError('source_layout_changed')
    rows, seen = [], set()
    for module in modules:
        if not isinstance(module, dict):
            continue
        for project in module.get('projects') or []:
            record = _project(project)
            if record and record['published'] == str(year) and record['source_url'] not in seen:
                seen.add(record['source_url'])
                rows.append(record)
                if max_entries is not None and len(rows) >= max_entries:
                    return rows
    return rows


def parse_detail(text, source_url):
    record = _project(_data(text))
    if not record:
        return {'has_video': False}
    if record['source_url'] != source_url:
        raise ValueError('detail_identity_mismatch')
    return {'has_video': True, 'record': record}


def apply_detail(record, detail):
    if not detail.get('has_video'):
        return None
    verified = detail['record']
    if verified['source_url'] != record['source_url'] or verified['published'] != record['published']:
        raise ValueError('detail_identity_mismatch')
    return verified
