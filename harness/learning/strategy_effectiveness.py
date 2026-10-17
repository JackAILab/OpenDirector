"""Private aggregate metrics for strategy retrieval and adoption."""
import hashlib
import math


def summarize(records):
    if not isinstance(records, list):
        raise ValueError('Candidate records must be a list')
    stats={}
    mechanism_stats={}
    feedback_stats={'count':0,'ratings':[],'decisions':{}}
    observed=0
    missing_quality=0
    for record in records:
        if not isinstance(record, dict):continue
        plan=record.get('plan') or {}; candidates=plan.get('strategy_candidates') or []
        trajectory=record.get('trajectory') or {}
        for feedback in trajectory.get('owner_feedback') or []:
            if not isinstance(feedback,dict):continue
            rating=feedback.get('rating')
            if type(rating) is int and 1<=rating<=5:
                feedback_stats['count']+=1;feedback_stats['ratings'].append(rating)
                decision=str(feedback.get('decision','unknown'))
                feedback_stats['decisions'][decision]=feedback_stats['decisions'].get(decision,0)+1
        score=record.get('quality_mean_score')
        if not isinstance(score,(int,float)) or isinstance(score,bool) or not math.isfinite(score) or not 1<=score<=5:
            missing_quality+=1
            continue
        observed+=1
        selected={choice.get('candidate_index') for choice in (plan.get('strategy_selection') or [])
                  if isinstance(choice,dict) and type(choice.get('candidate_index')) is int}
        for index,candidate in enumerate(candidates):
            if not isinstance(candidate,dict):continue
            principle=str(candidate.get('principle','')).strip()
            if not principle:continue
            key=hashlib.sha256(principle.encode()).hexdigest()
            item=stats.setdefault(key,{'strategy_key':key,'recommendations':0,'adoptions':0,'quality_scores':[],
                                       'selection_reasons':[]})
            item['recommendations']+=1
            for tag in dict.fromkeys(tag for tag in candidate.get('mechanism_tags') or [] if isinstance(tag,str)):
                if not isinstance(tag,str) or not tag.strip():continue
                tag_key=hashlib.sha256(tag.encode()).hexdigest()
                tag_item=mechanism_stats.setdefault(tag_key,{'mechanism_key':tag_key,'recommendations':0,'adoptions':0,'quality_scores':[]})
                tag_item['recommendations']+=1
                if index in selected:
                    tag_item['adoptions']+=1;tag_item['quality_scores'].append(float(score))
            if index in selected:
                item['adoptions']+=1;item['quality_scores'].append(float(score))
                for choice in plan.get('strategy_selection') or []:
                    if isinstance(choice,dict) and choice.get('candidate_index')==index and choice.get('reason'):
                        item['selection_reasons'].append(str(choice['reason'])[:200])
    output=[]
    for item in stats.values():
        scores=item.pop('quality_scores')
        item['adoption_rate']=round(item['adoptions']/item['recommendations'],3) if item['recommendations'] else 0
        item['adopted_quality_mean']=round(sum(scores)/len(scores),2) if scores else None
        item['adopted_quality_min']=round(min(scores),2) if scores else None
        item['selection_reason_count']=len(item.pop('selection_reasons'))
        output.append(item)
    mechanism_output=[]
    for item in mechanism_stats.values():
        scores=item.pop('quality_scores')
        item['adoption_rate']=round(item['adoptions']/item['recommendations'],3) if item['recommendations'] else 0
        item['adopted_quality_mean']=round(sum(scores)/len(scores),2) if scores else None
        item['adopted_quality_min']=round(min(scores),2) if scores else None
        mechanism_output.append(item)
    ratings=feedback_stats.pop('ratings')
    feedback_stats['rating_mean']=round(sum(ratings)/len(ratings),2) if ratings else None
    return {'schema':'visualagent.strategy-effectiveness.v1','observed_records':observed,
            'records_missing_valid_quality':missing_quality,
            'comparison_ready':False,
            'strategies':sorted(output,key=lambda x:(-x['adoptions'],-x['recommendations'],x['strategy_key'])),
            'mechanisms':sorted(mechanism_output,key=lambda x:(-x['adoptions'],-x['recommendations'],x['mechanism_key'])),
            'owner_feedback':feedback_stats,
            'training_eligible':False,'content_exported':False,
            'limitations':['相关性不等于因果效果','样本量不足时不要比较策略优劣','独立评分不是投放转化数据']}
