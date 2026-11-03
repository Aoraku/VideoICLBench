import numpy as np
import pytest
from videoicl_isaaclab.execution_design_e34_reference import supported_handle_xy


def test_long_cutlery_handle_stays_in_original_cell_while_mass_moves_inside():
    lower=[.005,.005,-.012];upper=[.098,.076,.019]
    # The observed old centre placement put a long fork COM beyond the tray.
    offset=np.array([.081,0.]);original=np.mean([lower[:2],upper[:2]],axis=0)
    assert original[0]+offset[0]>.12
    handle=supported_handle_xy(lower,upper,offset)
    assert np.all(handle>np.asarray(lower)[:2])and np.all(handle<np.asarray(upper)[:2])
    assert .005<handle[0]+offset[0]<.098
    assert handle[1]==pytest.approx(original[1])


def test_mass_already_near_handle_keeps_the_original_cell_center():
    lower=[.005,.005,-.012];upper=[.098,.076,.019]
    assert np.allclose(supported_handle_xy(lower,upper,[0.,0.]),[.0515,.0405])
