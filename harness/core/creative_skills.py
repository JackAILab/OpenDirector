"""Versioned creative recipes: inputs, bounded steps and acceptance criteria."""
from copy import deepcopy


RECIPES = {
    'story-short': {
        'id': 'story-short', 'title': '短故事创作', 'category': '叙事短片',
        'description': '以主体行动、转折和收束构成一支 15 秒有声短片，不强加广告结构。',
        'inputs': ['主体与主要动作', '故事场景或参考图', '视觉风格与声音偏好'],
        'steps': ['明确主体目标与场景关系', '安排开场、变化、收束三个连续节拍', '保持主体外观、空间和动作衔接', '按所选模型一次生成整片', '检查动作因果、连续性和声音'],
        'checks': ['主体与要求一致', '动作与转折可理解', '没有无关商品或广告文案', '声音与画面相符'],
        'output': '15 秒有声故事短片、分镜与可选后期字幕',
    },
    'scene-mood': {
        'id': 'scene-mood', 'title': '场景氛围短片', 'category': '场景创作',
        'description': '通过环境、光线、运镜与声音呈现场景氛围，适合自然风景与空间展示。',
        'inputs': ['场景或参考图', '时间、天气或光照', '希望传达的情绪'],
        'steps': ['明确场景空间与光照条件', '规划建立空间、发现细节、情绪收束', '限制运镜以保持空间可读性', '设计环境音与可选原创音乐', '一次生成并检查空间和声音连续性'],
        'checks': ['场景符合描述', '光照和天气连贯', '运镜可读', '无强加旁白、商品或行动号召'],
        'output': '15 秒场景氛围短片与声音设计',
    },
    'character-moment': {
        'id': 'character-moment', 'title': '角色动作短片', 'category': '角色创作',
        'description': '围绕人物或动物的一次行动设计短片，关注主体特征、动作关系和反应。',
        'inputs': ['角色外观或参考图', '主要动作和互动对象', '场景与表现风格'],
        'steps': ['区分角色身份与参考职责', '拆解动作准备、发生、反应三个节拍', '保持朝向、比例与空间关系', '安排动作音效与克制音乐', '一次生成并审阅角色和动作'],
        'checks': ['角色特征稳定', '互动关系明确', '动作可理解', '没有擅加品牌、商品或口播'],
        'output': '15 秒角色动作短片与分镜',
    },
    'ad-video': {
        'id': 'ad-video', 'title': '商品广告导演', 'category': '商品展示',
        'description': '用可见细节与使用动作证明一个卖点，完成 15 秒有声广告。',
        'inputs': ['商品参考图或已确认的外观', '唯一卖点', '受众与投放目的'],
        'steps': ['核实商品事实，标记未知信息', '设计吸引注意、可见证明、行动收束三个节拍',
                  '确定商品、场景与人物参考职责', '按所选模型生成一次有声整片', '叠加字幕并检查商品、声音与叙事'],
        'checks': ['商品外观一致', '卖点有画面证据', '旁白可听且不过密', '字幕来自后期', '行动号召真实'],
    },
    'brand-story': {
        'id': 'brand-story', 'title': '品牌情绪短片', 'category': '品牌故事',
        'description': '从一个生活瞬间出发，用人物的变化传递品牌主张。',
        'inputs': ['品牌主张', '目标人群', '真实产品资料', '情绪与场景'],
        'steps': ['找到观众能认出的生活矛盾', '用产品介入引起可见变化', '以人物反应完成情绪收束',
                  '设计贯穿音乐和克制旁白', '生成整片，后期字幕与审阅'],
        'checks': ['人物行动有因果', '产品融入情节', '情绪递进', '不编造功效'],
    },
    'ugc-product': {
        'id': 'ugc-product', 'title': '真人感商品演示', 'category': '转化广告',
        'description': '痛点开场、一次清晰演示、直接行动号召，适合服饰与日常用品。',
        'inputs': ['商品正面图', '已确认的结构细节', '口播语言与市场', '人物呈现方式'],
        'steps': ['核对可见商品特征和允许的主张', '设计一个具体痛点和演示动作',
                  '固定人物、空间、光线及商品约束', '编写自然短句口播与镜头时码', '生成、加字幕、检查口播和细节'],
        'checks': ['演示与商品一致', '无虚构体验或价格', '口播短且自然', '行动号召清楚'],
    },
}


def builtin_skills():
    return [dict(deepcopy(r), version=1, kind='video', duration=15,
                 source='recipe', **({'output':'15 秒有声广告、分镜与后期字幕'} if 'output' not in r else {})) for r in RECIPES.values()]


def from_template(template):
    recipe=deepcopy(RECIPES['ad-video'])
    recipe.update(id='template-'+template['id'], title=template['title'],
                  category=template.get('category','商品展示'), description='基于样片拆解的叙事 Skill；替换为你的商品事实与原创镜头。',
                  version=1, kind='video', duration=15, source='template', template_id=template['id'],
                  output='15 秒有声广告、分镜与后期字幕',
                  example_media={k:template.get(k) for k in ('duration','audio','aspect','model_label')},
                  examples=[{'title':s.get('title',''), 'purpose':s.get('rationale','')}
                            for s in template.get('storyboard',[])[:6]])
    mechanisms=[s.get('rationale','').strip() for s in template.get('storyboard',[]) if s.get('rationale','').strip()]
    if mechanisms:
        recipe['steps']=[recipe['steps'][0],
                         *['评估并改写叙事任务：'+purpose[:400] for purpose in mechanisms[:4]],
                         '把可迁移的任务改写为新商品的原创动作与镜头，按所选模型生成并审阅']
    from harness.core.template_recipes import specialize
    return specialize(template,recipe)
