import math
from types import SimpleNamespace
import pytest
from videoicl_isaaclab.execution_design_e15_held_red import positive_remaining,run_segment

@pytest.mark.parametrize('goal,yaw,expected',[(270,98,172),(270,-90,0),(270,-88,-2)])
def test_selected_positive_turn_uses_real_yaw_and_accepts_small_terminal_error(goal,yaw,expected):
 assert math.degrees(positive_remaining(math.radians(goal),math.radians(yaw)))==pytest.approx(expected)

def test_rejects_wrong_boundary_before_native_access(monkeypatch):
 from videoicl_isaaclab import execution_design_e15_wrist as wrist
 monkeypatch.setattr(wrist,'_scope',lambda _:None)
 a=SimpleNamespace(scene=SimpleNamespace(spec=dict(variant='B',seed=4201,execution_design=dict(condition='I'))),_engineering_resume_checkpoint=dict(source=dict(steps=13,physics_ticks=1303)),c=SimpleNamespace(_engineering_checkpoint_readback_passed=True))
 with pytest.raises(ValueError,match='14/1403'):run_segment(a,'e15_b_rotate_place_red_from14',{})
