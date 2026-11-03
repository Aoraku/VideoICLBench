import pytest
from videoicl_isaaclab.execution_design_e31_open_finish import support_force_z_bias


def test_real_contact_feedback_approaches_only_when_contact_is_weak():
    assert support_force_z_bias(0.,0.,.004)==pytest.approx(-.0001)
    assert support_force_z_bias(.7,-.002,.004)==-.002
    assert support_force_z_bias(3.,-.002,.004)==pytest.approx(-.00196)


def test_contact_target_feedback_stays_within_motor_excursion_limits():
    assert support_force_z_bias(0.,-.04,.004)==-.04
    assert support_force_z_bias(3.,.004,.004)==.004
    with pytest.raises(ValueError):support_force_z_bias(float('nan'),0.,.004)
