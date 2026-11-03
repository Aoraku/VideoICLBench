import math
from types import SimpleNamespace
import numpy as np
import pytest
from videoicl_isaaclab.execution_design_e18_reference import E18MeasuredAuthor,solve_e18_reference
from videoicl_isaaclab.realworld_mechanism_expert import MechanismExecutionError
from videoicl_isaaclab.realworld_tool_expert import _axis_rotation
from videoicl_isaaclab.author_orientation import _axis_angle
from videoicl_isaaclab.execution_design import REVISION_V3,REVISION_V2


def controller(fraction=.2):
    q=np.eye(3);calls=[];c=SimpleNamespace(steps=0)
    a=SimpleNamespace(stage='before',scene=SimpleNamespace(embodiment=SimpleNamespace(config={'control':{'rotation_deg':[.5,10.]}})))
    a.tcp_rotation_task=lambda side:q.copy()
    a.tip=lambda side:np.zeros(3)
    a.finger_geometry=lambda side:dict(source='actual_collision_mesh_current_body_pose',fingers=[
        dict(body_origin_task_m=(q@np.array([0,.05,.045])).tolist()),
        dict(body_origin_task_m=(q@np.array([0,-.05,.045])).tolist())])
    def act(left,right,rotation_deg):
        nonlocal q
        token=left if left!='STILL'else right
        axis,sign={'ROLL_LEFT':([1,0,0],1),'ROLL_RIGHT':([1,0,0],-1),'PITCH_UP':([0,1,0],1),'PITCH_DOWN':([0,1,0],-1),'ROTATE_CCW':([0,0,1],1),'ROTATE_CW':([0,0,1],-1)}[token]
        calls.append((token,rotation_deg));q=_axis_rotation(axis,math.radians(rotation_deg)*sign*fraction)@q;c.steps+=1
    a.act=act;worker=E18MeasuredAuthor.__new__(E18MeasuredAuthor)
    worker.a=a;worker.c=c;worker.task='E18';worker.spec={'execution_design':{'revision':REVISION_V3}}
    worker.points={'drawer':{'wrist_yaw_deg':90}};worker.start_steps=0;worker.max_actions=3000;worker.operations=[]
    worker.mechanisms=lambda:{}
    worker.moves=[]
    worker.move=lambda side,target,**kw:worker.moves.append((side,list(target)))
    worker.point=lambda role:np.array([-.084,.075,.878])
    worker._e18_clearance_probe=lambda rotation:dict(feasible=True,target_position=[-.094,.075,.878],rotation_safe_z_m=1.02)
    worker._e18_ik_probe=lambda a,c,side,targets:[dict(kinematically_reachable=True,minimum_joint_margin_rad=.2,joint_distance_rad=1.)for _ in targets]
    worker._e18_increment_ik_probe=lambda a,c,side,targets:[dict(kinematically_reachable=True,
        minimum_joint_margin_rad=.2,joint_distance_rad=.1,position_error_m=0.,orientation_error_rad=0.)for _ in targets]
    worker.frame=lambda entry,snapshot:(np.zeros(3),np.array([[0,0,-1],[-1,0,0],[0,1,0.]]))
    return worker,calls


def test_partial_native_responses_do_not_count_as_ninety_degrees():
    w,calls=controller();w.orient('drawer','left')
    assert len(calls)>9
    from videoicl_isaaclab.execution_design_e18_reference import handle_orientation_target
    fresh,_=controller();target=handle_orientation_target(fresh.a,'left',[-1,0,0],[0,-1,0])
    assert _axis_angle(target@w.a.tcp_rotation_task('left').T)[1]<math.radians(1.5)
    assert all(.5<=degrees<=10 for token,degrees in calls)
    assert w.operations[-1]['native_handle_success_not_asserted']
    assert w.a.stage=='mechanism-safe-empty-wrist-staging-drawer'
    w.orient('drawer','left',inverse=True)
    assert _axis_angle(w.a.tcp_rotation_task('left'))[1]<math.radians(1.5)


def test_zero_motion_is_failure_not_assumed_orientation():
    w,calls=controller(fraction=0)
    with pytest.raises(MechanismExecutionError,match='stalled'):w.orient('drawer','left')
    assert len(calls)==12 and not w.operations and w.a.stage=='mechanism-safe-empty-wrist-staging-drawer'


def test_old_revision_and_unapproved_reference_are_refused():
    w,_=controller();w.spec['execution_design']['revision']=REVISION_V2
    with pytest.raises(ValueError,match='scope'):w.orient('drawer','left')
    with pytest.raises(ValueError,match='authorization'):solve_e18_reference(SimpleNamespace())


def test_budget_stops_before_next_public_action():
    w,calls=controller();w.max_actions=3
    with pytest.raises(MechanismExecutionError,match='budget'):w.orient('drawer','left')
    assert len(calls)==3


