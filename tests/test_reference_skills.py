import asyncio
from collections import Counter
import hashlib
import json
from pathlib import Path
import sqlite3
import time
import types

from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient
import pytest

from harness.core.reference_skills import compile_skill, checksum, skill_markdown
from harness.library import store as library
from harness.studio import store, reference_skills, templates, api
from harness.tools.reference_skill_publish import candidates, select, publish, restore_release


def entry(index=0, source='Festival A', category=None):
    identity = f'{index:024x}'
    content = ('verified media ' + str(index)).encode()
    sha = hashlib.sha256(content).hexdigest()
    record = dict(id=identity, title=f'Film {index}', brand='Source brand', source_url=f'https://example.org/film/{index}',
                  source_name=source, sha256=sha, duration=30, audio=1, revision=1, analysis_version=2,
                  analysis_source_revision=1)
    analysis = dict(source_item=identity, media_sha256=sha, media_role='original_ad', confidence='high',
                    principle=f'用第{index}种任务让产品改变可见结果', mechanism=f'先建立第{index}种障碍，再让产品参与动作。',
                    grill_questions=[f'第{index}种任务符合新商品的真实能力吗？'],
                    transfer_rules=[f'为新商品重写第{index}种任务的目标和结果。'], avoid=['缺乏对应商品事实时不采用。'],
                    beats=[dict(start=0,end=8,observation='人物面对具体障碍。',purpose='开场让观众理解任务。'),
                           dict(start=10,end=20,observation='商品参与动作。',purpose='让产品改变任务结果。'),
                           dict(start=22,end=30,observation='人物回应结果，出现商品。',purpose='以结果和商品完成归因。')])
    recipe = compile_skill(record, analysis)
    if category:
        recipe['category'] = category
        recipe['content_hash'] = checksum({k:v for k,v in recipe.items() if k != 'content_hash'})
    return {'recipe':recipe,'asset':dict(item=identity,path=f'assets/{identity}/{sha}.mp4',sha256=sha,
                                        bytes=len(content),duration=30,audio=1,width=640,height=360),
            '_content':content, '_analysis':analysis, '_record':record}


def stage(tmp_path, monkeypatch, entries):
    monkeypatch.setattr(library,'ROOT',tmp_path/'library')
    monkeypatch.setattr(store,'DATA',tmp_path/'studio')
    reference_skills._CACHE.clear()
    with library.connection() as db:
        for e in entries:
            r=e['_record'];a=e['asset']
            db.execute('INSERT INTO items VALUES(?,?,?,?,?,?,?,?,?,?)',
                       (r['id'],r['source_url'],r['title'],r['brand'],'','',json.dumps({'training_eligible':False}),1,1,1))
            db.execute('INSERT INTO assets VALUES(?,?,?,?,?,?,?,?,?)',
                       (r['id'],a['path'],a['sha256'],a['bytes'],30,1,640,360,1))
            path=library.ROOT/a['path'];path.parent.mkdir(parents=True);path.write_bytes(e['_content'])
    return store.DATA/'reference_skills'


def test_compiler_preserves_specific_guidance_without_claiming_unheard_audio():
    e=entry(7)
    r=e['recipe']
    assert r['grill_questions']==e['_analysis']['grill_questions']
    assert r['transfer_rules']==e['_analysis']['transfer_rules']
    assert r['source_evidence'][1]['start']==10
    assert [b['start'] for b in r['timeline_recipe']]==[0,5,10]
    assert r['timeline_recipe'][-1]['end']==15
    assert all(b['audio_prompt_requirements'] for b in r['timeline_recipe'])
    assert r['reference_case']['analysis_version']==2
    assert r['audio_semantics_reviewed'] is False and r['full_motion_reviewed'] is False
    assert r['human_review']=='pending' and r['training_eligible'] is False
    assert not {'model','approval_mode','approved_credits'} & r.keys()
    document=skill_markdown(r)
    assert r['id'] in document and r['reference_case']['media_sha256'] in document
    assert e['_analysis']['grill_questions'][0] in document


