#!/usr/bin/env python3
"""Author-stated feature requests paired with existing synthetic capability variants."""
import argparse
from copy import deepcopy
import json
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from harness.research.briefs import digest,validate,visible_input

REQUESTS={
 'carry':'希望主镜头展示通勤途中背包遇到路边短暂飞溅后，里面的电脑仍保持干燥。',
 'drink':'希望主镜头展示杯子装了饮品后被横放进包，包内仍保持干燥。',
 'listen':'希望主镜头展示戴上耳机后周围噪声被减弱，更专注地听内容。',
 'light':'希望主镜头展示人物双手拿着书和包走近书桌时，灯自动亮起迎接。',
 'sling':'希望主镜头展示湿折叠伞放入包内后，其他随身物品仍保持干燥。',
 'duffel':'希望主镜头展示装满的手提包符合目标航司的随身行李尺寸限制。',
 'glass':'希望主镜头展示用杯子盛接热饮，突出日常使用便利。',
 'bottle':'希望主镜头展示运动后把水瓶交给洗碗机清洗，轻松整理。',
 'earbuds':'希望主镜头展示耳塞在电脑与手机之间切换播放来源。',
 'speaker':'希望主镜头展示户外水边活动中有水碰到音箱，音乐仍能继续。',
 'reading':'希望主镜头展示按阅读场景改变灯光亮度，适应个人使用习惯。',
 'lantern':'希望主镜头展示小灯不连电线也能陪伴一段晚间活动。'}


def build(base):
    cards=[]
    for parent in validate(base):
        request=REQUESTS[parent['family_id']]
        card=deepcopy(parent)
        card['brief']=parent['brief']+' 客户创意要求：'+request+' 请核对该动作是否符合实际功能及适用条件；若不成立或资料不足，请明确说明，并给出保留原传播目的的可实现替代。'
        card['id']=digest({'parent':parent['id'],'brief':card['brief'],'version':'goal-dependent-v2'})[:12]
        card['evaluation_only']['parent_card_id']=parent['id']
        cards.append(card)
    result={'schema':'visualagent.synthetic-briefs.v1','status':'authored_development_protocol_probes',
        'synthetic':True,'training_eligible':False,'parent_dataset_sha256':digest(base),
        'scope':'Feature-dependent author requests across 12 existing fictional families. Not independent gold or held-out data. Do not pool with generic briefs.',
        'cards':cards}
    validate(result)
    for family in REQUESTS:
        group=[c for c in cards if c['family_id']==family]
        if len(group)!=3 or len({digest(visible_input(c,'underspecified')) for c in group})!=1:
            raise ValueError('Counterfactual visibility mismatch')
    return result


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--base',type=Path,default=Path('data/research/advertising_briefs_v1.json'))
    p.add_argument('--out',type=Path,required=True);a=p.parse_args()
    result=build(json.loads(a.base.read_text()))
    with a.out.open('x') as f:json.dump(result,f,ensure_ascii=False,indent=2);f.write('\n')
    print(json.dumps({'cards':len(result['cards']),'families':len(REQUESTS),'dataset_sha256':digest(result),'paid_calls':0}))
