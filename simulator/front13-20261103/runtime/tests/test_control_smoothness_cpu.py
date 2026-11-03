"""Exercise staged production control semantics without Isaac or simulation."""
import ast
import math
from pathlib import Path
from types import SimpleNamespace, MethodType
import pytest
import torch

SOURCE=Path(__file__).resolve().parents[1]/'videoicl_isaaclab/control.py'
TREE=ast.parse(SOURCE.read_text())
NS={'torch':torch,'math':math}
nodes=[n for n in TREE.body if isinstance(n,(ast.FunctionDef,ast.Assign)) or
       (isinstance(n,ast.Expr) and isinstance(n.value,ast.Call) and
        isinstance(n.value.func,ast.Attribute) and isinstance(n.value.func.value,ast.Name) and
        n.value.func.value.id=='MOTION' and n.value.func.attr=='update')]
exec(compile(ast.Module(body=nodes,type_ignores=[]),str(SOURCE),'exec'),NS)
CLS=next(n for n in TREE.body if isinstance(n,ast.ClassDef) and n.name=='Controller')
for name in ['validate_action','begin_action','tick','public_action_converged','action_feedback']:
    method=next(n for n in CLS.body if isinstance(n,ast.FunctionDef) and n.name==name)
    exec(compile(ast.Module(body=[method],type_ignores=[]),str(SOURCE),'exec'),NS)

def qz(degrees):
    a=math.radians(degrees)/2
    return torch.tensor([[math.cos(a),0.,0.,math.sin(a)]])

def apply_pose(p,q,delta):
    # Independent axis-angle quaternion composition, base-frame increment.
    rv=delta[:,3:];angle=rv.norm(dim=-1,keepdim=True)
    xyz=rv*torch.where(angle>1e-8,torch.sin(angle/2)/angle.clamp_min(1e-8),torch.full_like(angle,.5))
    a=torch.cat((torch.cos(angle/2),xyz),dim=-1)
    result=torch.cat((a[:,:1]*q[:,:1]-(a[:,1:]*q[:,1:]).sum(-1,keepdim=True),
                      a[:,:1]*q[:,1:]+q[:,:1]*a[:,1:]+torch.cross(a[:,1:],q[:,1:],dim=-1)),dim=-1)
    return p+delta[:,:3],result

NS.update(apply_delta_pose=apply_pose,quat_apply_inverse=lambda q,v:v,
          quat_apply=lambda q,v:v,matrix_from_quat=lambda q:torch.eye(3,dtype=q.dtype)[None],
          skew_symmetric_matrix=lambda v:torch.zeros((1,3,3),dtype=v.dtype))

def controller(continuing=True):
    p=torch.zeros((1,3));measured=qz(0)
    robots={s:SimpleNamespace(data=SimpleNamespace(root_quat_w=qz(0))) for s in ('left','right')}
    c=SimpleNamespace(scene=SimpleNamespace(robots=robots,layout=SimpleNamespace(task_rotation=torch.eye(3)),
        embodiment=SimpleNamespace(config={'control':{'step_mm':[.5,50.],'rotation_deg':[.5,20.]}})),
        device='cpu',evaluator=SimpleNamespace(event_enabled=False),steps=7,
        pose=lambda side:(p,measured),grips={'left':.04,'right':.04},
        targets={s:(p.clone(),qz(40)) for s in robots},
        _public_action={'left':'STILL','right':'STILL'} if continuing else None,
        _public_reference={'left':torch.tensor([[.12]])},
        _public_reference_velocity={'left':torch.tensor([[.2]])})
    c.validate_action=MethodType(NS['validate_action'],c)
    return c

def test_explicit_rotation_rebases_measured_quaternion_and_reports_superseded_error():
    c=controller()
    NS['begin_action'](c,left='ROTATE_CW',rotation_deg=5.)
    torch.testing.assert_close(c.targets['left'][1],qz(-5),atol=1e-7,rtol=1e-6)
    assert c._public_superseded_orientation['left'].item()==pytest.approx(math.radians(40))
    assert c.steps==7

@pytest.mark.parametrize('token',['UP','STILL','GRASP','RELEASE'])
def test_nonrotation_preserves_held_quaternion(token):
    c=controller();old=c.targets['left'][1].clone()
    NS['begin_action'](c,left=token)
    torch.testing.assert_close(c.targets['left'][1],old)
    assert 'left' not in c._public_superseded_orientation
    if token=='GRASP':assert c.grips['left']==0.
    if token=='RELEASE':assert c.grips['left']==.04

