import itertools
from types import SimpleNamespace
import numpy as np


def test_reversed_jaws_preserve_approach_and_reverse_only_bilateral_axes():
    from videoicl_isaaclab.execution_design_e08_approach import reversed_jaw_turns
    initial=np.diag([1.,-1.,-1.]);quarter,flipped=reversed_jaw_turns(initial)
    np.testing.assert_allclose(quarter[:,2],initial[:,2])
    np.testing.assert_allclose(flipped[:,2],initial[:,2])
    np.testing.assert_allclose(flipped[:,:2],-initial[:,:2])
    np.testing.assert_allclose(quarter.T@quarter,np.eye(3))
    assert np.linalg.det(flipped)==1
import pytest
from videoicl_isaaclab.execution_design_e08_approach import swept_clearance,approach

def box(center,half):return np.array(center)+np.array(list(itertools.product((-1,1),repeat=3)))*np.array(half)
def test_sweep_catches_palm_shoe_contact_despite_clear_fingers():
    shoe=box([0,0,.86],[.13,.04,.05]);f=[box([0,y,1.0],[.01,.005,.025])for y in(-.06,.06)]
    palm=box([0,0,1.08],[.03,.04,.02])
    with pytest.raises(RuntimeError,match='shoe hull'):swept_clearance(shoe,[palm,*f],[0,0,1.0],[0,0,.82])
def test_clear_sweep_and_table_guard_are_independent():
    shoe=box([0,0,.86],[.05,.04,.05]);b=[box([-.15,y,1.1],[.01,.005,.01])for y in(-.04,0,.04)]
    assert swept_clearance(shoe,b,[-.15,0,1.1],[-.15,0,.85])['minimum_table_clearance_m']>.03
    with pytest.raises(RuntimeError,match='table'):swept_clearance(shoe,b,[-.15,0,1.1],[-.15,0,.8])
def test_formal_other_tasks_cannot_enter_candidate():
    p=SimpleNamespace(task='E09',a=object())
    with pytest.raises(ValueError,match='engineering'):approach(p,'left',{})


def test_pending_rotation_waits_keep_accepted_target_and_stop_on_stall():
    from videoicl_isaaclab.execution_design_e08_approach import settle_accepted_rotation
    from types import SimpleNamespace
    values=iter([.08,.04,.04]);state={'error':next(values),'tokens':[]}
    c=SimpleNamespace(steps=0,action_feedback=lambda:{'control_feedback':{'left':{'orientation_error_rad':state['error']}}})
    def act(side,token):
        assert side=='left';state['tokens'].append(token);c.steps+=1;state['error']=next(values)
    p=SimpleNamespace(c=c,act=act)
    rows=settle_accepted_rotation(p,'left',lambda:None)
    assert state['tokens']==['STILL','STILL'] and len(rows)==2

def test_already_settled_rotation_does_not_add_actions():
    from videoicl_isaaclab.execution_design_e08_approach import settle_accepted_rotation
    from types import SimpleNamespace
    p=SimpleNamespace(c=SimpleNamespace(action_feedback=lambda:{'control_feedback':{'left':{'orientation_error_rad':.001}}}),act=lambda *a:(_ for _ in ()).throw(AssertionError()))
    assert settle_accepted_rotation(p,'left',lambda:None)==[]


def test_reviewed_route_can_clear_when_unused_diagonal_hits_shoe():
    from videoicl_isaaclab.execution_design_e08_approach import approach_path,path_clearance
    shoe=box([0,0,.86],[.05,.04,.05]);tip=np.array([-.1,.15,1.04]);target=np.array([-.1,0,.84])
    bodies=[box(tip+[0,y,0],[.01,.005,.01])for y in(-.06,0,.06)]
    # Put an obstruction across the obsolete diagonal but below the high route.
    obstruction=box([-.1,.1,.92],[.02,.01,.015])
    with pytest.raises(RuntimeError,match='shoe hull'):swept_clearance(obstruction,bodies,tip,target)
    receipt=path_clearance(obstruction,bodies,tip,approach_path(tip,target,1.04))
    assert receipt['minimum_table_clearance_m']>.02
    for start,end in zip(receipt['waypoints'][:-1],receipt['waypoints'][1:]):
        assert np.count_nonzero(abs(np.array(start)-end)>1e-10)<=1
    with pytest.raises(RuntimeError,match='table'):
        path_clearance(shoe,bodies,tip,approach_path(tip,[-.1,0,.79],1.04))
