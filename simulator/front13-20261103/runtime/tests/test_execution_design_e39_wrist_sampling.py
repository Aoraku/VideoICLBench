import json
import math
from pathlib import Path

from videoicl_isaaclab.execution_design_local_pose_path import solve_local_pose_path


def test_real_C_wrist_prefix_uses_finer_knots_without_relaxing_joint_bounds():
    data=json.loads((Path(__file__).parent/'fixtures/e39_c_measured_wrist_prefix.json').read_text())
    r=data['measured_reference']
    result=solve_local_pose_path(r['position'],r['rotation_task'],r['jacobian'],r['q'],r['limits'],
        data['poses'],minimum_joint_margin_rad=.02,max_rotation_step_rad=math.radians(2.))
    assert result['feasible']
    assert max(row['maximum_joint_step_rad']for row in result['rows'])<=.18+1e-8
    assert min(row['minimum_joint_margin_rad']for row in result['rows'])>=.02
    assert not result['actuation_performed']and not result['collision_verified']
