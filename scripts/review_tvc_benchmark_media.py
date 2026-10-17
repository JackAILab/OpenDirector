#!/usr/bin/env python3
"""Produce decoding/audio evidence and sampled frames; never infer semantic approval."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from harness.evaluators.live import probe_video
from harness.renderers.common import ffmpeg_executable


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('case_id')
    args = parser.parse_args()
    if args.case_id not in {p.parent.name for p in (ROOT/'productions/omni_tvc_benchmark_10_v1/cases').glob('*/input.json')}:
        parser.error('unknown case')
    folder = ROOT/'outputs/artifacts/omni_tvc_benchmark_10_v1'/args.case_id
    video = folder/'omni-attempt-01.mp4'
    if not video.is_file():
        parser.error('video has not completed')
    review = folder/'media-review'
    review.mkdir(exist_ok=True)
    report = review/'technical.json'
    if report.exists():
        parser.error('review already exists; preserve prior evidence')
    ffmpeg = ffmpeg_executable()
    probe = probe_video(video)
    decoded = subprocess.run([ffmpeg,'-hide_banner','-v','error','-xerror','-i',str(video),'-f','null','-'],capture_output=True,text=True)
    audio = subprocess.run([ffmpeg,'-hide_banner','-i',str(video),'-vn','-af','volumedetect,silencedetect=noise=-42dB:d=0.5','-f','null','-'],capture_output=True,text=True)
    (review/'audio-measurements.txt').write_text('\n'.join(line for line in audio.stderr.splitlines() if 'volumedetect' in line or 'silencedetect' in line)+'\n')
    # Keep frame times explicit. These samples support, but do not replace, a motion review.
    subprocess.run([ffmpeg,'-hide_banner','-loglevel','error','-n','-i',str(video),'-vf','fps=2,scale=480:-1,tile=5x6','-frames:v','1',str(review/'frames-half-second.jpg')],check=True)
    checks = {'full_decode':decoded.returncode==0,'duration':abs(probe.get('duration',0)-15)<=0.25,'resolution':(probe.get('width'),probe.get('height'))==(1920,1080),'audio_stream':probe.get('audio_stream_count',0)>0}
    result = {'schema':'visualagent.tvc-media-review.v1','case_id':args.case_id,'video_sha256':hashlib.sha256(video.read_bytes()).hexdigest(),'probe':probe,'checks':checks,'technical_passed':all(checks.values()),'semantic_review':'pending','perceptual_audio_review':'pending','frame_sample_interval_seconds':0.5,'training_eligible':False}
    with report.open('x') as handle:
        json.dump(result,handle,ensure_ascii=False,indent=2)
    print(json.dumps(result,ensure_ascii=False),flush=True)
    return 0 if result['technical_passed'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
