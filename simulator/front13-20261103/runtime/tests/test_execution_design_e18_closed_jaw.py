import numpy as np
import pytest
from videoicl_isaaclab.execution_design_e18_geometry import normalized_jaw_axis


def test_real_submillimetre_closed_finger_separation_still_has_measured_direction():
    jaw=normalized_jaw_axis([.0000001,.0003676,0.])
    assert jaw[1]>.99999
    assert np.linalg.norm(jaw)==pytest.approx(1.)


def test_fully_closed_coincident_origins_use_native_prismatic_axis():
    assert normalized_jaw_axis([0.,0.,0.],[0.,2.,0.]).tolist()==[0.,1.,0.]
    with pytest.raises(RuntimeError):normalized_jaw_axis([0.,0.,0.])
    with pytest.raises(RuntimeError):normalized_jaw_axis([0.,0.,0.],[0.,0.,0.])


def test_measured_open_direction_takes_precedence_over_fallback():
    assert normalized_jaw_axis([1.,0.,0.],[0.,2.,0.]).tolist()==[1.,0.,0.]
