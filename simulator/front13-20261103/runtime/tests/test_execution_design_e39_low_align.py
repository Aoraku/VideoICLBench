import pytest
from videoicl_isaaclab.execution_design_e39_reference import swept_height
from videoicl_isaaclab.realworld_tool_expert import ToolExecutionError


def test_real_B_745mm_lid_gap_needs_no_tall_lift_at_native_3mm_boundary():
    lo=[-.0695,-.18659658,-.00712];hi=[.0695,.18687294,.058]
    lid=([.068,-.21837,.87448],[.222,-.14404446,1.26353542])
    box=([.068,-.147,.8],[.222,.247,.872])
    kwargs=dict(margin=.008,vertical_tracking_allowance=.006)
    assert swept_height([.145,.05985,.89],[.145,.05,.89],lo,hi,[lid,box],**kwargs)>1.2
    low=swept_height([.145,.05985,.89],[.145,.05,.89],lo,hi,[lid,box],horizontal_margin=.003,**kwargs)
    assert low==pytest.approx(.872+.008+.00712+.006)


@pytest.mark.parametrize('invalid',[-.001,float('nan')])
def test_invalid_horizontal_boundary_is_not_silently_accepted(invalid):
    with pytest.raises(ToolExecutionError,match='horizontal tracking'):
        swept_height([0,0,1],[.1,0,1],[-.01]*3,[.01]*3,[],horizontal_margin=invalid)
