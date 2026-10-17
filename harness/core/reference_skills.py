"""Compile observed advertising mechanisms into reusable, evidence-bound skills."""
import hashlib
import json
import math
import re

from harness.library.mechanisms import annotate

SCHEMA = 'visualagent.reference-skill.v1'
CATEGORIES = {
    '反转与揭示': ('反转', '误会', '误判', '悬念', '揭示', '重新解释'),
    '商品动作证明': ('功能', '任务', '操作', '解决', '使用动作', '能力'),
    '情绪与关系': ('情感', '亲密', '关系', '陪伴', '人物反应', '归属'),
    '感官与材质': ('感官', '触感', '味觉', '气味', '材质', '质感', '香气'),
    '挑战与对照': ('压力', '极端', '障碍', '挑战', '对照', '反差'),
    '累积与升级': ('累积', '越来越', '逐渐', '递进', '重复', '升级'),
    '工艺与过程': ('工艺', '制作过程', '制造', '手工', '加工', '生产'),
}


def checksum(value):
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True,
                                     separators=(',', ':')).encode()).hexdigest()


def category_for(analysis):
    text = str(analysis['principle']) * 3 + str(analysis['mechanism'])
    scores = {name: sum(text.count(term) for term in terms) for name, terms in CATEGORIES.items()}
    best = max(scores, key=scores.get)
    return best if scores[best] else '品牌世界与主张'


def _text(value, limit):
    if not isinstance(value, str) or not value.strip() or len(value) > limit:
        raise ValueError('invalid_skill_evidence')
    return value.strip()


def _strings(value, minimum=1, maximum=12, limit=700):
    if not isinstance(value, list) or not minimum <= len(value) <= maximum:
        raise ValueError('invalid_skill_evidence')
    return [_text(v, limit) for v in value]


