import numpy as np
import pytest
from videoicl_isaaclab.execution_design_e31_edge import rim_plan,choose_edge_route


def geometry():
    theta=np.linspace(0,2*np.pi,361)
    p=np.array([[r*np.cos(t),r*np.sin(t)-.12,z]for r in(.078,.082,.086,.09,.094)for t in theta for z in(.814,.824)])
    center=np.array([0,-.12,.812])
    fingers=[np.array([[x,y,z]for x in(-.025,.015)for y in(-.008,.008)for z in band])for band in ((-.035,-.015),(.015,.035))]
    bounds=dict(lower=np.array([-.35,-.6,.8]),upper=np.array([.35,.6,.8]),top=.8)
    return p,center,fingers,bounds


@pytest.mark.parametrize('sign',[-1.,1.])
def test_real_lower_finger_exterior_and_supported_center(sign):
    p,c,f,b=geometry();plan=rim_plan(p,c,f,b,[sign,0,0]);g=plan['target_grasp'];low=f[0]+g
    assert np.min(sign*(low[:,0]-b['upper'if sign>0 else'lower'][0]))>=.002-1e-12
    assert abs(plan['translated_center'][0])<.325
    assert plan['rim_thickness']==pytest.approx(.01)
    assert np.allclose(p,geometry()[0])


def test_empty_rim_section_rejected():
    p,c,f,b=geometry()
    with pytest.raises(ValueError,match='rim section'):rim_plan(p+np.array([0,.2,0]),c,f,b,[-1,0,0])


def test_lower_finger_cannot_force_center_off_table():
    p,c,f,b=geometry();f[0][:,0]-=.15
    with pytest.raises(ValueError,match='support margin'):rim_plan(p,c,f,b,[1,0,0])


def test_no_below_table_finger_is_not_claimed_as_side_pinch():
    p,c,f,b=geometry()
    with pytest.raises(ValueError,match='lower finger'):rim_plan(p,c,[x+[0,0,.1]for x in f],b,[1,0,0])


@pytest.mark.parametrize('axis',[(0,1,0),(0,0,1),(np.nan,0,0)])
def test_bad_axes(axis):
    with pytest.raises(ValueError):rim_plan(*geometry(),axis)


def route(joints,margin=.2):
    return [dict(kinematically_reachable=True,minimum_joint_margin_rad=margin,
                 joint_distance_rad=1.,candidate_joints_rad=q)for q in joints]


def test_actual_v6_disconnected_stage_and_rim_branch_rejected():
    stage=[-.039,-1.333,2.199,-2.852,2.629,3.592,1.890]
    rim=[.616,.948,.367,-2.701,-2.182,1.049,-.594]
    with pytest.raises(RuntimeError,match='same-branch'):
        choose_edge_route([route([stage,stage,stage,rim,rim])])


def test_symmetric_jaw_with_short_safe_path_selected():
    bad=route([[0]*7]*5);bad[2]['candidate_joints_rad']=[0,0,0,0,3.3,0,0]
    good=route([[i*.1]*7 for i in range(5)])
    assert choose_edge_route([bad,good])==1


def test_endpoint_margin_is_not_relaxed_to_allow_hard_stop():
    r=route([[0]*7]*5);r[1]['minimum_joint_margin_rad']=.000192
    with pytest.raises(RuntimeError):choose_edge_route([r])


def test_all_five_phases_and_reachable_endpoints_required():
    with pytest.raises(ValueError):choose_edge_route([route([[0]*7]*4)])
    r=route([[0]*7]*5);r[-1]['kinematically_reachable']=False
    with pytest.raises(RuntimeError):choose_edge_route([r])
