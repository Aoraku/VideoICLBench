import itertools
from types import SimpleNamespace
import numpy as np
import pytest
from videoicl_isaaclab import execution_design_e08_branch as shoe
from videoicl_isaaclab import execution_design_e13_branch as phone
from videoicl_isaaclab.execution_design_branch_geometry import swept_pose_clearance
from videoicl_isaaclab.realworld_tool_expert import ToolExecutionError,_axis_rotation


def box(center,half):return np.array(center)+np.array(list(itertools.product((-1,1),repeat=3)))*np.array(half)


def test_full_hand_sweep_catches_palm_even_when_payload_and_fingers_clear():
    obstacle=box([.1,0,.95],[.01,.02,.02]);bodies={'panda_hand':box([0,0,.95],[.01,.01,.01]),'payload':box([0,0,1.1],[.02,.01,.01])}
    with pytest.raises(ToolExecutionError,match='panda_hand.*stand'):
        swept_pose_clearance(bodies,[0,0,.95],[.2,0,.95],np.eye(3),{'stand':[obstacle]},.8)


def test_allowed_payload_support_never_allows_palm_contact():
    support=box([0,0,.85],[.04,.04,.03]);payload=box([0,0,.88],[.01,.01,.01]);hand=box([0,0,1.05],[.01,.01,.01])
    assert swept_pose_clearance({'payload':payload,'hand':hand},[0,0,1.], [0,0,1.],np.eye(3),{'box':[support]},.8,('box',))
    with pytest.raises(ToolExecutionError,match='hand.*box'):
        swept_pose_clearance({'payload':payload,'hand':support},[0,0,1.],[0,0,1.],np.eye(3),{'box':[support]},.8,('box',))


def test_rotation_arc_guard_does_not_approve_table_crossing():
    hand=box([0,0,.84],[.01,.01,.06])
    with pytest.raises(ToolExecutionError,match='table'):
        swept_pose_clearance({'hand':hand},[0,0,.9],[0,0,.9],np.eye(3),{},.8)


class FakePolicy:
    def __init__(self,actor):
        self.actor=actor;self.r=np.eye(3);self.calls=[];self.pending=0.;self.held=True;self.variant='A'
        self.s={'phone':'phone','camera_end_points':{'phone':[.07,0,0]},'back_normals':{'phone':[0,0,1]}}
        self.min_mm=.5;self.max_mm=12.;self.min_deg=.5;self.max_deg=10.;self.a=SimpleNamespace()
        self.c=SimpleNamespace(steps=1036 if actor=='phone' else 225,action_feedback=lambda:{'control_feedback':{'left':{'orientation_error_rad':self.pending}}})
    def snapshot(self):return {self.actor:{'mat':self.r,'pos':np.array([0.,0.,1.]),'grasp':[self.held,False]}},set()
    def tip(self,side):return np.array([0.,0.,1.])
    def contact(self,*args):return False
    def act(self,side=None,token='STILL',mm=1.,degrees=5.,follower=None):
        self.calls.append(token);self.c.steps+=1
        labels={'ROLL_LEFT':(0,1),'ROLL_RIGHT':(0,-1),'PITCH_UP':(1,1),'PITCH_DOWN':(1,-1),'ROTATE_CCW':(2,1),'ROTATE_CW':(2,-1)}
        if token in labels:
            axis,sign=labels[token];self.r=_axis_rotation(np.eye(3)[axis],sign*np.deg2rad(degrees))@self.r;self.pending=.1
        elif token=='STILL':self.pending/=3
        elif token=='RELEASE':self.held=False


class FakeGeometry:
    def __init__(self,p,*args,**kwargs):self.p=p;self.side='left'
    def __call__(self):
        if not self.p.held:raise ToolExecutionError('Actual grip lost')
    def check(self,**kwargs):self()
    def rotate(self,*args):self()


