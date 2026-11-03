from types import SimpleNamespace
import numpy as np
import pytest
from videoicl_isaaclab.execution_design import REVISION_V3,source_sha256
from videoicl_isaaclab.execution_design_mallet_route import approach_key


def test_actual_lift_precedes_xy_then_descent_and_grip_is_guarded(tmp_path):
    calls=[];tcp=np.array([-.35,-.2,.81]);work=np.array([-.21,-.2,.84])
    def move(side,target,guard):
        guard();delta=np.asarray(target)-tcp;calls.append(('tcp',np.asarray(target).copy()));tcp[:]+=delta;work[:]+=delta
    def move_point(side,ref,target,guard):
        guard();delta=np.asarray(target)-work;calls.append(('work',np.asarray(target).copy()));tcp[:]+=delta;work[:]+=delta
    p=SimpleNamespace(task='E29',spec={'execution_design':{'revision':REVISION_V3,'source_sha256':source_sha256(REVISION_V3)}},
        a=SimpleNamespace(control_report={'engineering_reference_only':True},stage='strike-key-1',out=tmp_path),
        c=SimpleNamespace(steps=0),clearance=1.05,tip=lambda side:tcp.copy(),point=lambda ref:work.copy(),
        move=move,move_point=move_point,operations=[],held=lambda *args:True,
        require_held=lambda *args:calls.append(('guard',None)))
    approach_key(p,{}, {},'right',[.18,0,.855])
    moves=[c for c in calls if c[0]!='guard'];assert [c[0]for c in moves]==['tcp','work','work']
    np.testing.assert_allclose(moves[0][1],[-.35,-.2,1.05]);assert moves[1][1][2]>.935
    np.testing.assert_allclose(work,[.18,0,.855]);assert len([c for c in calls if c[0]=='guard'])==3
    assert (tmp_path/'mallet-public-route.private.jsonl').exists()


def test_formal_or_source_mismatch_cannot_enable_route(tmp_path):
    p=SimpleNamespace(task='E29',spec={'execution_design':{}},a=SimpleNamespace(control_report={}))
    with pytest.raises(ValueError,match='Isolated'):approach_key(p,{}, {},'right',[0,0,.8])


def test_short_native_impact_inside_public_action_is_not_repeated():
    from videoicl_isaaclab.execution_design_mallet_route import strike_key
    e=SimpleNamespace(steps=10,strikes=[],pending_strikes={});actions=[]
    def act(side,token,mm):
        actions.append(token);e.steps+=100;e.strikes.append({'step':20,'key':1,'release_step':22,'contact_impulse':.1})
    p=SimpleNamespace(c=SimpleNamespace(evaluator=e,steps=0),a=SimpleNamespace(stage='strike'),
        require_held=lambda *args:None,act=act,move_point=lambda side,head,target,guard:guard(),
        wait=lambda n:None,contact=lambda *args:False,operations=[])
    strike_key(p,{'actor':'mallet'},{},{},'right','xylophone/key_1',[0,0,.82],[0,0,1])
    assert actions==['DOWN'];assert p.operations[0]['native_strike']['release_step']==22


def test_wrong_native_impact_cannot_be_claimed_as_intended_strike():
    from videoicl_isaaclab.execution_design_mallet_route import strike_key
    from videoicl_isaaclab.realworld_tool_expert import ToolExecutionError
    e=SimpleNamespace(steps=10,strikes=[],pending_strikes={})
    def act(*args,**kwargs):e.strikes.append({'step':20,'key':5,'release_step':22})
    p=SimpleNamespace(c=SimpleNamespace(evaluator=e),require_held=lambda *args:None,act=act)
    with pytest.raises(ToolExecutionError,match='unexpected native key'):
        strike_key(p,{'actor':'mallet'},{},{},'right','xylophone/key_1',[0,0,.82],[0,0,1])


def test_native_strike_reader_does_not_mutate_history():
    from videoicl_isaaclab.execution_design_mallet_route import actual_strike_events
    e=SimpleNamespace(strikes=[{'step':1,'key':2}],pending_strikes={3:{'step':7,'key':3}})
    p=SimpleNamespace(c=SimpleNamespace(evaluator=e));events=actual_strike_events(p,3);events[0]['key']=9
    assert e.pending_strikes[3]['key']==3


def test_actual_flat_head_center_removes_native_twelve_mm_marker_bias():
    from videoicl_isaaclab.execution_design_mallet_route import bottom_face_center
    vertices=np.array([[x,y,-.0211224]for x in (.05445438,.09491261)for y in (-.03266022,.03269604)]+
                      [[-.094,0,0],[0,0,.008]])
    point=bottom_face_center(vertices)
    assert .011<.08667961-point[0]<.013
    np.testing.assert_allclose(point,[.074683495,.00001791,-.0211224])


def test_descent_corrects_real_xy_drift_before_pressing():
    from videoicl_isaaclab.execution_design_mallet_route import strike_key
    e=SimpleNamespace(steps=10,strikes=[],pending_strikes={});working=np.array([-.006,0,.83]);actions=[]
    def act(side,token,mm):
        actions.append((token,mm));e.steps+=100
        if token=='FWD':working[0]+=mm*.001
        elif token=='DOWN':
            assert abs(working[0])<.00035
            e.strikes.append({'step':e.steps,'key':6,'release_step':e.steps+1})
    p=SimpleNamespace(c=SimpleNamespace(evaluator=e,steps=0),a=SimpleNamespace(stage='strike'),
        min_mm=.1,point=lambda ref:working.copy(),require_held=lambda *args:None,act=act,
        move_point=lambda side,head,target,guard:guard(),wait=lambda n:None,contact=lambda *args:False,operations=[])
    strike_key(p,{'actor':'mallet'},{},{},'right','xylophone/key_6',[0,0,.82],[0,0,1])
    assert [x[0]for x in actions]==['FWD','FWD','FWD','DOWN']


def test_unreviewed_head_geometry_is_rejected():
    from videoicl_isaaclab.execution_design_mallet_route import bottom_face_center
    with pytest.raises(ValueError,match='footprint'):
        bottom_face_center([[x,y,0]for x in (-.2,.2)for y in (-.2,.2)])
