#!/usr/bin/env python3
"""One explicit CodeBuddy still per template; no hidden retries or raw payload logs."""
import hashlib
import json
from pathlib import Path
import subprocess
from PIL import Image

ROOT=Path(__file__).resolve().parents[1]
CASES=json.loads((ROOT/'productions/recommendation_20_v1/cases.json').read_text())['cases']
OUT=Path('/var/lib/visualstation-local/template-reference-images')
STATE=OUT/'references.json'
state=json.loads(STATE.read_text()) if STATE.exists() else {}
first=OUT/'morning-coffee'/'codebuddy-2026-09-30T02-46-09-143Z-1.png'
if first.exists() and 'morning-coffee' not in state:
    state['morning-coffee']={'state':'completed','path':str(first),'attempt':1}

def save():
    p=STATE.with_suffix('.tmp');p.write_text(json.dumps(state,ensure_ascii=False,indent=2));p.replace(STATE)

save()
for case in CASES:
    if case['id'] in state:continue
    directory=OUT/case['id'];directory.mkdir(parents=True,exist_ok=True)
    prompt=(f"为真实商业广告拍摄一张精致的商品场景参考照片。唯一主商品：{case['product']}。场景：{case['scene']}。"
            "精确明确商品的几何形状和材质，产品完整入镜，符合物理常识。场景有前中后景、自然道具与层次灯光，商业摄影质感。"
            "这是一张将被重复用作两个镜头固定外观约束的参考图，只展示一件明确的主商品，不要拼贴或多视图。"
            "无品牌、无标志、无标签、无可读文字、无水印、无UI，不写字。背景环境具体，避免空白产品图。")
    size={'16:9':'1024x576','9:16':'576x1024','1:1':'1024x1024'}[case['aspect']]
    state[case['id']]={'state':'requested','attempt':1,'size':size,'prompt_sha256':hashlib.sha256(prompt.encode()).hexdigest()};save()
    try:
        r=subprocess.run(['codebuddy-image','--prompt',prompt,'--size',size,'--output-dir',str(directory)],capture_output=True,text=True,timeout=600)
        if r.returncode:raise RuntimeError('generation_failed')
        outputs=json.loads(r.stdout)['outputs'];assert len(outputs)==1
        path=Path(outputs[0]['path']);assert path.is_file() and path.resolve().is_relative_to(directory.resolve())
        with Image.open(path) as image:
            width,height=image.size
        desired={'16:9':16/9,'9:16':9/16,'1:1':1}[case['aspect']]
        assert abs(width/height/desired-1)<.05
        state[case['id']].update(state='completed',path=str(path),width=width,height=height,sha256=hashlib.sha256(path.read_bytes()).hexdigest())
        print(case['id'],'reference_ready',flush=True)
    except Exception:
        state[case['id']]['state']='failed_no_retry';print(case['id'],'reference_failed_no_retry',flush=True)
    save()