@pytest.mark.parametrize('continuing',[True,False])
def test_reference_continues_only_across_public_actions(continuing):
    c=controller(continuing)
    ref=c._public_reference['left'].clone();velocity=c._public_reference_velocity['left'].clone()
    NS['begin_action'](c)
    if continuing:
        torch.testing.assert_close(c._public_reference['left'],ref)
        torch.testing.assert_close(c._public_reference_velocity['left'],velocity)
    else:
        assert c._public_reference=={} and c._public_reference_velocity=={}

def test_transient_failure_recovers_and_counter_is_consecutive():
    f=NS['public_refusal_state'];blocked=torch.tensor([False]);count=torch.tensor([0]);no=torch.tensor([False]);yes=~no
    for _ in range(5):blocked,count=f(blocked,count,no,no,6)
    assert not blocked.item() and count.item()==5
    blocked,count=f(blocked,count,yes,no,6)
    assert not blocked.item() and count.item()==0
    for _ in range(6):blocked,count=f(blocked,count,no,no,6)
    assert blocked.item() and count.item()==6
    blocked,count=f(blocked,count,yes,no,6)
    assert blocked.item()  # Latch lasts for this command, even if solve recovers.

def test_hard_failure_latches_immediately_and_arms_are_independent():
    b,c=NS['public_refusal_state'](torch.tensor([False,False]),torch.tensor([0,0]),
                                torch.tensor([False,False]),torch.tensor([True,False]),6)
    assert b.tolist()==[True,False] and c.tolist()==[1,1]

def test_acceleration_bounds_use_reference_velocity_not_measured_offset():
    f=NS['accelerated_reference_bounds'];current=torch.tensor([[.1,.2]],dtype=torch.float64)
    reference=torch.tensor([[.11,.19]],dtype=torch.float64);v=torch.tensor([[.2,-.3]],dtype=torch.float64)
    lo=torch.full_like(v,-.02);hi=-lo;dt=.004;a=20.
    lower,upper,override=f(current,reference,v,lo,hi,dt,a)
    assert not override.item()
    for delta in (lower,upper):
        velocity=(current+delta-reference)/dt
        assert ((velocity-v).abs()<=a*dt+1e-10).all()
        assert (delta>=lo).all() and (delta<=hi).all()

def test_acceleration_conflict_reports_override_and_keeps_original_bounds():
    f=NS['accelerated_reference_bounds'];z=torch.zeros((1,2));v=torch.ones_like(z)*2
    lo=-torch.ones_like(z)*.001;hi=torch.zeros_like(z)
    lower,upper,override=f(z,z,v,lo,hi,.004,20.)
    assert override.item()
    torch.testing.assert_close(lower,lo);torch.testing.assert_close(upper,hi)

@pytest.mark.parametrize('degrees',[.5,5.])
def test_small_rotation_requires_positive_correct_angular_progress(degrees):
    e=torch.zeros((1,6));e[0,5]=math.radians(degrees);valid=torch.tensor([True]);guard=NS['public_motion_guard']
    assert guard(e,e*.2,valid,True).item()
    assert not guard(e,torch.zeros_like(e),valid,True).item()
    assert not guard(e,-e*.2,valid,True).item()
    assert not guard(e,e*1.5,valid,True).item()

def test_submillimeter_translation_and_endpoint_overshoot():
    e=torch.tensor([[0.,0.,.0005,0.,0.,0.]])
    g=NS['public_motion_guard'];v=torch.tensor([True])
    assert g(e,e*.5,v).item()
    assert not g(e,e*2,v).item()
    assert not g(e,-e,v).item()

@pytest.mark.parametrize('dtype',[torch.float32,torch.float64])
@pytest.mark.parametrize('residual_um,remaining_degrees',[(4.968,.498735),(4.854,.498673)])
@pytest.mark.parametrize('translation_um',[0.,-.1])
def test_native_probe_rotation_residual_allows_position_hold(dtype,residual_um,remaining_degrees,translation_um):
    # Measured magnitudes from E02B/E03A/E03C initial text/real probes.
    # Predicted candidates are synthetic; the probe did not capture Jacobians.
    residual=torch.tensor([[residual_um*1e-6,0.,0.,0.,0.,math.radians(remaining_degrees)]],dtype=dtype)
    predicted=torch.tensor([[translation_um*1e-6,0.,0.,0.,0.,math.radians(.05)]],dtype=dtype)
    assert NS['public_motion_guard'](residual,predicted,torch.tensor([True]),True).item()

