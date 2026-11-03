import math
from types import SimpleNamespace
import numpy as np
import pytest
from videoicl_isaaclab.execution_design_e24_side_pinch import pitch_to_side,side_grasp_local
from videoicl_isaaclab.realworld_tool_expert import ToolExecutionError


def test_explicit_pitch_stops_after_three_real_nonadvancing_actions(monkeypatch):
 from videoicl_isaaclab import execution_design_segments_e23_e24 as air
 from videoicl_isaaclab.realworld_tool_expert import _axis_rotation
 monkeypatch.setattr(air,'_air_check',lambda *args,**kwargs:{})
 monkeypatch.setattr(air,'_air_feedback',lambda *args:None)
 calls=[];c=SimpleNamespace(steps=0)
 def act(*args,**kwargs):calls.append((args,kwargs));c.steps+=1
 p=SimpleNamespace(c=c,snapshot=lambda:({'lid':dict(grasp=[False,False])},[]),a=SimpleNamespace(tcp_rotation_task=lambda _:np.eye(3)),tip=lambda _:np.array([0,0,.98]),act=act)
 with pytest.raises(ToolExecutionError,match='three actions'):pitch_to_side(p,_axis_rotation([0,1,0],-math.pi/3))
 assert len(calls)==3 and all(args==('left','PITCH_DOWN')and kwargs['degrees']==10 for args,kwargs in calls)


def test_source_grasp_centers_actual_whole_lid_height_not_roof(monkeypatch):
 from videoicl_isaaclab import execution_design_e24_collision as collision
 points=np.array([[0,0,-.022],[0,0,.022]])
 monkeypatch.setattr(collision,'actual_object_parts',lambda _: [dict(name='object:lid:part0',points=points)])
 p=SimpleNamespace(snapshot=lambda:({'lid':dict(pos=np.zeros(3),mat=np.eye(3))},[]))
 np.testing.assert_allclose(side_grasp_local(p),[0,.098,0])
