"""Isolated CPU worker: bounded audio has already been extracted by the Tool."""
import json
import sys
from faster_whisper import WhisperModel

if __name__=='__main__':
    wav,model_path,language=sys.argv[1:]
    model=WhisperModel(model_path,local_files_only=True,device='cpu',compute_type='int8',cpu_threads=2,num_workers=1)
    segments,info=model.transcribe(wav,language=None if language=='auto' else language,task='transcribe',
        beam_size=3,temperature=0,word_timestamps=True,vad_filter=True,condition_on_previous_text=False)
    result={'language':info.language,'language_probability':info.language_probability,'segments':[]}
    for segment in segments:
        if len(result['segments'])>=500: raise ValueError('Too many speech segments')
        result['segments'].append({'start':segment.start,'end':segment.end,'text':segment.text,
            'words':[{'start':w.start,'end':w.end,'text':w.word,'probability':w.probability} for w in segment.words or []]})
    print(json.dumps(result,ensure_ascii=False))
