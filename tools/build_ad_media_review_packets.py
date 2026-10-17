#!/usr/bin/env python3
"""Write private, bounded audio/motion review packets for ad references."""
import argparse, json, os
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from harness.library.learning import analysis_review_queue
from harness.library.review_packets import build_packets, dumps

parser = argparse.ArgumentParser()
parser.add_argument('--output', type=Path, required=True)
parser.add_argument('--limit', type=int, default=200)
parser.add_argument('--only-semantic', action='store_true', help='跳过尚未完成结构分析的素材')
args = parser.parse_args()
if args.output.exists() or args.output.is_symlink():
    raise FileExistsError('Refusing to overwrite review packets')
payload = build_packets(analysis_review_queue(max(args.limit, 5000)), args.limit, only_semantic=args.only_semantic)
args.output.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
fd = os.open(args.output, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
with os.fdopen(fd, 'w', encoding='utf-8') as f:
    f.write(dumps(payload))
print(json.dumps({'count': payload['count'], 'total_pending': payload['total_pending']}, ensure_ascii=False))