@pytest.mark.parametrize('residual_um',[4.968,4.854])
@pytest.mark.parametrize('angular_degrees',[-.05,0.,.6])
def test_rotation_position_hold_does_not_relax_angular_direction_or_endpoint(residual_um,angular_degrees):
    residual=torch.tensor([[residual_um*1e-6,0.,0.,0.,0.,math.radians(.498)]],dtype=torch.float64)
    predicted=torch.tensor([[-.1e-6,0.,0.,0.,0.,math.radians(angular_degrees)]],dtype=torch.float64)
    assert not NS['public_motion_guard'](residual,predicted,torch.tensor([True]),True).item()

@pytest.mark.parametrize('distance,step,expected',[
    (.0019,-.0002,False),  # Small tick would leave the 2 mm hold envelope.
    (.0019,-.00005,True),  # Same direction of drift, endpoint remains inside.
    (0.,.001001,False),   # Endpoint inside envelope, but tick exceeds 1 mm.
    (0.,.000999,True),
    (.00201,0.,False),    # Outside envelope, corrective progress is required.
    (.00201,-.00001,False),
    (.00201,.0001,True),
])
def test_rotation_position_hold_preserves_endpoint_and_tick_bounds(distance,step,expected):
    residual=torch.tensor([[distance,0.,0.,0.,0.,math.radians(.5)]],dtype=torch.float64)
    predicted=torch.tensor([[step,0.,0.,0.,0.,math.radians(.05)]],dtype=torch.float64)
    assert NS['public_motion_guard'](residual,predicted,torch.tensor([True]),True).item()==expected

@pytest.mark.parametrize('distance',[4.968e-6,4.854e-6,.0005])
def test_translation_within_rotation_hold_envelope_still_requires_progress(distance):
    residual=torch.tensor([[distance,0.,0.,0.,0.,0.]],dtype=torch.float64)
    guard=NS['public_motion_guard'];valid=torch.tensor([True])
    assert guard(residual,residual*.5,valid,False).item()
    assert not guard(residual,torch.zeros_like(residual),valid,False).item()
    assert not guard(residual,-residual*.1,valid,False).item()
    assert not guard(residual,residual*2,valid,False).item()

def test_production_tick_retries_then_advances_with_accelerated_rolling_reference(monkeypatch):
    c=controller();q=torch.zeros((1,7));targets=[];root=qz(0)
    data=SimpleNamespace(root_quat_w=root,body_quat_w=root[:,None],joint_pos=torch.zeros((1,9)),
        joint_pos_limits=torch.tensor([[[-2.,2.]]*7+[[0.,.04]]*2]),joint_vel_limits=torch.ones((1,9))*5)
    robot=SimpleNamespace(data=data,is_fixed_base=True,
        root_physx_view=SimpleNamespace(get_coms=lambda:torch.zeros((1,1,7)),get_jacobians=lambda:torch.cat((torch.eye(6),torch.zeros((6,3))),dim=-1)[None,None]),
        set_joint_position_target=lambda value,joint_ids:targets.append((value.clone(),joint_ids)),write_data_to_sim=lambda:None)
    c.scene=SimpleNamespace(robots={'left':robot},embodiment=SimpleNamespace(tcp=[0.,0.,0.],arm_joints=[f'joint{i}' for i in range(7)],
        config={'physics':{'max_joint_delta':.08},'actuators':{'arm':{'velocity_limit':5.}},
                'control':{'rolling_joint_reference':True,'public_reference_acceleration_rad_s2':20.,'public_ik_retry_ticks':6}},
        gripper_values=lambda f:[f*.04]*2),apply_passive_efforts=lambda:None)
    c.dt=.004;c.ids={'left':(list(range(7)),[7,8],0)};c.ik={'left':SimpleNamespace(set_command=lambda x:None)}
    c.targets={'left':(torch.tensor([[0.,0.,.05]]),qz(0))};c._public_action={'left':'UP'}
    c._public_reference={};c._public_reference_velocity={};c._public_acceleration_override={}
    c._public_blocked={};c._public_blocked_before={};c._public_hold_q={};c._public_limit_seen={};c._author_ff_twists={}
    calls=[]
    def solve(J,residual,lo,hi,rotation):
        calls.append(1);dq=torch.zeros_like(lo)
        if len(calls)==1:return dq,torch.tensor([False])
        dq[:,2]=torch.minimum(hi[:,2],torch.tensor(.0001))
        return dq,torch.tensor([True])
    monkeypatch.setitem(NS,'guarded_cartesian_delta',solve)
    NS['tick'](c,phase='write')
    assert not c._public_blocked['left'].item()
    torch.testing.assert_close(targets[0][0],q)
    assert c._public_failures['left'].item()==1
    NS['tick'](c,phase='write')
    assert not c._public_blocked['left'].item()
    assert c._public_failures['left'].item()==0
    assert targets[2][0][0,2]>0
    assert c._public_acceleration_override['left'].item()


