#!/usr/bin/env python3
"""Submit one exact, full-coverage reference audio/motion review receipt.

The input JSON is an allowlisted reviewer summary, not a provider payload.
This command never generates media, retries a model, or grants training
eligibility.  Existing analysis and current asset hashes are checked before
any write.
"""
import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from harness.library import learning, store
from harness.learning.audio_review import build_audio_review
from harness.learning.motion_review import build_motion_review
from harness.learning.reference_reviews import apply_receipts


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--item', required=True)
    parser.add_argument('--analysis-version', required=True, type=int)
    parser.add_argument('--audio-json', type=Path)
    parser.add_argument('--motion-json', type=Path)
    args = parser.parse_args()
    if not args.audio_json and not args.motion_json:
        parser.error('at least one of --audio-json or --motion-json is required')
    with store.connection() as connection:
        asset = connection.execute('SELECT sha256 FROM assets WHERE item=?', (args.item,)).fetchone()
    if not asset:
        raise SystemExit('asset_not_found')
    digest = asset['sha256']

    def read(path):
        if path.is_symlink() or not path.is_file():
            raise SystemExit('review_input_missing')
        data = json.loads(path.read_text(encoding='utf-8'))
        if not isinstance(data, dict):
            raise SystemExit('review_input_malformed')
        return data

    audio = build_audio_review(item=args.item, media_sha256=digest,
                               analysis_version=args.analysis_version,
                               result=read(args.audio_json)) if args.audio_json else None
    motion = build_motion_review(item=args.item, media_sha256=digest,
                                 analysis_version=args.analysis_version,
                                 result=read(args.motion_json)) if args.motion_json else None
    result = apply_receipts(item=args.item, media_sha256=digest,
                            analysis_version=args.analysis_version,
                            audio=audio, motion=motion)
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))


if __name__ == '__main__':
    main()
