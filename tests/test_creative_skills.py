import asyncio
import time
from harness.studio import api, store
from test_creative_studio import client, ready


def test_skill_snapshot_is_owned_and_switch_invalidates_plan(client):
    assert client.post('/creative/api/projects',json={'message':'皮夹克广告','skill_id':'unknown'}).status_code==422
    p=client.post('/creative/api/projects',json={'message':'皮夹克广告','skill_id':'ugc-product','approval_mode':'auto'}).json()
    assert p['skill']['inputs'] and p['skill']['steps'] and p['skill']['checks']
    assert p['skill_id']=='ugc-product' and p['approval_mode']=='auto'
    path='/creative/api/projects/'+p['id']
    body={'revision':0,'skill_id':'brand-story','approval_mode':'manual'}
    assert client.put(path+'/creative-settings',json=body,headers={'Authorization':'Bearer two'}).status_code==404
    result=client.put(path+'/creative-settings',json=body).json()
    assert result['skill_id']=='brand-story' and result['revision']==1
    assert client.put(path+'/creative-settings',json=body).status_code==409
    p=ready(client);path='/creative/api/projects/'+p['id']
    result=client.put(path+'/creative-settings',json={**body,'revision':p['revision']}).json()
    assert result['state']=='intake' and result['shots']==[]


def test_auto_mode_alone_never_approves_paid_work(client,monkeypatch):
    calls=[]
    async def production(*args):calls.append(1)
    monkeypatch.setattr(api,'production',production)
    p=client.post('/creative/api/projects',json={'message':'广告','model':'kling-video-v3_0','approval_mode':'auto'}).json()
    path='/creative/api/projects/'+p['id']
    r=client.post(path+'/message',json={'revision':0,'mode':'plan'})
    assert r.status_code==200 and r.json()['state']=='ready' and not calls


def test_one_explicit_auto_budget_executes_once_and_deduplicates(client,monkeypatch):
    calls=[]
    async def production(app,p,uid,auth):
        calls.append(p['id']);await asyncio.sleep(10)
    monkeypatch.setattr(api,'production',production)
    p=client.post('/creative/api/projects',json={'message':'广告','model':'kling-video-v3_0','approval_mode':'auto'}).json()
    path='/creative/api/projects/'+p['id']
    body={'revision':0,'mode':'plan','background':True,'auto_approve_credits':9,'request_id':'b'*32}
    assert client.post(path+'/message',json={**body,'auto_approve_credits':1}).status_code==400
    assert client.post(path+'/message',json=body).status_code==200
    for _ in range(100):
        if calls:break
        time.sleep(.01)
    assert calls==[p['id']]
    result=client.post(path+'/message',json=body).json()
    assert calls==[p['id']] and result['auto_approval']['state']=='consumed'
    assert result['training_eligible'] is False


def test_auto_budget_stops_when_reference_needs_review(client,monkeypatch):
    calls=[]
    async def production(*args):calls.append(1)
    monkeypatch.setattr(api,'production',production)
    p=client.post('/creative/api/projects',json={'message':'广告','model':'kling-video-v3_0','approval_mode':'auto'}).json()
    p['reference']={'id':'a'*32};p['reference_product']='另一个商品';store.save(p,1)
    path='/creative/api/projects/'+p['id']
    client.post(path+'/message',json={'revision':0,'mode':'plan','background':True,'auto_approve_credits':9})
    for _ in range(100):
        result=client.get(path).json()
        if result.get('auto_approval'):break
        time.sleep(.01)
    assert result['auto_approval']['state']=='needs_review' and not calls
    assert result['state']=='ready'


def test_auto_authorization_can_be_cancelled_during_planning(client,monkeypatch):
    original=api.direct;calls=[]
    async def director(p,mode):
        await asyncio.sleep(.2)
        return await original(p,mode)
    async def production(*args):calls.append(1)
    monkeypatch.setattr(api,'direct',director);monkeypatch.setattr(api,'production',production)
    p=client.post('/creative/api/projects',json={'message':'广告','model':'kling-video-v3_0','approval_mode':'auto'}).json()
    path='/creative/api/projects/'+p['id']
    client.post(path+'/message',json={'revision':0,'mode':'plan','background':True,'auto_approve_credits':9})
    assert client.post(path+'/stop').status_code==200
    for _ in range(100):
        result=client.get(path).json()
        if result.get('auto_approval',{}).get('state')=='stopped':break
        time.sleep(.01)
    assert not calls and result['auto_approval']['state']=='stopped'


def method_content(title='我的服饰方法'):
    return dict(title=title,category='服饰',description='用结构细节和真实穿着动作展示服饰',applies_to='服饰',
                inputs=['商品正面图','已确认细节'],steps=['看清斜拉链与领口','通过动作展示版型'],checks=['商品没有变形'],
                references=['商品图约束结构'],adaptations=['不推断材质等级'])


