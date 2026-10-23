import asyncio
import json
from contextlib import asynccontextmanager
import httpx
import pytest
from harness.models.creative_director import CreativeDirectorModel, PlanningResponseError, public_decisions


def test_incremental_public_decisions_only():
    prefix=json.dumps({'reply':'quoted "decisions": [{"title":"fake"}]','brief':{}})[:-1]+',"decisions":['
    first={'title':'商品外观','reason':'使用已上传商品图'}
    assert public_decisions(prefix+json.dumps(first)+',{"title":"still')==[first]
    assert public_decisions('{"reasoning":"private"')==[]
    assert public_decisions('{"decisions":[{"title":"incomplete"')==[]


@pytest.mark.parametrize('finish,expected',[('stop',None),('length','output_truncated'),(None,'response_content')])
def test_stream_callback_before_completion_without_reasoning(monkeypatch,tmp_path,finish,expected):
    key=tmp_path/'key';key.write_text('test-key')
    monkeypatch.setenv('CREATIVE_MODEL_KEY_FILE',str(key));monkeypatch.setenv('CREATIVE_MODEL_URL','https://example.invalid')
    seen=[];requests=[]
    data={'reply':'摘要','decisions':[{'title':'外观保持','reason':'使用商品参考'}],'shots':[]}
    text=json.dumps(data,ensure_ascii=False);cut=text.index(', "shots"')
    class Response:
        is_success=True
        async def aiter_lines(self):
            yield 'data: '+json.dumps({'choices':[{'delta':{'reasoning_content':'private chain','content':text[:cut]}}]})
            assert seen==data['decisions']
            yield 'data: '+json.dumps({'choices':[{'delta':{'content':text[cut:]},'finish_reason':finish}]})
            yield 'data: [DONE]'
    @asynccontextmanager
    async def stream(self,*args,**kwargs):
        requests.append(kwargs['json']);yield Response()
    monkeypatch.setattr(httpx.AsyncClient,'stream',stream)
    if expected:
        with pytest.raises(PlanningResponseError) as exc:asyncio.run(CreativeDirectorModel().complete([],seen.append))
        assert str(exc.value)==expected
    else: assert asyncio.run(CreativeDirectorModel().complete([],seen.append))==data
    assert len(requests)==1 and requests[0]['stream'] is True
    assert 'private' not in str(seen)


def test_planner_saves_progress_and_retains_stop(monkeypatch,tmp_path):
    from harness.studio import store
    from harness.core.creative_planner import plan
    monkeypatch.setattr(store,'DATA',tmp_path)
    p=dict(id='f'*24,revision=2,state='planning',duration=15,brief={},messages=[],shots=[],canvas_assets={},canvas={'nodes':[],'edges':[]})
    store.save(p,1)
    async def director(project,mode,on_activity=None):
        on_activity('references',None)
        on_activity('decision',{'title':'外观','reason':'沿用上传的图片'})
        live=store.load(p['id'],1)
        assert live['planning_activity']['state']=='running'
        assert live['planning_activity']['decisions'][0]['title']=='外观'
        live['stop_requested']=True;store.save(live,1)
        on_activity('validating')
        assert store.load(p['id'],1)['stop_requested'] is True
        raise RuntimeError('private exception')
    asyncio.run(plan(p,1,'plan',director))
    result=store.load(p['id'],1)
    assert result['planning_activity']['state']=='failed'
    assert result['stop_requested'] is True
    assert 'private exception' not in json.dumps(result)
