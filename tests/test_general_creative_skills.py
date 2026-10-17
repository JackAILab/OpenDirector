import asyncio
import json
from harness.core.creative_skills import builtin_skills
from harness.agents.creative_policy import director_system, GENERAL_SYSTEM
from harness.agents import creative_director
from test_creative_studio import client


def test_general_recipe_snapshot_and_workspace_default(client):
    recipes={r['id']:r for r in builtin_skills()}
    assert recipes['ad-video']['output']=='15 秒有声广告、分镜与后期字幕'
    for sid in ('story-short','scene-mood','character-moment'):
        p=client.post('/creative/api/projects',json={'message':'动物在森林里相遇','skill_id':sid}).json()
        assert p['skill']['id']==sid and p['skill']['output']==recipes[sid]['output']
        assert p['approval_mode']=='manual' and not p.get('artifact')
    parent=client.post('/creative/api/projects',json={'message':'图片画布','creation_mode':'image'}).json()
    child=client.post('/creative/api/projects/'+parent['id']+'/director').json()
    assert child['skill_id']=='story-short'
    assert child['manual_parent']==parent['id']
    assert child['state']=='intake' and not child['shots']


def test_policy_uses_frozen_skill_not_title_or_untrusted_id():
    assert director_system({'skill_id':'story-short','skill':{'id':'ad-video','title':'短故事'}},'ad policy')=='ad policy'
    assert director_system({'skill':{'id':'story-short'}},'ad policy')==GENERAL_SYSTEM


def test_generic_policy_reaches_model_and_preserves_output_contract(monkeypatch):
    captured=[]
    async def complete(self,messages):
        captured.extend(messages)
        return {'reply':'森林相遇','brief':{'product':'猫与蝴蝶','cta':''},'questions':[],
                'shots':[{'title':'动作','prompt':'A cat follows a butterfly in a forest.','audio_prompt':'Forest ambience and soft music, no narration.','caption':'','rationale':'连续动作'} for _ in range(3)]}
    monkeypatch.setattr(creative_director.CreativeDirectorModel,'complete',complete)
    monkeypatch.setattr(creative_director,'compact',lambda:{})
    monkeypatch.setattr('harness.library.mechanism_report.build_mechanism_report',lambda summary:{})
    project={'duration':15,'provider':'kling','aspect':'16:9','messages':[{'role':'user','content':'猫在森林追蝴蝶，不要旁白'}], 'skill':{'id':'character-moment'},'generation_mode':'single_native'}
    result=asyncio.run(creative_director.direct(project,'plan'))
    assert captured[0]['content']==GENERAL_SYSTEM
    payload=json.loads(captured[1]['content']);assert payload['shot_count']==3
    assert result['brief']['cta']=='' and [s['start'] for s in result['shots']]==[0,5,10]
    assert all(s['caption']=='' and s['state']=='planned' for s in result['shots'])
