import hashlib
import json
import zipfile
import pytest
from harness.research.briefs import digest
from tools.prepare_reference_plan_review import build


def setup(tmp_path):
    batch=tmp_path/'batch';run=batch/'run';run.mkdir(parents=True)
    def save(p,x):p.write_text(json.dumps(x))
    save(batch/'assignment.json',{'rows':[['run','R009','present']]})
    save(run/'summary.json',{'conditions':[{'condition':'hidden-strategy','plan_completed':True},{'condition':'failed-strategy','plan_completed':False}]})
    obs={'result':{'claim':'test','shots':[],'unresolved':[]}}
    inp={'messages':[{'role':'system','content':'not-exposed'},{'role':'user','content':json.dumps({'task':{'brief':'test','facts':{'appearance':'glass'}}})}]}
    prefix=run/'hidden-strategy-plan'
    save(prefix.with_name(prefix.name+'-observation.json'),obs)
    save(prefix.with_name(prefix.name+'-input.json'),inp)
    save(prefix.with_name(prefix.name+'-event.json'),{'state':'completed','observation_sha256':digest(obs),'prompt_sha256':digest(inp['messages'])})
    source=tmp_path/'source';source.mkdir();clips=[]
    for i in range(2):
        name=f'S{i}.mp4';raw=f'media-{i}'.encode();(source/name).write_bytes(raw)
        clips.append({'label':f'S{i}','media':name,'sha256':hashlib.sha256(raw).hexdigest(),'duration':20})
    save(source/'packet.json',{'clips':clips})
    save(source/'private-mapping.json',{'mapping':{'S0':'R009','S1':'R010'}})
    return batch,source,tmp_path/'out'


def test_blind_package_omits_allocations_and_preserves_missing(tmp_path):
    args=setup(tmp_path);r=build(*args)
    assert r['completed_plans']==1 and r['missing_conditions']==1 and not r['training_eligible']
    with zipfile.ZipFile(args[2]/'reviewer-package.zip') as z:
        assert 'private-mapping.json' not in z.namelist()
        for name in ('packet.json','review.html'):
            s=z.read(name).decode();assert 'hidden-strategy' not in s and 'failed-strategy' not in s and 'not-exposed' not in s
    private=json.loads((args[2]/'private-mapping.json').read_text())
    assert private['missing_conditions']==[{'run':'run','condition':'failed-strategy'}]
    with pytest.raises(FileExistsError):build(*args)


def test_corrupt_plan_rejected(tmp_path):
    args=setup(tmp_path);p=args[0]/'run'/'hidden-strategy-plan-observation.json';p.write_text('{"result":{}}')
    with pytest.raises(ValueError,match='plan_evidence_mismatch'):build(*args)
    assert not args[2].exists()


def test_changed_media_rejected(tmp_path):
    args=setup(tmp_path);(args[1]/'S0.mp4').write_bytes(b'changed')
    with pytest.raises(ValueError,match='media_digest_mismatch'):build(*args)
    assert not args[2].exists()
