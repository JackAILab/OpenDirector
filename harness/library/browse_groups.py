"""Small browsing groups derived only from recorded source categories.

Groups describe the award/archive category, not an observed film genre or a
human judgement. Keep the original category intact; a record can belong to
several groups and unfamiliar categories remain unconfirmed.
"""
import re

LABELS = {
    'film': '广告影片',
    'tv_cinema': '电视与影院',
    'online_social': '网络与社交',
    'branded': '品牌内容',
    'product': '产品介绍',
    'animation': '动画',
    'sound': '音乐与声音',
    'craft': '摄影与制作',
    'strategy': '创意策略',
    'visual': '视觉参考',
    'unconfirmed': '类别待确认',
}

EXACT = {
    '品牌广告影片': ('film',), 'commercial_film': ('film',),
    '广告影片 shortlist': ('film',), '品牌内容 / 创新 shortlist': ('branded', 'strategy'),
    '品牌视觉参考': ('visual',), '动画影像参考': ('animation',),
    '音乐影像参考': ('sound',), '电视/点播广告': ('tv_cinema',),
    '电视/影院广告': ('tv_cinema',), '影院广告': ('tv_cinema',),
    '社交媒体广告': ('online_social',), '即时营销广告': ('strategy',),
    'winner spotlight / case film': ('strategy',),
}
MEDIA = {
    'tv & cinema': 'tv_cinema', 'tv/cinema': 'tv_cinema',
    'online film': 'online_social', 'use of social media & influencers': 'online_social',
    'audio & radio': 'sound', 'radio & audio': 'sound', 'audio/radio': 'sound',
    'music & sound': 'sound', 'music video': 'sound', 'branded content': 'branded',
    'branded entertainment': 'branded', 'branded content & entertainment': 'branded',
    'branded content/entertainment': 'branded',
    'production & post-production': 'craft', 'film craft': 'craft',
    'film': 'film', 'creative strategy': 'strategy',
    'digital': 'strategy', 'integration': 'strategy', 'ambient & activation': 'strategy',
}


def is_explicit_non_ad(category):
    """Defer only a recorded non-advertising medium, never a title keyword.

    Craft and sound awards can be commercials. Berlin's detail header is the
    currently supported source that explicitly distinguishes these sections.
    Unknown categories stay eligible for discovery and classification.
    """
    value = re.sub(r'\s+', ' ', str(category or '')).strip().casefold()
    prefix = 'berlin commercial · '
    if not value.startswith(prefix):
        return False
    medium = value.removeprefix(prefix).partition(' / ')[0]
    return medium in ('music video', 'music videos', 'personal work')


def group_ids(category):
    value = re.sub(r'\s+', ' ', str(category or '')).strip().casefold()
    if value in EXACT:
        return EXACT[value]
    groups = set()
    # Exact medium tokens: the slash inside TV/Cinema or AUDIO/RADIO is part
    # of its name. Never infer from a title, brand, or an arbitrary substring.
    parts = value.split(' / ')
    if parts[0] in MEDIA:
        groups.add(MEDIA[parts[0]])
        # NYF may provide multiple media categories for the same work.
        groups.update(MEDIA[p] for p in parts[1:] if p in MEDIA)
    if value.startswith('cresta · 1: moving image'):
        groups.add('film')
    elif value.startswith('cresta · 16: film craft'):
        groups.add('craft')
    elif value.startswith('ciclope · '):
        section = value.removeprefix('ciclope · ')
        mapped = {'production': 'craft', 'post-production': 'craft',
                  'animation': 'animation', 'sound & music': 'sound',
                  'ideas': 'strategy', 'innovation': 'craft',
                  'ciclope craft': 'craft', 'ciclope ideas': 'strategy',
                  'ciclope entertainment': 'branded'}
        if section in mapped:
            groups.add(mapped[section])
    elif value.startswith('kyoorius · ') and len(value.split(' · ')) >= 3 and value.split(' · ')[1] in ('film', 'regional film', 'film craft'):
        # The 2026 gallery separates its discipline and category with dots.
        # Match those recorded tokens, never words in a title or brand name.
        _, discipline, category, *_ = value.split(' · ')
        groups.add('craft' if discipline == 'film craft' else 'film')
        if discipline == 'film craft':
            if category == 'animation':
                groups.add('animation')
            elif category in ('sound design / sfx', 'use of adapted or existing / licensed music',
                              'use of original music or compositions'):
                groups.add('sound')
    elif value.startswith('kyoorius · film tv & cinema'):
        groups.add('tv_cinema')
    elif value.startswith(('kyoorius · film craft', 'kinsale · film craft')):
        groups.add('craft')
    elif value in ('kyoorius · film', 'kinsale · advertising film'):
        groups.add('film')
    elif value.startswith('british arrows · '):
        if value.removeprefix('british arrows · ') in ('15秒以内奖项', '30秒以内奖项', '广告与制作工艺'):
            groups.add('film')
    elif value.startswith('berlin commercial · '):
        section = value.removeprefix('berlin commercial · ')
        medium, _, category = section.partition(' / ')
        if medium in ('commercials and branded content', 'commercials and branded content - short', 'commercials and branded content - long'):
            groups.update(('film', 'branded'))
        elif medium == 'commercial work':
            # The 2024 detail headers use this explicit commercial section.
            groups.add('film')
        elif medium == 'music videos':
            groups.add('sound')
        elif medium == 'personal work':
            groups.add('visual')
        if section.startswith('craft: ') or category.startswith('craft: '):
            groups.add('craft')
    elif value.startswith('adfest film lotus / '):
        groups.add('film')
    elif value.startswith('adfest film craft lotus / '):
        groups.add('craft')
    elif value.startswith('adfest entertainment lotus / '):
        groups.add('branded')
    elif value.startswith('effie case · '):
        groups.add('strategy')
    elif value == 'webby · best video campaign':
        groups.add('online_social')
    elif value in ('b19 product and launch videos', 'b23 product and launch videos'):
        groups.add('product')
    elif value in ('a2.a marketing communication – b2b', 'a2.b marketing communication – b2c'):
        groups.add('branded')
    return tuple(key for key in LABELS if key in groups) or ('unconfirmed',)


def options(categories):
    present = {key for category in categories for key in group_ids(category)}
    return [{'id': key, 'label': label} for key, label in LABELS.items() if key in present]


def groups_for(category):
    return [{'id': key, 'label': LABELS[key]} for key in group_ids(category)]
