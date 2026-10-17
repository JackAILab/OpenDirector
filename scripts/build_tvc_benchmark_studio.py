#!/usr/bin/env python3
"""Project the ten canonical benchmark cases into a read-only studio gallery."""
import json
from pathlib import Path
import shutil

ROOT = Path(__file__).resolve().parents[1]
bundle = ROOT/'productions/omni_tvc_benchmark_10_v1'
site = ROOT/'tools/asset_studio'
public = site/'public/tvc'
public.mkdir(exist_ok=True)
cases = []
blocker_path = bundle/'generation-blocker.json'
blocker = json.loads(blocker_path.read_text()) if blocker_path.exists() else None
for path in sorted(bundle.glob('cases/*/input.json')):
    spec = json.loads(path.read_text())
    case_id = spec['case_id']
    output = ROOT/'outputs/artifacts/omni_tvc_benchmark_10_v1'/case_id
    item = {'id':case_id,'title':spec['title'],'brief':spec['brief'],'video':None,'reference':None,'status':'等待生成','findings':[],'technicalPassed':False,'trainingEligible':False}
    if blocker and not blocker.get('resolved_at'):
        item['status'] = '等待视频额度'
    if spec['references']:
        reference = path.parent/spec['references'][0]['path']
        shutil.copy2(reference,public/f'{case_id}.png')
        item['reference'] = f'/tvc/{case_id}.png'
    video = output/'omni-attempt-01.mp4'
    if video.is_file() and video.with_suffix('.receipt.json').exists():
        target = public/f'{case_id}-attempt-01.mp4'
        if not target.exists() or target.stat().st_size != video.stat().st_size:
            shutil.copy2(video,target)
        item['video'] = f'/api/media/{target.name}'
        item['status'] = '已生成 · 审片中'
    elif (output/'attempt-01.reservation.json').exists():
        item['status'] = '已提交'
        result_path = output/'technical-result.json'
        if result_path.exists() and json.loads(result_path.read_text()).get('status') == 'failed':
            item['status'] = '提交失败 · 视频额度不足' if blocker else '提交失败'
    technical = output/'media-review/technical.json'
    semantic = output/'media-review/semantic.json'
    if technical.exists():
        item['technicalPassed'] = json.loads(technical.read_text())['technical_passed']
    if semantic.exists():
        review = json.loads(semantic.read_text())
        item['findings'] = review['findings']
        item['status'] = {'needs_revision':'已生成 · 有待改进项','passed':'审片通过','visual_pass_with_notes':'画面审片通过 · 有备注'}.get(review['verdict'],'已生成 · 审片中')
    cases.append(item)
archive = bundle/'comparison-inputs-10-cases-v1.zip'
if archive.exists():
    shutil.copy2(archive,public/archive.name)
(site/'app/data/tvc-benchmark.json').write_text(json.dumps({'cases':cases,'inputArchive':f'/tvc/{archive.name}','completed':sum(bool(c['video']) for c in cases)},ensure_ascii=False,indent=2)+'\n')
print(json.dumps({'cases':len(cases),'videos':sum(bool(c['video']) for c in cases)}))
