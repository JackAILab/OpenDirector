#!/usr/bin/env python3
"""Create a private non-overwriting metadata manifest, never export user content."""
import argparse
import json
import os
import signal
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from harness.learning.inventory import prepare


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--salt-file',type=Path,required=True)
    parser.add_argument('--registry',type=Path,required=True)
    parser.add_argument('--seed')
    parser.add_argument('--reuse-frozen-split',action='store_true',
                        help='Reuse existing assignments; unseen families remain quarantined')
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--timeout-seconds',type=int,default=600,
                        help='Abort a shared-storage scan without writing a partial manifest')
    args=parser.parse_args()
    if args.timeout_seconds < 30:
        parser.error('--timeout-seconds must be at least 30')
    if args.salt_file.is_symlink() or args.salt_file.stat().st_mode & 0o077:raise ValueError('Pseudonymization key must be private')
    # Reserve the output before mutating the split registry. Existing reports cannot be overwritten.
    fd=os.open(args.output,os.O_CREAT|os.O_EXCL|os.O_WRONLY,0o600)
    try:
        if not args.reuse_frozen_split and not args.seed:
            raise ValueError('--seed is required unless --reuse-frozen-split is used')
        def timeout(_signum, _frame):
            raise TimeoutError('preparation_timeout')
        previous=signal.signal(signal.SIGALRM, timeout)
        signal.alarm(args.timeout_seconds)
        try:
            result=prepare(args.salt_file.read_bytes(),args.registry,args.seed,
                           reuse_frozen_split=args.reuse_frozen_split)
        finally:
            signal.alarm(0)
            signal.signal(signal.SIGALRM, previous)
        with os.fdopen(fd,'w',encoding='utf-8') as out:
            fd=None;json.dump(result,out,ensure_ascii=False,indent=2);out.write('\n')
    except Exception as exc:
        if fd is not None:os.close(fd)
        args.output.unlink(missing_ok=True)
        if isinstance(exc, TimeoutError):
            print(json.dumps({'state':'failed','error_code':'preparation_timeout',
                              'partial_manifest':False},ensure_ascii=False), file=sys.stderr)
        raise
    print(json.dumps(result['summary'],ensure_ascii=False))


if __name__=='__main__':main()