def linearized_test_plant(joints=7, response=1.,cartesian_jacobian=None):
    """Synthetic Cartesian joints + yaw, NOT robot FK, actuator physics or PhysX.

    Drives production tick and its real constrained solver with measured feedback.
    The optional first-order lag models tracking error only, not contact dynamics.
    """
    c=controller(False);root=qz(0);pending={};history=[]
    data=SimpleNamespace(root_quat_w=root,body_quat_w=root[:,None],joint_pos=torch.zeros((1,joints+2)),
        joint_pos_limits=torch.tensor([[[-2.,2.]]*joints+[[0.,.04]]*2]),
        joint_vel_limits=torch.ones((1,joints+2))*5.)
    J=torch.zeros((6,joints+2));J[:6,:6]=torch.eye(6)
    if cartesian_jacobian is not None:J[:,:joints]=cartesian_jacobian
    def set_target(value,joint_ids):
        if len(joint_ids)==joints:pending['arm']=value.clone()
    robot=SimpleNamespace(data=data,is_fixed_base=True,
        root_physx_view=SimpleNamespace(get_coms=lambda:torch.zeros((1,1,7)),get_jacobians=lambda:J[None,None]),
        set_joint_position_target=set_target,write_data_to_sim=lambda:None)
    c.scene=SimpleNamespace(robots={'left':robot},layout=SimpleNamespace(task_rotation=torch.eye(3)),
        embodiment=SimpleNamespace(tcp=[0.,0.,0.],arm_joints=[f'joint{i}' for i in range(joints)],
        config={'physics':{'max_joint_delta':.08},'actuators':{'arm':{'velocity_limit':5.}},
                'control':{'rolling_joint_reference':True,'public_reference_acceleration_rad_s2':20.,
                'public_ik_retry_ticks':6,'step_mm':[.5,50.],'rotation_deg':[.5,20.]}},
        gripper_values=lambda f:[f*.04]*2),apply_passive_efforts=lambda:None)
    c.dt=.004;c.ids={'left':(list(range(joints)),[joints,joints+1],0)}
    c.ik={'left':SimpleNamespace(set_command=lambda x:None)}
    def pose(side):
        measured=data.joint_pos[:,:joints]
        cartesian=measured@J[:,:joints].T
        yaw=cartesian[:,5:6]
        quat=torch.cat((torch.cos(yaw/2),torch.zeros((1,2)),torch.sin(yaw/2)),dim=-1)
        return cartesian[:,:3].clone(),quat
    c.pose=pose;c.targets={'left':pose('left')};c._public_reference={};c._public_reference_velocity={}
    c._public_acceleration_override={};c._public_blocked={};c._public_blocked_before={}
    c._public_hold_q={};c._public_limit_seen={};c._author_ff_twists={}
    def advance(ticks=1):
        for _ in range(ticks):
            NS['tick'](c,phase='write')
            before=data.joint_pos[:,:joints].clone()
            data.joint_pos[:,:joints]+=response*(pending['arm']-before)
            history.append({'q':data.joint_pos[:,:joints].clone(),'reference':pending['arm'].clone(),
                'ref_velocity':c._public_reference_velocity['left'].clone(),
                'acceleration_override':c._public_acceleration_override['left'].item(),
                'measured_before':before,
                'failures':c._public_failures['left'].item(),'blocked':c._public_blocked['left'].item()})
    return c,advance,history


