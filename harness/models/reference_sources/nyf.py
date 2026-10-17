"""Official NYF advertising award records, grouped without inventing media facts."""
import re
from collections import defaultdict
from html import unescape
from html.parser import HTMLParser
from urllib.parse import urljoin, urlsplit

ORIGIN = 'https://www.nyfadvertising.com'
# IDs published by the official archive's year selector, not guessed paths.
ARCHIVES = {2026: 'a8e617c3-8b51-48bf-9be5-de349d59cba5',
            2025: '56f6454a-72bb-42e8-8847-f77d053e4c4f',
            2024: '1793d1da-469f-4b6d-94f8-b748e3d905cf',
            2023: '0e45120a-c1e1-46fa-ab57-64944c7ffdea'}
MEDIUMS = {'FILM', 'FILM CRAFT', 'BRANDED CONTENT/ENTERTAINMENT', 'AUDIO/RADIO'}
AWARDS = {'Best of Show', 'Grand', 'Gold', 'Silver', 'Bronze'}
UUID = r'[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}'


def listing_url(year):
    if type(year) is not int or year not in ARCHIVES:
        raise ValueError('invalid_nyf_year')
    return ORIGIN + '/Winners/List/' + ARCHIVES[year]


def text(value):
    return re.sub(r'\s+', ' ', unescape(re.sub(r'<[^>]*>', ' ', value))).strip()


class _Cards(HTMLParser):
    """Bound a card to its enclosing div; never parse navigation as a winner."""
    def __init__(self):
        super().__init__()
        self.cards, self.selected = [], []
        self.depth, self.year_select, self.option = 0, False, None

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag == 'select':
            self.year_select = attrs.get('id') == 'id'
        if tag == 'option' and self.year_select and 'selected' in attrs:
            self.option = [attrs.get('value'), '']
        if tag == 'div' and not self.depth and 'grid-item' in attrs.get('class', '').split():
            self.depth, self.attrs, self.body = 1, attrs, []
        elif self.depth:
            self.body.append(self.get_starttag_text())
            if tag == 'div':
                self.depth += 1

    def handle_data(self, value):
        if self.option is not None:
            self.option[1] += value
        if self.depth:
            self.body.append(value)

    def handle_endtag(self, tag):
        if tag == 'option' and self.option is not None:
            self.selected.append(tuple(self.option))
            self.option = None
        if tag == 'select':
            self.year_select = False
        if self.depth:
            self.body.append('</' + tag + '>')
            if tag == 'div':
                self.depth -= 1
                if not self.depth:
                    self.cards.append((self.attrs, ''.join(self.body)))


def _field(pattern, body):
    match = re.search(pattern, body, re.S | re.I)
    return text(match[1]) if match else ''


def parse_listing(html_text, year):
    listing_url(year)
    parser = _Cards()
    parser.feed(html_text)
    if parser.selected != [(ARCHIVES[year], str(year))] or not parser.cards or parser.depth:
        raise ValueError('source_layout_changed')
    groups = defaultdict(dict)
    for attrs, body in parser.cards:
        award = attrs.get('data-award', '')
        medium = _field(r'<div\b[^>]*class=[\"\']cat-bar[\"\'][^>]*>(.*?)</div>', body).split(':')[0].strip()
        if award not in AWARDS or medium not in MEDIUMS:
            continue
        title = _field(r'<h5\b[^>]*>(.*?)</h5>', body)
        fields = {text(k).casefold(): text(v) for k, v in re.findall(
            r'<li>\s*<label>(.*?)</label>\s*<span>(.*?)</span>', body, re.S | re.I)}
        links = re.findall(r'href=[\"\']([^\"\']+)[\"\']', body, re.I)
        urls = []
        for href in links:
            parts = urlsplit(urljoin(ORIGIN, unescape(href)))
            if (parts.scheme == 'https' and parts.netloc == 'www.nyfadvertising.com'
                    and not parts.query and not parts.fragment
                    and re.fullmatch('/Winners/WinnerDetailsNew/' + UUID, parts.path)):
                urls.append(ORIGIN + parts.path)
        brand, company = fields.get('brand', ''), fields.get('company', '')
        if not title or not brand or not company or not urls:
            raise ValueError('source_layout_changed')
        poster_match = re.search(r'data-bg=[\"\']url\(([^\"\')]+)', body, re.I)
        poster = unescape(poster_match[1]) if poster_match else ''
        parts = urlsplit(poster)
        if (parts.scheme != 'https' or parts.netloc != 'nyfstorageprod.blob.core.windows.net'
                or parts.query or parts.fragment or not parts.path.startswith('/thumbnail/')):
            poster = ''
        # A source grouping, not proof that distinct edits or campaigns are the
        # same video. Every award permalink survives for human comparison.
        key = (title.casefold(), brand.casefold(), company.casefold())
        url = sorted(set(urls))[0]
        groups[key][url] = {'title': title, 'brand': brand, 'company': company,
                            'medium': medium, 'category': fields.get('category', ''),
                            'award': award, 'url': url, 'poster': poster}
    records = []
    for entries in groups.values():
        entries = sorted(entries.values(), key=lambda row: row['url'])
        first = entries[0]
        mediums = sorted({entry['medium'] for entry in entries})
        records.append({
            'source_url': first['url'], 'title': first['title'][:300],
            'brand': first['brand'][:200], 'published': str(year), 'industry': '待分类',
            'ad_type': ' / '.join(mediums), 'source_name': f'NYF {year} 官方广告获奖目录',
            'thumbnail_url': first['poster'], 'media_status': 'source_link',
            'media_role': 'work_or_case_film_unverified',
            'summary': '官方获奖候选，按同年同作品名、品牌及制作公司分组。原片或案例说明片、实际声音和时长待观看确认。',
            'quality_evidence': [{'kind': 'award_winner',
                'text': f"NYF {year} · {e['award']} · {e['medium']} · {e['category']}",
                'source_url': e['url']} for e in entries],
            'creative_structure': {'company': first['company'], 'mediums': mediums,
                'source_grouping': 'same_year_title_brand_company; distinct_edits_unverified',
                'award_entry_count': len(entries)},
            'rights': 'reference_only; redistribution_and_training_not_verified',
            'tags': ['NYF Award Winner', *mediums],
        })
    return sorted(records, key=lambda row: row['source_url'])
