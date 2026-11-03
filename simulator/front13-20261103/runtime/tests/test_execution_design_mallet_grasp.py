import numpy as np
import pytest
from videoicl_isaaclab.execution_design_mallet_grasp import safe_height


def test_native_failed_mallet_geometry_has_valid_table_clear_shaft_overlap():
    point=[-.35529514,-.19984423,.80606918];tip=[-.35465983,-.20038407,.80842906]
    shaft=np.array([[x,y,z]for x in (-.364104,-.346480)for y in (-.209901,-.190088)for z in (.797344,.814788)])
    target,receipt=safe_height(point,tip,dict(lowest_z_task_m=.79876957),shaft)
    assert target[2]==pytest.approx(.80995949)
    assert target[:2].tolist()==point[:2]
    assert target[2]<shaft[:,2].max()and not receipt['grasp_success_asserted']


def test_no_shaft_overlap_is_rejected_instead_of_blind_floor_clamp():
    shaft=np.array([[x,y,z]for x in (-.01,.01)for y in (-.01,.01)for z in (.801,.805)])
    with pytest.raises(RuntimeError,match='no verified shaft height overlap'):
        safe_height([0,0,.803],[0,0,.8084],dict(lowest_z_task_m=.7987),shaft)


def test_safe_existing_grasp_height_is_preserved():
    shaft=np.array([[x,y,z]for x in (-.01,.01)for y in (-.01,.01)for z in (.8,.85)])
    target,_=safe_height([0,0,.83],[0,0,1.],dict(lowest_z_task_m=.991),shaft)
    assert target.tolist()==[0,0,.83]
