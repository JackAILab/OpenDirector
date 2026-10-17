"""Bounded creative-method editing. Recipes are data, never model/fee permissions."""
from copy import deepcopy
import hashlib
import json

TEXT_FIELDS = {'title':80, 'category':40, 'description':1000, 'applies_to':300}
LIST_FIELDS = {'inputs':(1,12), 'steps':(1,12), 'checks':(1,12), 'references':(0,8), 'adaptations':(0,8)}


def validate_content(content):
    if not isinstance(content,dict): raise ValueError('Skill 内容无效')
    clean={}
    for key,limit in TEXT_FIELDS.items():
        value=content.get(key,'')
        if not isinstance(value,str) or len(value.strip())>limit: raise ValueError('名称或说明长度超过限制')
        if key in ('title','description') and not value.strip(): raise ValueError('请填写 Skill 名称和简介')
        clean[key]=value.strip()
    for key,(minimum,maximum) in LIST_FIELDS.items():
        values=content.get(key,[])
        if not isinstance(values,list) or not minimum<=len(values)<=maximum: raise ValueError('输入、步骤和验收各需 1–12 项；参考和改编各最多 8 项')
        if any(not isinstance(v,str) or not 1<=len(v.strip())<=700 for v in values): raise ValueError('每项内容需为 1–700 字')
        clean[key]=[v.strip() for v in values]
    return clean


def build_revision(content, previous=None, *, sid, version):
    clean=validate_content(content);recipe={}
    if previous:
        for field in ('template_id','examples','example_media','derivation','parent','reference_case',
                      'grill_questions','transfer_rules','avoid','mechanism','timeline_recipe','source_evidence','mechanism_tags'):
            if field in previous: recipe[field]=deepcopy(previous[field])
    recipe.update(clean,id=sid,version=version,source='custom',kind='video',duration=15,
                  method_status='我的制作方法',output='15 秒有声广告、分镜与后期字幕',training_eligible=False)
    recipe['content_hash']=hashlib.sha256(json.dumps(recipe,sort_keys=True,ensure_ascii=False).encode()).hexdigest()
    return recipe
