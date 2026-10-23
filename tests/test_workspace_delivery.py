"""No browser or model calls: durable owned-result delivery and ancestry."""
import asyncio
import io
import json
import pytest
from PIL import Image
from harness.studio import store
from harness.core import creative_workspace_delivery as delivery
from harness.tools.creative_canvas import save_asset,asset_directory
from harness.tools.canvas_lineage import lineage


@pytest.fixture
def projects(tmp_path,monkeypatch):
    monkeypatch.setattr(store,'DATA',tmp_path);store.LOCKS.clear();store.RUNNING.clear()
    parent=dict(id='a'*24,creation_mode='video',revision=1,state='ready',manual_nodes=[{'project':'b'*24}],canvas={'nodes':[],'edges':[]},canvas_assets={},direct_prompt='original prompt')
    child=dict(id='b'*24,creation_mode='agent',manual_parent=parent['id'],revision=1,state='intake',canvas={'nodes':[],'edges':[]},canvas_assets={})
    store.save(parent,1);store.save(child,1)
    yield parent,child
    store.LOCKS.clear();store.RUNNING.clear()


def image(p,color,sources=()):
    raw=io.BytesIO();Image.new('RGB',(256,256),color).save(raw,'PNG')
    asset=save_asset(p,raw.getvalue(),'image');asset['provenance']={'kind':'image_generated','sources':list(sources),'training_eligible':False}
    p['canvas_assets'][asset['id']]=asset
    p['canvas']['nodes'].append(dict(id='n'+asset['id'],kind='image',asset=asset['id'],label='参考素材',text='',role='style',x=40,y=40))
    return asset['id']


def queue_image(child):
    source=image(child,'red');result=image(child,'blue',[source]);child['image_task']={'state':'completed','asset':result};store.save(child,1)
    return source,result


def rows():
    with store.connection() as c:return c.execute('SELECT asset,state,code FROM workspace_deliveries ORDER BY asset').fetchall()


def run():return asyncio.run(delivery.drain())


def test_closed_browser_delivers_result_and_ancestry_once(projects):
    parent,child=projects;source,result=queue_image(child)
    assert rows()==[(result,'pending','')]
    assert run()==1
    saved=store.load(parent['id'],1)
    assert saved['revision']==2 and saved['direct_prompt']==parent['direct_prompt']
    assert {n['asset'] for n in saved['canvas']['nodes']}=={source,result}
    assert saved['canvas']['edges']==[]  # provenance, not new generation inputs
    assert lineage(saved)[result]['sources']==[source]
    assert asset_directory(saved,result).joinpath(saved['canvas_assets'][result]['filename']).is_file()
    position=next(n for n in saved['canvas']['nodes'] if n['asset']==result);position['x']=900
    store.save(saved,1);store.save(child,1)
    assert run()==0 and rows()==[(result,'delivered','')]
    assert next(n for n in store.load(parent['id'],1)['canvas']['nodes'] if n['asset']==result)['x']==900


def test_parent_busy_is_deferred_and_survives_worker_restart(projects):
    parent,child=projects;_,result=queue_image(child)
    parent['state']='running';store.save(parent,1)
    assert run()==0 and rows()==[(result,'pending','workspace_busy')]
    assert store.load(parent['id'],1)['canvas']['nodes']==[]
    parent['state']='ready';store.save(parent,1)
    with store.connection() as c:c.execute('UPDATE workspace_deliveries SET next_attempt=0')
    store.LOCKS.clear()  # a fresh process has no in-memory scheduling state
    assert run()==1
    assert rows()==[(result,'delivered','')]


def test_capacity_failure_preserves_output_and_can_retry_without_generation(projects):
    parent,child=projects;_,result=queue_image(child)
    parent['canvas']['nodes']=[dict(id='t'+str(i),kind='text',text='keep',label='note',role='reference',x=i*10,y=0) for i in range(16)];store.save(parent,1)
    assert run()==0 and rows()==[(result,'needs_review','workspace_inputs_or_capacity')]
    assert child['canvas_assets'][result]==store.load(child['id'],1)['canvas_assets'][result]
    parent['canvas']['nodes']=[];store.save(parent,1)
    with store.connection() as c:c.execute("UPDATE workspace_deliveries SET state='pending',next_attempt=0")
    assert run()==1


def test_cross_owner_delivery_never_copies_files(projects):
    parent,child=projects
    with store.connection() as c:c.execute('UPDATE projects SET owner=2 WHERE id=?',(parent['id'],))
    _,result=queue_image(child)
    assert run()==0 and rows()==[(result,'needs_review','workspace_missing')]
    assert not asset_directory(parent,result).exists()


def test_edit_while_copying_is_not_overwritten(projects,monkeypatch):
    parent,child=projects;_,result=queue_image(child);original=delivery.import_assets
    def concurrent_edit(p,c,ids):
        changed=original(p,c,ids)
        edit=store.load(parent['id'],1);edit['direct_prompt']='concurrent user change';edit['revision']+=1;store.save(edit,1)
        return changed
    monkeypatch.setattr(delivery,'import_assets',concurrent_edit)
    assert run()==0 and rows()==[(result,'pending','workspace_changed')]
    assert store.load(parent['id'],1)['direct_prompt']=='concurrent user change'
    monkeypatch.setattr(delivery,'import_assets',original)
    with store.connection() as c:c.execute('UPDATE workspace_deliveries SET next_attempt=0')
    assert run()==1 and store.load(parent['id'],1)['direct_prompt']=='concurrent user change'


def test_each_completed_chapter_queues_before_final_render(projects):
    _,child=projects;source=image(child,'red');chapter=image(child,'blue',[source]);tail=image(child,'green',[chapter])
    child['state']='running';child['campaign']={'chapters':[{'state':'completed','asset':chapter,'tail_asset':tail},{'state':'generating'}]}
    store.save(child,1)
    assert {r[0] for r in rows()}=={chapter,tail}
    assert run()==2
    assert all(r[1]=='delivered' for r in rows())


def test_source_cycle_is_rejected_without_parent_changes(projects):
    parent,child=projects;source,result=queue_image(child)
    child['canvas_assets'][source]['provenance']['sources']=[result];store.save(child,1)
    assert run()==0
    assert store.load(parent['id'],1)['canvas']==parent['canvas']


def test_service_lifespan_delivers_saved_work_and_preserves_host_lifecycle(projects):
    from contextlib import asynccontextmanager
    from fastapi import FastAPI
    parent,child=projects;_,result=queue_image(child);events=[]
    @asynccontextmanager
    async def host(app):
        events.append('start')
        yield {'host':'preserved'}
        events.append('stop')
    app=FastAPI(lifespan=host);delivery.install(app)
    async def exercise():
        async with app.router.lifespan_context(app) as state:
            assert state=={'host':'preserved'}
            for _ in range(100):
                if rows()==[(result,'delivered','')]:break
                await asyncio.sleep(.02)
            assert rows()==[(result,'delivered','')]
            assert store.load(parent['id'],1)['canvas']['nodes']
        assert app.state.workspace_delivery_task.done()
    asyncio.run(exercise())
    assert events==['start','stop']


def test_final_result_requires_current_completed_artifact(projects):
    _,child=projects;result=image(child,'blue')
    child.update(state='completed',result_asset=result,artifact='current',result_artifact='old')
    store.save(child,1);assert rows()==[]
    child['result_artifact']='current';store.save(child,1)
    assert rows()==[(result,'pending','')]
    assert run()==1
