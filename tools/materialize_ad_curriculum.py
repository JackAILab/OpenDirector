#!/usr/bin/env python3
"""Materialize a privacy-safe director curriculum from the current strategy snapshot."""
import argparse, json, os
from pathlib import Path

def build(index):
    summary=index.get('analysis_summary') or {};coverage=summary.get('mechanism_coverage') or {}
    total=int(summary.get('analysis_count',0) or 0)
    stages=[
      ('fact_boundary','确认商品事实、限制和可证明的单一主张','先追问事实与限制，再允许写分镜',coverage.get('product_as_action',0),['claim_is_single','facts_are_source_bound','unsupported_benefit_is_flagged']),
      ('observable_proof','把主张转成观众能看见的任务和结果变化','每个节拍写动作、结果和因果，不只写氛围',coverage.get('observable_task',0),['task_is_visible','result_has_before_after','product_causes_action']),
      ('controlled_conflict','只保留一条压力、对照或反转','删掉第二卖点和无关支线',max(coverage.get('pressure_test',0),coverage.get('contrast_reversal',0),coverage.get('misdirection_reveal',0)),['one_conflict','reversal_is_explainable','no_reference_copying']),
      ('reaction_attribution','用人物或环境反应收束，再完成品牌归因','结果之后安排反应、商品识别和可证实行动',max(coverage.get('human_reaction',0),coverage.get('brand_reveal',0)),['reaction_follows_result','product_is_identified','cta_is_fact_safe']),
      ('native_sound','让声音承担节奏、因果或记忆点','为每段分别写旁白、音乐、环境声和动作音，并标注审阅状态',summary.get('audio_semantics_reviewed',0),['audio_prompt_exists','audio_is_not_inferred_from_stills','semantic_audio_review_pending_until_heard']),
      ('release_gates','把技术、语义、人工和授权门禁分开','所有证据齐备前保持不可训练',0,['technical_qa','independent_review','privacy_rights_sanitization','human_approval','explicit_consent'])]
    return {'schema':'visualagent.ad-agent-curriculum.v2','source_scope':'bounded mechanism coverage from current validated sampled-frame analyses','analysis_count':total,'review_state':{'audio_semantics_reviewed':int(summary.get('audio_semantics_reviewed',0) or 0),'full_motion_reviewed':int(summary.get('full_motion_reviewed',0) or 0),'sound_review_pending':total-int(summary.get('audio_semantics_reviewed',0) or 0)},'stages':[{'id':a,'order':i+1,'goal':b,'agent_action':c,'evidence':int(d),'pass':e} for i,(a,b,c,d,e) in enumerate(stages)],'training_policy':{'training_eligible':False,'requires_all_release_gates':True},'prohibitions':['copy reference brand, person, wording, shot sequence, product or audio','treat heuristic coverage as a quality score','infer sound meaning or full motion from sampled frames']}

def main():
    ap=argparse.ArgumentParser();ap.add_argument('--index',type=Path,required=True);ap.add_argument('--output',type=Path,required=True);a=ap.parse_args()
    if a.output.exists() or a.output.is_symlink():raise FileExistsError('Refusing to overwrite curriculum')
    data=json.loads(a.index.read_text());payload=build(data);a.output.parent.mkdir(parents=True,exist_ok=True,mode=0o700);fd=os.open(a.output,os.O_CREAT|os.O_EXCL|os.O_WRONLY,0o600)
    with os.fdopen(fd,'w',encoding='utf-8') as f:json.dump(payload,f,ensure_ascii=False,indent=2);f.write('\n')
    print(json.dumps({'analysis_count':payload['analysis_count'],'training_eligible':False},ensure_ascii=False))
if __name__=='__main__':main()