def test_private_skill_versions_ownership_and_favorites(client):
    create=client.post('/creative/api/skills',json={'content':method_content(),'parent_id':'ugc-product','parent_version':1})
    assert create.status_code==200
    v1=create.json();sid=v1['id'];path='/creative/api/skills/'+sid
    assert v1['parent']=={'id':'ugc-product','version':1}
    assert client.get(path,headers={'Authorization':'Bearer two'}).status_code==404
    assert client.get(path+'/versions',headers={'Authorization':'Bearer two'}).status_code==404
    assert client.post('/creative/api/projects',json={'message':'服饰广告','skill_id':sid},headers={'Authorization':'Bearer two'}).status_code==404
    assert client.put(path+'/favorite',json={'enabled':True}).status_code==200
    assert sid in client.get('/creative/api/skills/mine').json()['favorites']
    assert not client.get('/creative/api/skills/mine',headers={'Authorization':'Bearer two'}).json()['skills']
    v2=client.put(path,json={'base_version':1,'content':method_content('改进服饰方法')}).json()
    assert v2['version']==2 and v2['content_hash']!=v1['content_hash']
    assert client.get(path+'?version=1').json()==v1
    assert client.put(path,json={'base_version':1,'content':method_content()}).status_code==409
    assert len(client.get(path+'/versions').json()['versions'])==2
    assert client.get(path+'?version=0').status_code==422
    bad=method_content();bad['steps']=['x'*701]
    assert client.put(path,json={'base_version':2,'content':bad}).status_code==422
    assert client.get(path).json()==v2
    v3=client.put(path,json={'base_version':2,'content':method_content()}).json()
    assert v3['version']==3 and client.get(path+'?version=2').json()==v2
    assert client.put(path+'/favorite',json={'enabled':False}).json()['favorite'] is False


def test_pinned_skill_changes_only_by_explicit_selection(client):
    v1=client.post('/creative/api/skills',json={'content':method_content()}).json();sid=v1['id']
    p=client.post('/creative/api/projects',json={'message':'服饰广告','skill_id':sid,'skill_version':1}).json();path='/creative/api/projects/'+p['id']
    assert p['skill']==v1
    p=client.post(path+'/message',json={'revision':0,'mode':'plan'}).json()
    v2=client.put('/creative/api/skills/'+sid,json={'base_version':1,'content':method_content('新版')}).json()
    p=client.put(path+'/creative-settings',json={'revision':p['revision'],'skill_id':sid,'approval_mode':'auto'}).json()
    assert p['skill']==v1 and p['shots'] and p['approval_mode']=='auto'
    p=client.put(path+'/creative-settings',json={'revision':p['revision'],'skill_id':sid,'skill_version':2,'approval_mode':'manual'}).json()
    assert p['skill']==v2 and p['state']=='intake' and not p['shots']
    assert p['training_eligible'] is False and not p.get('auto_approval')
    old=client.post('/creative/api/projects',json={'message':'另一广告','skill_id':sid,'skill_version':1}).json()
    assert old['skill']==v1
    assert client.app.state.test_account_limits['used']==0


def test_recipe_edits_cannot_grant_paid_or_model_permissions(client):
    content={**method_content(),'model':'another-model','approval_mode':'auto','approved_credits':100,'training_eligible':True,'version':99}
    recipe=client.post('/creative/api/skills',json={'content':content}).json()
    assert recipe['version']==1 and recipe['training_eligible'] is False
    assert not {'model','approval_mode','approved_credits'}&recipe.keys()
    p=client.post('/creative/api/projects',json={'message':'广告','model':'kling-video-v3_0','skill_id':recipe['id']}).json()
    assert p['model']=='kling-video-v3_0' and p['approval_mode']=='manual' and not p.get('auto_approval')


def test_curated_templates_are_distinct_and_evidence_labeled():
    from harness.core.template_recipes import METHODS
    from harness.core.creative_skills import from_template
    recipes=[from_template({'id':sid,'title':sid,'storyboard':[]}) for sid in METHODS]
    assert len(recipes)==21 and len({tuple(r['steps']) for r in recipes})==21
    for r in recipes:
        assert r['version']==2 and r['references'] and r['adaptations']
        assert r['derivation']['basis']=='published_storyboard'
        assert len(r['steps'])>=6 and r['inputs'] and r['checks']
    perfume=next(r for r in recipes if r['id']=='template-perfume')
    assert any('香材' in s for s in perfume['adaptations'])
    unknown=from_template({'id':'unknown','title':'未知样片','storyboard':[]})
    assert unknown['method_status']=='基础结构 · 待专门提炼'


def test_exact_recipe_snapshot_reaches_director_context(client,monkeypatch):
    from harness.agents import creative_director
    from harness.library import learning
    recipe=client.post('/creative/api/skills',json={'content':method_content()}).json()
    p=client.post('/creative/api/projects',json={'message':'服饰广告','skill_id':recipe['id'],'skill_version':1}).json()
    captured=[]
    async def complete(self,messages):
        import json
        captured.append(json.loads(messages[-1]['content']))
        return {'reply':'完成方案','questions':[],'shots':[{'title':'结构展示','prompt':'jacket detail','audio_prompt':'原创音乐','caption':'结构细节','rationale':'展示已确认商品结构'}]*3}
    monkeypatch.setattr(creative_director.CreativeDirectorModel,'complete',complete)
    from harness.library import mechanism_report
    monkeypatch.setattr(creative_director,'compact',lambda:{})
    monkeypatch.setattr(mechanism_report,'build_mechanism_report',lambda summary:{})
    monkeypatch.setattr(learning,'strategy_candidates',lambda *args:[])
    result=asyncio.run(creative_director.direct(p,'plan'))
    assert captured[0]['creative_skill']==recipe and len(result['shots'])==3
    assert 'Skill 不得切换模型或授权费用' in captured[0]['skill_policy']