def setup(monkeypatch,module,actor):
    p=FakePolicy(actor);monkeypatch.setattr(module,'_policy',lambda author,context:p);monkeypatch.setattr(module,'HeldGeometry',FakeGeometry)
    return p


def test_shoe_chunk_is_local_public_rotation_and_holds_without_replaying_pickup(monkeypatch):
    p=setup(monkeypatch,shoe,'left_shoe');context={'actor':'left_shoe','side':'left','support':'box','target_actor_rotation':_axis_rotation([0,0,1],np.pi).tolist()}
    result=shoe.run_branch(object(),context,'yaw_ccw_chunk')
    assert p.calls.count('ROTATE_CCW')==6 and p.calls.count('STILL')==18
    assert set(p.calls)=={'ROTATE_CCW','STILL'}
    assert result['local_completed'] and not result['original_orientation_reached']
    assert result['whole_task_score']is None and result['physics_success_not_asserted']
    assert context['rotation_commands_used']==6


def test_shoe_larger_debug_chunk_keeps_original120_round_bound(monkeypatch):
    p=setup(monkeypatch,shoe,'left_shoe')
    context={'actor':'left_shoe','side':'left','support':'box','rotation_commands':120,'rotation_commands_used':110}
    result=shoe.run_branch(object(),context,'yaw_ccw_chunk')
    assert p.calls.count('ROTATE_CCW')==10 and context['rotation_commands_used']==120
    assert result['whole_task_score']is None
    p.calls.clear();context.update(rotation_commands=121,rotation_commands_used=0)
    with pytest.raises(ValueError,match='120command'):shoe.run_branch(object(),context,'yaw_ccw_chunk')
    assert not p.calls


def test_phone_chunk_preserves_original_goal_and_returns_only_local_result(monkeypatch):
    p=setup(monkeypatch,phone,'phone');context={'support':'stand','goal':{'pitch':-1.0272375716022242}}
    result=phone.run_branch(object(),context,'rotate_chunk')
    assert result['native_orientation']['allowed'] and result['whole_task_score']is None
    assert not result['original_orientation_reached'] and result['remaining_rotation_degrees']>6
    assert 'GRASP'not in p.calls and 'RELEASE'not in p.calls


@pytest.mark.parametrize('module,actor,branch,context',[(shoe,'left_shoe','place_left_to_release',{'actor':'left_shoe','side':'left','support':'box','target_actor_rotation':_axis_rotation([0,0,1],1.).tolist(),'control_local':[0,0,0],'destination_point_task':[0,0,.85],'material_clearance_z':1.12}),(phone,'phone','place_to_release',{'support':'stand','goal':{'pitch':1.}})])
def test_placement_refuses_unreached_original_orientation_before_commands(monkeypatch,module,actor,branch,context):
    p=setup(monkeypatch,module,actor)
    with pytest.raises(ToolExecutionError,match='orientation must converge'):module.run_branch(object(),context,branch)
    assert not p.calls


def test_first_real_guard_failure_stops_without_extra_hold(monkeypatch):
    p=setup(monkeypatch,phone,'phone');original=p.act
    def lose_after_one(*args,**kwargs):original(*args,**kwargs);p.held=False
    p.act=lose_after_one
    with pytest.raises(ToolExecutionError,match='grip lost'):phone.run_branch(object(),{'support':'stand','goal':{'pitch':1.}},'rotate_chunk')
    assert len(p.calls)==1 and 'STILL'not in p.calls


@pytest.mark.parametrize('module,actor,context,branch',[(shoe,'left_shoe',{'actor':'left_shoe','side':'left','support':'box','rotation_commands_used':120,'target_actor_rotation':_axis_rotation([0,0,1],1.).tolist()},'yaw_short_chunk'),(phone,'phone',{'support':'stand','rotation_commands_used':80,'goal':{'pitch':1.}},'rotate_chunk')])
def test_checkpoint_chunks_do_not_reset_original_rotation_round_bound(monkeypatch,module,actor,context,branch):
    p=setup(monkeypatch,module,actor)
    with pytest.raises(ValueError,match='round|Round|120|80'):module.run_branch(object(),context,branch)
    assert not p.calls


