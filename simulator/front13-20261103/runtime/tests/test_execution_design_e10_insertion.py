from pathlib import Path
from types import SimpleNamespace
import numpy as np
import pytest
from videoicl_isaaclab.realworld_scenes import load
from videoicl_isaaclab.realworld_tool_expert import ToolExecutionError,_axis_rotation
from videoicl_isaaclab.execution_design_e10_insertion import post_clearances,thread_piece


@pytest.fixture(autouse=True)
def native_turn_is_separate_from_geometric_descent_model(monkeypatch):
    from videoicl_isaaclab import execution_design_e10_insertion
    monkeypatch.setattr(execution_design_e10_insertion,'turn_to_post_rotation',lambda a,n,s,r:a.rotate_actor(n,s,r))
    monkeypatch.setattr(execution_design_e10_insertion,'post_transport_height',lambda *args:.94)


def test_reachable_lean_keeps_all_original_bores_and_native_axis_clear():
    from videoicl_isaaclab.execution_design_e10_insertion import planned_post_rotation
    a,_,g=fixture(angle=6.)
    r=planned_post_rotation(g['rotation'])
    assert r[2,2]>.98
    rows=post_clearances(a,'red_square',g['post_indices'])
    assert min(x['margin_m']for x in rows)>.001


def test_single_centered_bore_does_not_spend_actions_on_irrelevant_yaw():
    from videoicl_isaaclab.execution_design_e10_insertion import post_rotation_for_object
    a=SimpleNamespace(s={'holes':{'ring':[{'center_local':[0,0,0]}]}},frame=lambda ref:(np.zeros(3),np.eye(3)))
    r=post_rotation_for_object(a,'ring',_axis_rotation([0,0,1],np.pi/2))
    assert r[0,0]>.99 and r[2,2]>.98


def test_suffix_route_does_not_inherit_an_unreachable_default_stow_height():
    a,_,g=fixture();a.clearance=1.15;targets=[];original=a.move_point
    def move(side,ref,target,guard):
        targets.append(np.asarray(target).copy());return original(side,ref,target,guard)
    a.move_point=move
    thread_piece(a,'red_square',{'actor':'red_square'},'left',[.15,.05,.81301],g['rotation'],g['post_indices'],'board')
    assert targets[0][2]==pytest.approx(.94) and max(p[2]for p in targets)==pytest.approx(.94)


def fixture(shift=(0,0,0),angle=0):
    s=load('E10','A',0,Path(__file__).parents[1]/'configs/realworld_full50_bindings.json',verify_files=False)
    sem=s['semantic'];rot=_axis_rotation([0,0,1],np.pi/2);piece_rot=rot@_axis_rotation([1,0,0],np.radians(angle))
    board=np.array([.14,0,.80001]);pos=np.array([.14,.06,.90])+shift
    a=SimpleNamespace(task='E10',s=sem,a=SimpleNamespace(control_report={'engineering_reference_only':True}),clearance=.95)
    a.objects={'red_square':{'shape':'square'}}
    a.a.scene=SimpleNamespace(objects={'red_square':SimpleNamespace(root_physx_view=SimpleNamespace(max_shapes=218))})
    a.frame=lambda ref:(board,rot)if ref['actor']=='board'else(pos.copy(),piece_rot)
    a.body_point=lambda ref,point:a.frame(ref)[0]+a.frame(ref)[1]@point
    a.point=lambda ref:a.body_point(ref,np.array(ref['local']));a.tip=lambda side:pos.copy()
    events=[];a.require_held=lambda *args:None;a.rotate_actor=lambda *args:None;a.stage=lambda name:events.append(name)
    a.move_point=lambda side,ref,target,guard:pos.__setitem__(slice(None),pos+np.asarray(target)-a.point(ref))
    def act(side,token,mm=.5,**kwargs):
        events.append(token)
        if token=='RELEASE':return
        pos[:]+=np.array({'UP':[0,0,1],'DOWN':[0,0,-1],'FWD':[1,0,0],'BACK':[-1,0,0],'LEFT':[0,1,0],'RIGHT':[0,-1,0]}[token])*mm/1000
    a.act=act;a.release=lambda *args:events.append('RELEASE');a.move=lambda *args:None;a.wait=lambda *args:None;a.contact=lambda *args:'RELEASE'in events
    a.snapshot=lambda:({'red_square':{'grasp':[False,False]}},set())
    return a,events,sem['structural_expert']['threading_targets']['red_square']


def test_four_measured_bores_have_source_clearance_and_distinct_posts():
    a,_,g=fixture();rows=post_clearances(a,'red_square',g['post_indices'])
    assert len(rows)==4 and all(r['margin_m']==pytest.approx(.0022)for r in rows)
    with pytest.raises(ToolExecutionError,match='own actual post'):post_clearances(a,'red_square',[5]*4)


def test_offset_and_tilt_are_not_hidden_by_first_hole_alignment():
    a,_,g=fixture(shift=(.0012,0,0),angle=8.4)
    rows=post_clearances(a,'red_square',g['post_indices'])
    assert min(r['margin_m']for r in rows)<.0022
    a,_,g=fixture(shift=(.003,0,0));assert min(r['margin_m']for r in post_clearances(a,'red_square',g['post_indices']))<0


def test_real_public_descent_precedes_release_and_actual_support_is_required():
    a,events,g=fixture();p=a.s['posts'][g['post_indices'][0]];target=a.body_point(p['ref'],p['base_local'])+[0,0,.004]
    thread_piece(a,'red_square',{'actor':'red_square'},'left',target,g['rotation'],g['post_indices'],'board')
    assert 0<events.count('DOWN')<50 and events[-1]=='RELEASE'
    assert len(a.a.control_report['e10_precise_threading'][0]['actual_final_holes'])==4
    a,events,g=fixture();a.contact=lambda *args:False
    with pytest.raises(ToolExecutionError,match='actual board support'):
        thread_piece(a,'red_square',{'actor':'red_square'},'left',target,g['rotation'],g['post_indices'],'board')


