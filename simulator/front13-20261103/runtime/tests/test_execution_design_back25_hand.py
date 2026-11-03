"""New input layouts select a hand using actual source and destination poses."""
from pathlib import Path
from types import SimpleNamespace
import json
import numpy as np
import pytest
from videoicl_isaaclab.realworld_scenes import load
from videoicl_isaaclab.execution_design import REVISION_V3
from videoicl_isaaclab.execution_design_generated_route import choose_generated_hand, initial_back25_hand

@pytest.mark.parametrize('origin',[(0,0,0),(8,0,0),(0,8,0)])
@pytest.mark.parametrize('variant',list('ABC'))
def test_relocated_bowl_plate_choose_endpoint_reach_without_changing_contract(tmp_path,origin,variant):
    raw=json.loads((Path(__file__).parents[1]/'configs/realworld_full50_bindings.json').read_text())
    raw['execution_design']=dict(revision=REVISION_V3,condition='I')
    p=tmp_path/'binding.json';p.write_text(json.dumps(raw));spec=load('E31',variant,4201,p,verify_files=False)
    before=json.dumps(spec,sort_keys=True);offset=np.array(origin)
    state={o['id']:dict(pos=np.array([*o['xy'],o['bottom']+o['size'][2]]),mat=np.eye(3))for o in spec['objects']}
    robots={side:SimpleNamespace(data=SimpleNamespace(root_pos_w=np.array([offset+[-.65,y,.75]])))for side,y in [('left',.3),('right',-.3)]}
    a=SimpleNamespace(scene=SimpleNamespace(spec=spec,robots=robots,world_to_task=lambda p:p-offset),
        c=SimpleNamespace(snapshot=lambda:(state,[])),_execution_design_reference_authorized=True)
    for goal in spec['goals']:
        target=next(z for z in spec['zones']if z['id']==goal['target'])
        result=choose_generated_hand(a,goal['object'],goal,target,'right')
        assert result['max_endpoint_horizontal_reach_m'][result['chosen']]==pytest.approx(min(result['max_endpoint_horizontal_reach_m'].values()),abs=.001)
        assert result['native_reachability_verified'] is False
        if variant=='A':assert result['chosen']=='left'
    if variant=='A':assert initial_back25_hand(a,'right')=='left'
    assert json.dumps(spec,sort_keys=True)==before
    a._execution_design_reference_authorized=False
    assert initial_back25_hand(a,'right')=='right'
    with pytest.raises(ValueError,match='Engineering'):choose_generated_hand(a,goal['object'],goal,target,'right')
