"""Independent constrained least-squares oracle for the production fallback."""
import torch
import pytest
from test_control_constrained_cpu import namespace as ns

@pytest.mark.parametrize('joints',[6,7])
@pytest.mark.parametrize('dtype',[torch.float32,torch.float64])
def test_production_releasing_solver_against_independent_box_oracle(joints,dtype):
    np=pytest.importorskip('numpy')
    scipy=pytest.importorskip('scipy.optimize')
    rng=np.random.default_rng(42+joints)
    for _ in range(30):
        J=rng.normal(size=(6,joints)); e=rng.normal(size=6)*.02
        lo=np.full(joints,-.01); hi=-lo
        # Include joints already at their positive and negative travel limits.
        hi[0]=0;lo[1]=0
        t=lambda a:torch.tensor(a,dtype=dtype)
        dq,valid=ns['releasing_bounded_delta'](t(J),t(e),t(lo),t(hi))
        assert valid.item()
        assert (dq>=t(lo)-1e-7).all() and (dq<=t(hi)+1e-7).all()
        ref=scipy.lsq_linear(np.vstack([J,.01*np.eye(joints)]),np.r_[e,np.zeros(joints)],bounds=(lo,hi),tol=1e-12)
        cost=lambda q:np.linalg.norm(J@q-e)**2+.0001*np.linalg.norm(q)**2
        assert abs(cost(dq.numpy())-cost(ref.x))<1e-8


def test_scaled_fallback_reallocates_limited_joint_without_changing_original_goal():
    J=torch.zeros((2,6,2),dtype=torch.float64);J[:,2,:]=1
    residual=torch.tensor([[0,0,.01,0,0,0]],dtype=torch.float64).expand(2,6).clone()
    original=residual.clone();lo=torch.full((2,2),-.02,dtype=torch.float64);hi=-lo;hi[:,0]=0
    dq,valid=ns['scaled_bounded_fallback'](J,residual,lo,hi,ns['public_motion_guard'])
    assert valid.all() and (dq[:,0]<=1e-7).all() and (dq[:,1]>.0099).all()
    torch.testing.assert_close(residual,original)


def test_invalid_samples_do_not_poison_valid_batch_members():
    J=torch.eye(6).repeat(4,1,1);e=torch.ones((4,6))*.01
    lo=torch.full_like(e,-.01);hi=-lo
    J[0,0,0]=float('nan');lo[1,0]=.02;e[2,0]=float('inf')
    dq,valid=ns['releasing_bounded_delta'](J,e,lo,hi)
    assert valid.tolist()==[False,False,False,True]
    assert torch.isfinite(dq).all() and not dq[:3].any()


def test_full_guarded_solver_rejects_invalid_samples_before_dense_solve():
    J=torch.eye(6).repeat(5,1,1);e=torch.ones((5,6))*.001
    lo=torch.full_like(e,-.01);hi=-lo
    J[0,0,0]=float('nan');lo[1,0]=.02;e[2,0]=float('inf');hi[3,0]=float('inf')
    dq,valid=ns['guarded_cartesian_delta'](J,e,lo,hi)
    assert valid.tolist()==[False,False,False,False,True]
    assert torch.isfinite(dq).all() and not dq[:4].any()


@pytest.mark.parametrize('base,new,joints',[
    ('franka-workspace-v4-front100.json','franka-workspace-v4-front100-ik-smooth-v1.json',7),
    ('inference-generalization-ur5-wsg-v1.json','inference-generalization-ur5-wsg-ik-smooth-v1.json',6)])
def test_smooth_profiles_change_only_controller_parameters(base,new,joints):
    from pathlib import Path
    from videoicl_isaaclab.embodiments import load_profile
    root=Path(__file__).resolve().parents[1]/'configs'
    old=load_profile(root/base);new=load_profile(root/new)
    assert len(new.arm_joints)==joints
    data=dict(new.config);data.pop('ik_smoothness_revision')
    control=dict(data['control'])
    assert control.pop('public_reference_acceleration_rad_s2')==20.
    assert control.pop('public_ik_retry_ticks')==6
    data['control']=control
    assert data==old.config


def test_braking_keeps_stationary_zero_nominal_joint_available_for_compensation():
    current=torch.zeros((1,2),dtype=torch.float64)
    goal=torch.tensor([[.01,0.]],dtype=torch.float64)
    lo=torch.full_like(current,-.02);hi=-lo
    lower,upper,override=ns['accelerated_reference_bounds'](current,current,current,lo,hi,.004,20.,goal=goal)
    assert not override.item()
    assert lower[0,1]<0 and upper[0,1]>0
    assert upper[0,1]<=20*.004**2+1e-12
