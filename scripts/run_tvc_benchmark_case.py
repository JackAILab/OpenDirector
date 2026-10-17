#!/usr/bin/env python3
"""Run one portable benchmark case through the existing harness, without retries."""
from __future__ import annotations
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import sys
from datetime import datetime, timezone

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from scripts.run_camera_segment import uuid7
from harness.agents import ScriptedAgent
from harness.core import AgentAction, HarnessRunner
from harness.evaluators import CameraVideoEvaluator
from harness.models import KlingVideoModel
from harness.tasks import Task
from harness.tools import CameraVideoTool, ToolRegistry
from harness.trajectory import TrajectoryRecorder

BUNDLE = ROOT / 'productions/omni_tvc_benchmark_10_v1'

def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('case_id')
    ap.add_argument('--execute', action='store_true', help='Submit this case once within the user-authorized ten-case batch')
    args = ap.parse_args()
    batch = json.loads((BUNDLE / 'benchmark.json').read_text())
    declared = {c['case_id']: c for c in batch['cases']}
    if args.case_id not in declared:
        raise ValueError('case_id must belong to the ten declared cases')
    path = BUNDLE / declared[args.case_id]['input']
    spec = json.loads(path.read_text())
    refs = []
    problems = []
    for ref in spec['references']:
        p = (path.parent / ref['path']).resolve()
        if path.parent.resolve() not in p.parents or not p.is_file():
            problems.append('missing or out-of-bundle reference')
            continue
        if hashlib.sha256(p.read_bytes()).hexdigest() != ref['sha256']:
            problems.append('reference hash mismatch')
        refs.append(p)
    if not refs:
        problems.append('no generated reference image available')
    g = spec['generation']
    if g['model'] != 'kling-video-v3_0_omni':
        problems.append('benchmark requires Kling Omni')
    output_root = ROOT / 'outputs/artifacts/omni_tvc_benchmark_10_v1'
    case_output = output_root / args.case_id
    video = case_output / 'omni-attempt-01.mp4'
    reservation = case_output / 'attempt-01.reservation.json'
    if reservation.exists() or video.exists():
        problems.append('attempt already reserved; inspect existing task, never resubmit automatically')
    print(json.dumps({'case_id':args.case_id,'ready':not problems,'problems':problems,'execute_requested':args.execute},ensure_ascii=False), flush=True)
    if not args.execute:
        return 0
    if problems:
        return 2
    executable = shutil.which('kling')
    if not executable:
        raise RuntimeError('Kling CLI unavailable')
    model = KlingVideoModel(executable=executable)
    # A reservation survives process death; it is never cleared automatically.
    # The shared batch lock also serializes CLI OAuth refresh and paid submissions.
    import fcntl
    output_root.mkdir(parents=True,exist_ok=True)
    with (output_root / '.batch.lock').open('a') as lock:
        try:
            fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        except BlockingIOError:
            print('Another benchmark case is active; wait for that case.',flush=True)
            return 2
        # Read-only identity check; do not print account details or provider payload.
        try:
            model._run(['who_am_i','--quiet'])
        except Exception:
            print('Kling preflight failed; no generation submitted. Renew CLI login and re-run preflight.',flush=True)
            return 2
        case_output.mkdir(parents=True,exist_ok=True)
        with reservation.open('x') as out:
            json.dump({'case_id':args.case_id,'attempt':1,'created_at':datetime.now(timezone.utc).isoformat(),'automatic_retry':False,'model_substitution':False,'training_eligible':False},out,indent=2)
        registry=ToolRegistry()
        registry.register(CameraVideoTool(model,output_root=output_root))
        arguments={**g,'prompt':spec['brief'],'reference_images':[str(p) for p in refs],'output':f'{args.case_id}/{video.name}','task_trace_id':uuid7(),'metadata':{'case_id':args.case_id,'attempt':1,'input_mode':g['input_mode'],'training_eligible':False}}
        arguments.pop('input_mode')
        task=Task(args.case_id,spec['title'],inputs={'portable_input':str(path.relative_to(ROOT))},constraints={'paid_generation_budget':{'scope':'one_of_ten_cases','max_calls_without_confirmation':1,'used':0},'automatic_retry':False,'model_substitution':False},metadata={'training_eligible':False})
        result=HarnessRunner(registry,recorder=TrajectoryRecorder(ROOT/'outputs/trajectories')).run(task=task,agent=ScriptedAgent([AgentAction.tool('generate_camera_video',arguments,rationale='Produce the requested original multi-shot TVC directly through Omni.'),AgentAction.finish({'artifact':str(video),'training_eligible':False})]),evaluator=CameraVideoEvaluator(video,expected_duration=g['duration_seconds'],expected_resolution=(1920,1080),expected_audio=True),max_steps=2)
        with (case_output/'technical-result.json').open('x') as out:
            json.dump(result.__dict__,out,ensure_ascii=False,indent=2)
        print(json.dumps(result.__dict__,ensure_ascii=False),flush=True)
        return 0 if result.status=='completed' and result.evaluation and result.evaluation.get('passed') else 3

if __name__=='__main__':
    raise SystemExit(main())
