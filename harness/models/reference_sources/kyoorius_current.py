"""Public Film entries from Kyoorius' 2026 gallery.

Read JSON embedded by the public site without executing its scripts. Keep
only source evidence and media locators, never the individual-credit payload.
"""
import json
import re
import unicodedata
from html.parser import HTMLParser
from urllib.parse import urlsplit

from harness.models.reference_download import KYOORIUS_MEDIA_HOSTS, validate_url
from harness.models.reference_sources.kyoorius import _award_kind, _text

ORIGIN = 'https://winners.kyoorius.com'
LISTING_MAX_BYTES = 12 * 1024 * 1024
FILM_DISCIPLINES = frozenset(('Film', 'Film Craft', 'Regional Film'))


def listing_url(year):
    if type(year) is not int or year != 2026:
        raise ValueError('invalid_kyoorius_year')
    return ORIGIN + '/winners/2026/kca/'


class _Flight(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=False)
        self.in_script = False
        self.script = []
        self.chunks = []

    def handle_starttag(self, tag, attrs):
        if tag == 'script':
            self.in_script, self.script = True, []

    def handle_data(self, data):
        if self.in_script:
            self.script.append(data)

    def handle_endtag(self, tag):
        if tag != 'script' or not self.in_script:
            return
        self.in_script = False
        raw = ''.join(self.script).strip().removesuffix(';')
        prefix = 'self.__next_f.push('
        if not raw.startswith(prefix) or not raw.endswith(')'):
            return
        try:
            value = json.loads(raw[len(prefix):-1])
        except ValueError:
            return
        if isinstance(value, list) and len(value) == 2 and value[0] == 1 and isinstance(value[1], str):
            self.chunks.append(value[1])


def _embedded(text, field):
    if len(text.encode('utf-8')) > LISTING_MAX_BYTES:
        raise ValueError('source_page_too_large')
    parser = _Flight()
    parser.feed(text)
    stream = ''.join(parser.chunks)
    expected = '[' if field == 'entries' else '{'
    match = re.search(r'"' + field + r'":\s*(' + re.escape(expected) + ')', stream)
    if not match:
        raise ValueError('unrecognized_kyoorius_page')
    value, _ = json.JSONDecoder().raw_decode(stream, match.start(1))
    return value


def _source_url(entry):
    identity, title = entry.get('id'), entry.get('title')
    if type(identity) is not int or identity <= 0 or not isinstance(title, str) or not title.strip():
        raise ValueError('invalid_kyoorius_entry')
    # Match the public gallery's client-side slug rule.  In particular, the
    # gallery removes apostrophes before collapsing punctuation; replacing
    # them with a dash produces a different route (and a 404) for titles such
    # as "Don't Waste Water".  Details are independently checked against the
    # numeric ID before any source record is ingested.
    slug = unicodedata.normalize('NFKD', title.strip())
    slug = re.sub(r'[\u0300-\u036f]', '', slug).lower()
    slug = re.sub(r"['\u2019]", '', slug)
    slug = re.sub(r'[^a-z0-9]+', '-', slug).strip('-')
    if not slug:
        raise ValueError('invalid_kyoorius_entry')
    return listing_url(2026) + str(identity) + '-' + slug + '/'


def _record(entry):
    if not isinstance(entry, dict):
        raise ValueError('invalid_kyoorius_entry')
    if str(entry.get('year')) != '2026':
        return None
    hierarchy = entry.get('hierarchy', [])
    if not isinstance(hierarchy, list):
        raise ValueError('invalid_kyoorius_entry')
    disciplines = [h.get('programName') for h in hierarchy if isinstance(h, dict) and h.get('currentLabel') == 'Discipline']
    if not FILM_DISCIPLINES.intersection(disciplines):
        return None
    source = _source_url(entry)
    categories = [_text(h.get('programName')) for h in hierarchy if isinstance(h, dict)
                  and h.get('currentLabel') in ('Discipline', 'Category', 'Sub-Category')]
    award = _text(entry.get('awardLevel'))
    return {
        'source_url': source, 'title': _text(entry['title'])[:300],
        'brand': _text(entry.get('brand'))[:200], 'industry': '待分类',
        'ad_type': 'Kyoorius · ' + ' · '.join(categories), 'format': 'video',
        'source_name': 'Kyoorius Creative Awards 2026 官方案例', 'published': '2026',
        'summary': 'Kyoorius 2026 官方 Film 案例；保留原始奖项级别。公开视频的原片身份、声音和品牌事实仍待人工确认。',
        'quality_evidence': [{'kind': _award_kind(award),
            'text': 'Kyoorius Creative Awards 2026 · ' + (award or '奖项级别待核实') + ' · ' + ' · '.join(categories),
            'source_url': source}],
        'media_status': 'source_link', 'media_role': 'work_or_case_film_unverified',
        'rights': 'reference_only; redistribution_and_training_not_verified',
        'tags': ['Kyoorius', 'film', 'human_review_pending'],
        'creative_structure': {'award': award, 'category': ' · '.join(categories),
                               'source_page': source, 'source_entry_id': entry['id']},
    }


def parse_listing(text, year=2026, max_entries=12):
    listing_url(year)
    entries = _embedded(text, 'entries')
    if not isinstance(entries, list) or not 0 < len(entries) <= 5000:
        raise ValueError('unrecognized_kyoorius_listing')
    found, seen = [], set()
    for entry in entries:
        if not isinstance(entry, dict):
            raise ValueError('invalid_kyoorius_entry')
        record = _record(entry)
        if record and record['source_url'] not in seen:
            seen.add(record['source_url'])
            found.append(record)
            if max_entries is not None and len(found) >= max_entries:
                break
    return found


def _video(value):
    try:
        if not isinstance(value, str):
            return ''
        validate_url(value)
        if urlsplit(value).hostname not in KYOORIUS_MEDIA_HOSTS:
            return ''
        return value
    except ValueError:
        return ''


def parse_detail(text, source_url):
    entry = _embedded(text, 'entry')
    record = _record(entry)
    expected = re.fullmatch(re.escape(listing_url(2026)) + r'(\d+)-[^/]+/', source_url)
    if not record or not expected or entry['id'] != int(expected.group(1)):
        raise ValueError('kyoorius_detail_identity_mismatch')
    record['source_url'] = source_url
    record['creative_structure']['source_page'] = source_url
    for evidence in record['quality_evidence']:
        evidence['source_url'] = source_url
    videos, seen = [], set()
    for media in entry.get('media', []):
        if not isinstance(media, dict) or media.get('mediaType') != 'video':
            continue
        url = _video(media.get('videoResizePath')) or _video(media.get('path'))
        if url and url not in seen:
            seen.add(url)
            videos.append({'url': url, 'source_label': _text(media.get('adminFieldName'))[:100]})
    if len(videos) > 32:
        raise ValueError('too_many_kyoorius_videos')
    # Prefer the work over a case-study explanation. Preserve every public
    # variant and its source label, making the single preview choice explicit.
    videos.sort(key=lambda video: video['source_label'] != 'Content AV')
    return {'has_video': bool(videos), 'record': record, 'videos': videos}


def apply_detail(record, detail):
    if not detail.get('has_video'):
        return None
    result = {**detail['record'], 'source_url': record['source_url']}
    videos = detail['videos']
    result['creative_structure'].update(public_video_url=videos[0]['url'], public_video_variants=videos,
        preview_selection='first_content_av_else_first_public_video', public_video_count=len(videos))
    if len(videos) > 1:
        result['summary'] += f' 详情页含 {len(videos)} 个视频，本地预览优先取首个作品视频；各版本链接保留供核对。'
    return result
