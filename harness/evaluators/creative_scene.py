"""Validate scene proposals and compute actual changes, without claiming visual QA."""
from harness.tools.creative_scene import validate_scene

LABELS={'title':'场景名称','duration':'总时长','aspect':'画幅','background':'背景',
        'name':'名称','kind':'类型','position':'位置','rotation':'旋转','scale':'缩放','color':'颜色',
        'roughness':'粗糙度','metalness':'金属度','intensity':'光强','asset':'资产','visible':'显示',
        'fov':'视角','target':'注视点','points':'路径点','closed':'闭合路径','easing':'缓动'}


def scene_changes(original, spec):
    changes=[]
    def change(label, before, after):
        if before!=after: changes.append(dict(label=label,before=before,after=after))
    for k in ('title','duration','aspect','background'):
        change(LABELS[k],original[k],spec[k])
    for collection,label in (('objects','对象'),('shots','镜头')):
        old={v['id']:v for v in original[collection]};new={v['id']:v for v in spec[collection]}
        if collection=='shots':change('镜头顺序',[s['id'] for s in original['shots']],[s['id'] for s in spec['shots']])
        for id in dict.fromkeys([*old,*new]):
            a,b=old.get(id),new.get(id);name=(b or a)['name']
            if not a or not b:
                change(('新增' if b else '移除')+label+' · '+name,a,b);continue
            for k in a:
                if k=='camera':
                    for field in a[k]:change(name+' · '+LABELS.get(field,field),a[k][field],b[k][field])
                elif k!='id':change(name+' · '+('镜头时长' if k=='duration' else LABELS.get(k,k)),a[k],b[k])
    return changes


def evaluate_scene_proposal(raw, original, assets, observations):
    if not isinstance(raw,dict) or set(raw)!={'spec','summary','reasons'}:raise ValueError('场景建议格式无效')
    if not isinstance(raw['spec'],dict):raise ValueError('场景建议格式无效')
    spec=validate_scene(raw['spec'],assets)
    old={o['id']:o for o in original['objects']};new={o['id']:o for o in spec['objects']}
    for id in set(old)|set(new):
        a,b=old.get(id),new.get(id)
        if (a and a['kind']=='glb') or (b and b['kind']=='glb'):
            if not a or not b or any(a[k]!=b[k] for k in ('kind','asset','color','roughness','metalness','intensity')):
                raise ValueError('建议改变了受保护的 GLB 资产')
    summary=raw['summary'];reasons=raw['reasons'];known={v['id'] for v in observations}
    if not isinstance(summary,str) or not 1<=len(summary.strip())<=500:raise ValueError('摘要无效')
    if not isinstance(reasons,list) or not 1<=len(reasons)<=8:raise ValueError('说明无效')
    clean=[]
    for reason in reasons:
        if not isinstance(reason,dict) or set(reason)!={'text','views'}:raise ValueError('说明无效')
        text,views=reason['text'],reason['views']
        if not isinstance(text,str) or not 1<=len(text.strip())<=240:raise ValueError('说明无效')
        if not isinstance(views,list) or len(views)>4 or any(not isinstance(v,str) or v not in known for v in views):raise ValueError('未知画面依据')
        clean.append(dict(text=text.strip(),views=views))
    return dict(spec=spec,summary=summary.strip(),reasons=clean,changes=scene_changes(original,spec),
                observations=[{k:v for k,v in item.items() if k!='image'} for item in observations],
                qa=dict(contract='passed',semantic='pending',human='pending',training_eligible=False))
