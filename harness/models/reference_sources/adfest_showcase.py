"""Read the public ADFEST 2026 showcase; never use its delegate-only archive."""
import copy
import hashlib
import json
import re
from html.parser import HTMLParser
from urllib.parse import parse_qs, urljoin, urlsplit

from harness.models.reference_download import validate_url
from harness.models.reference_sources.award_evidence import award_evidence_kind

ORIGIN = 'https://www.adfest.com'
YEAR = 2026
MEDIA_BASE = 'https://adfest.d-energy.cn/adfest/works2026/'
SHOWCASE_PATH = '/Home/Winners/winners_showcase.html'
DETAIL_PATH = '/Home/Winners/winners_showcase_detail.html'
CATEGORIES = {11: ('Film Lotus', 'F'), 10: ('Film Craft Lotus', 'CF'),
              9: ('Entertainment Lotus', 'EN')}
MAX_BYTES = 4 * 1024 * 1024
MAX_PAGES = 100
MAX_ENTRIES = 12


class _Node:
    def __init__(self, tag='', attrs=()):
        self.tag, self.attrs, self.children = tag, dict(attrs), []

    def find(self, tag, cls=''):
        for child in self.children:
            if not isinstance(child, _Node):
                continue
            if child.tag == tag and (not cls or cls in child.attrs.get('class', '').split()):
                yield child
            yield from child.find(tag, cls)

    def text(self):
        return ' '.join(' '.join(c.text() if isinstance(c, _Node) else c
                                for c in self.children).split())


class _Markup(HTMLParser):
    """Small read-only DOM; scripts are just text and are never evaluated."""
    VOID = {'area', 'base', 'br', 'col', 'embed', 'hr', 'img', 'input',
            'link', 'meta', 'param', 'source', 'track', 'wbr'}

    def __init__(self, text):
        super().__init__(convert_charrefs=True)
        self.root = _Node()
        self.stack = [self.root]
        self.feed(text)
        self.close()

    def handle_starttag(self, tag, attrs):
        if len(self.stack) > 128:
            raise ValueError('unrecognized_listing')
        node = _Node(tag, attrs)
        self.stack[-1].children.append(node)
        if tag not in self.VOID:
            self.stack.append(node)

    def handle_startendtag(self, tag, attrs):
        self.handle_starttag(tag, attrs)
        if tag not in self.VOID:
            self.stack.pop()

    def handle_endtag(self, tag):
        for i in range(len(self.stack) - 1, 0, -1):
            if self.stack[i].tag == tag:
                del self.stack[i:]
                break

    def handle_data(self, data):
        self.stack[-1].children.append(data)


def listing_url(category, page=1):
    if type(category) is not int or category not in CATEGORIES:
        raise ValueError('invalid_adfest_category')
    if type(page) is not int or not 1 <= page <= MAX_PAGES:
        raise ValueError('invalid_adfest_page')
    return ORIGIN + SHOWCASE_PATH + f'?category={category}&awards=all&page={page}'


def _query(value, path):
    url = urlsplit(urljoin(ORIGIN, value))
    if url.scheme != 'https' or url.netloc != 'www.adfest.com' or url.path != path or url.fragment:
        raise ValueError('unrecognized_listing')
    return parse_qs(url.query, keep_blank_values=True)