def compile_skill(record, analysis):
    """Preserve case-specific questions and transfer rules; invent no source audio."""
    identity, sha = record['id'], record['sha256']
    if not re.fullmatch(r'[a-f0-9]{24}', identity) or not re.fullmatch(r'[a-f0-9]{64}', sha):
        raise ValueError('invalid_skill_identity')
    if (analysis.get('media_role') != 'original_ad'
            or analysis.get('confidence') not in ('high', 'medium')
            or analysis.get('media_sha256') != sha
            or analysis.get('source_item') != identity):
        raise ValueError('ineligible_skill_evidence')
    source_section = str(record.get('source_section') or '').strip()
    # A sampled-frame guess cannot override an explicit source classification.
    if source_section.casefold() in ('music video', 'music videos', 'personal work'):
        raise ValueError('ineligible_skill_source_section')
    principle = _text(analysis.get('principle'), 160)
    mechanism = _text(analysis.get('mechanism'), 1800)
    questions = _strings(analysis.get('grill_questions'))
    transfer = _strings(analysis.get('transfer_rules'))
    avoid = _strings(analysis.get('avoid'))
    beats = analysis.get('beats')
    if not isinstance(beats, list) or not 2 <= len(beats) <= 12:
        raise ValueError('insufficient_skill_evidence')
    duration = record['duration']
    if type(duration) not in (int, float) or not math.isfinite(duration) or duration < 15:
        raise ValueError('invalid_skill_duration')
    windows = []
    for beat in beats:
        start, end = beat.get('start'), beat.get('end')
        if (type(start) not in (int, float) or type(end) not in (int, float)
                or not math.isfinite(start) or not math.isfinite(end)
                or not 0 <= start < end <= duration + .1):
            raise ValueError('invalid_skill_evidence')
        windows.append({'start': start, 'end': end,
                        'observation': _text(beat.get('observation'), 800),
                        'purpose': _text(beat.get('purpose'), 600)})
    windows.sort(key=lambda b: (b['start'], b['end']))
    chosen = [windows[0], windows[len(windows)//2], windows[-1]]
    roles = ['提出任务或感受', '用新商品的动作推进', '结果与品牌归因']
    timeline = []
    for i, (window, role) in enumerate(zip(chosen, roles)):
        timeline.append({
            'start': i*5, 'end': (i+1)*5, 'role': role,
            'planning_instruction': '借鉴此叙事用途，按新商品事实另写原创动作：' + window['purpose'],
            'visual_prompt_requirements': ['新商品外观与位置', '主体动作及可见结果', '场景与构图',
                                          '机位运镜、灯光材质', '与前后节拍的连续关系'],
            'audio_prompt_requirements': ['原创音乐在此时段的变化', '同步环境声或动作音',
                                         '如需旁白：说话人、准确短句、语气与结束时间'],
            'source_window': {'start': window['start'], 'end': window['end']},
            'basis': 'adaptation_guidance_not_source_edit_points',
        })
    category = category_for(analysis)
    title = principle.rstrip('。')
    if len(title) > 60:
        title = title[:57] + '…'
    recipe = {
        'schema': SCHEMA, 'id': 'reference-' + identity, 'version': 1,
        'title': title, 'category': category, 'description': principle,
        'applies_to': '适合希望采用“' + category + '”表达方式的商品；先用下方追问判断与新商品事实是否匹配。',
        'source': 'reference', 'kind': 'video', 'duration': 15,
        'method_status': '真实案例提炼 · 可试用',
        'output': '15秒原生有声整片方案、三个时间段的画面及声音提示词、后期字幕',
        'inputs': ['新商品的真实资料、外观参考与可证实卖点', '目标人群、投放场景和单一创作目标',
                   *questions[:8]],
        'steps': ['先判断这条机制是否适合新商品：' + principle,
                  *transfer[:9],
                  '编写0–5、5–10、10–15秒的画面与声音提示，统一商品、人物和环境连续性，按所选模型一次生成整片。'],
        'checks': ['新商品主张有已确认事实或画面证据', '每个时间段有具体动作、构图和声音安排',
                   '原生音频可听，旁白在结束前说完，时长至少15秒', '商品外观与用户参考一致',
                   '文字由后期准确渲染', '没有移植原品牌、人物、文案、音轨或逐镜头顺序'],
        'references': ['商品参考约束新商品几何、颜色和材质；需要人物参考时单独确认其职责',
                       '案例原片用于理解创意机制，不自动作为生成模型的参考输入'],
        'adaptations': avoid[:8], 'grill_questions': questions,
        'transfer_rules': transfer, 'avoid': avoid, 'mechanism': mechanism,
        'timeline_recipe': timeline, 'source_evidence': windows,
        'mechanism_tags': annotate(analysis)['mechanism_tags'],
        'reference_case': {
            'id': identity, 'title': record['title'], 'brand': record.get('brand', ''),
            'source_name': record['source_name'], 'source_url': record['source_url'],
            'source_section': source_section,
            'duration': duration, 'audio': bool(record['audio']),
            'media_sha256': sha, 'source_revision': record['revision'],
            'analysis_source_revision': record['analysis_source_revision'],
            'analysis_version': record['analysis_version'], 'confidence': analysis['confidence'],
        },
        'derivation': {'basis': 'timecoded_sampled_frames_and_source_metadata',
                       'note': '由真实参考片的时码采样分析提炼。声音和完整运动尚待人工审阅；新片声音需重新设计。'},
        'example_media': {'duration': duration, 'audio': bool(record['audio'])},
        'audio_semantics_reviewed': False, 'full_motion_reviewed': False,
        'human_review': 'pending', 'training_eligible': False,
    }
    recipe['content_hash'] = checksum(recipe)
    return recipe


def skill_markdown(recipe):
    """Portable entrypoint, also useful outside this application's recipe UI."""
    case = recipe['reference_case']
    parts = ['---', 'name: ' + recipe['id'],
             'description: ' + json.dumps(recipe['description'] + ' ' + recipe['applies_to'], ensure_ascii=False),
             '---', '', '# ' + recipe['title'], '', recipe['mechanism'], '',
             '参考案例：' + case['title'] + '；来源：' + case['source_name'],
             '来源链接：' + case['source_url'],
             f"证据版本：分析v{case['analysis_version']}；视频SHA-256 {case['media_sha256']}", '',
             recipe['derivation']['note'], '训练资格：false。Skill不授权模型切换、费用或自动重试。']
    for label, key in [('适用前先确认', 'inputs'), ('关键追问', 'grill_questions'),
                       ('创作方法', 'steps'), ('参考输入职责', 'references'),
                       ('不适用情境', 'avoid'), ('验收', 'checks')]:
        parts += ['', '## ' + label, '', *['- ' + value for value in recipe[key]]]
    parts += ['', '## 15秒有声整片规划', '']
    for beat in recipe['timeline_recipe']:
        parts += [f"### {beat['start']}–{beat['end']}秒：{beat['role']}", '',
                  beat['planning_instruction'],
                  '画面提示需要：' + '；'.join(beat['visual_prompt_requirements']),
                  '声音提示需要：' + '；'.join(beat['audio_prompt_requirements']), '']
    parts += ['## 原片时间证据（采样窗口，不是精确镜头切点）', '']
    for beat in recipe['source_evidence']:
        parts.append(f"- {beat['start']}–{beat['end']}秒：{beat['observation']}；可能用途：{beat['purpose']}")
    return '\n'.join(parts) + '\n'
