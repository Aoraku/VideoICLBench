import numpy as np
import pytest
from test_execution_design_segments_e17_e20 import context
from videoicl_isaaclab.execution_design_expert import ExecutionDesignAuthor as P
from videoicl_isaaclab.realworld_tool_expert import ToolExecutionError


@pytest.mark.parametrize('moving',[False,True])
def test_engineering_E20_ends_three_stalled_actions_but_allows_real_progress(moving):
    a,state,contacts=context('E20','B');a.stage='local-actual-transport';p=P(a);tip=np.array([0.,0.,.95]);p.tip=lambda side:tip.copy();calls=[]
    def act(side,token,**kwargs):
        calls.append(token)
        if moving:tip[0]+=.005
    p.act=act
    if moving:
        p.move('left',[.05,0,.95]);assert len(calls)==10
    else:
        with pytest.raises(ToolExecutionError,match='three actions'):p.move('left',[.05,0,.95])
        assert len(calls)==3
    assert p.act is act


def test_material_transit_keeps_requested_five_mm_tolerance():
    a,state,contacts=context('E20','B');p=P(a);tip=np.zeros(3);point=np.zeros(3);p.tip=lambda side:tip.copy();p.point=lambda ref:point.copy();tolerances=[]
    def move(side,target,guard,follower,tolerance):
        tolerances.append(tolerance);delta=np.asarray(target)-tip
        tip[:]=target;point[:]+=delta
    p.move=move;p.move_point('left',{'actor':'blue_supply_1','local':[0,0,0]},[.05,0,0],tolerance=.005)
    assert tolerances and set(tolerances)=={.005}
    assert np.max(abs(point-[.05,0,0]))<=.005
