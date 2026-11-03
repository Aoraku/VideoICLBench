"""The far box changes which arm can avoid a stretched cross-table route."""
import numpy as np
import pytest
from videoicl_isaaclab.execution_design_e09_hand import rank_hands
from videoicl_isaaclab.realworld_tool_expert import ToolExecutionError

BASES={'left':[-.6,.3,.8],'right':[-.6,-.3,.8]}


def test_far_blue_group_prefers_nearer_destination_arm():
    side,cost=rank_hands([-.18,-.1,.84],[.1,.1,.84],BASES,'right')
    assert side=='left'
    assert cost['right']-cost['left']>.07


def test_near_red_group_retains_shorter_source_side_route():
    side,cost=rank_hands([-.28,-.3,.84],[-.2,.1,.84],BASES,'right')
    assert side=='right' and cost['right']<cost['left']


def test_same_choice_after_room_translation_and_rotation():
    source=np.array([-.18,-.1,.84]);goal=np.array([.1,.1,.84]);shift=np.array([8.,-2.,.4])
    r=np.array([[0.,-1,0],[1,0,0],[0,0,1]])
    assert rank_hands(r@source+shift,r@goal+shift,{k:r@np.array(v)+shift for k,v in BASES.items()},'right')[0]=='left'


def test_equal_route_preserves_preferred_hand():
    assert rank_hands([-.3,0,.84],[0,0,.84],BASES,'right')[0]=='right'


@pytest.mark.parametrize('source,goal,bases,preferred',[
    ([0,0,float('nan')],[0,0,0],BASES,'left'),
    ([0,0,0],[float('inf'),0,0],BASES,'left'),
    ([0,0],[0,0,0],BASES,'left'),
    ([0,0,0],[0,0,0],{'left':[0,0,0]},'left'),
    ([0,0,0],[0,0,0],{**BASES,'left':[float('nan'),0,0]},'left'),
    ([0,0,0],[0,0,0],BASES,'other')])
def test_missing_or_invalid_native_geometry_is_rejected(source,goal,bases,preferred):
    with pytest.raises(ToolExecutionError):rank_hands(source,goal,bases,preferred)
