from types import SimpleNamespace
import numpy as np
import pytest
from videoicl_isaaclab import execution_design_e28_rock as rock
from videoicl_isaaclab.realworld_tool_expert import ToolExecutionError


def policy(tmp_path, *, stop_contact=True, hand_grasp=False):
    actions=[]
    body=dict(pos=np.array([0.,0.,.807]),mat=np.eye(3),grasp=[hand_grasp,False])
    state={'food':body,'spatula':dict(pos=np.zeros(3),mat=np.eye(3))}
    p=SimpleNamespace(spec={'objects':[dict(id='food',size=[.025,.018,.007])]},
        snapshot=lambda:(state,set()),point=lambda ref:np.array([0.,-.018,.800]),
        contact=lambda actor,other:other=='table'or stop_contact and other=='left_finger1',
        require_held=lambda *args:None,stage=lambda s:None,
        c=SimpleNamespace(steps=0,contact_forces={}),
        a=SimpleNamespace(out=tmp_path,act=lambda *args,**kw:actions.append((args,kw))))
    p.act=lambda *args,**kw:actions.append((args,kw))
    return p,actions


def test_no_upper_edge_push_without_real_open_far_side_stop(tmp_path):
    p,actions=policy(tmp_path,stop_contact=False)
    with pytest.raises(ToolExecutionError,match='actual existing open far-side stop'):
        rock.prepare(p,{'actor':'spatula'}, {},'right','food',{},np.array([0.,1.,0.]))
    assert actions==[]


def test_food_hand_grasp_aborts_before_vertical_or_forward_blade_action(tmp_path,monkeypatch):
    p,actions=policy(tmp_path,hand_grasp=True)
    monkeypatch.setattr(rock,'center_over_blade',lambda *args:(False,np.zeros(3)))
    with pytest.raises(ToolExecutionError,match='Food acquired by a hand'):
        rock.prepare(p,{'actor':'spatula'}, {},'right','food',{},np.array([0.,1.,0.]))
    assert len(actions)==1 and actions[0][0]==('ROTATE_CCW','ROTATE_CCW')


def test_open_gap_after_raise_does_not_trigger_an_unnecessary_food_push(tmp_path,monkeypatch):
    p,actions=policy(tmp_path)
    monkeypatch.setattr(rock,'center_over_blade',lambda *args:(False,np.zeros(3)))
    monkeypatch.setattr(rock,'near_bottom',lambda *args:np.array([0.,-.018,.8042 if len(actions)>=2 else .8]))
    rock.prepare(p,{'actor':'spatula'}, {},'right','food',{},np.array([0.,1.,0.]))
    assert len(actions)==2
    assert actions[1][0]==('right','UP')