@pytest.mark.parametrize('joints',[6,7])
@pytest.mark.parametrize('response',[1.,.2])
def test_closed_loop_translation_reaches_endpoint_without_drift(joints,response):
    c,advance,history=linearized_test_plant(joints,response)
    NS['begin_action'](c,left='UP',step_mm=50.)
    assert not NS['public_action_converged'](c)
    advance(300)
    z=c.pose('left')[0][0,2].item()
    assert z==pytest.approx(.05,abs=2e-5), history[-1]
    assert not c._public_blocked['left'].item()
    before=c.pose('left')[0].clone();advance(50)
    assert (c.pose('left')[0]-before).abs().max()<2e-5
    assert max(r['q'][0,2].item() for r in history)<=.050002
    assert max(r['reference'][0,2].item() for r in history)<=.050002
    assert NS['public_action_converged'](c)


@pytest.mark.parametrize('joints',[6,7])
@pytest.mark.parametrize('response',[1.,.2])
def test_closed_loop_half_degree_rotation_and_reverse(joints,response):
    c,advance,history=linearized_test_plant(joints,response)
    NS['begin_action'](c,left='ROTATE_CCW',rotation_deg=.5)
    # Before executing anything, the entire requested small angle remains.
    assert not NS['public_action_converged'](c)
    advance(300)
    yaw=history[-1]['q'][0,5].item()
    assert yaw==pytest.approx(math.radians(.5),abs=2e-5)
    assert not c._public_blocked['left'].item()
    end=history[-1]['q'].clone();advance(50)
    assert (history[-1]['q']-end).abs().max()<2e-5
    assert max(r['reference'][0,5].item() for r in history)<=math.radians(.5)+2e-6
    NS['begin_action'](c,left='ROTATE_CW',rotation_deg=.5)
    advance(300)
    assert history[-1]['q'][0,5].item()==pytest.approx(0.,abs=4e-5)
    assert not c._public_blocked['left'].item()


@pytest.mark.parametrize('response',[1.,.2])
def test_closed_loop_reversal_mid_motion_keeps_endpoint_and_bounds(response):
    c,advance,history=linearized_test_plant(7,response)
    NS['begin_action'](c,left='UP',step_mm=50.);advance(8)
    start=c.pose('left')[0][0,2].item()
    NS['begin_action'](c,left='DOWN',step_mm=20.);advance(300)
    assert c.pose('left')[0][0,2].item()==pytest.approx(start-.02,abs=2e-5)
    assert not c._public_blocked['left'].item()
    assert all(torch.isfinite(r['q']).all() for r in history)
    assert max(r['reference'].abs().max().item() for r in history)<2.


@pytest.mark.parametrize('token,magnitude,axis,target',[
    ('UP',.5,2,.0005),('ROTATE_CCW',.5,5,math.radians(.5)),
    ('ROTATE_CCW',5.,5,math.radians(5.))])
@pytest.mark.parametrize('joints',[6,7])
@pytest.mark.parametrize('response',[1.,.2])
def test_small_action_feedback_and_measured_completion(token,magnitude,axis,target,joints,response):
    c,advance,history=linearized_test_plant(joints,response)
    kwargs={'step_mm':magnitude} if token=='UP' else {'rotation_deg':magnitude}
    NS['begin_action'](c,left=token,**kwargs)
    assert not NS['public_action_converged'](c)
    assert NS['action_feedback'](c)['control_feedback']['left']['status']=='partial'
    for tick in range(300):
        advance()
        if NS['public_action_converged'](c):break
    else:pytest.fail('Measured completion was not reached within 300 ticks')
    assert not c._public_blocked['left'].item()
    measured=history[-1]['q'][0,axis].item()
    assert measured>=target*.9-1e-7
    assert measured<=target+2e-6
    assert NS['action_feedback'](c)['control_feedback']['left']['status']=='reached'
    advance(50)
    assert history[-1]['q'][0,axis].item()==pytest.approx(target,abs=2e-5)


def test_retry_pending_feedback_is_partial_even_at_cartesian_goal():
    c,advance,history=linearized_test_plant()
    NS['begin_action'](c,left='STILL')
    c._public_failures={'left':torch.tensor([1])}
    assert not NS['public_action_converged'](c)
    feedback=NS['action_feedback'](c)['control_feedback']['left']
    assert feedback['status']=='partial' and feedback['reason']=='ik_retry_pending'