@pytest.mark.parametrize('module',[shoe,phone])
def test_unknown_branch_cannot_construct_author_or_issue_actions(module):
    with pytest.raises(ValueError,match='Unknown'):module.run_branch(object(),{},'full_pickup')


def test_unfinished_rotation_cannot_be_overwritten_after_hold_bound(monkeypatch):
    p=setup(monkeypatch,phone,'phone');original=p.act
    def stuck_hold(*args,**kwargs):
        original(*args,**kwargs)
        if len(args)>1 and args[1]=='STILL':p.pending=.1
    p.act=stuck_hold
    with pytest.raises(ToolExecutionError,match='did not settle'):
        phone.run_branch(object(),{'support':'stand','goal':{'pitch':1.}},'rotate_chunk')
    assert p.calls.count('PITCH_UP')==1 and p.calls.count('STILL')==6


def test_shoe_existing225_allows_local_ccw_diagnostic_without_inventing_original_goal(monkeypatch):
    p=setup(monkeypatch,shoe,'left_shoe');context={'actor':'left_shoe','side':'left','support':'box'}
    result=shoe.run_branch(object(),context,'yaw_ccw_chunk')
    assert p.calls.count('ROTATE_CCW')==6
    assert result['original_orientation_reached']is None
    assert not result['original_placement_parameters_available']
    p.calls.clear()
    with pytest.raises(ValueError,match='cannot guess'):shoe.run_branch(object(),context,'place_left_to_release')
    assert not p.calls


def test_phone_reports_intermediate_convergence_separately_from_original_goal(monkeypatch):
    p=setup(monkeypatch,phone,'phone');context={'support':'stand','goal':{'pitch':1.},'intermediate_actor_rotation':_axis_rotation([0,0,1],.005).tolist()}
    result=phone.run_branch(object(),context,'rotate_intermediate_chunk')
    assert result['intermediate_orientation_reached']
    assert result['intermediate_remaining_degrees']==pytest.approx(np.degrees(.005))
    assert not result['original_orientation_reached'] and result['whole_task_score']is None
    assert not p.calls


def test_phone_hold_pending_preserves_original_target_and_rotation_count(monkeypatch):
    p=setup(monkeypatch,phone,'phone');p.pending=.1
    context={'support':'stand','goal':{'pitch':1.},'rotation_commands_used':17}
    before=p.r.copy();result=phone.run_branch(object(),context,'hold_pending')
    assert p.calls==['STILL']*3
    assert context['rotation_commands_used']==17 and result['context_updates']['rotation_commands_used']==17
    np.testing.assert_array_equal(p.r,before)
    assert not result['original_orientation_reached'] and result['whole_task_score']is None


def test_phone_pending_escape_is_explicit_public_reanchor_then_reviewed_stage(monkeypatch):
    p=setup(monkeypatch,phone,'phone');p.pending=.05;stages=[]
    monkeypatch.setattr(FakeGeometry,'move',lambda self,target:stages.append(target.copy()),raising=False)
    goal={'pitch':-1.0272375716022242};context={'variant':'A','support':'stand','goal':goal.copy(),
        'rotation_commands_used':17,'staging_tcp':[-.28,.24,.98]}
    result=phone.run_branch(object(),context,'escape_pending_stage')
    assert p.calls[0]=='PITCH_DOWN'and set(p.calls)=={'PITCH_DOWN','STILL'}
    assert len(stages)==3 and stages[0][0]==-.28 and stages[1][1]==.24 and stages[2][2]==.98
    assert context['goal']==goal and context['rotation_commands_used']==18
    assert context['superseded_pending_error_rad']==pytest.approx(.05)
    assert result['pending_escape_strategy']=='public_pitch_down2_then_axis_stage_v1'
    assert result['whole_task_score']is None


