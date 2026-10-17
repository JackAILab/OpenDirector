"""One observation/Agent/Evaluator attempt. Runner never retries or applies a draft."""
import asyncio
from harness.studio import store
from harness.tools.creative_edit import validate_edit
from harness.tools.creative_edit_media import source_catalog
from harness.tools.creative_edit_observe import observe_edit
from harness.agents.creative_editor import propose_edit
from harness.evaluators.creative_edit import evaluate_edit_proposal
from harness.tools.creative_transcript import evidence_for, speech_findings


async def run_suggestion(pid, uid, job_id, snapshot, intent, slots):
    try:
        async with slots:
            catalog = await asyncio.to_thread(source_catalog, snapshot)
            original = validate_edit(snapshot['edit'], catalog=catalog)
            observations = await asyncio.to_thread(observe_edit, snapshot, original)
            store.event(snapshot, 'tool', 'edit_observation_completed')
            speech = evidence_for(snapshot, original)
            raw = await propose_edit(original, observations, intent, catalog, speech)
            result = evaluate_edit_proposal(raw, original, catalog, observations)
            result['speech_findings'] = speech_findings(result['spec'], speech)
            result['speech_sources'] = list(speech)
            # Check media bindings again after model latency, before releasing a proposal.
            latest_catalog = await asyncio.to_thread(source_catalog, snapshot)
            validate_edit(original, catalog=latest_catalog)
        async with store.lock(pid):
            p = store.load(pid, uid);job=p['edit_suggestions'][job_id]
            if p['revision']!=job['revision']: raise ValueError('Stale project')
            job.update(state='completed',result=result);store.save(p,uid)
            store.event(p,'evaluator','edit_suggestion_checked')
    except Exception:
        async with store.lock(pid):
            p=store.load(pid,uid);p['edit_suggestions'][job_id].update(state='failed',error='建议未通过检查或服务暂不可用。原草稿保留，没有自动重试；可明确重新请求。')
            store.save(p,uid);store.event(p,'agent','edit_suggestion_failed')
    finally:
        store.RUNNING.pop(pid,None)
