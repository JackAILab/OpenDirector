#!/usr/bin/env python3
"""Publish one independently reviewed revision, bound to its exact media hash."""
import argparse
import hashlib
import json
from pathlib import Path
import sqlite3
import subprocess
from harness.studio import store
from harness.studio.templates import publish_template


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--slug', required=True)
    parser.add_argument('--report', required=True)
    parser.add_argument('--poster', required=True)
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument('--project-file')
    group.add_argument('--project-id')
    args = parser.parse_args()
    report_path = Path(args.report).resolve()
    assert report_path.is_relative_to(store.DATA.resolve())
    report = json.loads(report_path.read_text())
    assert report['verdict'] == 'publishable' and report['training_eligible'] is False
    if args.project_file:
        project = json.loads(Path(args.project_file).read_text())
    else:
        with sqlite3.connect(f'file:{store.DATA}/projects.sqlite3?mode=ro', uri=True) as connection:
            project = json.loads(connection.execute('select data from projects where id=?',
                                 (args.project_id,)).fetchone()[0])
    video = (store.DATA / project['artifact']).resolve()
    assert video.is_relative_to(store.DATA.resolve())
    assert report['run_id'] == project['run_id'] and report['artifact'] == project['artifact']
    assert report['sha256'] == hashlib.sha256(video.read_bytes()).hexdigest()
    case = next(c for c in json.loads((store.ROOT / 'productions/recommendation_20_v1/cases.json').read_text())['cases']
                if c['id'] == args.slug)
    meta = json.loads(subprocess.check_output([
        '/opt/visualstation/creative-runtime/bin/ffprobe', '-v', 'error', '-show_streams', '-of', 'json', str(video)]))
    published = publish_template(case, project, video, args.poster,
                                 any(s['codec_type'] == 'audio' for s in meta['streams']),
                                 '技术检查与独立20帧补充审阅通过；完整内容与声音仍需用户确认。')
    print(args.slug, 'published' if published else 'already_published')


if __name__ == '__main__':
    main()