def test_phone_pending_escape_stops_failed_new_turn_before_any_translation(monkeypatch):
    p=setup(monkeypatch,phone,'phone');p.pending=.05;stages=[];original=p.act
    monkeypatch.setattr(FakeGeometry,'move',lambda self,target:stages.append(target.copy()),raising=False)
    def stuck_hold(*args,**kwargs):
        original(*args,**kwargs)
        if len(args)>1 and args[1]=='STILL':p.pending=.05
    p.act=stuck_hold
    context={'variant':'A','support':'stand','goal':{'pitch':-1.0272375716022242},
        'rotation_commands_used':17,'staging_tcp':[-.28,.24,.98]}
    with pytest.raises(ToolExecutionError,match='did not settle'):phone.run_branch(object(),context,'escape_pending_stage')
    assert p.calls==['PITCH_DOWN']+['STILL']*6 and not stages
    assert context['rotation_commands_used']==18


@pytest.mark.parametrize('patch',[{'variant':'B'},{'staging_tcp':[-.2,.24,.98]},{'rotation_commands_used':80}])
def test_phone_pending_escape_requires_reviewed_scope_and_preserves_round_limit(monkeypatch,patch):
    p=setup(monkeypatch,phone,'phone');p.pending=.05
    context={'variant':'A','support':'stand','goal':{'pitch':-1.0272375716022242},
        'rotation_commands_used':17,'staging_tcp':[-.28,.24,.98],**patch}
    with pytest.raises(ValueError,match='Reviewed|80-round'):phone.run_branch(object(),context,'escape_pending_stage')
    assert not p.calls


def test_native_convex_decomposition_reader_preserves_cooked_pieces_without_mutation():
    from videoicl_isaaclab.execution_design_branch_geometry import cooked_mesh_vertices
    floor=box([0,0,.81],[.1,.1,.01]);wall=box([.1,0,.9],[.01,.1,.1]);calls=[]
    class Cooking:
        def request_convex_collision_representation(self,stage,path,flag,callback):
            calls.append((stage,path,flag));callback('success',[SimpleNamespace(vertices=floor),SimpleNamespace(vertices=wall)])
    result=cooked_mesh_vertices(Cooking(),17,'/World/Rooms/room00/Props/box/collision',lambda path:99)
    assert calls==[(17,99,False)] and len(result)==2
    np.testing.assert_array_equal(result[0],floor)
    np.testing.assert_array_equal(result[1],wall)


def test_unavailable_actual_cooked_geometry_fails_closed():
    from videoicl_isaaclab.execution_design_branch_geometry import cooked_mesh_vertices
    cooking=SimpleNamespace(request_convex_collision_representation=lambda *args:None)
    with pytest.raises(ToolExecutionError,match='unavailable'):cooked_mesh_vertices(cooking,1,'/box',lambda p:1)


def test_cooked_geometry_rejects_partial_success_with_one_malformed_hull():
    from videoicl_isaaclab.execution_design_branch_geometry import cooked_mesh_vertices
    def call(stage,path,flag,callback):callback('success',[SimpleNamespace(vertices=box([0,0,1],[.1,.1,.1])),SimpleNamespace(vertices=[[0,0,0]])])
    with pytest.raises(ToolExecutionError,match='incomplete'):
        cooked_mesh_vertices(SimpleNamespace(request_convex_collision_representation=call),1,'/box',lambda p:1)


