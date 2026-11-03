import numpy as np
import pytest
from videoicl_isaaclab.public_gripper_reference import advance,parameters


def path(goal=.0,steps=1600):
    x=np.array([[.04,.03999]]);v=np.zeros_like(x);rows=[x.copy()];vel=[v.copy()]
    for _ in range(steps):
        x,v=advance(x,v,np.full_like(x,goal),.004,.01,.05,np);rows.append(x.copy());vel.append(v.copy())
    return np.array(rows),np.array(vel)


def test_goal_is_reached_without_snapping_speed_acceleration_or_bounds():
    x,v=path()
    assert np.max(abs(v))<=.01+1e-12
    assert np.max(abs(np.diff(v,axis=0)))/.004<=.05+1e-9
    assert x.min()>=-1e-12 and x.max()<=.04+1e-12
    assert np.all(np.diff(x,axis=0)<=1e-12)
    assert np.allclose(x[-1],0,atol=1e-10)
    assert np.allclose(x[1],[[.0399996,.0399896]],atol=1e-12)
    assert x[100,0,0]>.0369  # Original goal0 persists, without an instant40mm jump.


def test_reversal_brakes_without_resetting_to_measured_joint_positions():
    x=np.array([[.04]]);v=np.zeros_like(x);vel=[];positions=[]
    for i in range(1400):
        goal=.04 if i>=100 else 0.
        x,v=advance(x,v,np.full_like(x,goal),.004,.01,.05,np);vel.append(v.copy());positions.append(x.copy())
    vel=np.array(vel);positions=np.array(positions)
    assert np.max(abs(np.diff(vel,axis=0)))/.004<=.05+1e-9
    assert positions.min()>=0 and positions.max()<=.04+1e-10
    assert np.allclose(positions[-1],.04,atol=1e-10)
    assert positions[101]<positions[100]  # No velocity reset at a new goal.


def test_no_config_is_legacy_and_partial_or_nonfinite_config_is_rejected():
    assert parameters({})is None
    for c in [{'public_gripper_reference_speed_m_s':.01},{'public_gripper_reference_speed_m_s':True,'public_gripper_reference_acceleration_m_s2':.05},{'public_gripper_reference_speed_m_s':.01,'public_gripper_reference_acceleration_m_s2':float('nan')}]:
        with pytest.raises(ValueError):parameters(c)


def test_native_float32_path_continues_through_a_checkpoint_cache_boundary():
    import torch
    x=torch.tensor([[.04,.03999]]);v=torch.zeros_like(x);old=v.clone()
    for i in range(1250):
        x,v=advance(x,v,torch.zeros_like(x),.004,.01,.05,torch)
        assert torch.isfinite(x).all()and torch.isfinite(v).all()
        assert float(v.abs().max())<=.010001
        assert float((v-old).abs().max())/.004<=.05001
        old=v.clone()
        if i==99:x=x.clone();v=v.clone()  # Exact cache continuation, no q reseed.
    assert torch.max(x.abs())<1e-8
