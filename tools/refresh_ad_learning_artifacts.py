#!/usr/bin/env python3
"""Refresh private ad-learning snapshots without overwriting prior evidence."""
import argparse, json, os, subprocess, sys
from datetime import datetime, timezone
from pathlib import Path

ROOT=Path('/var/lib/visualstation-local/creative/learning')
DB=Path('/assets/library')

def main():
    ap=argparse.ArgumentParser();ap.add_argument('--output-dir',type=Path,default=ROOT);ap.add_argument('--limit',type=int,default=24);args=ap.parse_args()
    if not 1<=args.limit<=24:raise ValueError('limit must be 1-24')
    stamp=datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')
    out=args.output_dir;out.mkdir(parents=True,exist_ok=True,mode=0o700)
    names={
      'report':out/f'ad-learning-grammar-report-{stamp}.json',
      'strategy':out/f'strategy-candidates-{stamp}.json',
      'queue':out/f'ad-analysis-review-queue-{stamp}.json',
      'semantic_packets':out/f'ad-media-semantic-review-packets-{stamp}.json',
      'aggregate':out/f'ad-analysis-aggregate-{stamp}.json',
      'mechanism_report':out/f'ad-mechanism-report-{stamp}.json',
      'curriculum':out/f'ad-agent-curriculum-{stamp}.json',
    }
    for path in names.values():
        if path.exists() or path.is_symlink():raise FileExistsError(str(path))
    common=[sys.executable]
    commands=[
      common+['tools/materialize_ad_learning_report.py','--db',str(DB),'--output',str(names['report'])],
      common+['tools/build_strategy_index.py','--output',str(names['strategy']),'--limit',str(args.limit)],
      common+['tools/build_ad_analysis_review_queue.py','--output',str(names['queue']),'--limit','5000'],
      common+['tools/build_ad_media_review_packets.py','--output',str(names['semantic_packets']),'--limit','200','--only-semantic'],
      common+['tools/summarize_ad_analyses.py','--output',str(names['aggregate'])],
      common+['tools/materialize_ad_mechanism_report.py','--aggregate',str(names['aggregate']),'--output',str(names['mechanism_report'])],
      common+['tools/materialize_ad_curriculum.py','--index',str(names['strategy']),'--output',str(names['curriculum'])],
    ]
    completed=[]
    try:
        for command in commands:
            subprocess.run(command,check=True,timeout=240)
            completed.append(command[1])
    except Exception:
        for path in names.values(): path.unlink(missing_ok=True)
        raise
    print(json.dumps({'stamp':stamp,'artifacts':{k:str(v) for k,v in names.items()},'completed':completed},ensure_ascii=False))

if __name__=='__main__':main()
