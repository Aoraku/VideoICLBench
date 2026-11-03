import json
from pathlib import Path
import numpy as np
from videoicl_isaaclab.realworld_tool_expert import _axis_rotation
from videoicl_isaaclab.execution_design_pour_path import candidate_poses
from videoicl_isaaclab.execution_design_local_pose_path import solve_local_pose_path


def test_actual_native_cup_grasp_endpoint_does_not_certify_full_pour_and_return():
    f=json.loads((Path(__file__).parent/'fixtures/e45_native_v6_ik_path.json').read_text());n=f['native_context']
    target=n['candidates'][0];assert target['kinematically_reachable'] and target['minimum_joint_margin_rad']>.5
    r=np.array(target['target_rotation']);up=-r[:,2];x=r[:,1];body=np.column_stack((x,np.cross(up,x),up))
    grip=n['candidates'][3]['target_position'];native=[n[k]for k in('position','rotation_task','jacobian','q','limits')]
    def screen(hand):
        poses=candidate_poses(n['position'],n['rotation_task'],hand,grip,.94802,1.06,body,[-.036,0,.031],[0,0,.044],[-.051505805975990415,-.13049737060070038,.9386277848],'PITCH_DOWN')
        return solve_local_pose_path(*native,poses)
    rejected=screen(r)
    assert not rejected['feasible'] and rejected['rows'][-1]['reason']=='joint_margin'
    # Same upright cup, same grasp point and real jaw axis; only empty-gripper
    # palm tilt differs. Actual grip remains a later native requirement.
    tilted=_axis_rotation(body[:,0],np.deg2rad(-30))@r
    assert np.allclose(tilted[:,1],r[:,1])
    passed=screen(tilted)
    assert passed['feasible'] and len(passed['rows'])>350
    assert min(x['minimum_joint_margin_rad']for x in passed['rows'])>.4
    assert not passed['actuation_performed'] and not passed['collision_verified']