@pytest.mark.parametrize('response',[1.,.2])
@pytest.mark.parametrize('token,magnitude',[('UP',50.),('UP',.5),('ROTATE_CCW',.5),('ROTATE_CCW',5.)])
@pytest.mark.parametrize('joints',[6,7])
def test_closed_loop_reference_velocity_acceleration_and_lead_constraints(response,token,magnitude,joints):
    c,advance,history=linearized_test_plant(joints,response)
    kwargs={'step_mm':magnitude} if token=='UP' else {'rotation_deg':magnitude}
    NS['begin_action'](c,left=token,**kwargs);advance(300)
    previous_ref=torch.zeros((1,joints));previous_velocity=torch.zeros_like(previous_ref)
    normal_ticks=0
    for row in history:
        # Safety override is latched for the whole public action. Once present,
        # no blanket acceleration promise is made for the remaining samples.
        if not row['acceleration_override']:
            actual_velocity=(row['reference']-previous_ref)/c.dt
            torch.testing.assert_close(actual_velocity,row['ref_velocity'],atol=1e-6,rtol=1e-5)
            assert (actual_velocity-previous_velocity).abs().max()<=20.*c.dt+2e-6
            assert actual_velocity.abs().max()<=5.+2e-6
            normal_ticks+=1
        assert (row['reference']-row['measured_before']).abs().max()<=.08+2e-6
        assert row['reference'].abs().max()<2.
        previous_ref=row['reference'];previous_velocity=row['ref_velocity']
    assert normal_ticks==300  # Ordinary endpoint braking must need no safety override.


@pytest.mark.parametrize('joints',[6,7])
@pytest.mark.parametrize('response',[1.,.2])
def test_coupled_joint_endpoint_brakes_without_safety_override(joints,response):
    J=torch.zeros((6,joints));J[:,:6]=torch.eye(6)
    # Orthogonal x/z mapping means a straight UP needs two joint coordinates.
    J[0,0]=.8;J[0,2]=.6;J[2,0]=-.6;J[2,2]=.8
    c,advance,history=linearized_test_plant(joints,response,J)
    NS['begin_action'](c,left='UP',step_mm=50.);advance(350)
    torch.testing.assert_close(c.pose('left')[0],torch.tensor([[0.,0.,.05]]),atol=2e-5,rtol=0.)
    assert not c._public_blocked['left'].item()
    assert not any(r['acceleration_override'] for r in history)
    prev_ref=torch.zeros((1,joints));prev_v=torch.zeros_like(prev_ref)
    for row in history:
        velocity=(row['reference']-prev_ref)/c.dt
        assert velocity.abs().max()<=5.+2e-6
        assert ((velocity-prev_v)/c.dt).abs().max()<=20.001
        prev_ref=row['reference'];prev_v=velocity


