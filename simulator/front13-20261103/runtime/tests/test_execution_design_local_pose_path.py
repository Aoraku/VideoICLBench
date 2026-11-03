import copy,json
from pathlib import Path
import numpy as np
import pytest
from videoicl_isaaclab.execution_design_drawer_ik_probe import forward_at_delta
from videoicl_isaaclab.execution_design_local_pose_path import solve_local_pose_path


def measured():
    return json.loads((Path(__file__).parent/'fixtures/e40_native_v9_ik_path.json').read_text())['native_context']


def test_small_native_joint_generated_path_is_continuous_and_inputs_are_read_only():
    m=measured();before=copy.deepcopy(m);q=np.array(m['q']);jac=np.array(m['jacobian']);p=np.array(m['position']);r=np.array(m['rotation_task'])
    targets=[]
    for amount in(.01,.02,.03):
        delta=np.zeros(7);delta[0]=amount
        point,rot=forward_at_delta(p,r,jac,delta)
        targets.append(dict(position=point.tolist(),rotation=rot.tolist()))
    result=solve_local_pose_path(p,r,jac,q,m['limits'],targets)
    assert result['feasible'] and result['random_restarts'] is False
    assert all(x['maximum_joint_step_rad']<=.18+1e-8 for x in result['rows'])
    assert m==before
    assert not result['actuation_performed'] and not result['collision_verified']


def test_bad_native_shape_and_waypoint_fail_closed():
    m=measured();args=[m[k]for k in('position','rotation_task','jacobian','q','limits')]
    with pytest.raises(ValueError,match='Invalid measured'):
        solve_local_pose_path(*[m['position'],m['rotation_task'],np.zeros((6,7)),m['q'],m['limits']],[])
    with pytest.raises(ValueError,match='Invalid Cartesian'):
        solve_local_pose_path(*args,[dict(position=[0,0,float('nan')],rotation=np.eye(3))])


def test_private_cpu_budget_stops_proposal_without_claiming_physical_unreachability(monkeypatch):
    import videoicl_isaaclab.execution_design_local_pose_path as module
    m=measured();before=copy.deepcopy(m);ticks=iter((0.,1.))
    monkeypatch.setattr(module.time,'monotonic',lambda:next(ticks))
    result=solve_local_pose_path(*[m[k]for k in('position','rotation_task','jacobian','q','limits')],
        [dict(position=m['position'],rotation=m['rotation_task'])],max_seconds=.1)
    assert not result['feasible'] and result['cpu_budget_exhausted']
    assert result['failure_reason']=='private_cpu_planning_budget'
    assert not result['actuation_performed'] and m==before
