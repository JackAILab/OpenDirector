#!/usr/bin/env python3
"""Create a fail-closed, non-overwriting release receipt; never exports raw data."""
import argparse,json
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from harness.learning.export import release

p=argparse.ArgumentParser();p.add_argument('--manifest',type=Path,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args()
print(json.dumps(release(a.manifest,a.output),ensure_ascii=False))
