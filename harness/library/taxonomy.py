"""Conservative browsing labels derived from collected, official award categories.

These are reversible source-category mappings, never human preferences or
claims about effectiveness. Titles, brand names and craft categories are not
industry evidence. Unknown or conflicting categories remain unclassified.
"""
import re
from urllib.parse import urlsplit


RULE_VERSION = 2
UNKNOWN = {'', '待分类', 'consumer', 'advertising'}
SOURCE_HOSTS = {
    'www.dandad.org', 'awards.ciclopefestival.com',
    'www.cresta-awards.com', 'kinsalesharks.awardsengine.com',
    'berlincommercial.awardsengine.com',
}


def _normalized(value):
    return re.sub(r'\s+', ' ', value).strip().casefold()


# Exact source labels only. For example, "Use of Music", "Gaming" and
# "Corporate Purpose" describe a technique or theme, not the client's sector.
_LABELS = {
    '食品饮料': ('Foods', 'Beverages', 'Beverages - Alcoholic',
             'Beverages - Non-Alcoholic', 'Confections/Snacks', 'Alcoholic drinks',
             'Food, Confectionery, Snacks & Cakes & Non - Alcoholic Drink'),
    '汽车出行': ('Automotive', 'Automotive including Auto Products and Services'),
    '金融保险': ('Banking & Finance', 'Finance', 'Financial Services', 'Financial and Insurance'),
    '医疗健康': ('Health & Wellness', 'Health & Pharma', 'Pharmaceuticals',
             'Health Care and Pharmaceuticals', 'Health Care Services', 'Healthcare & Pharmacy'),
    '美妆个护': ('Beauty', 'Beauty & Well-being', 'Cosmetics/Toiletries', 'Toiletries & Personal Care',
             'Fragrance, Cosmetics, Beauty'),
    '家居生活': ('Home Products',),
    '零售电商': ('Retail',),
    '奢侈时尚': ('Fashion & Accessories', 'Fashion, Clothing, Footwear & Accessories',
             'SPECIAL SECTION - FASHION & LUXURY'),
    '科技互联网': ('Technology & Tech Equipment',),
    '通信服务': ('Communication Providers',),
    '教育培训': ('Education',),
    '能源公用事业': ('Utilities',),
    '文旅休闲': ('Travel', 'Travel & Leisure', 'Travel & Tourism', 'Travel, Tourism, Hotels'),
    '公益与公共服务': ('Public Service/Charity/NGO', 'Charities & Trusts',
                'Public Service and Charities', 'Public Service & Charities'),
}
CATEGORY_INDUSTRY = {_normalized(category): label
                     for label, categories in _LABELS.items() for category in categories}


def classified_metadata(source_url, data):
    """Return enriched metadata only when all mapped categories agree.

    Existing substantive industry labels are preserved. A source's award medium
    is retained separately; grouping for browsing never changes source evidence.
    """
    if _normalized(str(data.get('industry') or '')) not in UNKNOWN:
        return data
    try:
        host = urlsplit(source_url).hostname or ''
    except (TypeError, ValueError):
        return data
    if host not in SOURCE_HOSTS and not re.fullmatch(r'20\d{2}\.liaentries\.com', host):
        return data
    structure = data.get('creative_structure')
    candidates = [structure.get('category')] if isinstance(structure, dict) else []
    if host == 'www.dandad.org':
        # Only the award taxonomy tags from the adapter; not free-text notes.
        for tag in data.get('tags', []) or []:
            if isinstance(tag, str) and re.match(r'^(Film|TV & Cinema Advertising)\s*/', tag):
                candidates.append(tag.split(' / ')[-1])
    matches = []
    for category in candidates:
        if not isinstance(category, str):
            continue
        key = _normalized(category)
        if key.endswith(' campaign'):
            key = key[:-len(' campaign')]
        if key in CATEGORY_INDUSTRY:
            matches.append((category.strip(), CATEGORY_INDUSTRY[key]))
    labels = {label for _, label in matches}
    if len(labels) != 1:
        return data
    return {**data, 'industry': labels.pop(), 'industry_evidence': {
        'kind': 'source_category_mapping', 'rule_version': RULE_VERSION,
        'categories': sorted({category for category, _ in matches}),
        'human_confirmed': False,
    }}