def test_source_handle_pinches_vertical_with_palm_outside_instead_of_panel_gap():
    from videoicl_isaaclab.execution_design_e18_reference import handle_orientation_target
    w,_=controller();target=handle_orientation_target(w.a,'left',[-1,0,0],[0,-1,0])
    assert np.allclose(target@np.array([0,1,0]),[0,0,1])
    assert np.allclose(target@np.array([0,0,1]),[-1,0,0])
    # Unknown/stale approximated finger geometry must not drive the new route.
    w.a.finger_geometry=lambda side:{'source':'estimated_size'}
    with pytest.raises(MechanismExecutionError,match='Actual finger'):handle_orientation_target(w.a,'left',[-1,0,0],[0,-1,0])


def test_horizontal_approach_uses_current_articulation_point_and_public_moves(monkeypatch):
    import videoicl_isaaclab.execution_design_e18_reference as module
    monkeypatch.setattr(module,'handle_tcp_target',lambda author,side,point,normal:point)
    w,_=controller();w.point=lambda role:np.array([-.084,.075,.878]);w.axis=lambda role:np.array([-1.,0,0]);w.tip=lambda side:np.array([-.2,.3,.95]);moves=[]
    w.move=lambda side,target,**kwargs:moves.append((np.array(target),kwargs))
    w.approach('drawer','left')
    assert np.allclose(moves[0][0],[-.194,.075,.95])
    assert np.allclose(moves[1][0],[-.194,.075,.878])
    assert np.allclose(moves[-1][0],[-.084,.075,.878])
    assert moves[-1][1]['tolerance']==.0005
    assert all(p[0]<=-.084 for p,_ in moves)


def test_equivalent_vertical_pinch_avoids_limit_at_approach_not_just_home():
    from videoicl_isaaclab.execution_design_e18_reference import choose_handle_orientation
    w,_=controller();seen=[]
    def ik(a,c,side,targets):
        seen.append(targets);margin=.0001 if len(seen)==1 else .2
        return [dict(kinematically_reachable=True,minimum_joint_margin_rad=.3 if i==0 else margin,joint_distance_rad=1.)for i,_ in enumerate(targets)]
    target=choose_handle_orientation(w.a,w.c,'left',[-.084,.075,.878],[-1,0,0],[0,-1,0],ik,w._e18_clearance_probe)
    assert len(seen)==22 and all(len(t)==5 for t in seen)
    assert np.allclose(target@np.array([0,1,0]),[0,0,-1])
    assert np.allclose(target@np.array([0,0,1]),[-1,0,0])
    with pytest.raises(MechanismExecutionError,match='Neither equivalent'):
        choose_handle_orientation(w.a,w.c,'left',[-.084,.075,.878],[-1,0,0],[0,-1,0],lambda a,c,s,t:[dict(kinematically_reachable=False,minimum_joint_margin_rad=.2,joint_distance_rad=1.)for _ in t],w._e18_clearance_probe)


def test_rotation_is_planned_at_measured_safe_staging_not_home():
    from videoicl_isaaclab.execution_design_e18_reference import choose_handle_orientation
    w,_=controller();seen=[]
    def ik(a,c,side,targets):
        seen.append(targets)
        # The neutral wrist first rises and translates. Rotation endpoints
        # are at the source front lane, never the infeasible lateral home.
        assert np.allclose(targets[0]['rotation'],np.eye(3))
        assert np.allclose(targets[1]['rotation'],np.eye(3))
        assert targets[2]['position'][2]>=1.02
        assert not np.allclose(targets[2]['position'],a.tip(side))
        return [dict(kinematically_reachable=True,minimum_joint_margin_rad=.3,joint_distance_rad=1.)for _ in targets]
    choose_handle_orientation(w.a,w.c,'left',[-.084,.075,.878],[-1,0,0],[0,-1,0],ik,w._e18_clearance_probe)
    assert len(seen)==22
    raise_to,staging=w.a._e18_orientation_staging['left']
    assert raise_to[2]>=1.02 and staging[2]>=1.02
    w.orient('drawer','left')
    assert len(w.moves)==2


