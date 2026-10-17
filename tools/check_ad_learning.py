#!/usr/bin/env python3
"""Read-only health report for the advertising-agent learning pipeline."""
import argparse,json,time,sys,multiprocessing
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))

def load(path):
    path=Path(path)
    if not path.is_file() or path.is_symlink():return None
    try:return json.loads(path.read_text(encoding='utf-8'))
    except (OSError,ValueError):return None


class FingerprintTimeout(Exception):
    pass


def _fingerprint_worker(reader, output):
    try:
        output.put(('ok', reader()))
    except BaseException as exc:
        output.put(('error', type(exc).__name__))


def bounded_input_fingerprints(reader, seconds=15):
    """Prevent a slow shared filesystem from wedging the health endpoint."""
    output = multiprocessing.Queue(maxsize=1)
    process = multiprocessing.Process(target=_fingerprint_worker, args=(reader, output))
    process.start()
    process.join(max(1, int(seconds)))
    if process.is_alive():
        process.terminate()
        process.join(2)
        raise FingerprintTimeout()
    if output.empty():
        raise RuntimeError('fingerprint_worker_no_result')
    state, value = output.get()
    if state == 'error':
        raise RuntimeError(value)
    return value


def read_current_fingerprints():
    """Import and read inventory only inside the bounded health-check window."""
    from harness.learning.inventory import input_fingerprints
    return input_fingerprints()


def read_current_markers():
    from harness.learning.inventory import input_markers
    return input_markers()

def main():
    p=argparse.ArgumentParser();p.add_argument('--index',type=Path,required=True);p.add_argument('--manifest',type=Path,required=True);p.add_argument('--candidates',type=Path);p.add_argument('--preferences',type=Path);p.add_argument('--review-queue',type=Path);a=p.parse_args()
    index=load(a.index);manifest=load(a.manifest);now=time.time()
    if not isinstance(index,dict) or index.get('schema')!='visualagent.strategy-index.v1':
        index_status={'state':'missing_or_invalid','count':0}
    else:
        age=max(0,now-float(index.get('generated_at',0))) if isinstance(index.get('generated_at'),(int,float)) else None
        index_status={'state':'fresh' if age is not None and age<=7*86400 else 'stale','age_seconds':age,'count':len(index.get('records',[])) if isinstance(index.get('records'),list) else 0,'input_fingerprints':index.get('input_fingerprints',{})}
    summary=manifest.get('summary',{}) if isinstance(manifest,dict) else {}
    preparation_state='missing' if not manifest else 'ready'
    preparation_error=None
    changed_inputs=[]
    if isinstance(manifest,dict) and manifest.get('input_fingerprints'):
        preparation_state='unverified'
        try:
            # A matching metadata marker is sufficient for the health page to
            # trust the already-created manifest. Release preparation still
            # performs the expensive logical before/after fingerprint check.
            current_markers=read_current_markers()
            if manifest.get('input_markers') and manifest['input_markers'] == current_markers:
                preparation_state='ready'
            elif manifest.get('input_markers'):
                # A marker mismatch is already authoritative evidence that
                # this manifest predates current inputs. Do not scan large
                # shared SQLite tables just to report the same stale state.
                preparation_state='stale'
                changed_inputs=sorted(key for key in manifest['input_markers']
                                      if manifest['input_markers'].get(key)!=current_markers.get(key))
            if not manifest.get('input_markers'):
                preparation_state='unverified'
                for attempt in range(3):
                    try:
                        current=bounded_input_fingerprints(read_current_fingerprints)
                        preparation_state='ready' if manifest['input_fingerprints']==current else 'stale'
                        if preparation_state=='stale':
                            changed_inputs=sorted(key for key,value in manifest['input_fingerprints'].items()
                                                 if current.get(key)!=value)
                        break
                    except FingerprintTimeout:
                        preparation_error='fingerprint_timeout'; break
                    except Exception:
                        preparation_error='fingerprint_read_failed'
                        if attempt<2:time.sleep(0.2)
        except Exception as exc:
            preparation_state='unverified'
            preparation_error='fingerprint_check_unavailable:' + type(exc).__name__
    candidate=load(a.candidates) if a.candidates else None
    preferences=load(a.preferences) if a.preferences else None
    review_queue=load(a.review_queue) if a.review_queue else None
    report={'schema':'visualagent.ad-learning-health.v1','index':index_status,
            'preparation':{'state':preparation_state,'projects':summary.get('projects',0),'versions':summary.get('versions',0),'training_eligible':summary.get('training_eligible',0),'release_ready':summary.get('release_ready',False),'changed_inputs':changed_inputs},
            'candidate_queue':{'state':'present' if candidate else 'missing','records':candidate.get('record_count',0) if candidate else 0,'training_eligible':candidate.get('training_eligible',False) if candidate else False},
            'preference_queue':{'state':'present' if preferences else ('not_configured' if not a.preferences else 'missing'),
                                'records':preferences.get('record_count',0) if preferences else 0,
                                'training_eligible':preferences.get('training_eligible',False) if preferences else False},
            'analysis_review_queue':{'state':review_queue.get('state','present') if review_queue else ('not_configured' if not a.review_queue else 'missing'),
                                     'pending':review_queue.get('total_pending',0) if review_queue else 0,
                                     'listed':review_queue.get('count',0) if review_queue else 0,
                                     'training_eligible':review_queue.get('training_eligible',False) if review_queue else False},
            'next_action':'refresh_strategy_index' if index_status['state']!='fresh' else ('refresh_preparation_manifest' if preparation_state!='ready' else ('complete_missing_release_gates' if not summary.get('release_ready') else 'review_candidate_queue'))}
    if review_queue and type(review_queue.get('total_pending')) is int and review_queue.get('total_pending')>0 and index_status['state']=='fresh':
        report['next_action']='complete_reference_analysis_review'
    if review_queue and review_queue.get('state')=='unavailable':
        report['next_action']='restore_reference_analysis_queue'
    if preparation_error:report['preparation']['check_error']=preparation_error
    print(json.dumps(report,ensure_ascii=False,indent=2))
    raise SystemExit(0 if index_status['state']=='fresh' and preparation_state=='ready' else 2)
if __name__=='__main__':main()