def test_source_plan_adoption_is_explicit_new_strategy_not_historical166(monkeypatch):
    p=setup(monkeypatch,shoe,'left_shoe')
    def prepared(author,context):
        return dict(context,new_reference_strategy=True,reference_strategy_origin='new_source_axes_and_measured_cavity_v1',historical_166_parameters_available=False,
                    target_actor_rotation=_axis_rotation([0,0,1],1.).tolist(),control_local=[0,0,-.05],destination_point_task=[0,0,.81],material_clearance_z=1.12,
                    reference_orientation_tolerance_degrees=.25)
    monkeypatch.setattr(shoe,'prepare_new_source_context',prepared)
    context={'actor':'left_shoe','side':'left','support':'box'};result=shoe.run_branch(object(),context,'adopt_source_plan')
    assert p.calls==['STILL']
    assert result['new_reference_strategy'] and not result['historical_166_parameters_available']
    assert not result['original_placement_parameters_available'] and result['reference_placement_parameters_available']
    assert result['original_orientation_reached']is None and result['whole_task_score']is None


def test_actual_cooked_floor_ray_preserves_open_cavity_and_detects_solid_cook():
    from videoicl_isaaclab.execution_design_branch_geometry import cooked_floor_height
    floor=box([0,0,-.052],[.17,.096,.005]);wall=box([.174,0,0],[.004,.1,.055])
    assert cooked_floor_height([floor,wall],[0,0,0],np.eye(3),[0,.046],.055)==pytest.approx(-.047,abs=1e-8)
    solid=box([0,0,0],[.175,.1,.055])
    assert cooked_floor_height([solid],[0,0,0],np.eye(3),[0,.046],.055)==pytest.approx(.055,abs=1e-8)


def test_new_shoe_strategy_stops_at_native_geometry_instead_of_chasing_recipe_angle(monkeypatch):
    p=setup(monkeypatch,shoe,'left_shoe')
    monkeypatch.setattr(shoe,'_source_settled_geometry',lambda p,c:{'acceptable':True})
    context={'actor':'left_shoe','side':'left','support':'box','target_actor_rotation':_axis_rotation([0,0,1],.2).tolist(),
        'new_reference_strategy':True,'reference_orientation_tolerance_degrees':.25,
        'release_horizontal_velocity_limit_m_s':.001,'release_angular_velocity_limit_rad_s':.01}
    result=shoe.run_branch(object(),context,'yaw_short_chunk')
    assert not p.calls and result['reference_orientation_reached']
    assert result['remaining_rotation_degrees']>4 and result['original_orientation_reached']is None
    assert not any(k in context for k in('reference_orientation_tolerance_degrees','release_horizontal_velocity_limit_m_s','release_angular_velocity_limit_rad_s'))


def test_new_shoe_recipe_nearby_angle_cannot_bypass_actual_cavity_geometry(monkeypatch):
    p=setup(monkeypatch,shoe,'left_shoe')
    monkeypatch.setattr(shoe,'_source_settled_geometry',lambda p,c:{'acceptable':False})
    context={'actor':'left_shoe','side':'left','support':'box','target_actor_rotation':_axis_rotation([0,0,1],.001).tolist(),
        'new_reference_strategy':True,'rotation_commands':1}
    result=shoe.run_branch(object(),context,'yaw_short_chunk')
    assert p.calls.count('ROTATE_CCW')==1 and not result['reference_orientation_reached']


def test_shoe_completion_preserves_original_count_and_continues_to_placement_in_same_world(monkeypatch):
    p=setup(monkeypatch,shoe,'left_shoe');calls=[];complete=shoe.run_branch
    def phase(author,context,name):
        calls.append(name)
        if name=='yaw_short_chunk':
            assert context['rotation_commands']==120 and context['rotation_commands_used']==36
            context['rotation_commands_used']+=7;p.c.steps+=21
            return {'reference_orientation_reached':True,'actions':21}
        assert context['rotation_commands_used']==43;p.c.steps+=70
        return {'local_completed':True,'whole_task_score':None,'actions':70,'post_release_retreat_executed':True}
    monkeypatch.setattr(shoe,'run_branch',phase)
    context={'actor':'left_shoe','new_reference_strategy':True,'reference_strategy_origin':'new_source_axes_and_measured_cavity_v1',
        'historical_166_parameters_available':False,'rotation_commands_used':36}
    result=complete(object(),context,'complete_left_from_held')
    assert calls==['yaw_short_chunk','place_left_to_release']and result['actions']==91
    assert context['rotation_commands_used']==43 and context['e08_held_completion_phase']=='complete_left'
    assert result['whole_task_score']is None and result['post_release_retreat_executed']


