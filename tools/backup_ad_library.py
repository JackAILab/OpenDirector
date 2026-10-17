#!/usr/bin/env python3
import argparse
import json
import os
import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from harness.models.reference_backup import ModelScopeBackup
from harness.tools.reference_backup import backup, resume_verification, SAFE_ERRORS
from harness.library import store
from harness.library.backup_progress import write_progress


def report(value):
    write_progress(store.ROOT, value)
    print(json.dumps(value), flush=True)


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--verify-snapshot');parser.add_argument('--metadata-only',action='store_true',help='只备份主库元数据与人工标注，不包含学习证据或原始媒体');parser.add_argument('--learning-only',action='store_true',help='备份主库元数据、人工标注与学习证据，不复制原始媒体');parser.add_argument('--readback-workers',type=int,choices=range(1,5),default=4,help='回读并发数1–4；每个文件仍独立校验');args=parser.parse_args()
    if args.metadata_only and args.learning_only: parser.error('选择 --metadata-only 或 --learning-only 之一')
    try:
        os.environ.setdefault('TQDM_DISABLE','1')
        transport=ModelScopeBackup(revisions_dir=store.ROOT/'backup_revisions')
        options={'readback_workers':args.readback_workers,'progress':report}
        result=resume_verification(transport,args.verify_snapshot,**options) if args.verify_snapshot else backup(transport,include_media=not (args.metadata_only or args.learning_only),include_learning=not args.metadata_only,**options)
        print(json.dumps(result))
    except Exception as e:
        code=str(e) if str(e) in SAFE_ERRORS else 'backup_failed'
        # Expose only the bounded diagnostic vocabulary; never print provider
        # payloads, credentials, signed URLs, or personal data.
        print(json.dumps({'state':'failed','error_type':type(e).__name__,'error_code':code}));sys.exit(1)