def sample_closed_loop_evidence():
    """Reproducible endpoint diagnostics; run this file directly to save evidence."""
    import hashlib
    original_bounds=NS['accelerated_reference_bounds'];original_solver=NS['guarded_cartesian_delta'];events=[]
    def observed_bounds(*args,**kwargs):
        result=original_bounds(*args,**kwargs)
        events[-1]['bounds_override']=bool(result[2].item())
        return result
    def observed_solver(*args,**kwargs):
        result=original_solver(*args,**kwargs)
        events[-1]['solver_refused']=not bool(result[1].item())
        return result
    NS['accelerated_reference_bounds']=observed_bounds;NS['guarded_cartesian_delta']=observed_solver
    rows=[]
    try:
        for joints in [6,7]:
            for response in [1.,.2]:
                for token,magnitude,axis,target,coupled in [('UP',50.,2,.05,False),('UP',.5,2,.0005,False),
                        ('ROTATE_CCW',.5,5,math.radians(.5),False),('ROTATE_CCW',5.,5,math.radians(5.),False),
                        ('UP',50.,2,.05,True)]:
                    J=None
                    if coupled:
                        J=torch.zeros((6,joints));J[:,:6]=torch.eye(6)
                        J[0,0]=.8;J[0,2]=.6;J[2,0]=-.6;J[2,2]=.8
                    c,advance,history=linearized_test_plant(joints,response,J)
                    kwargs={'step_mm':magnitude} if token=='UP' else {'rotation_deg':magnitude}
                    NS['begin_action'](c,left=token,**kwargs);events.clear();converged_tick=None
                    for tick in range(350):
                        events.append({});advance()
                        if converged_tick is None and NS['public_action_converged'](c):converged_tick=tick+1
                    prev_ref=torch.zeros((1,joints));prev_v=torch.zeros_like(prev_ref);prior_override=False
                    peaks=[];normal_peaks=[];overrides=[];refusals=[];bounds_overrides=[]
                    for tick,(row,event) in enumerate(zip(history,events),1):
                        actual_velocity=(row['reference']-prev_ref)/c.dt
                        acceleration=float(((actual_velocity-prev_v)/c.dt).abs().max())
                        safety=event['bounds_override'] or event['solver_refused'] or row['blocked']
                        peaks.append(acceleration)
                        if not safety and not prior_override:normal_peaks.append(acceleration)
                        if safety:overrides.append(tick)
                        if event['solver_refused']:refusals.append(tick)
                        if event['bounds_override']:bounds_overrides.append(tick)
                        prev_ref=row['reference'];prev_v=actual_velocity;prior_override=safety
                    final_coordinate=float((history[-1]['q']@J.T)[0,axis]) if coupled else float(history[-1]['q'][0,axis])
                    rows.append(dict(joints=joints,response=response,token=token,magnitude=magnitude,target=target,
                        coupled_jacobian=coupled,final_measured=final_coordinate,
                        endpoint_error=abs(final_coordinate-target),
                        extra_50_tick_drift=float((history[-1]['q']-history[299]['q']).abs().max()),
                        converged_tick=converged_tick,max_reference_acceleration_including_safety=max(peaks),
                        max_reference_acceleration_excluding_safety_and_next_tick=max(normal_peaks,default=0),
                        safety_override_count=len(overrides),first_safety_override_tick=next(iter(overrides),None),
                        safety_override_ticks=overrides,bounds_override_ticks=bounds_overrides,
                        refused_ticks=refusals,final_blocked=bool(c._public_blocked['left'].item())))
    finally:
        NS['accelerated_reference_bounds']=original_bounds;NS['guarded_cartesian_delta']=original_solver
    return dict(kind='CPU synthetic Cartesian generalized-coordinate ideal/first-order-lag feedback adapter',
        limitations='Not robot FK, PhysX, actuator/contact/collision validation. XYZ generalized coordinates are synthetic; reference acceleration is not measured robot acceleration.',
        acceleration_units='generalized coordinate / s^2; yaw axis rad/s^2',
        normal_peak_definition='Exclude current and immediately previous safety-override ticks; interrupted reference history changes finite-difference acceleration.',
        control_sha256=hashlib.sha256(SOURCE.read_bytes()).hexdigest(),
        test_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),rows=rows)


@pytest.mark.parametrize('token,axis,sign',[
    ('ROTATE_CW',5,-1),('ROTATE_CCW',5,1),('PITCH_UP',4,1),
    ('PITCH_DOWN',4,-1),('ROLL_LEFT',3,1),('ROLL_RIGHT',3,-1)])
def test_all_explicit_rotation_axes_start_at_measured_pose(token,axis,sign):
    c=controller()
    NS['begin_action'](c,left=token,rotation_deg=5.)
    expected=torch.tensor([[math.cos(math.radians(2.5)),0.,0.,0.]])
    expected[0,axis-2]=sign*math.sin(math.radians(2.5))
    torch.testing.assert_close(c.targets['left'][1],expected,atol=1e-7,rtol=1e-6)
    assert c._public_tolerances['left'][1]==pytest.approx(math.radians(.5))


if __name__=='__main__':
    import argparse,json
    parser=argparse.ArgumentParser()
    parser.add_argument('--output',required=True,type=Path)
    arguments=parser.parse_args()
    evidence=sample_closed_loop_evidence()
    destination=arguments.output
    destination.write_text(json.dumps(evidence,indent=2)+'\n')
    print(json.dumps({'evidence':str(destination),'cases':len(evidence['rows']),
        'summary':[{k:r[k] for k in ['joints','response','token','magnitude','endpoint_error',
        'safety_override_count','first_safety_override_tick','max_reference_acceleration_including_safety',
        'max_reference_acceleration_excluding_safety_and_next_tick']} for r in evidence['rows']]},indent=2))
