"""Bounded research observations; semantic correctness remains independently unverified."""
from harness.models.research_planner import ResearchPlanner
from harness.tools.research_plan import BoundedTextError
from harness.research.transfer import validate_review, validate_transfer_plan


class TransferValidationError(ValueError):
    def __init__(self, code, raw, usage, validation_error=None):
        super().__init__(code)
        self.usage = usage
        # Structural diagnostics only: no model text or unrestricted provider values.
        self.diagnostics = {'object':isinstance(raw,dict)}
        if isinstance(validation_error,BoundedTextError):
            self.diagnostics['text_failure']=dict(validation_error.text_diagnostic)
        if isinstance(raw,dict):
            for key in ('checks','shots','fact_basis','unresolved'):
                value=raw.get(key)
                self.diagnostics[key+'_count']=len(value) if isinstance(value,list) else None
            for key in ('claim','proposal','recommendation'):
                value=raw.get(key)
                self.diagnostics[key+'_length']=len(value) if isinstance(value,str) else None
            if isinstance(raw.get('shots'),list):
                self.diagnostics['shot_text_lengths']=[
                    {k:len(shot[k]) if isinstance(shot,dict) and isinstance(shot.get(k),str) else None
                     for k in ('visual','audio','caption')} for shot in raw['shots'][:6]]

        record=raw.get('record') if isinstance(raw,dict) else None
        if isinstance(record,dict):
            for name,section in [('original',record),('replacement',record.get('replacement'))]:
                requirements=section.get('requirements') if isinstance(section,dict) else None
                safe={'count':len(requirements) if isinstance(requirements,list) else None}
                if isinstance(requirements,list):
                    safe['non_object_count']=sum(not isinstance(r,dict) for r in requirements)
                    safe['invalid_status_count']=sum(isinstance(r,dict) and r.get('status') not in ('supported','contradicted','unknown') for r in requirements)
                    ids=[r.get('fact_id') for r in requirements if isinstance(r,dict) and isinstance(r.get('fact_id'),str)]
                    safe['repeated_fact_id_count']=len(ids)-len(set(ids))
                self.diagnostics[name+'_requirements']=safe


async def transfer_step(messages, model, stage, fact_ids, max_tokens=2200):
    if stage not in ('review','plan'):raise ValueError('invalid_stage')
    raw, usage = await ResearchPlanner(model, max_tokens=max_tokens).complete(messages)
    try:
        result = validate_review(raw) if stage=='review' else validate_transfer_plan(raw,fact_ids)
    except ValueError as e:
        raise TransferValidationError(str(e),raw,usage,validation_error=e) from None
    return {'result':result,'usage':usage,'semantic_review':'pending','training_eligible':False}