def test_shoe_completion_never_places_after_exhausted_or_failed_orientation(monkeypatch):
    setup(monkeypatch,shoe,'left_shoe');calls=[];complete=shoe.run_branch
    def phase(author,context,name):
        calls.append(name);context['rotation_commands_used']=120
        return {'reference_orientation_reached':False,'actions':84}
    monkeypatch.setattr(shoe,'run_branch',phase)
    context={'actor':'left_shoe','new_reference_strategy':True,'reference_strategy_origin':'new_source_axes_and_measured_cavity_v1',
        'historical_166_parameters_available':False,'rotation_commands_used':36}
    with pytest.raises(ToolExecutionError,match='rotation bound'):complete(object(),context,'complete_left_from_held')
    assert calls==['yaw_short_chunk']and context['rotation_commands_used']==120
    assert context['e08_held_completion_phase']=='orient_left'


def test_phone_completion_turns_only_to_native_allowance_then_places_without_reconstruction(monkeypatch):
    p=setup(monkeypatch,phone,'phone');calls=[];complete=phone.run_branch
    def phase(author,context,name):
        calls.append(name)
        if name=='rotate_chunk':
            assert context['rotation_commands_used']==35 and context['rotation_commands']==6
            context['rotation_commands_used']+=2;p.c.steps+=8;p.r=_axis_rotation([0,1,0],-1.)
            return {'actions':8}
        assert name=='place_to_release';p.c.steps+=90
        return {'actions':90,'whole_task_score':None,'post_release_retreat_executed':True}
    monkeypatch.setattr(phone,'run_branch',phase)
    context={'rotation_commands_used':35};result=complete(object(),context,'complete_from_held')
    assert calls==['rotate_chunk','place_to_release']and result['actions']==98
    assert context['rotation_commands_used']==37 and context['e13_held_completion_phase']=='complete_phone'
    assert result['whole_task_score']is None


def test_phone_completion_preserves_original80_round_limit_before_placement(monkeypatch):
    setup(monkeypatch,phone,'phone');calls=[];complete=phone.run_branch
    monkeypatch.setattr(phone,'run_branch',lambda *args:calls.append(args[-1]))
    with pytest.raises(ToolExecutionError,match='original80'):
        complete(object(),{'rotation_commands_used':80},'complete_from_held')
    assert not calls


def test_new_shoe_task_geometry_can_finish_before_private_pending_angle_threshold(monkeypatch):
    p=setup(monkeypatch,shoe,'left_shoe')
    monkeypatch.setattr(shoe,'_source_settled_geometry',lambda policy,context:{'acceptable':bool(p.calls)})
    context={'actor':'left_shoe','side':'left','support':'box','new_reference_strategy':True,
        'target_actor_rotation':_axis_rotation([0,0,1],1.).tolist()}
    result=shoe.run_branch(object(),context,'yaw_short_chunk')
    assert p.calls==['ROTATE_CCW']and p.pending==.1
    assert result['reference_orientation_reached']and result['whole_task_score']is None


def test_task_acceptance_cannot_bypass_real_held_geometry_guard():
    from videoicl_isaaclab.execution_design_branch_geometry import public_rotation_holds
    p=FakePolicy('left_shoe');p.held=False;p.pending=.1
    with pytest.raises(ToolExecutionError,match='grip lost'):
        public_rotation_holds(p,'left',FakeGeometry(p),task_accepted=lambda:True)
    assert not p.calls
