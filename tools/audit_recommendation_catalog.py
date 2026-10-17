#!/usr/bin/env python3
"""Audit the full twenty-film deliverable against actual media and review evidence."""
import argparse
from array import array
import hashlib
import json
import math
from pathlib import Path
import sqlite3
import subprocess

ROOT = Path(__file__).resolve().parents[1]
PRIVATE = Path('/var/lib/visualstation-local')
DATA = PRIVATE / 'creative'


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--allow-incomplete', action='store_true')
    args = parser.parse_args()
    cases = {c['id']: c for c in json.loads((ROOT / 'productions/recommendation_20_v1/cases.json').read_text())['cases']}
    assert len(cases) == 20
    catalog = json.loads((DATA / 'templates/catalog.json').read_text())['templates']
    ids = [t['id'] for t in catalog]
    assert len(ids) == len(set(ids)) and set(ids) <= cases.keys()
    projects = {}
    with sqlite3.connect(f'file:{DATA}/projects.sqlite3?mode=ro', uri=True) as connection:
        for name in ('recommendation20-v2-state.json', 'recommendation20-repair-state.json'):
            state_file = PRIVATE / name
            if not state_file.exists():
                continue
            for record in json.loads(state_file.read_text())['cases'].values():
                if record.get('project'):
                    row = connection.execute('select data from projects where id=?', (record['project'],)).fetchone()
                    if row:
                        project = json.loads(row[0])
                        if project.get('run_id'):
                            projects[project['run_id']] = project
    checks, seen_hashes = [], set()
    for item in catalog:
        slug = item['id']
        case = cases[slug]
        assert all(item[k] == case[k] for k in ('provider', 'model', 'aspect', 'duration'))
        assert item['training_eligible'] is False
        assert len(item['storyboard']) == 2 and all(s['caption'].strip() for s in item['storyboard'])
        directory = DATA / 'templates' / slug
        video, poster = directory / 'final.mp4', directory / 'poster.jpg'
        assert video.is_file() and poster.is_file() and poster.stat().st_size > 1000
        sha = digest(video)
        assert sha not in seen_hashes, 'Two cases contain an identical final video'
        seen_hashes.add(sha)
        meta = json.loads(subprocess.check_output([
            '/opt/visualstation/creative-runtime/bin/ffprobe', '-v', 'error', '-show_streams',
            '-show_format', '-of', 'json', str(video)]))
        stream = next(s for s in meta['streams'] if s['codec_type'] == 'video')
        dimensions = {'16:9': (1280, 720), '9:16': (720, 1280), '1:1': (720, 720)}[item['aspect']]
        assert (stream['width'], stream['height']) == dimensions
        assert abs(float(meta['format']['duration']) - 10) < .2
        assert any(s['codec_type'] == 'audio' for s in meta['streams']) == item['audio']
        audio_signal = None
        if item['audio']:
            pcm = subprocess.check_output([
                '/opt/visualstation/creative-runtime/bin/ffmpeg', '-v', 'error', '-i', str(video),
                '-vn', '-ac', '1', '-ar', '16000', '-f', 'f32le', 'pipe:1'])
            samples = array('f', pcm)
            assert len(samples) >= 9.8 * 16000 and all(math.isfinite(v) for v in samples)
            rms = math.sqrt(sum(v * v for v in samples) / len(samples))
            assert rms > 1e-6, 'Native audio track is effectively silent'
            audio_signal = {'decoded_seconds': len(samples) / 16000,
                            'rms_dbfs': round(20 * math.log10(rms), 2),
                            'peak': max(abs(v) for v in samples),
                            'clipped_fraction': sum(abs(v) >= .999 for v in samples) / len(samples),
                            'semantic_listening': 'not_performed'}
        evidence = []
        for review_root in ('template-reviews-v2', 'template-reviews-repair', 'template-reviews-ceramic-static'):
            for path in (DATA / review_root / slug).rglob('review.json'):
                review = json.loads(path.read_text())
                if review.get('verdict') != 'publishable' or review.get('training_eligible') is not False:
                    continue
                if review.get('sha256'):
                    if review['sha256'] == sha:
                        source = (DATA / review['artifact']).resolve()
                        assert source.is_relative_to(DATA) and digest(source) == sha
                        evidence.append(str(path.relative_to(DATA)))
                else:
                    project = projects.get(review.get('run_id'), {})
                    if project.get('artifact') and project.get('qa', {}).get('technical') == 'passed':
                        source = (DATA / project['artifact']).resolve()
                        assert source.is_relative_to(DATA)
                        if digest(source) == sha:
                            evidence.append(str(path.relative_to(DATA)))
        assert evidence, f'{slug}: no passed independent review of this exact video'
        checks.append({'id': slug, 'sha256': sha, 'dimensions': dimensions,
                       'audio': item['audio'], 'audio_signal': audio_signal,
                       'independent_review_evidence': evidence})
    missing = sorted(cases.keys() - set(ids))
    result = {'complete': not missing, 'expected': 20, 'published': len(ids), 'missing': missing,
              'checked': checks, 'human': 'pending', 'training_eligible': False,
              'scope': 'Media dimensions, duration, audio flags, unique videos and passed sampled review provenance; public interaction requires separate browser acceptance.'}
    (PRIVATE / 'recommendation20-catalog-audit.json').write_text(json.dumps(result, ensure_ascii=False, indent=2))
    print(json.dumps({k: result[k] for k in ('complete', 'expected', 'published', 'missing')}, ensure_ascii=False))
    if missing and not args.allow_incomplete:
        raise SystemExit(1)


if __name__ == '__main__':
    main()