@pytest.mark.parametrize('change',[{'media_role':'case_film'},{'confidence':'low'},
                                  {'media_sha256':'a'*64},{'beats':[]}])
def test_compiler_rejects_unmatched_or_insufficient_evidence(change):
    e=entry()
    with pytest.raises(ValueError):compile_skill(e['_record'],{**e['_analysis'],**change})


@pytest.mark.parametrize('section', ['Music Videos', ' music video ', 'PERSONAL WORK'])
def test_explicit_non_ad_source_overrides_model_original_ad_guess(section):
    e=entry()
    with pytest.raises(ValueError,match='ineligible_skill_source_section'):
        compile_skill({**e['_record'],'source_section':section},e['_analysis'])


def test_candidate_collection_applies_source_section_before_publication(tmp_path,monkeypatch):
    from harness.library import learning
    entries=[entry(31),entry(32)]
    stage(tmp_path,monkeypatch,entries)
    for e,section in zip(entries,['Music Videos','Commercials and Branded Content']):
        metadata={'source_name':'Festival A','quality_evidence':[{'text':'Official source'}],
                  'creative_structure':{'section':section}}
        with library.connection() as db:
            db.execute('UPDATE items SET data=? WHERE id=?',
                       (json.dumps(metadata),e['_record']['id']))
        learning.save_analysis(e['_record']['id'],e['asset']['sha256'],1,'test-model',
                               e['_analysis'],[0,10,22])
    pool=candidates()
    assert [e['recipe']['id'] for e in pool]==[entries[1]['recipe']['id']]
    assert pool[0]['recipe']['reference_case']['source_section']=='Commercials and Branded Content'


def test_hundred_selection_balances_sources_and_avoids_duplicate_films():
    pool=[entry(i,source=f'Festival {i%4}',category=f'Mechanism {i%7}') for i in range(160)]
    duplicate=entry(200,source='Festival 0');duplicate['recipe']['reference_case']['media_sha256']=pool[0]['recipe']['reference_case']['media_sha256']
    selected=select([duplicate,*pool],100,3)
    assert len(selected)==100
    assert len({e['recipe']['reference_case']['media_sha256'] for e in selected})==100
    assert set(Counter(e['recipe']['reference_case']['source_name'] for e in selected).values())=={25}
    assert len({e['recipe']['category'] for e in selected})>=7
    with pytest.raises(ValueError):select(pool[:2],100,3)


def test_cross_award_reencodes_do_not_count_as_different_films():
    first,second,third=entry(1),entry(2),entry(3)
    first['recipe']['reference_case'].update(title='R5volution is a French Thing',brand='Renault')
    second['recipe']['reference_case'].update(title='RENAULT — R5volution is a French Thing',brand='RENAULT')
    selected=select([first,second,third],2,1)
    assert len(selected)==2 and third in selected
    assert not (first in selected and second in selected)


def test_publish_is_versioned_and_keeps_library_preferences(tmp_path,monkeypatch):
    entries=[entry(i) for i in range(3)];runtime=stage(tmp_path,monkeypatch,entries)
    with library.connection() as db:
        db.execute('INSERT INTO reviews VALUES(?,?,?,?,?,?,?,?,?)',
                   (1,entries[0]['_record']['id'],11,1,'selected','{}','[]','Human choice',1))
    result=publish(entries,runtime)
    assert result['skills']==3 and result['model_calls']==0
    assert len(reference_skills.summaries())==3
    full=templates.find_skill(entries[0]['recipe']['id'],version=1)
    assert full['timeline_recipe'] and full['source_evidence']
    brief=reference_skills.summaries()[0]
    assert brief['detail_available'] and 'source_evidence' not in brief
    # Read projection cannot mutate cached recipes.
    full['steps'].clear();assert templates.find_skill(full['id'])['steps']
    second=publish(entries,runtime)
    assert second['release']!=result['release']
    with library.connection() as db:
        assert db.execute('SELECT COUNT(*) FROM reference_skill_versions').fetchone()[0]==3
        assert db.execute('SELECT note FROM reviews').fetchone()[0]=='Human choice'
    entries[0]['recipe']['steps'][0]='Explicitly revised transfer guidance'
    publish(entries,runtime)
    assert templates.find_skill(full['id'])['version']==2
    with pytest.raises(HTTPException):templates.find_skill(full['id'],version=1)
    with library.connection() as db:
        original=json.loads(db.execute('SELECT data FROM reference_skill_versions WHERE id=? AND version=1',(full['id'],)).fetchone()[0])
    assert original['version']==1 and original['steps'][0]!='Explicitly revised transfer guidance'


