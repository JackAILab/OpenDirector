"""Public AICP shortlist metadata; intentionally drops expiring signed media URLs."""
import re
from html import unescape
from urllib.parse import urlencode

ORIGIN = 'https://aicpawards.awardcore.com'


def _text(value):
    return unescape(re.sub(r'<[^>]*>', ' ', value)).strip()


def parse_shortlist(html, category_id, year=2026, award_type='aicp'):
    records = []
    pattern = re.compile(
        r'<div class="vid_elem"[^>]*data-entid="(\d+)"[^>]*>.*?'
        r'<div class="brand\s*">(.*?)</div>.*?'
        r'<span class="campaign">(.*?)</span>', re.S)
    for entry, brand, campaign in pattern.findall(html):
        query = urlencode({'catID': int(category_id), 'type': award_type, 'entry': int(entry)})
        records.append({
            'source_url': ORIGIN + '/shortlist/list.php?' + query,
            'title': _text(campaign)[:300] or _text(brand)[:300],
            'brand': _text(brand)[:200],
            'source_name': 'AICP 官方 ' + ('Next' if award_type == 'next' else 'Show') + ' Shortlist 档案',
            'published': str(year),
            'industry': '待分类',
            'ad_type': ('品牌内容 / 创新 Shortlist' if award_type == 'next' else '广告影片 Shortlist'),
            'summary': 'AICP 官方入选条目。媒体链接可能是短期签名地址，未保存；等待人工从官方页面观看和标注。',
            'quality_evidence': [{'kind': 'award_shortlist', 'text': f'AICP {year} Shortlist · category {category_id}',
                                  'source_url': ORIGIN + '/shortlist/list.php?' + query}],
            'media_status': 'source_link',
            'media_role': 'work_or_case_film_unverified',
            'rights': 'reference_only; redistribution_and_training_not_verified',
            'tags': ['AICP Shortlist'],
        })
    return records
