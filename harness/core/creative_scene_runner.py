"""One scene planning attempt; no retries, model swaps or automatic application."""
import asyncio
from harness.studio import store
from harness.agents.creative_scene_director import propose_scene
from harness.evaluators.creative_scene import evaluate_scene_proposal
from harness.tools.creative_scene import scene_hash,validate_scene


async def run_scene_suggestion(pid,uid,job_id,snapshot,intent,selection,observations,slots):
    try:
        async with slots:
            spec=validate_scene(snapshot['scene3d'],snapshot.get('scene_assets',{}))
            raw=await propose_scene(spec,observations,intent,selection)
            result=evaluate_scene_proposal(raw,spec,snapshot.get('scene_assets',{}),observations)
        async with store.lock(pid):
            p=store.load(pid,uid);job=p['scene_suggestions'][job_id]
            if p['revision']!=job['revision'] or scene_hash(validate_scene(p['scene3d'],p.get('scene_assets',{})))!=job['base_digest']:
                raise ValueError('场景已更新')
            job.update(state='completed',result=result);store.save(p,uid)
            store.event(p,'evaluator','scene_suggestion_checked')
    except Exception:
        async with store.lock(pid):
            p=store.load(pid,uid);p['scene_suggestions'][job_id].update(state='failed',error='建议未通过检查或服务暂不可用。原场景保留，没有自动重试；可重新发起一次请求。')
            store.save(p,uid);store.event(p,'agent','scene_suggestion_failed')
    finally:
        store.RUNNING.pop(pid,None)
