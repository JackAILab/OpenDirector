import asyncio
import httpx
import pytest
from harness.models.creative_director import CreativeDirectorModel, PlanningResponseError
from harness.core.creative_planner import failure_code

@pytest.mark.parametrize('payload,code', [
    ({'choices':[{'finish_reason':'length','message':{'content':'private'}}]},'output_truncated'),
    ({'choices':[]},'response_envelope'),
    ({'choices':[{'message':{'content':None}}]},'response_content'),
    ({'choices':[{'message':{'content':'private malformed response'}}]},'invalid_json'),
])
def test_response_error_is_bounded(monkeypatch,tmp_path,payload,code):
    key=tmp_path/'key';key.write_text('test-key')
    monkeypatch.setenv('CREATIVE_MODEL_KEY_FILE',str(key));monkeypatch.setenv('CREATIVE_MODEL_URL','https://example.invalid')
    calls=[]
    async def post(self,*args,**kwargs):
        calls.append(1);return httpx.Response(200,json=payload)
    monkeypatch.setattr(httpx.AsyncClient,'post',post)
    with pytest.raises(PlanningResponseError) as exc:asyncio.run(CreativeDirectorModel().complete([]))
    assert failure_code(exc.value)==code
    assert str(exc.value)==code
    assert len(calls)==1


def test_unknown_exception_never_leaks_details():
    assert failure_code(ValueError('private provider payload'))=='plan_validation'
    assert failure_code(KeyError('private field'))=='missing_plan_field'
    assert failure_code(RuntimeError('private credential'))=='planning_internal'
    assert failure_code(ValueError('invalid shot count'))=='shot_count'
