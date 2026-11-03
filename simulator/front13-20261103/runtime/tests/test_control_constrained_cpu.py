"""Constraint solving and E02 failure-state regression without Isaac or GPU."""
import ast,math,json
from pathlib import Path
from types import SimpleNamespace
import pytest
import torch

SOURCE=Path(__file__).resolve().parents[1]/'videoicl_isaaclab/control.py'
tree=ast.parse(SOURCE.read_text());namespace={'torch':torch,'math':math}
names={'pose_residual','bounded_cartesian_delta','public_motion_guard','guarded_cartesian_delta','rolling_reference_bounds','accelerated_reference_bounds','public_refusal_state','releasing_bounded_delta','scaled_bounded_fallback'}
exec(compile(ast.Module(body=[n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name in names],type_ignores=[]),str(SOURCE),'exec'),namespace)
solve=namespace['bounded_cartesian_delta'];guard=namespace['public_motion_guard'];pose_error=namespace['pose_residual']
safe_step=namespace['guarded_cartesian_delta']


def test_rolling_reference_rate_and_anti_windup_are_distinct_constraints():
    current=torch.tensor([[.1,.2]],dtype=torch.float64)
    reference=torch.tensor([[.15,.14]],dtype=torch.float64)
    limits=torch.tensor([[[-1.,1.],[-1.,1.]]],dtype=torch.float64)
    lo,hi=namespace['rolling_reference_bounds'](current,reference,limits,torch.full_like(current,5.),.004,.08)
    assert torch.allclose(lo,torch.tensor([[.03,-.08]],dtype=torch.float64))
    assert torch.allclose(hi,torch.tensor([[.07,-.04]],dtype=torch.float64))
    # These are offsets from measured q, but rates are relative to old q_ref.
    for target in (current+lo,current+hi):
        assert ((target-reference).abs()<=.02000001).all()
        assert ((target-current).abs()<=.08000001).all()


def test_convergence_checks_each_arm_and_does_not_equate_one_blocked_arm_with_done():
    cls=next(n for n in tree.body if isinstance(n,ast.ClassDef) and n.name=='Controller')
    method=next(n for n in cls.body if isinstance(n,ast.FunctionDef) and n.name=='public_action_converged')
    ns=dict(namespace)
    exec(compile(ast.Module(body=[method],type_ignores=[]),str(SOURCE),'exec'),ns)
    zero=torch.zeros((1,3));q=torch.tensor([[1.,0.,0.,0.]])
    c=SimpleNamespace(scene=SimpleNamespace(robots={'left':None,'right':None}),
        pose=lambda side:(zero,q),targets={'left':(zero,q),'right':(zero+torch.tensor([[0.,0.,.05]]),q)},
        _public_blocked={'left':torch.tensor([True])})
    assert not ns['public_action_converged'](c)
    c._public_blocked['right']=torch.tensor([True])
    assert ns['public_action_converged'](c)
    c._public_blocked={};c.targets['right']=(zero+.0005,q)
    assert ns['public_action_converged'](c)
    c.targets['right']=(zero,torch.tensor([[math.cos(.05),0.,math.sin(.05),0.]]))
    assert not ns['public_action_converged'](c)
    c.targets['right']=(zero+float('nan'),q)
    with pytest.raises(RuntimeError,match='Nonfinite measured robot pose'):
        ns['public_action_converged'](c)
    c._public_blocked={'right':torch.tensor([True])}
    with pytest.raises(RuntimeError,match='Nonfinite measured robot pose'):
        ns['public_action_converged'](c)

def test_joint_bounds_are_in_solver_not_applied_after_solution():
    # x=dq0+dq1. First joint has no remaining travel; second must compensate.
    J=torch.tensor([[[1.,1.]]],dtype=torch.float64);e=torch.tensor([[.01]],dtype=torch.float64)
    dq,valid=solve(J,e,torch.tensor([[-.02,-.02]]),torch.tensor([[0.,.02]]))
    assert valid.item();assert dq[0,0]<=1e-7
    assert (J@dq.unsqueeze(-1)).item()==pytest.approx(.01,abs=2e-6)
    assert dq[0,1]>.0099


def test_velocity_and_position_bounds_both_hold():
    torch.manual_seed(12)
    J=torch.randn(5,6,7,dtype=torch.float64);e=torch.randn(5,6,dtype=torch.float64)
    lo=torch.full((5,7),-.004,dtype=torch.float64);hi=torch.full((5,7),.003,dtype=torch.float64);hi[:,3]=0
    dq,valid=solve(J,e,lo,hi)
    assert valid.all();assert (dq>=lo-1e-7).all();assert (dq<=hi+1e-7).all()