def test_nearby_rotation_rejects_endpoint_ik_branch_jump_and_joint_limit():
    from videoicl_isaaclab.execution_design_e18_reference import choose_rotation_increment
    w,_=controller();target=_axis_rotation([1,1,0],math.radians(30))
    seen=[]
    def probe(a,c,side,targets):
        seen.extend(targets)
        return [dict(kinematically_reachable=True,position_error_m=0.,orientation_error_rad=0.,
            minimum_joint_margin_rad=.0002 if i==0 else .2,joint_distance_rad=.1)for i in range(len(targets))]
    token,degrees=choose_rotation_increment(w.a,w.c,'left',target,.5,10.,probe)
    assert token=='PITCH_UP' and degrees<=5.
    assert all(np.allclose(row['position'],w.a.tip('left'))for row in seen)
    for field,value in [('joint_distance_rad',.4),('minimum_joint_margin_rad',.04),('position_error_m',float('nan'))]:
        def bad(a,c,side,targets):
            row=dict(kinematically_reachable=True,position_error_m=0.,orientation_error_rad=0.,minimum_joint_margin_rad=.2,joint_distance_rad=.1)
            row[field]=value;return [dict(row)for _ in targets]
        with pytest.raises(MechanismExecutionError,match='near-neighbor'):
            choose_rotation_increment(w.a,w.c,'left',target,.5,10.,bad)


def test_incomplete_increment_probe_cannot_send_public_action():
    w,calls=controller();w._e18_increment_ik_probe=lambda *args:[]
    with pytest.raises(MechanismExecutionError,match='Incomplete'):w.orient('drawer','left')
    assert calls==[]


def test_rotation_subdivides_at_singularity_without_relaxing_joint_jump_guard():
    from videoicl_isaaclab.execution_design_e18_reference import choose_rotation_increment
    w,_=controller();target=_axis_rotation([0,1,0],math.radians(-50));seen=[]
    def probe(a,c,side,targets):
        result=[]
        for entry in targets:
            degrees=math.degrees(_axis_angle(np.asarray(entry['rotation'])@a.tcp_rotation_task(side).T)[1]);seen.append(degrees)
            result.append(dict(kinematically_reachable=True,position_error_m=0.,orientation_error_rad=0.,
                minimum_joint_margin_rad=.45,joint_distance_rad=degrees*.0964))
        return result
    token,degrees=choose_rotation_increment(w.a,w.c,'left',target,.5,10.,probe)
    assert token=='PITCH_DOWN' and degrees==pytest.approx(2.5)
    assert seen==pytest.approx([5.,2.5])


def test_equivalent_grip_prefers_shorter_joint_branch_once_margin_is_adequate():
    from videoicl_isaaclab.execution_design_e18_reference import choose_handle_orientation
    w,_=controller();calls=[]
    def probe(a,c,side,targets):
        calls.append(targets);index=len(calls)
        margin=.4 if index==1 else .3 if index==2 else .001
        distance=2. if index==1 else 1.
        return [dict(kinematically_reachable=True,minimum_joint_margin_rad=margin,joint_distance_rad=distance)for _ in targets]
    target=choose_handle_orientation(w.a,w.c,'left',[-.084,.075,.878],[-1,0,0],[0,-1,0],probe,w._e18_clearance_probe)
    assert np.allclose(target@np.array([0,1,0]),[0,0,-1])


def test_short_geodesic_orientation_waypoints_preserve_exact_final_pose():
    from videoicl_isaaclab.execution_design_e18_reference import orientation_waypoints
    current=_axis_rotation([0,1,0],.3);target=_axis_rotation([1,2,-3],2.2)@current
    points=orientation_waypoints(current,target);previous=current
    for point in points:
        assert _axis_angle(point@previous.T)[1]<=math.radians(12)+1e-10
        assert np.allclose(point.T@point,np.eye(3)) and np.linalg.det(point)>0.9999
        previous=point
    assert np.allclose(points[-1],target)
    assert len(orientation_waypoints(current,current))==1
    with pytest.raises(ValueError):orientation_waypoints(current,target,20)


def test_rotations_recover_measured_staging_center_with_public_move():
    w,calls=controller(fraction=.8);position=np.zeros(3);old_act=w.a.act;corrections=[]
    w.a.tip=lambda side:position.copy()
    def act(*args,**kwargs):
        old_act(*args,**kwargs);position[0]+=.0008
    w.a.act=act
    def move(side,target,**kwargs):
        if kwargs.get('tolerance')==.004:
            corrections.append((position.copy(),np.asarray(target).copy()));position[:]=target
    w.move=move;w.orient('drawer','left')
    assert calls and corrections
    assert all(np.max(np.abs(before-after))>.006 for before,after in corrections)
    assert np.max(np.abs(position))<=.006


def test_failed_physical_center_recovery_cannot_issue_another_rotation():
    w,calls=controller(fraction=.8);position=np.zeros(3);old_act=w.a.act
    w.a.tip=lambda side:position.copy()
    def act(*args,**kwargs):
        old_act(*args,**kwargs);position[0]+=.003
    w.a.act=act
    # The stub move deliberately does not move the real measured centre.
    with pytest.raises(MechanismExecutionError,match='centre not recovered'):
        w.orient('drawer','left')
    # The practical transit bound permits6mm; a third3mm drift requires a
    # successful real correction before another public rotation is allowed.
    assert len(calls)==3
