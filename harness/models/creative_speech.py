"""Offline transcription adapter. Explicit installed model; no network or fallback."""
import json
import os
from pathlib import Path
import subprocess
import sys

MODEL_ID = 'faster-whisper-small-int8-v1'
LANGUAGES = {'auto','zh','en','ja','ko','es','fr','de','pt','it','ru','ar','hi'}


def settings():
    root=Path(os.getenv('CREATIVE_ASR_ROOT','/opt/visualstation/creative-runtime/asr'))
    available=all((root/'small'/f).is_file() for f in ('model.bin','config.json','tokenizer.json','vocabulary.txt')) and (root/'packages/faster_whisper').is_dir()
    return {'available':available,'model':MODEL_ID,'local':True,'root':root}


def transcribe(wav: Path, language: str):
    config=settings()
    if not config['available']: raise ValueError('口播识别尚未配置')
    if language not in LANGUAGES: raise ValueError('识别语言无效')
    env=dict(os.environ,PYTHONPATH=str(config['root']/'packages'),HF_HUB_OFFLINE='1',TRANSFORMERS_OFFLINE='1',OMP_NUM_THREADS='2')
    result=subprocess.run([os.getenv('CREATIVE_ASR_PYTHON',sys.executable),str(Path(__file__).with_name('creative_speech_worker.py')),
                          str(wav),str(config['root']/'small'),language],env=env,capture_output=True,timeout=300)
    if result.returncode or len(result.stdout)>2_000_000: raise ValueError('口播识别未完成，未切换模型或重试')
    return json.loads(result.stdout)