def test_up_never_accepts_sideways_or_downward_prediction():
    e=torch.tensor([[0.,0.,.05,0.,0.,0.]])
    assert guard(e,torch.tensor([[0.,0.,.004,0.,0.,0.]]),torch.tensor([True])).item()
    for prediction in ([.003,0.,.001,0.,0.,0.],[0.,0.,-.001,0.,0.,0.]):
        assert not guard(e,torch.tensor([prediction]),torch.tensor([True])).item()


def test_e02_large_old_orientation_rejected_for_both_step_sizes():
    # Observed step47: 46.12-degree error to maintained orientation, elbow at stop.
    for mm in (5,50):
        e=torch.tensor([[0.,0.,mm/1000,0.,math.radians(46.12),0.]])
        p=torch.tensor([[0.,0.,.001,0.,.01,0.]])
        assert not guard(e,p,torch.tensor([True])).item()
        assert guard(e,p,torch.tensor([True]),rotation_command=True).item()


def test_pose_error_keeps_original_goal_and_shortest_quaternion_sign():
    p=torch.tensor([[0.,0.,0.]]);q=torch.tensor([[1.,0.,0.,0.]])
    goal=torch.tensor([[math.cos(.4),0.,math.sin(.4),0.]])
    result=pose_error(p,q,p,goal)
    assert result[0,4].item()==pytest.approx(.8)
    assert torch.allclose(result,pose_error(p,-q,p,goal))
    assert goal[0,2].item()==pytest.approx(math.sin(.4))


def test_pool_propagates_full_robot_diagnostics():
    from test_room_pool_actions import active_pool
    pool,controllers,sim,events=active_pool()
    feedback=dict(tracking_error_m={'left':.049,'right':0.},orientation_error_rad={'left':.8,'right':0.},control_feedback={'left':{'status':'blocked','joint_limit_names':['panda_joint4']}})
    for c in controllers.values():c.action_feedback=lambda:feedback
    receipts=pool.action_batch({room:{} for room in controllers})
    for receipt in receipts.values():
        for key,value in feedback.items():assert receipt[key]==value


def test_actual_e02_state_refuses_wrong_direction_without_erasing_goal():
    d=json.loads((Path(__file__).parent/'fixtures/e02_step47_control.json').read_text())
    tensor=lambda x:torch.tensor([x],dtype=torch.float64)
    J=tensor(d['jacobian']);q=tensor(d['joint_position']);limits_lo=tensor(d['lower_limits']);limits_hi=tensor(d['upper_limits'])
    position=tensor(d['position']);quat=tensor(d['quaternion_wxyz']);goal_p=tensor(d['target_position']);goal_q=tensor(d['target_quaternion_wxyz'])
    residual=pose_error(position,quat,goal_p,goal_q)
    lower=torch.maximum(torch.full_like(q,-.0087),limits_lo+1e-4-q)
    upper=torch.minimum(torch.full_like(q,.0087),limits_hi-1e-4-q)
    delta,valid=solve(J,residual,lower,upper)
    predicted=(J@delta.unsqueeze(-1)).squeeze(-1)
    assert valid.item();assert delta[0,3]<0  # elbow cannot extend any farther
    assert residual[0,3:].norm().item()>math.radians(46)
    assert not guard(residual,predicted,valid).item()
    segment,allowed=safe_step(J,residual,lower,upper)
    assert not allowed.item() and not segment.any()
    # The original goal is preserved, not replaced with the achieved orientation.
    assert torch.equal(goal_q,tensor(d['target_quaternion_wxyz']))


def test_native_e31_up50_uses_safe_segment_instead_of_sideways_saturation():
    d=json.loads((Path(__file__).parent/'fixtures/e31_initial_up50_control.json').read_text())
    t=lambda x:torch.tensor([x],dtype=torch.float64)
    J=t(d['jacobian']);q=t(d['joint_position'])
    residual=pose_error(t(d['position']),t(d['quaternion_wxyz']),t(d['target_position']),t(d['target_quaternion_wxyz']))
    lo=torch.full_like(q,-d['maximum_joint_step']);hi=-lo
    old,valid=solve(J,residual,lo,hi)
    assert not guard(residual,(J@old.unsqueeze(-1)).squeeze(-1),valid).item()
    delta,allowed=safe_step(J,residual,lo,hi)
    predicted=(J@delta.unsqueeze(-1)).squeeze(-1)
    assert allowed.item()
    assert (delta>=lo-1e-7).all() and (delta<=hi+1e-7).all()
    assert .0027<predicted[0,2]<.0029
    assert predicted[0,:2].norm()<.000002
    # Near the goal, velocity permits the whole residual; do not impose an
    # arbitrary tiny Cartesian step or erase the maintained quaternion.
    small=residual*.01
    delta,allowed=safe_step(J,small,lo,hi)
    assert allowed.item()
    assert (J@delta.unsqueeze(-1))[0,2,0]>.00049