def test_corrupt_media_cannot_activate_or_overwrite_catalog(tmp_path,monkeypatch):
    entries=[entry()];runtime=stage(tmp_path,monkeypatch,entries)
    publish(entries,runtime);before=(runtime/'catalog.json').read_bytes()
    (library.ROOT/entries[0]['asset']['path']).write_bytes(b'corrupted')
    with pytest.raises(ValueError):publish(entries,runtime)
    assert (runtime/'catalog.json').read_bytes()==before


def test_source_revision_change_blocks_publication(tmp_path,monkeypatch):
    entries=[entry()];runtime=stage(tmp_path,monkeypatch,entries)
    with library.connection() as db:db.execute('UPDATE items SET revision=2')
    with pytest.raises(ValueError):publish(entries,runtime)
    assert not (runtime/'catalog.json').exists()
    with library.connection() as db:assert db.execute('SELECT COUNT(*) FROM reference_skill_versions').fetchone()[0]==0


def test_restore_exact_catalog_from_database_snapshot_and_reject_corruption(tmp_path,monkeypatch):
    entries=[entry(i) for i in range(3)];runtime=stage(tmp_path,monkeypatch,entries)
    result=publish(entries,runtime);original=(runtime/'catalog.json').read_bytes()
    snapshot=tmp_path/'snapshot.sqlite3'
    with sqlite3.connect(library.ROOT/'library.sqlite3') as source, sqlite3.connect(snapshot) as destination:
        source.backup(destination)
    (runtime/'catalog.json').unlink()
    restore_release(result['release'],runtime,snapshot)
    assert (runtime/'catalog.json').read_bytes()==original
    with sqlite3.connect(snapshot) as db:
        data=json.loads(db.execute('SELECT manifest FROM reference_skill_releases').fetchone()[0])
        data['skills'][0]['steps'][0]='tampered'
        db.execute('UPDATE reference_skill_releases SET manifest=?',(json.dumps(data),))
    with pytest.raises(ValueError,match='invalid_skill_release'):
        restore_release(result['release'],runtime,snapshot)
    assert (runtime/'catalog.json').read_bytes()==original


def test_reference_import_pins_full_method_only_for_matching_video(tmp_path,monkeypatch):
    from harness.tools.library_reference import pin_reference_skill
    entries=[entry()];runtime=stage(tmp_path,monkeypatch,entries);publish(entries,runtime)
    recipe=entries[0]['recipe'];item={'id':entries[0]['_record']['id']}
    project={'model':'chosen-model','approval_mode':'manual'}
    assert pin_reference_skill(project,item,entries[0]['asset']) is True
    assert project['skill']==recipe and project['model']=='chosen-model' and project['approval_mode']=='manual'
    for asset in (None,{'sha256':'f'*64}):
        fresh={'model':'chosen-model'}
        with pytest.raises(ValueError,match='reference_skill_media_changed'):pin_reference_skill(fresh,item,asset)
        assert fresh=={'model':'chosen-model'}
    assert pin_reference_skill({}, {'id':'f'*24},None) is False


