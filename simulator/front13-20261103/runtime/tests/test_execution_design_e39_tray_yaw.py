import math
from types import SimpleNamespace
import numpy as np
import pytest

from videoicl_isaaclab.execution_design_e39_tray_yaw import yaw_error,align_loaded_yaw
from videoicl_isaaclab.realworld_tool_expert import _axis_rotation,ToolExecutionError


def test_real_B_small_yaw_crosses_lid_margin_and_box_width():
    yaw=math.radians(-1.2765490818256744)
    assert math.degrees(yaw_error(_axis_rotation([0,0,1],yaw),np.eye(3)))==pytest.approx(1.2765490818256744)
    # Real main tray footprint is 130x370mm; its rotated width alone no
    # longer fits 138mm box interior, before including small measured tilt.
    assert .065*abs(math.cos(yaw))+.185*abs(math.sin(yaw))>.069
    good=math.radians(.6)
    assert .065*math.cos(good)+.185*math.sin(good)<.069


def test_yaw_wrap_uses_small_real_turn_not_full_revolution():
    a=_axis_rotation([0,0,1],math.radians(179.5))
    b=_axis_rotation([0,0,1],math.radians(-179.5))
    assert math.degrees(yaw_error(a,b))==pytest.approx(1.)


def test_already_small_loaded_yaw_has_zero_actions():
    class Policy:
        task='E39';a=SimpleNamespace(control_report={'engineering_reference_only':True})
        d={'target_members':['red'],'reference_objects':[]}
        def ref(self,n):return {'actor':n}
        def require_held(self,*a):pass
        def snapshot(self):return {'work_tray':{'mat':np.eye(3)}},{frozenset(('red','work_tray'))}
        def frame(self,r):return np.zeros(3),np.eye(3)
        def act(self,*a,**k):pytest.fail('Unnecessary rotation issued')
    align_loaded_yaw(Policy(),'box')


def test_actual_support_loss_rejects_before_any_rotation():
    class Policy:
        task='E39';a=SimpleNamespace(control_report={'engineering_reference_only':True})
        d={'target_members':['red'],'reference_objects':[]}
        def ref(self,n):return {'actor':n}
        def require_held(self,*a):pass
        def snapshot(self):return {},set()
        def frame(self,r):return np.zeros(3),np.eye(3)
        def act(self,*a,**k):pytest.fail('Unsupported assembly moved')
    with pytest.raises(ToolExecutionError,match='actual carried support'):
        align_loaded_yaw(Policy(),'box')


def test_real_b_entry_width_needs_functional_turn_not_fixed_subdegree_goal():
    from types import SimpleNamespace
    from videoicl_isaaclab.execution_design_e39_tray_yaw import insertion_width_fits
    from videoicl_isaaclab.realworld_tool_expert import _axis_rotation
    rot=_axis_rotation([0,0,1],np.deg2rad(-1.1375))@_axis_rotation([1,0,0],np.deg2rad(1.108))
    p=SimpleNamespace(d={'packages':[dict(container='box',lower=[-.069,-.197,-.03],upper=[.069,.197,.04])]},
        objects={'work_tray':{'size':[.065,.185,.03]}},
        frame=lambda ref:(np.zeros(3),np.eye(3)if ref['actor']=='box'else rot))
    assert not insertion_width_fits(p,'box')
    rot=_axis_rotation([1,0,0],np.deg2rad(1.108))
    assert insertion_width_fits(p,'box')
