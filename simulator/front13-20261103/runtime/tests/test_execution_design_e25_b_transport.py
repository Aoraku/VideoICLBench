from copy import deepcopy
import json
import numpy as np
import pytest
from test_execution_design_e25_b_reference import execution_author
from videoicl_isaaclab.realworld_tool_expert import _axis_rotation
from videoicl_isaaclab.execution_design_e25_b_transport import route_targets,rotate_transport_payload,solve_path


def test_interleave_preserves_final_goal_and_exact_actual_held_transform():
    tip=np.array([-.2,0.,1.]);body=np.array([-.26,0.,1.]);tcp=np.diag([1.,-1.,-1.]);desired=_axis_rotation([0,0,1],np.pi)
    before=tip.copy();rows=route_targets(tip,tcp,body,np.eye(3),[.2,.1],desired,np.pi)
    rotations=[r for r in rows if r['phase']=='rotate'];assert len(rotations)==8
    np.testing.assert_allclose(rotations[-1]['body_rotation'],desired,atol=1e-12)
    np.testing.assert_allclose(rows[-1]['position'],[.14,.1,1.],atol=1e-12)
    np.testing.assert_allclose(rows[-1]['rotation'],desired@tcp,atol=1e-12)
    assert all(np.max(abs(np.asarray(b['position'])-a['position']))<=.0080001 for a,b in zip(rows,rows[1:]))
    np.testing.assert_array_equal(tip,before)
    with pytest.raises(ValueError,match='half-turn'):route_targets(tip,tcp,body,np.eye(3),[.2,.1],desired,.2)


def author(tmp_path):
    a=execution_author(tmp_path);position=np.array([-.2,0.,1.]);rotation=np.diag([1.,-1.,-1.]);offset=np.array([.06,0.,0.])
    a.state['spoon']['pos']=position-offset;a.scene.spec['goals']=[dict(object='spoon',target='spoon_target',yaw=np.pi)];a.scene.spec['zones']=[dict(id='spoon_target',xy=[.2,.1])]
    a.tip=lambda side:position.copy();a.tcp_rotation_task=lambda side:rotation.copy();actions=[];a.c.steps=451
    def act(left,right,mm=20.,rotation_deg=10.):
        nonlocal rotation
        assert right=='STILL';actions.append(left);a.c.steps+=1
        axis={'ROLL_LEFT':[1,0,0],'ROLL_RIGHT':[-1,0,0],'PITCH_UP':[0,1,0],'PITCH_DOWN':[0,-1,0],'ROTATE_CCW':[0,0,1],'ROTATE_CW':[0,0,-1]}.get(left)
        if axis is not None:
            delta=_axis_rotation(axis,np.deg2rad(rotation_deg));a.state['spoon']['mat']=delta@a.state['spoon']['mat'];rotation=delta@rotation
            a.scene.robots['left'].data.joint_pos[0,6]-=axis[2]*np.deg2rad(rotation_deg)
            a.state['spoon']['pos']=position-a.state['spoon']['mat']@offset
        else:
            delta=np.array({'FWD':[1,0,0],'BACK':[-1,0,0],'LEFT':[0,1,0],'RIGHT':[0,-1,0],'UP':[0,0,1],'DOWN':[0,0,-1]}[left])*mm/1000
            position[:]+=delta;a.state['spoon']['pos']+=delta
    a.act=act;a.actions=actions
    measured=dict(q=a.scene.robots['left'].data.joint_pos[0].tolist(),position=position.tolist())
    return a,measured


def solver():
    calls=[]
    def solve(measured,targets):
        calls.append(targets)
        return [dict(kinematically_reachable=len(calls)==1,minimum_joint_margin_rad=.5)for _ in targets]
    return solve


def goal():return dict(object='spoon',target='spoon_target',yaw=np.pi,_e07_after_relay={})


def test_complete_public_transport_keeps_grip_and_source_and_returns_no_task_score(tmp_path):
    a,m=author(tmp_path);before=deepcopy(a.scene.spec);rotate_transport_payload(a,'spoon','left',goal(),measured=m,solver=solver())
    np.testing.assert_allclose(a.state['spoon']['pos'][:2],[.2,.1],atol=.002)
    np.testing.assert_allclose(a.state['spoon']['mat'],np.diag([-1.,-1.,1.]),atol=.021)
    assert a.state['spoon']['grasp']==[True,False] and a.scene.spec==before
    assert 'GRASP'not in a.actions and 'RELEASE'not in a.actions and len(a.actions)>80
    assert a.stage=='grasped-spoon'and not a.control_report['e25_b_interleaved_transports'][0]['native_passed']
    rows=[json.loads(x)for x in (tmp_path/'e25-b-interleaved-transport.private.jsonl').read_text().splitlines()]
    assert rows[-1]['phase']=='transport_complete'
    assert sum(r['phase']=='public_step'for r in rows)==len(a.actions)


@pytest.mark.parametrize('fault',['slip','peer_hold','collision','floor','limit','blocked','model_q'])
def test_native_guard_stops_first_failed_action(tmp_path,fault):
    a,m=author(tmp_path);base=a.act
    if fault=='model_q':m['q'][0]+=.1
    else:
        def act(*args,**kwargs):
            base(*args,**kwargs)
            if fault=='slip':a.state['spoon']['grasp']=[False,False]
            elif fault=='peer_hold':a.state['spoon']['grasp']=[True,True]
            elif fault=='collision':a.contacts.add(frozenset(('spoon','table')))
            elif fault=='floor':a.finger_geometry=lambda side:dict(source='actual_collision_mesh_current_body_pose',lowest_z_task_m=.8)
            elif fault=='limit':a.scene.robots['left'].data.joint_pos[0,6]=2.99
            else:a.feedback['status']='blocked'
        a.act=act
    with pytest.raises(RuntimeError,match='grip|peer|collision|clearance|limit|IK|starting state'):
        rotate_transport_payload(a,'spoon','left',goal(),measured=m,solver=solver())
    assert len(a.actions)==(0 if fault=='model_q'else 1)


def test_failed_full_route_screen_has_zero_actions(tmp_path):
    a,m=author(tmp_path)
    with pytest.raises(RuntimeError,match='no connected'):
        rotate_transport_payload(a,'spoon','left',goal(),measured=m,solver=lambda m,t:[])
    assert a.actions==[]


def test_goal_mutation_and_nonreceiver_rejected_without_actions(tmp_path):
    a,m=author(tmp_path)
    with pytest.raises(ValueError,match='Original'):rotate_transport_payload(a,'spoon','left',dict(goal(),yaw=0.),measured=m,solver=solver())
    with pytest.raises(ValueError,match='receiving'):rotate_transport_payload(a,'spoon','right',goal(),measured=m,solver=solver())
    assert a.actions==[]


def test_solver_refuses_actual_q_at_screen_margin_without_clipping():
    q=np.zeros(7);limits=np.tile([-3.,3.],(7,1));q[6]=2.98
    measured=dict(position=[0,0,1],rotation_task=np.eye(3),jacobian=np.vstack((np.zeros((3,7)),np.tile([[0],[0],[1]],(1,7)))),q=q.copy(),limits=limits)
    with pytest.raises(ValueError,match='starting joints'):solve_path(measured,[])
    np.testing.assert_array_equal(q,measured['q'])
