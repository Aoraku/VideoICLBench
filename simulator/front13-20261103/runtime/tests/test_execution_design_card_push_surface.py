import json,math
from pathlib import Path
import numpy as np
import pytest
from videoicl_isaaclab.realworld_tool_expert import _axis_rotation
from videoicl_isaaclab.execution_design_card_push_surface import leading_surface


def at_card_height(yaw,roll):
    d=json.loads((Path(__file__).parent/'fixtures/e50_native_closed_fingers.json').read_text())
    turn=_axis_rotation([1,0,0],math.radians(roll))@_axis_rotation([0,0,1],math.radians(yaw))
    meshes=[np.asarray(m)@turn.T for m in d['fingers_relative_to_tcp']]
    dz=.80002-min(m[:,2].min()for m in meshes)
    return [m+[0,0,dz]for m in meshes]


def test_native_old_outer_toe_surface_is_rejected_for_downward_normal():
    with pytest.raises(ValueError,match='press card down'):
        leading_surface(at_card_height(90,0),.800175,[1,0,0])


def test_measured_rolled_pad_exposes_a_horizontal_card_push_surface():
    r=leading_surface(at_card_height(-90,30),.800175,[1,0,0])
    assert r['normal_along_push']>.99 and abs(r['vertical_normal'])<.04
