"""Verified provider IDs and platform-credit policy, never provider credentials.

Capabilities checked with Kling who_am_i on 2026-10-16. Credits are the site's
own tariff, not a claim about Kling inspiration values or a currency price.
"""
import math

MODELS = (
    {'id':'kling-video-v4_0','provider':'kling','label':'Kling 4.0 · 全能参考','credits_per_5s':4,'audio':True,'single_film':True,'billing_note':'供应商按秒计费；视频参考时长也计费。本入口暂支持文字与图片参考。'},
    {'id':'kling-video-v3_0','provider':'kling','label':'Kling 3.0','credits_per_5s':3,'audio':True,'single_film':True},
    {'id':'kling-video-v3_0_omni','provider':'kling','label':'Kling O3','credits_per_5s':4,'audio':True,'single_film':True},
    {'id':'kling-video-v2_5','provider':'kling','label':'Kling 2.5','credits_per_5s':2,'audio':False,'single_film':False,'limitation':'单次最长 10 秒，不适用于 15 秒有声整片'},
    {'id':'kling-video-v3_0_turbo','provider':'kling','label':'Kling 3.0 Turbo','credits_per_5s':3,'audio':False,'single_film':False,'limitation':'手动工作台可用；不适用于 Agent 有声整片'},
    {'id':'kling-video-v2_6','provider':'kling','label':'Kling 2.6','credits_per_5s':2,'audio':True,'single_film':False,'limitation':'单次最长 10 秒；手动工作台可用；不适用于 Agent 有声整片'},
    {'id':'kling-video-o1','provider':'kling','label':'Kling O1','credits_per_5s':3,'audio':False,'single_film':False,'limitation':'单次最长 10 秒；手动工作台可用；不适用于 Agent 有声整片'},
    {'id':'MiniMax-H3','provider':'minimax-h3','label':'MiniMax H3','credits_per_5s':1,'audio':True,'single_film':False,'limitation':'15 秒有声整片路径待验证'},
)
# Independent manual generation is not constrained by the Agent's 15s film brief.
MANUAL_DURATIONS = {
    'kling-video-v4_0': tuple(range(3,31)),
    'kling-video-v3_0': tuple(range(3,16)),
    'kling-video-v3_0_omni': tuple(range(3,16)),
    'kling-video-v3_0_turbo': tuple(range(3,16)),
    'kling-video-o1': tuple(range(3,11)),
    'kling-video-v2_5': (5,10), 'kling-video-v2_6': (5,10),
}
MODELS = tuple(dict(m,manual_available=m['id'] in MANUAL_DURATIONS,
                   manual_durations=MANUAL_DURATIONS.get(m['id'],())) for m in MODELS)

DEFAULTS = {'kling':'kling-video-v4_0','minimax-h3':'MiniMax-H3'}

# Display-only entries have no provider adapter and can never pass model_spec.
PENDING_MODELS = tuple({'id':identifier,'label':label,'available':False,'single_film':False,
                       'limitation':'尚未接入','capability_status':'unsupported','service_status':'unavailable'}
                      for identifier,label in [('seedance-2.5','Seedance 2.5'),
                          ('seedance-2.0','Seedance 2.0'),('wan-3.0','Wan 3.0'),
                          ('wan-3.0-prime','Wan 3.0 Prime'),('vidu-q4','Vidu Q4 Preview'),
                          ('minimax-h3-max','MiniMax H3 Max')])


def model_spec(provider, model=None):
    model = model or DEFAULTS.get(provider)
    for spec in MODELS:
        if spec['id']==model and spec['provider']==provider:
            return dict(spec)
    raise ValueError('所选模型未接入，或与视频服务不匹配')


def quote(provider, model, duration):
    spec=model_spec(provider,model)
    if type(duration) is not int or not 3<=duration<=30:
        raise ValueError('镜头时长不受支持')
    if spec['id'] in MANUAL_DURATIONS and duration not in MANUAL_DURATIONS[spec['id']]:
        raise ValueError('时长超出所选模型范围')
    if provider=='minimax-h3' and duration<4:
        raise ValueError('MiniMax H3 镜头至少 4 秒')
    return spec['credits_per_5s']*math.ceil(duration/5)


def project_quote(project):
    spec=model_spec(project['provider'],project.get('model'))
    if project.get('generation_mode')=='single_native':
        credits=0 if not project.get('shots') or project.get('film',{}).get('job_id') else quote(project['provider'],spec['id'],project['duration'])
        return {'model':spec['id'],'label':spec['label'],'audio':spec['audio'],'credits_per_5s':spec['credits_per_5s'],'new_shots':int(credits>0),'new_jobs':int(credits>0),'credits':credits,'policy':'single-native-v1'}
    remaining=[s for s in project['shots'] if not s.get('job_id')]
    return {'model':spec['id'],'label':spec['label'], 'audio':spec['audio'],
            'credits_per_5s':spec['credits_per_5s'],
            'new_shots':len(remaining),
            'credits':sum(quote(project['provider'],spec['id'],s['duration']) for s in remaining),
            'policy':'platform-v1'}
