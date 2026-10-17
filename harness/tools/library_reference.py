"""Import three owned reference frames; source video is never a generation condition."""
import json
from pathlib import Path
import subprocess
import tempfile
from harness.library import store as library
from harness.tools.creative_canvas import save_asset


def pin_reference_skill(project,item,asset):
    """Bind the published case method only to its exact registered video."""
    from harness.studio.reference_skills import find
    skill=find('reference-'+item['id'])
    if not skill:return False
    case=skill['reference_case']
    if not asset or case['id']!=item['id'] or case['media_sha256']!=asset['sha256']:
        raise ValueError('reference_skill_media_changed')
    project.update(skill_id=skill['id'],skill_title=skill['title'],skill=skill)
    return True


def attach(project,item):
    with library.connection() as c:asset=c.execute('SELECT * FROM assets WHERE item=?',(item['id'],)).fetchone()
    pin_reference_skill(project,item,asset)
    notes={'source':item['source_url'],'title':item['title'],'classification':item.get('ad_type'),
           'evidence':[{'kind':e.get('kind'),'text':e.get('text','')[:180]} for e in item.get('quality_evidence',[])[:3]],
           'my_preference':{**item['review'],'note':item['review'].get('note','')[:500]},
           'limitations':('参考案例的品牌与文案不能移植到新商品。采样画面供理解构图；未分析原片声音和精确运镜。' if asset else
                           '当前仅带入官网来源、基础信息和用户标注，没有原片、采样画面或影片内容分析。不能依据片名编造镜头、声音、创意机制或广告效果；须先观看核实或由用户补充。原品牌事实与文案不能移植到新商品。')}
    from harness.library.learning import get_analysis
    analysis=get_analysis(item['id'])
    if analysis:
        notes['learning_strategy']={'principle':analysis['principle'],'mechanism':analysis['mechanism'][:650],
            'grill_questions':analysis['grill_questions'][:3],'transfer_rules':analysis['transfer_rules'][:3],
            'avoid':analysis['avoid'][:2],'evidence_scope':analysis['evidence_scope'],'human_review':analysis['human_review']}
        notes['limitations']+=' 策略由采样证据推断，尚待人工审阅；不是原作者思维链或已验证训练数据。'
        project['library_learning']={'source_item':item['id'],'media_sha256':analysis['media_sha256'],'analysis_version':analysis['analysis_version'],'human_review':analysis['human_review'],'training_eligible':False}
    text=json.dumps(notes,ensure_ascii=False)
    if len(text)>3800:
        notes['evidence']=[]
        notes['my_preference']['note']=notes['my_preference']['note'][:200]
        strategy=notes.get('learning_strategy',{})
        for field in ('grill_questions','transfer_rules','avoid'):
            if field in strategy:strategy[field]=[v[:180] for v in strategy[field][:2]]
        text=json.dumps(notes,ensure_ascii=False)
    if len(text)>4000:raise ValueError('reference_notes_limit')
    graph={'nodes':[{'id':'library-notes','kind':'text','label':'广告案例与我的偏好','text':text,'x':35,'y':30}],
           'edges':[{'source':'library-notes','target':'director'}]}
    project.update(canvas=graph,canvas_assets={})
    if not asset:return 0
    source=(library.ROOT/asset['path']).resolve()
    if not source.is_relative_to((library.ROOT/'assets').resolve()):raise ValueError('invalid_source')
    count=0
    with tempfile.TemporaryDirectory(prefix='ad-reference-') as tmp:
        for i,fraction in enumerate((.15,.5,.85)):
            path=Path(tmp)/f'frame-{i}.jpg'
            subprocess.run(['/opt/visualstation/creative-runtime/bin/ffmpeg','-nostdin','-v','error','-ss',str(asset['duration']*fraction),'-i',str(source),'-vf','scale=960:-2','-frames:v','1',str(path)],check=True,timeout=30,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
            image=save_asset(project,path.read_bytes(),'image');project['canvas_assets'][image['id']]=image
            node=f'library-frame-{i}'
            graph['nodes'].append({'id':node,'kind':'image','asset':image['id'],'label':f'原片 {round(fraction*100)}% 采样画面','text':'只借鉴镜头构图与视觉语言，不复制原品牌、人物身份或商品外观。','x':35+i*320,'y':260})
            graph['edges'].append({'source':node,'target':'director'});count+=1
    return count
