#!/usr/bin/env python3
"""Collect bounded Cresta Awards moving-image winner metadata."""
import argparse
from contextlib import ExitStack
import fcntl, json, os, secrets, sys, time
from pathlib import Path
from urllib.robotparser import RobotFileParser
import httpx
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from harness.library import store
from harness.models.reference_sources import cresta
from harness.tools.award_archive import collect_archive

SOURCE = 'Cresta Awards official moving-image winners'
MAX_BYTES = 4 * 1024 * 1024
REQUEST_DELAY = 10

def _year(year):
    if year is None:
        return cresta.YEARS[int(time.time() // (3 * 3600)) % len(cresta.YEARS)]
    if type(year) is not int or year not in cresta.YEARS:
        raise ValueError('invalid_cresta_year')
    return year

def run(year=None, offset=None):
    return collect_archive(cresta, SOURCE, 'cresta', _year(year), offset, REQUEST_DELAY)

if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__); parser.add_argument('--year',type=int,choices=cresta.YEARS); parser.add_argument('--offset',type=int)
    args=parser.parse_args(); result=run(args.year,args.offset); print(json.dumps(result,ensure_ascii=False)); sys.exit(1 if result['state']=='failed' else 0)
