import hashlib
import pytest
from harness.studio import store
from harness.tools.creative_canvas import asset_directory
from harness.tools.creative_image_inputs import prepare_inputs, checked_paths
from harness.models.kling_studio_image import catalog


def test_large_owned_generated_source_is_frozen_without_reencoding(tmp_path, monkeypatch):
    monkeypatch.setattr(store, 'DATA', tmp_path)
    aid='b'*32
    project={'id':'a'*24,'aspect':'16:9','canvas_assets':{aid:{'id':aid,'kind':'image','filename':'source.png'}}}
    path=asset_directory(project,aid)/'source.png'
    path.parent.mkdir(parents=True)
    # Input resolution consumes already validated owned files; test the size/hash contract.
    data=b'x'*(5*1024*1024)
    path.write_bytes(data)
    model=next(m for m in catalog() if m['id']=='kling-image-o1')
    prepared=prepare_inputs(project,model,'暖色侧光',[],aid,False)
    assert prepared['references'][0]['sha256']==hashlib.sha256(data).hexdigest()
    assert checked_paths(project,prepared['references'])==[path]
    assert path.read_bytes()==data
    legacy={**model,'id':'legacy-edit'};legacy.pop('max_reference_bytes')
    with pytest.raises(ValueError,match='4 MB'):
        prepare_inputs(project,legacy,'暖色侧光',[],aid,False)
    with path.open('wb') as f:f.truncate(model['max_reference_bytes']+1)
    with pytest.raises(ValueError,match='30 MB'):
        prepare_inputs(project,model,'暖色侧光',[],aid,False)
    path.unlink()
    with pytest.raises(ValueError,match='缺失'):
        prepare_inputs(project,model,'暖色侧光',[],aid,False)
