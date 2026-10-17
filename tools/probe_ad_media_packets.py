#!/usr/bin/env python3
"""Write a private, hash-bound technical probe report for ad review packets."""
import argparse
import json
import os
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from harness.library.review_packets import build_packets
from harness.library.learning import analysis_review_queue
from harness.library import store
from harness.library.technical_probe import probe_file

parser = argparse.ArgumentParser()
parser.add_argument('--output', type=Path, required=True)
parser.add_argument('--limit', type=int, default=200)
parser.add_argument('--only-semantic', action='store_true', help='只探测已有结构分析、待音频/运动审阅的素材')
args = parser.parse_args()
if args.output.exists() or args.output.is_symlink():
    raise FileExistsError('Refusing to overwrite technical probe report')
packets = build_packets(analysis_review_queue(max(args.limit, 5000)), args.limit, only_semantic=args.only_semantic)
rows = []
with store.connection() as connection:
    for packet in packets['items']:
        row = connection.execute('SELECT path,sha256 FROM assets WHERE item=?', (packet['item'],)).fetchone()
        if not row:
            probe = {'status': 'asset_missing', 'semantic_review': 'pending', 'motion_review': 'pending', 'training_eligible': False}
        else:
            asset_path = Path(row['path'])
            if not asset_path.is_absolute():
                asset_path = store.ROOT / asset_path
            probe = probe_file(asset_path, row['sha256'])
        rows.append({'item': packet['item'], 'media_sha256': packet.get('media_sha256'), 'probe': probe})
payload = {
    'schema': 'visualagent.ad-media-technical-probes.v1',
    'source_schema': packets['schema'],
    'count': len(rows),
    'only_semantic': bool(args.only_semantic),
    'items': rows,
    'policy': 'container facts only; semantic audio and full motion review remain pending; no training eligibility',
    'training_eligible': False,
}
args.output.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
fd = os.open(args.output, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
with os.fdopen(fd, 'w', encoding='utf-8') as handle:
    json.dump(payload, handle, ensure_ascii=False, indent=2)
    handle.write('\n')
print(json.dumps({'count': len(rows), 'training_eligible': False}, ensure_ascii=False))
