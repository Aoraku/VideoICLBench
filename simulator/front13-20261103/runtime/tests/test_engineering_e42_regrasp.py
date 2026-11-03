import copy
import numpy as np
import pytest
from videoicl_isaaclab.engineering_e42_regrasp import forward_handle_reference
from videoicl_isaaclab.execution_design_spatula_clearance import SOURCE_SHA,HALF_SIZE,SUPPORT_VERTICES
from videoicl_isaaclab.realworld_tool_expert import ToolExecutionError


def original():
    return dict(id='spatula',source_asset=dict(sha256=SOURCE_SHA),size=list(HALF_SIZE)),dict(
        actor='spatula',local=[-.09033605958,-.00043158051,-.00263704093],jaw_axis_local=[0,1,0])


def test_forward_reference_is_inside_the_same_actual_handle_before_the_blade():
    from scipy.spatial import ConvexHull
    obj,old=original();before=copy.deepcopy((obj,old));new=forward_handle_reference(obj,old)
    p=np.array(new['local']);planes=ConvexHull(SUPPORT_VERTICES).equations
    assert np.max(planes[:,:3]@p+planes[:,3])<=1e-9
    assert p[0]==.03 and p[0]<.070018-.03
    assert np.linalg.norm(np.array([.14,0,-.013])-p)<.12
    assert new['jaw_axis_local']==old['jaw_axis_local'] and (obj,old)==before


def test_wrong_source_and_a_blade_instead_of_handle_are_rejected():
    obj,old=original()
    with pytest.raises(ToolExecutionError,match='handle section'):
        forward_handle_reference(obj,old,x=.07)
    obj['source_asset']['sha256']='different'
    with pytest.raises(ToolExecutionError,match='unchanged'):
        forward_handle_reference(obj,old)
