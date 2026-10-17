"""Auditable transfer record: structural checks do not certify semantic entailment."""
from harness.tools.research_plan import bounded_text
from harness.research.bridge_assumptions import validate_assumptions

STATUSES = ('supported', 'contradicted', 'unknown')
DECISIONS = ('retain', 'constrain', 'ask', 'replace', 'abstain')


def validate_record(raw, visible, reference, *, absent_reference=False):
    if not isinstance(raw,dict):raise ValueError('invalid_prerequisite_record')
    result={k:bounded_text(raw.get(k),1000,field="record."+k) for k in ('relation','target_action')}
    result['source_status']=raw.get('source_status')
    result['bridge_assumptions']=validate_assumptions(raw.get('bridge_assumptions',[]),visible,field_prefix='record.bridge_assumptions') if raw.get('bridge_assumptions') is not None else []
    allowed_statuses = ('no_source',) if absent_reference else ('observed_relation','interpretation','unverified')
    if result['source_status'] not in allowed_statuses:
        raise ValueError('invalid_source_status')
    event_ids={e['event_id'] for e in reference['evidence']['events']}
    cited=raw.get('source_event_ids')
    if absent_reference:
        if event_ids or reference.get('availability') != 'absent' or cited != []:
            raise ValueError('invalid_absent_reference')
    elif not isinstance(cited,list) or not cited or any(not isinstance(x,str) or x not in event_ids for x in cited):
        raise ValueError('unknown_source_event')
    result['source_event_ids']=list(dict.fromkeys(cited))
    result['requirements']=validate_requirements(raw.get('requirements'),visible,field_prefix='record.requirements')
    decision=raw.get('decision')
    if decision not in DECISIONS:raise ValueError('invalid_transfer_decision')
    if decision in ('retain','constrain') and any(r['status']!='supported' for r in result['requirements']):
        raise ValueError('declared_prerequisite_not_satisfied')
    question=raw.get('question')
    result['question']=None
    if decision=='ask':
        if not isinstance(question,dict):raise ValueError('missing_question')
        slot=bounded_text(question.get('fact_id'),100,field='record.question.fact_id')
        if not any(r['fact_id']==slot and r['status']=='unknown' for r in result['requirements']):
            raise ValueError('question_not_linked_to_unknown_requirement')
        result['question']={'fact_id':slot,'text':bounded_text(question.get('text'),500,field='record.question.text')}
    elif question is not None:raise ValueError('unexpected_question')
    result['replacement']=None
    replacement=raw.get('replacement')
    if decision=='replace':
        if not isinstance(replacement,dict):raise ValueError('missing_replacement_record')
        action=bounded_text(replacement.get('target_action'),1000,field='record.replacement.target_action')
        requirements=validate_requirements(replacement.get('requirements'),visible,field_prefix='record.replacement.requirements')
        if any(r['status']!='supported' for r in requirements):raise ValueError('replacement_prerequisite_not_satisfied')
        result['replacement']={'target_action':action,'requirements':requirements}
    elif replacement is not None:raise ValueError('unexpected_replacement_record')
    result['decision']=decision
    result['semantic_review']='pending'
    result['training_eligible']=False
    return result


def validate_requirements(requirements, visible, *, field_prefix="requirements"):
    if not isinstance(requirements,list) or not 1<=len(requirements)<=8:raise ValueError('invalid_requirements')
    result=[]
    for index,row in enumerate(requirements):
        if not isinstance(row,dict):raise ValueError('invalid_requirement')
        fact_id=bounded_text(row.get('fact_id'),100,field=f'{field_prefix}[{index}].fact_id')
        status=row.get('status')
        if status not in STATUSES:raise ValueError('invalid_requirement')
        # Several distinct conditions may legitimately cite one composite fact field.
        # A model cannot mark an undisclosed slot supported/contradicted. Presence still
        # does not prove that its status or proposed application is semantically correct.
        if status!='unknown' and fact_id not in visible['facts']:raise ValueError('undisclosed_fact_status')
        result.append({'fact_id':fact_id,'status':status,
            'condition':bounded_text(row.get('condition'),600,field=f'{field_prefix}[{index}].condition'),
            'basis':bounded_text(row.get('basis'),600,field=f'{field_prefix}[{index}].basis')})
    return result
