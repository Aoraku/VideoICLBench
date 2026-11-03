import json
from pathlib import Path
import numpy as np
import pytest
from videoicl_isaaclab.execution_design_e46_backstop_pose import contact_face_pitch
from videoicl_isaaclab.layout import rotation_matrix
from videoicl_isaaclab.realworld_tool_expert import _axis_rotation,ToolExecutionError


def test_actual_native_lower_finger_chamfer_can_face_up_without_new_geometry():
    f=json.loads((Path(__file__).parent/'fixtures/e46_v15_native_contact_face.json').read_text())
    r=rotation_matrix(f['native_tcp_quaternion']);d=np.array([-.0049083718,.9999879539,0.]);n=np.asarray(f['normal_tcp_local'])
    pitch=contact_face_pitch(f['mesh'],r,d,n)
    assert 33.<np.rad2deg(pitch)<34.
    after=_axis_rotation(np.cross([0.,0.,1.],d),pitch)@r@n
    assert .17<after[2]<.18 and float(after@d)<-.98
    with pytest.raises(ToolExecutionError):contact_face_pitch(f['mesh'],r,d,[0,0,1])