def test_original_native_bore_rule_does_not_require_extra_full_depth_clearance():
    a,_,g=fixture(shift=(.002,0,-.05),angle=6.)
    rows=post_clearances(a,'red_square',g['post_indices'])
    assert min(r['margin_m']for r in rows)<0.
    assert all(r['native_threaded']for r in rows)


def test_coarse_placement_keeps_original_native_failure_visible_and_rejects_large_tilt():
    a,_,g=fixture(shift=(0,0,-.05),angle=21.)
    rows=post_clearances(a,'red_square',g['post_indices'])
    assert all(r['coarse_shaft_crosses_bore']for r in rows)
    assert not any(r['native_threaded']for r in rows)
    a,_,g=fixture(shift=(0,0,-.05),angle=45.)
    assert not any(r['coarse_shaft_crosses_bore']for r in post_clearances(a,'red_square',g['post_indices']))


def test_lost_grip_prevents_all_precision_actions_and_release():
    a,events,g=fixture()
    def lost(*args):raise ToolExecutionError('real grip lost')
    a.require_held=lost
    with pytest.raises(ToolExecutionError,match='real grip lost'):
        thread_piece(a,'red_square',{'actor':'red_square'},'left',[.15,.05,.81301],g['rotation'],g['post_indices'],'board')
    assert 'DOWN'not in events and 'RELEASE'not in events


def test_tilted_piece_near_posts_never_forced_down_or_rotated_in_contact():
    a,events,g=fixture(shift=(0,0,-.035),angle=15.)
    a.move_point=lambda *args:None
    with pytest.raises(ToolExecutionError,match='multi-hole clearance lost'):
        thread_piece(a,'red_square',{'actor':'red_square'},'left',[.15,.05,.81301],g['rotation'],g['post_indices'],'board')
    assert 'DOWN'not in events and 'RELEASE'not in events


def test_missing_runtime_collision_piece_is_refused_before_any_threading_action():
    a,events,g=fixture();a.a.scene.objects['red_square'].root_physx_view.max_shapes=217
    with pytest.raises(ToolExecutionError,match='runtime collision shape count'):
        thread_piece(a,'red_square',{'actor':'red_square'},'left',[.15,.05,.81301],g['rotation'],g['post_indices'],'board')
    assert not events


def test_engaged_precision_resume_accepts_small_gravity_gap_without_replaying_approach():
    from videoicl_isaaclab.execution_design_e10_insertion import thread_precision
    a,events,g=fixture(shift=(0,0,-.0845));a.move_point=lambda *args:pytest.fail('Cannot repeat prefix approach')
    p=a.s['posts'][g['post_indices'][0]];target=a.body_point(p['ref'],p['base_local'])+[0,0,.004]
    report=thread_precision(a,'red_square',{'actor':'red_square'},'left',target,g['rotation'],g['post_indices'],'board',descent_mm=1.,release=False)
    assert report['ready_for_release'] and report['whole_task_score']is None and 'RELEASE'not in events
    assert 'DOWN'not in events  # All bores already engaged; only2.5mm above physical seating.


def test_engaged_release_uses_actual_holes_and_native_support_without_old_hold_claim():
    from videoicl_isaaclab.execution_design_e10_insertion import release_engaged_piece
    a,events,g=fixture(shift=(0,0,-.0845))
    a.require_held=lambda *args:pytest.fail('Release fixture does not assert historical held reconstruction')
    report=release_engaged_piece(a,'red_square',{'actor':'red_square'},'left',[.15,.05,.81301],g['rotation'],g['post_indices'],'board')
    assert report['actual_released_board_support'] and report['whole_task_score']is None
    assert events==['release-engaged-red_square','RELEASE']
    a,events,g=fixture(shift=(.004,0,-.0845))
    with pytest.raises(ToolExecutionError,match='not engaged'):
        release_engaged_piece(a,'red_square',{'actor':'red_square'},'left',[.15,.05,.81301],g['rotation'],g['post_indices'],'board')
    assert 'RELEASE'not in events


def test_released_stack_uses_original_native_support_chain_not_direct_board_only():
    from videoicl_isaaclab.execution_design_e10_insertion import physical_post_support
    a,_,_=fixture();state={n:{'grasp':[False,False]}for n in('red_square','blue_square','green_square')}
    edges={frozenset(('red_square','blue_square')),frozenset(('blue_square','board'))}
    a.contact=lambda n,b:frozenset((n,b))in edges
    assert 'red_square'in physical_post_support(a,state,'board')
    state['blue_square']['grasp']=[True,False]
    assert 'red_square'not in physical_post_support(a,state,'board')


def test_complete_original_bores_can_settle_along_their_posts_without_a_private_seat_coordinate():
    from videoicl_isaaclab.execution_design_e10_insertion import thread_precision
    a,events,g=fixture(shift=(.001905,0,-.046))
    a.move_point=lambda *args:pytest.fail('No high approach replay')
    rows=post_clearances(a,'red_square',g['post_indices'])
    assert 0<min(x['margin_m']for x in rows)<.0003
    assert max(x['gap_above_tip_m']for x in rows)<-.006
    report=thread_precision(a,'red_square',{'actor':'red_square'},'left',[.15,.05,.81301],g['rotation'],g['post_indices'],'board',release=False)
    assert report['ready_for_release'] and 'DOWN'not in events
