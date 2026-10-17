#!/usr/bin/env python3
"""Write a private queue for sampled ad analyses missing audio or motion review."""
import argparse
import json
import os
from datetime import datetime, timezone
from pathlib import Path
import sys
import tempfile
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))


def publish_queue(output, payload):
    """Expose a complete snapshot atomically, preserving all older evidence."""
    if output.exists() or output.is_symlink():
        raise FileExistsError('Refusing to overwrite review queue')
    output.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    fd, temporary = tempfile.mkstemp(prefix='.review-queue-', dir=output.parent)
    try:
        with os.fdopen(fd, 'w', encoding='utf-8') as f:
            json.dump(payload, f, ensure_ascii=False, indent=2)
            f.write('\n')
            f.flush()
            os.fsync(f.fileno())
        # A hard link publishes complete bytes without replacing a racing writer.
        os.link(temporary, output)
    finally:
        Path(temporary).unlink(missing_ok=True)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--output', type=Path)
    parser.add_argument('--limit', type=int, default=200)
    args = parser.parse_args()
    now = datetime.now(timezone.utc)
    root = Path(os.getenv('AD_LIBRARY_LEARNING_ARTIFACT_ROOT',
                          '/var/lib/visualstation-local/creative/learning'))
    output = args.output or root / f'ad-analysis-review-queue-{now:%Y%m%dT%H%M%S%fZ}.json'
    if output.exists() or output.is_symlink():
        raise FileExistsError('Refusing to overwrite review queue')
    from harness.library.learning import analysis_review_queue
    payload = analysis_review_queue(args.limit)
    payload['generated_at'] = now.isoformat()
    publish_queue(output, payload)
    print(json.dumps({key: payload[key] for key in
                      ('state', 'count', 'total_pending')}, ensure_ascii=False))
    return 0 if payload.get('state') == 'ready' else 1


if __name__ == '__main__':
    raise SystemExit(main())