def parse_listing(text, category, page=1):
    listing_url(category, page)
    if len(text.encode()) > MAX_BYTES:
        raise ValueError('source_page_too_large')
    # The site masthead may already advertise next year's event. The published
    # works directory, category selection and pagination identify this edition.
    bases = re.findall(r'\bvar\s+worksBase\s*=\s*[\'"]([^\'"]+)[\'"]', text)
    if bases != [MEDIA_BASE]:
        raise ValueError('source_edition_changed')
    root = _Markup(text).root
    selected = [n.attrs.get('value') for s in root.find('select', 'mobile_right_menu')
                for n in s.find('option') if 'selected' in n.attrs]
    awards = [n.attrs.get('value') for s in root.find('select', 'mobile_ws_menu')
              for n in s.find('option') if 'selected' in n.attrs]
    if selected != [str(category)] or awards != ['all']:
        raise ValueError('source_category_mismatch')
    pages, active = set(), []
    for node in root.find('a', 'showcase_page_number'):
        query = _query(node.attrs.get('href', ''), SHOWCASE_PATH)
        value = node.text()
        if not value.isdecimal() or not 1 <= int(value) <= MAX_PAGES or query != {
                'category': [str(category)], 'awards': ['all'], 'page': [value]}:
            raise ValueError('unrecognized_listing')
        pages.add(int(value))
        if 'winners_font02' in node.attrs.get('class', '').split():
            active.append(int(value))
    if not pages or pages != set(range(1, max(pages) + 1)) or active != [page]:
        raise ValueError('source_page_mismatch')

    records, seen = [], set()
    category_name, prefix = CATEGORIES[category]
    for card in root.find('div', 'showcase_item'):
        links = list(card.find('a', 'toDetail'))
        queries = [_query(n.attrs.get('href', ''), DETAIL_PATH) for n in links]
        if not queries or any(q != queries[0] for q in queries):
            raise ValueError('unrecognized_listing')
        query = queries[0]
        identity, code = query.get('id', [''])[0], query.get('code', [''])[0]
        if query != {'id': [identity], 'code': [code]} or not re.fullmatch(r'[1-9][0-9]{0,8}', identity) or not re.fullmatch(prefix + r'[0-9]{2}_[0-9]{3}', code):
            raise ValueError('unrecognized_listing')
        title_nodes = list(card.find('span', 'winners_font02'))
        brand_nodes = [n for m in card.find('div', 'showcase_item_meta')
                       for n in m.children if isinstance(n, _Node) and n.tag == 'div']
        award_nodes = [n for a in card.find('div', 'showcase_item_award') for n in a.find('img')]
        posters = [n.attrs.get('src', '') for t in card.find('div', 'showcase_item_thumb') for n in t.find('img')]
        if len(title_nodes) != 1 or not brand_nodes or len(award_nodes) != 1 or len(posters) != 1:
            raise ValueError('unrecognized_listing')
        title, brand = title_nodes[0].text(), brand_nodes[0].text()
        award = award_nodes[0].attrs.get('alt', '').strip().upper()
        if not title or len(title) > 300 or len(brand) > 200 or not re.fullmatch(r'[A-Z ]{1,40}', award):
            raise ValueError('unrecognized_listing')
        placeholder = posters[0] == MEDIA_BASE + 'pdfT.jpg'
        if not placeholder and not re.fullmatch(re.escape(MEDIA_BASE + code) + r'_[A-Za-z0-9_-]{1,32}\.jpg', posters[0]):
            raise ValueError('source_edition_changed')
        source = ORIGIN + SHOWCASE_PATH + '?id=' + identity
        if source in seen:
            raise ValueError('repeated_source_entry')
        seen.add(source)
        records.append({
            'source_url': source, 'detail_url': ORIGIN + DETAIL_PATH + '?id=' + identity,
            'title': title, 'brand': brand, 'industry': '待分类',
            'ad_type': 'ADFEST ' + category_name + ' / 类别待确认',
            'format': 'video', 'source_name': f'ADFEST {YEAR} {category_name} 公开作品展厅',
            'published': str(YEAR), 'thumbnail_url': '' if placeholder else posters[0],
            'summary': 'ADFEST 官方公开作品展厅；保留奖项与来源。视频的原片身份、声音、版本和品牌事实待人工确认。',
            'quality_evidence': [{'kind': 'award_winner' if award == 'GRANDE' else award_evidence_kind(award),
                'text': f'ADFEST {YEAR} · {category_name} · {award} · {code}', 'source_url': source}],
            'media_status': 'source_link', 'media_role': 'work_or_case_film_unverified',
            'rights': 'reference_only; redistribution_and_training_not_verified',
            'tags': ['adfest', 'public-showcase', 'human_review_pending'],
            'creative_structure': {'entry_code': code, 'source_entry_id': int(identity),
                'award': award, 'award_year': YEAR, 'discipline': category_name,
                'source_category_id': category, 'source_page': source},
        })
    if not 1 <= len(records) <= MAX_ENTRIES:
        raise ValueError('unrecognized_listing')
    return {'records': records, 'page': page, 'pages': max(pages),
            'fingerprint': hashlib.sha256(json.dumps([max(pages),
                *[(r['source_url'], r['creative_structure']['entry_code']) for r in records]]).encode()).hexdigest()}


def apply_detail(record, text):
    if len(text.encode()) > MAX_BYTES:
        raise ValueError('source_page_too_large')
    raw = json.loads(text)
    if not isinstance(raw, dict) or type(raw.get('code')) is not int or raw['code'] != 0:
        raise ValueError('invalid_source_detail')
    fields, rows, files = {}, raw.get('data'), raw.get('files2')
    if not isinstance(rows, list) or len(rows) > 200 or not isinstance(files, list) or len(files) > 32:
        raise ValueError('invalid_source_detail')
    # Retain only the facts needed to identify and browse a reference, not
    # credits, individual names, campaign prose or arbitrary external links.
    for field in rows:
        if not isinstance(field, dict):
            raise ValueError('invalid_source_detail')
        key = field.get('keyword')
        if key in ('TITLE', 'BRAND', 'SUB CATEGORY'):
            content = field.get('content')
            if not isinstance(content, str) or len(content) > 1000 or key in fields:
                raise ValueError('invalid_source_detail')
            fields[key] = _Markup(content).root.text()
    # The live Craft listing inserts a space before a parenthesized subtitle
    # while its detail omits it. Ignore only spacing around these delimiters;
    # preserve word boundaries, numbers and the words inside parentheses.
    def identity_text(value):
        return re.sub(r'\s*([()])\s*', r'\1', value.casefold())

    if any(identity_text(fields.get(key, '')) != identity_text(record[field])
           for key, field in (('TITLE', 'title'), ('BRAND', 'brand'))):
        raise ValueError('source_detail_identity_mismatch')
    videos, code = [], record['creative_structure']['entry_code']
    for file in files:
        if not isinstance(file, dict):
            raise ValueError('invalid_source_detail')
        if file.get('type') != 'mp4':
            continue
        name = file.get('name', '')
        if not isinstance(name, str) or not re.fullmatch(re.escape(code) + r'(?:_[A-Za-z0-9-]{1,32})?\.mp4', name):
            raise ValueError('source_detail_identity_mismatch')
        url = validate_url(MEDIA_BASE + name)
        if url not in videos:
            videos.append(url)
    if not videos:
        return None
    result = copy.deepcopy(record)
    result.pop('detail_url', None)
    category = fields.get('SUB CATEGORY', '')
    if not category or len(category) > 200:
        raise ValueError('invalid_source_detail')
    result['ad_type'] = 'ADFEST ' + result['creative_structure']['discipline'] + ' / ' + category
    result['creative_structure'].update(category=category, public_video_url=videos[0],
        public_video_variants=[{'url': u, 'source_label': 'Official public video'} for u in videos],
        public_video_count=len(videos), preview_selection='first_published_public_video')
    result['quality_evidence'].append({'kind': 'public_video_metadata',
        'text': f'官方展厅公开 {len(videos)} 个视频；默认预览首个，原广告与案例说明片身份待观看确认。',
        'source_url': result['source_url']})
    return result
