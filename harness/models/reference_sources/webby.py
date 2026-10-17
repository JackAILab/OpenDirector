"""Read-only Webby winner metadata for advertising video references.

The public winners page is an Angular shell; the official gallery API is the
stable source of the listing and detail metadata. We keep the Webby page as
the human-facing source link and retain external video links only as evidence
for review. This adapter never downloads or republishes media.
"""
import re
from urllib.parse import parse_qs, urlencode, urlsplit, urlunsplit

WEB_ORIGIN = 'https://winners.webbyawards.com'
API_ORIGIN = 'https://api.recogmedia.net/api'
MEDIA_TYPE_ID = 1
CATEGORY_ID = 46
CATEGORY_TYPE = 'advertising-campaigns'
CATEGORY_SLUG = 'best-video-campaign'
MEDIA_TYPE_SLUG = 'advertising-media-pr'
YEARS = (2025, 2024, 2023)
MAX_WINNERS = 2


def listing_payload(year, page=1):
    if type(year) is not int or year not in YEARS:
        raise ValueError('invalid_webby_year')
    if type(page) is not int or page < 1 or page > 20:
        raise ValueError('invalid_webby_page')
    return {
        'PageNumber': page,
        'PieceType': True,
        'awards': [],
        'categories': [CATEGORY_ID],
        'years': [str(year)],
        'Sort': None,
        'MediaType': [MEDIA_TYPE_ID],
        'ByEntries': False,
    }


def _slug(value):
    value = re.sub(r"[^\w\s-]", '', value or '', flags=re.UNICODE)
    return re.sub(r'[-\s]+', '-', value.strip()).strip('-').lower()[:120]


def winner_url(year, item_id, title):
    return (f'{WEB_ORIGIN}/{year}/{MEDIA_TYPE_SLUG}/{CATEGORY_TYPE}/'
            f'{CATEGORY_SLUG}/{int(item_id)}/{_slug(title)}')


def parse_listing(payload, year, page=1):
    listing_payload(year, page)
    if not isinstance(payload, dict) or payload.get('Success') is not True or not isinstance(payload.get('Data'), list):
        raise ValueError('source_layout_changed')
    records = []
    for item in payload['Data']:
        if not isinstance(item, dict):
            raise ValueError('source_layout_changed')
        if item.get('Year') != year or item.get('MediaTypeId') != MEDIA_TYPE_ID:
            raise ValueError('source_scope_mismatch')
        categories = item.get('Categories')
        if not isinstance(categories, list) or any(not isinstance(c, dict) for c in categories):
            raise ValueError('source_layout_changed')
        category = next((c for c in categories if c.get('CategoryId') == CATEGORY_ID), None)
        # Awards for another category on the same campaign are not evidence
        # that it won the specific category being collected.
        if not category or not (category.get('IsWinner') is True or category.get('IsPVWinner') is True):
            continue
        item_id = item.get('ItemId')
        title = str(item.get('Title') or '').strip()
        if type(item_id) is not int or item_id <= 0 or not title:
            raise ValueError('source_layout_changed')
        records.append({
            'item_id': int(item_id),
            'title': title[:300],
            # Organization is the submitting agency or business, not a
            # verified product brand. Preserve its actual role explicitly.
            'submitter': str(item.get('Organization') or '')[:200],
            'year': year,
            'source_url': winner_url(year, item_id, title),
            'category': str(category.get('Category') or 'Best Video Campaign'),
            'award_labels': [label for flag, label in (
                ('IsWinner', 'Webby Winner'), ('IsPVWinner', "People's Voice Winner"))
                if category.get(flag) is True],
        })
        if len(records) >= MAX_WINNERS:
            break
    return records


def _public_link(value):
    if not isinstance(value, str):
        return ''
    value = value.strip()
    parts = urlsplit(value)
    if (parts.scheme != 'https' or not parts.hostname or parts.username or parts.password
            or parts.port not in (None, 443) or parts.fragment):
        return ''
    host = parts.hostname.lower()
    if host not in {'www.youtube.com', 'youtube.com', 'youtu.be', 'vimeo.com', 'www.vimeo.com'}:
        return ''
    if host in {'www.youtube.com', 'youtube.com'}:
        query = parse_qs(parts.query, keep_blank_values=True)
        if parts.path != '/watch' or set(query) != {'v'} or len(query['v']) != 1:
            return ''
        video_id = query['v'][0]
        if not re.fullmatch(r'[A-Za-z0-9_-]{11}', video_id):
            return ''
        return urlunsplit((parts.scheme, 'www.youtube.com', '/watch', urlencode({'v': video_id}), ''))
    if parts.query:
        return ''
    pattern = r'/[A-Za-z0-9_-]{11}' if host == 'youtu.be' else r'/[0-9]+'
    if not re.fullmatch(pattern, parts.path):
        return ''
    return urlunsplit((parts.scheme, parts.netloc.lower(), parts.path or '/', '', ''))


def enrich(record, payload):
    if not isinstance(payload, dict) or payload.get('Success') is not True or not isinstance(payload.get('Data'), dict):
        raise ValueError('source_layout_changed')
    detail = payload['Data']
    if int(detail.get('PieceID', -1)) != record['item_id']:
        raise ValueError('source_layout_changed')
    links = []
    for value in str(detail.get('Url') or '').split('|'):
        link = _public_link(value)
        if link and link not in links:
            links.append(link)
    evidence = [{
        'kind': 'award_winner',
        'text': f"Webby {record['year']} · {' / '.join(record['award_labels'])} · {record['category']}",
        'source_url': record['source_url'],
    }]
    if links:
        evidence.append({'kind': 'public_video_link', 'text': '官方详情页公开外链，视频身份与版本待人审确认。', 'source_url': links[0]})
    return {
        'source_url': record['source_url'],
        'title': record['title'],
        'brand': '',
        'industry': '待分类',
        'ad_type': 'Webby · ' + record['category'],
        'format': 'video',
        'language': 'en',
        'summary': 'Webby 官方广告视频获奖条目；外链可能是系列中的一个版本，需人审确认是否为原片及其时长、声音和产品一致性。',
        'quality_evidence': evidence,
        'source_name': f"Webby {record['year']} 官方广告视频获奖",
        'published': str(record['year']),
        'media_status': 'source_link',
        'media_role': 'work_or_case_film_unverified',
        'embed_url': links[0] if links else '',
        'rights': 'reference_only; redistribution_and_training_not_verified',
        'creative_structure': {
            'submitter': record['submitter'],
            'award_labels': record['award_labels'],
            'category': record['category'],
            'public_video_links': links,
            'source_page': record['source_url'],
        },
        'tags': ['Webby', 'award-winner', 'video-campaign', 'human_review_pending'],
    }
