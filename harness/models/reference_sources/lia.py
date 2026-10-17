"""Public LIA winner metadata; keep permanent entry pages, never signed media URLs."""
import html
import re
from urllib.parse import parse_qsl, urlencode, urljoin, urlsplit, urlunsplit

ORIGIN = 'https://2025.liaentries.com'


def _text(value):
    return re.sub(r'\s+', ' ', html.unescape(re.sub(r'<[^>]*>', ' ', value))).strip()


def _stable_entry_url(href, origin=ORIGIN):
    parts = urlsplit(urljoin(origin + '/', html.unescape(href)))
    query = [(k, v) for k, v in parse_qsl(parts.query, keep_blank_values=True)
             if k in {'id_entry', 'id_medium', 'id_submedium', 'id_category', 'view', 'range'}]
    return urlunsplit(('https', parts.netloc, '/winners/', urlencode(query), ''))


def parse_winners(html_text, medium_id, year=2025, origin=ORIGIN):
    records = []
    for block in re.findall(r'<div class="medium-entry">(.*?)(?=<div class="medium-entry">|</section>|\Z)', html_text, re.S):
        href = re.search(r'href="([^"]*id_entry=[^"]+)"', block)
        if not href:
            continue
        entry_url = _stable_entry_url(href.group(1), origin)
        entry_id = dict(parse_qsl(urlsplit(entry_url).query)).get('id_entry', '')
        award = _text((re.search(r'class="medium-entry-title[^>]*">(.*?)</div>', block, re.S) or ('', ''))[1])
        labels = re.search(r'<em[^>]*>(.*?)</em>', block, re.S)
        labels = [_text(x) for x in (re.split(r'<br\s*/?>', labels.group(1), flags=re.I) if labels else []) if _text(x)]
        agency = _text((re.search(r'<h3[^>]*>.*?(?:<strong>)?(.*?)(?:</strong>)?</h3>', block, re.S) or ('', ''))[1])
        brand = _text((re.search(r'Brand:\s*<strong>(.*?)</strong>', block, re.S) or ('', ''))[1])
        title = _text((re.search(r'Title(?:\(s\))?:\s*<strong>(.*?)</strong>', block, re.S) or ('', ''))[1])
        if not title:
            title = brand or agency or ('LIA entry ' + entry_id)
        medium = labels[0] if labels else 'LIA Winners'
        category = labels[1] if len(labels) > 1 else ''
        records.append({
            'source_url': entry_url,
            'title': title[:300],
            'brand': brand[:200],
            'source_name': f'LIA {year} 官方 Winners 档案',
            'published': str(year),
            'industry': '待分类',
            'ad_type': medium + (' / ' + category if category else ''),
            'summary': 'LIA 官方获奖条目。媒体链接可能受站点权限或短期地址影响，未保存；等待人工观看和标注。',
            'quality_evidence': [{'kind': 'award_winner', 'text': f'LIA {year} · {award} · {medium} · {category}'.strip(' ·'),
                                  'source_url': entry_url}],
            'creative_structure': {'award': award, 'agency': agency, 'medium': medium, 'category': category},
            'media_status': 'source_link',
            'media_role': 'work_or_case_film_unverified',
            'rights': 'reference_only; redistribution_and_training_not_verified',
            'tags': ['LIA Winner', medium],
        })
    return records
