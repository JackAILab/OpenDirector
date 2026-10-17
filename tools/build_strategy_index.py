#!/usr/bin/env python3
"""Build the small local strategy index used by online planning."""
import argparse,json,os,hashlib,time
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from harness.library.learning import build_strategy_index,analysis_summary
from harness.learning.inventory import strategy_fingerprints


def _fingerprint_worker(queue):
    try:
        queue.put(('ok', strategy_fingerprints()))
    except BaseException as exc:
        queue.put(('error', type(exc).__name__))


def bounded_fingerprints(seconds=20):
    """Read source fingerprints in a killable worker.

    The library lives on a shared filesystem. A blocked FUSE read must not
    leave an index build holding the shell or the studio's worker forever.
    Failing closed also prevents publishing an index whose source snapshot
    cannot be identified.
    """
    import multiprocessing
    queue=multiprocessing.Queue(maxsize=1)
    process=multiprocessing.Process(target=_fingerprint_worker,args=(queue,))
    process.start();process.join(seconds)
    if process.is_alive():
        process.terminate();process.join(2)
        raise TimeoutError('strategy_index_fingerprint_timeout')
    if queue.empty():raise RuntimeError('strategy_index_fingerprint_no_result')
    state,value=queue.get()
    if state!='ok':raise RuntimeError(value)
    return value

parser=argparse.ArgumentParser();parser.add_argument('--output',type=Path,required=True);parser.add_argument('--limit',type=int,default=24);args=parser.parse_args()
items=build_strategy_index(args.limit)
from harness.library import store
def file_digest(path):
    if not path.is_file():return None
    h=hashlib.sha256()
    with path.open('rb') as stream:
        for chunk in iter(lambda:stream.read(1024*1024),b''):h.update(chunk)
    return h.hexdigest()
fingerprints=bounded_fingerprints()
payload={'schema':'visualagent.strategy-index.v1','generated_at':time.time(),
         'input_fingerprints':{'analyses':fingerprints.get('library_analyses'),'library':fingerprints.get('library')},'records':items}
payload['analysis_summary']=analysis_summary()
if args.output.exists() or args.output.is_symlink():raise FileExistsError('Refusing to overwrite strategy index')
args.output.parent.mkdir(parents=True,exist_ok=True,mode=0o700)
fd=os.open(args.output,os.O_CREAT|os.O_EXCL|os.O_WRONLY,0o600)
with os.fdopen(fd,'w',encoding='utf-8') as out:
    json.dump(payload,out,ensure_ascii=False,indent=2);out.write('\n')
print(json.dumps({'count':len(items)},ensure_ascii=False))