def test_segment_does_not_cross_position_limit_and_can_resolve_other_joints():
    J=torch.zeros((1,6,2),dtype=torch.float64);J[0,2,:]=1
    residual=torch.tensor([[0.,0.,.01,0.,0.,0.]],dtype=torch.float64)
    # The original direction wants to advance joint zero beyond its limit.
    # Uniform scaling has no progress; the bounded fallback uses joint one.
    lo=torch.tensor([[-.02,-.02]],dtype=torch.float64);hi=torch.tensor([[0.,.02]],dtype=torch.float64)
    delta,allowed=safe_step(J,residual,lo,hi)
    assert allowed.item() and delta[0,0]<=0 and delta[0,1]>.0099


def test_segment_rejects_inconsistent_bounds_and_stale_orientation_even_when_scaled():
    J=torch.eye(6,dtype=torch.float64).unsqueeze(0)
    residual=torch.tensor([[0.,0.,.05,0.,.8,0.]],dtype=torch.float64)
    lo=torch.full((1,6),-.001,dtype=torch.float64);hi=-lo
    delta,allowed=safe_step(J,residual,lo,hi)
    assert not allowed.item() and not delta.any()
    lo[0,0]=.01
    delta,allowed=safe_step(J,residual*0,lo,hi)
    assert not allowed.item() and not delta.any()


def test_production_tick_latches_hold_for_stale_pose_and_keeps_goal():
    cls=next(n for n in tree.body if isinstance(n,ast.ClassDef) and n.name=='Controller')
    tick=next(n for n in cls.body if isinstance(n,ast.FunctionDef) and n.name=='tick')
    ns=dict(namespace,MOTION={'UP':(2,1)},quat_apply=lambda q,x:x,
            matrix_from_quat=lambda q:torch.eye(3,dtype=q.dtype).unsqueeze(0),
            skew_symmetric_matrix=lambda x:torch.zeros((1,3,3),dtype=x.dtype))
    exec(compile(ast.Module(body=[tick],type_ignores=[]),str(SOURCE),'exec'),ns)
    d=json.loads((Path(__file__).parent/'fixtures/e02_step47_control.json').read_text());t=lambda x:torch.tensor([x],dtype=torch.float32)
    q=t(d['joint_position']);stored=[];rootq=t([1.,0.,0.,0.]);J=t(d['jacobian'])
    data=SimpleNamespace(root_quat_w=rootq,body_quat_w=rootq.unsqueeze(1),joint_pos=torch.cat((q,torch.zeros((1,2),dtype=q.dtype)),dim=-1),
       joint_pos_limits=torch.tensor([[*zip(d['lower_limits'],d['upper_limits']),[0.,.04],[0.,.04]]],dtype=q.dtype),joint_vel_limits=torch.full((1,9),2.175,dtype=q.dtype))
    robot=SimpleNamespace(data=data,is_fixed_base=True,root_physx_view=SimpleNamespace(get_coms=lambda:torch.zeros((1,1,7),dtype=q.dtype),get_jacobians=lambda:torch.cat((J,torch.zeros((1,6,2),dtype=q.dtype)),dim=-1).unsqueeze(1)),
       set_joint_position_target=lambda value,joint_ids:stored.append((value.clone(),joint_ids)),write_data_to_sim=lambda:None)
    profile=SimpleNamespace(tcp=[0.,0.,0.],config={'physics':{'max_joint_delta':.08},'actuators':{'arm':{'velocity_limit':5.}}},gripper_values=lambda fraction:[fraction*.04]*2)
    goal=(t(d['target_position']),t(d['target_quaternion_wxyz']))
    c=SimpleNamespace(scene=SimpleNamespace(robots={'right':robot},embodiment=profile,apply_passive_efforts=lambda:None),device='cpu',dt=.004,ids={'right':(list(range(7)),[7,8],0)},
       pose=lambda side:(t(d['position']),t(d['quaternion_wxyz'])),targets={'right':goal},ik={'right':SimpleNamespace(set_command=lambda x:None)},
       grips={'right':.04},_public_action={'right':'UP'},_public_blocked={},_public_blocked_before={},_public_hold_q={},_public_limit_seen={},_author_ff_twists={})
    ns['tick'](c,phase='write')
    assert torch.equal(stored[0][0],q)
    assert c._public_blocked['right'].item()
    assert c._public_limit_seen['right'][0,3].item()
    assert torch.equal(c.targets['right'][1],goal[1])
    ns['tick'](c,phase='write')
    assert torch.equal(stored[2][0],q)  # still holding, not retrying unsafe movement
