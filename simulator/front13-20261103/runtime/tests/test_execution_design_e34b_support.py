import itertools
import numpy as np
import pytest
from videoicl_isaaclab.execution_design_e34b_support import vertical_support_z,supported_handle_z


def box(lo, hi):
    return np.asarray(list(itertools.product(*zip(lo, hi))), float)


def test_tray_centre_does_not_replace_actual_interior_support():
    floor=box([-.12,.02,.800],[.12,.22,.802])
    wall=box([-.12,.02,.802],[-.11,.22,.842])
    assert vertical_support_z([floor,wall],[.07,.16])==pytest.approx(.802)
    assert vertical_support_z([floor,wall],[-.115,.16])==pytest.approx(.842)
    with pytest.raises(RuntimeError,match='No actual native tray support'):
        vertical_support_z([floor,wall],[.15,.16])


def test_asymmetric_payload_origin_and_coarse_box_do_not_raise_handle_target():
    # Native material can lie off-centre in the descriptor's bounding box.
    material=box([.10,.14,.861],[.15,.18,.896])
    handle=[.105,.16,.883]
    actual=supported_handle_z(handle,[material],.802)
    assert actual==pytest.approx(.827)
    assert actual < .820+.035+.003
    assert actual-.820 < .019


def test_nonfinite_native_material_is_rejected():
    with pytest.raises(ValueError):
        supported_handle_z([0,0,1],[np.array([[0,0,np.nan]])],.8)