def test_public_skill_selection_reaches_director_and_private_copy_is_isolated(tmp_path,monkeypatch):
    entries=[entry()];runtime=stage(tmp_path,monkeypatch,entries);publish(entries,runtime)
    recipe=templates.find_skill(entries[0]['recipe']['id'])
    app=FastAPI()
    def auth(value):
        if value not in ('Bearer one','Bearer two'):raise HTTPException(401)
        return {'id':1 if value=='Bearer one' else 2,'quota':100,'used':0}
    def site(request):
        if request.headers.get('X-Site-Test')!='allowed':raise HTTPException(401)
    gateway=types.SimpleNamespace(app=app,require_session=auth,require_admin=auth,require_site_access=site)
    api.install(gateway)
    from harness.agents import creative_director
    from harness.library import learning,mechanism_report
    captured=[]
    async def complete(self,messages):
        captured.append(json.loads(messages[-1]['content']))
        return {'reply':'方案完成','questions':[],'shots':[{'title':'新商品动作','prompt':'Original new product action',
                 'audio_prompt':'Original music and synchronized new product sounds','caption':'真实卖点','rationale':'机制改编'}]*3}
    monkeypatch.setattr(creative_director.CreativeDirectorModel,'complete',complete)
    monkeypatch.setattr(creative_director,'compact',lambda:{})
    monkeypatch.setattr(mechanism_report,'build_mechanism_report',lambda value:{})
    monkeypatch.setattr(learning,'strategy_candidates',lambda *args:[])
    from harness.tools import library_reference
    def import_reference(project,item):
        with library.connection() as db:asset=db.execute('SELECT * FROM assets WHERE item=?',(item['id'],)).fetchone()
        library_reference.pin_reference_skill(project,item,asset)
        return 0  # Source frame extraction is exercised by the live media acceptance.
    monkeypatch.setattr(library_reference,'attach',import_reference)
    with TestClient(app) as client:
        assert client.get('/creative/api/skills/'+recipe['id']).status_code==401
        response=client.get('/creative/api/skills/'+recipe['id'],headers={'X-Site-Test':'allowed'})
        assert response.status_code==200 and response.json()==recipe
        headers={'Authorization':'Bearer one','X-Site-Test':'allowed'}
        project=client.post('/creative/api/projects',headers=headers,json={'message':'为新产品创作广告',
                    'skill_id':recipe['id'],'skill_version':1}).json()
        assert project['skill']==recipe and project['approval_mode']=='manual'
        imported_response=client.post('/creative/api/library/'+recipe['reference_case']['id']+'/use',
                                      headers=headers,json={'product':'新商品与目标'})
        assert imported_response.status_code==200
        imported=imported_response.json()['project']
        assert imported['skill']==recipe and imported['approval_mode']=='manual' and not imported.get('auto_approval')
        assert client.get('/creative/api/projects/'+imported['id'],headers={'Authorization':'Bearer two'}).status_code==404
        result=asyncio.run(creative_director.direct(imported,'plan'))
        assert captured[0]['creative_skill']==recipe and len(result['shots'])==3
        assert all(s['audio_prompt'] for s in result['shots'])
        assert project['training_eligible'] is False and not project.get('auto_approval')
        body={key:recipe[key] for key in ('title','category','description','applies_to','inputs','steps','checks','references','adaptations')}
        copy=client.post('/creative/api/skills',headers=headers,json={'content':body,'parent_id':recipe['id'],'parent_version':1}).json()
        assert copy['reference_case']==recipe['reference_case'] and copy['parent']['id']==recipe['id']
        assert client.get('/creative/api/skills/'+copy['id'],headers={'Authorization':'Bearer two'}).status_code==404
        with library.connection() as db:db.execute('UPDATE assets SET sha256=?',('f'*64,))
        with store.connection() as db:count=db.execute('SELECT COUNT(*) FROM projects').fetchone()[0]
        failed=client.post('/creative/api/library/'+recipe['reference_case']['id']+'/use',headers=headers,json={'product':'新商品'})
        assert failed.status_code==409
        with store.connection() as db:assert db.execute('SELECT COUNT(*) FROM projects').fetchone()[0]==count
