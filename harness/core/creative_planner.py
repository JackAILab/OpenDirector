"""Bounded planning queue; one request survives browser disconnects."""
import asyncio
import inspect
import time
import httpx
from harness.models.creative_director import PlanningServiceError, PlanningResponseError
from harness.studio.store import RUNNING, save, event, load

def failure_code(exc):
    if isinstance(exc, (TimeoutError, httpx.TimeoutException)): return 'timeout'
    if isinstance(exc, (PlanningServiceError, httpx.TransportError)): return 'service_unavailable'
    if isinstance(exc, PlanningResponseError): return exc.code
    # Match known validator constants; never serialize arbitrary exception text.
    known = {'invalid director response': 'invalid_plan', 'invalid summary': 'invalid_summary',
             'invalid brief': 'invalid_brief', 'invalid shot count': 'shot_count', 'empty prompt': 'empty_prompt'}
    if isinstance(exc, ValueError): return known.get(str(exc), 'plan_validation')
    if isinstance(exc, KeyError): return 'missing_plan_field'
    return 'planning_internal'


SLOTS = asyncio.Semaphore(3)

async def plan(p, owner, mode, director):
    activity = {'revision': p['revision'], 'state': 'running', 'steps': [], 'decisions': []}
    p['planning_activity'] = activity
    def observe(stage, decision=None):
        if stage not in ('queued', 'references', 'composing', 'validating', 'decision'): return
        if stage == 'decision':
            if not isinstance(decision, dict) or len(activity['decisions']) >= 8: return
            activity['decisions'].append({'title': str(decision.get('title',''))[:100],
                                          'reason': str(decision.get('reason',''))[:800]})
        elif not any(s['stage'] == stage for s in activity['steps']):
            activity['steps'].append({'stage': stage, 'time': time.time()})
        # Preserve cancellation and canvas edits arriving during incremental output.
        latest = load(p['id'], owner)
        if latest.get('revision') != p['revision']: return
        if latest.get('stop_requested'): p['stop_requested'] = True
        for key in ('manual_nodes', 'director_project'):
            if key in latest: p[key] = latest[key]
        save(p, owner)
    observe('queued')
    try:
        original_product=p.get('brief',{}).get('product','')
        if p.get('generation_mode')=='chaptered_native':
            from harness.tools.creative_campaign import bind_plan_inputs
            await asyncio.to_thread(bind_plan_inputs,p)
        async with asyncio.timeout(900):
            async with SLOTS:
                p['planning_phase']='working';save(p,owner)
                result=await director(p,mode,**({'on_activity':observe} if 'on_activity' in inspect.signature(director).parameters else {}))
        if p.get('reference') and p.get('reference_product')!=result['brief'].get('product'):
            p['reference_needs_review']=True
        observe('validating')
        activity['state']='completed'
        activity['decisions']=result.get('decisions',[])
        p.update({k:result[k] for k in ('brief','assumptions','decisions','questions','shots')})
        if not original_product and p.get('video_inputs') and not p.get('video_inputs_product'):
            p['video_inputs_product']=p['brief'].get('product','')
        p['strategy_candidates']=result.get('strategy_candidates',[])
        p['strategy_selection']=result.get('strategy_selection',[])
        from harness.learning.evaluation import evaluate_plan
        p['plan_evaluation']=evaluate_plan(p)
        event(p,'evaluator','plan_contract_passed' if p['plan_evaluation']['passed'] else 'plan_contract_warnings')
        questions=''.join('\n\n'+q['question']+'\n追问依据：'+q['why'] for q in result['questions'])
        p['messages'].append({'role':'assistant','content':result['reply']+questions})
        p['state']='ready' if p['shots'] else 'intake';p['error']='';p.pop('planning_failure_code',None)
        if p.get('campaign'):
            from copy import deepcopy
            p.setdefault('campaign_attempts',[]).append(dict(run_id=p.get('run_id'), campaign=deepcopy(p['campaign'])))
        for k in ('run_id','artifact','qa','stop_requested','film','campaign'):p.pop(k,None)
        event(p,'agent','plan_ready' if p['shots'] else 'questions_ready')
        from harness.learning.episodes import record_plan
        try:record_plan(p,owner)
        except Exception:event(p,'learning','plan_capture_failed')
    except Exception as exc:
        activity['state']='failed'
        p['state']='planning_failed'
        p['planning_failure_code']=failure_code(exc)
        reason=('输出长度超过上限' if isinstance(exc,PlanningResponseError) and exc.code=='output_truncated' else '等待超时' if isinstance(exc,(TimeoutError,httpx.TimeoutException)) else
                '服务暂时不可用' if isinstance(exc,(PlanningServiceError,httpx.TransportError)) else '方案格式未通过检查')
        p['error']='导演'+reason+'。上下文已保存；可按现有信息重新规划，无需重复发送，尚未生成视频。'
        event(p,'agent','planning_failed')
    finally:
        # Stop may be requested while the director is working on this snapshot.
        latest=load(p['id'],owner)
        if latest.get('stop_requested') and latest['revision']==p['revision']:
            p['stop_requested']=True
        for key in ('manual_nodes','director_project'):
            if key in latest:p[key]=latest[key]
        p.pop('planning_phase',None)
        save(p,owner)
        if RUNNING.get(p['id']) is asyncio.current_task():RUNNING.pop(p['id'],None)
