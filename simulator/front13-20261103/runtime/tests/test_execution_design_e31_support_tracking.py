import numpy as np
import pytest
from videoicl_isaaclab.execution_design_e31_supported_separate import support_target_z_shift


def test_upper_finger_tracks_real_six_mm_fall_without_chasing_lateral_drag():
    eye=np.eye(3);tip=np.array([.01,.02,.94]);origin=np.array([0.,0.,.91])
    assert support_target_z_shift(origin,eye,tip,[.04,-.03,.904],eye)==pytest.approx(-.006)


def test_height_tracking_keeps_narrow_motor_excursion_bounds():
    eye=np.eye(3)
    assert support_target_z_shift([0,0,.91],eye,[0,0,.94],[0,0,.80],eye)==-.040
    assert support_target_z_shift([0,0,.91],eye,[0,0,.94],[0,0,1.0],eye)==.004


def test_fixed_hand_xy_uses_real_tilted_surface_intersection_after_lateral_shift():
    angle=.3;c=np.cos(angle);s=np.sin(angle)
    rotation=np.array([[c,0,s],[0,1,0],[-s,0,c]])
    expected=.02*np.tan(angle)
    assert support_target_z_shift([0,0,.91],rotation,[0,0,.94],[-.02,0,.91],rotation)==pytest.approx(-expected)
