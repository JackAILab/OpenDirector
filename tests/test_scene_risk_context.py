"""Risk-time evidence must not leak pairs from another sample or shot."""
import json
import subprocess
from harness.tools.creative_scene import station_keyframe_observation


def test_pairs_are_projected_at_their_own_keyframe_time():
    objects = [dict(id=name, kind='box', visible=True, position=position, scale=[1, 1, 1])
               for name, position in [('a', [10, 1, 0]), ('b', [0, 1, 0]), ('c', [4, 1, 0])]]
    spec = dict(objects=objects, shots=[dict(id='shot', station_keyframes=[
        dict(object_id='a', at=1, position=[0, 1, 0]),
        dict(object_id='a', at=2, position=[4, 1, 0]),
    ])])
    result = station_keyframe_observation(spec)
    assert result['shots'][0]['collision_pairs_by_time'] == [
        {'at': 1.0, 'pairs': [['a', 'b']]}, {'at': 2.0, 'pairs': [['a', 'c']]}]
    assert 'position' not in json.dumps(result)
    assert result['training_eligible'] is False


def test_shared_comparison_distinguishes_rounding_neighbors_and_missing_detail():
    script = r"""
const assert=require('node:assert/strict');
const risk=require('./tools/agent_studio/scene-risk-context.js');
const saved={collision_times:[1,2],collision_pairs:[['a','b'],['a','c']],collision_pairs_by_time:[{at:1,pairs:[['a','b']]},{at:2,pairs:[['a','c']]}]};
assert.deepEqual(risk.at(saved,2).pairs,[['a','c']]);
assert.deepEqual(risk.at(saved,1.1).pairs,[]);
assert.equal(risk.compare(saved,{collision_times:[1.1]},1).label,'仅保存版此时有命中记录');
assert.equal(risk.at({collision_times:[1.875]},1.88).hit,true);
const legacy=risk.at({collision_times:[1],collision_pairs:[['a','b']]},1);
assert.equal(legacy.hit,true);assert.equal(legacy.detail,false);assert.deepEqual(legacy.pairs,[]);
assert.match(risk.describe(legacy),/明细未记录/);
assert.equal(risk.compare(null,null,1).label,'两版此时均无命中记录');
assert.equal(risk.at(saved,NaN).hit,false);
"""
    subprocess.run(['node', '-e', script], check=True)
