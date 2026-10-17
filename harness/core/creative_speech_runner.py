"""One offline ASR attempt per explicit request; private transcript, sanitized events."""
import asyncio
from harness.studio import store
from harness.tools.creative_transcript import transcribe_source


async def run_transcription(pid,uid,job_id,snapshot,slots):
    try:
        job=snapshot['edit_transcriptions'][job_id]
        async with slots:
            result=await asyncio.to_thread(transcribe_source,snapshot,job['source'],job['source_sha256'],job['language'])
        async with store.lock(pid):
            p=store.load(pid,uid);p['edit_transcriptions'][job_id].update(state='completed',result=result)
            store.save(p,uid);store.event(p,'observation','edit_speech_recognized')
    except Exception:
        async with store.lock(pid):
            p=store.load(pid,uid);p['edit_transcriptions'][job_id].update(state='failed',error='口播识别未通过检查，原素材保留；没有重试或更换模型。')
            store.save(p,uid);store.event(p,'tool','edit_speech_failed')
    finally:store.RUNNING.pop(pid,None)
