#!/usr/bin/env python3
"""Inspect private prospective creation evidence; never export training content."""
import argparse
import os
import json
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from harness.learning.episodes import inspect_episode


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--project',required=True)
    parser.add_argument('--owner',required=True,type=int)
    parser.add_argument('--output',required=True,type=Path)
    args=parser.parse_args()
    report=inspect_episode(args.project,args.owner)
    # Non-overwriting local audit report; no source media/conversation/provider data.
    with os.fdopen(os.open(args.output,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600),'w',encoding='utf-8') as f:
        json.dump(report,f,ensure_ascii=False,indent=2)
        f.write('\n')
    print(json.dumps({'revisions':len(report['revisions']),'training_eligible':False}))


if __name__=='__main__':main()
