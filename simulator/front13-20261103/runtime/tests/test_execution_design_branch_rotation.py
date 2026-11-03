from types import SimpleNamespace
import math
import numpy as np
import pytest
import videoicl_isaaclab.execution_design_branch_rotation as rotation
from videoicl_isaaclab.realworld_tool_expert import ToolExecutionError


class Guard:
    def __init__(self):self.checks=0
    def __call__(self):self.checks+=1
    def check(self,**kwargs):self.checks+=1


def policy(errors):
    index=[0];commands=[]
    def feedback():
        return dict(control_feedback={'right':dict(orientation_error_rad=math.radians(errors[min(index[0],len(errors)-1)]),position_error_m=.0001,orientation_tolerance_rad=math.radians(1),position_tolerance_m=.002)})
    def act(side,token):commands.append((side,token));index[0]+=1
    return SimpleNamespace(c=SimpleNamespace(action_feedback=feedback),a=SimpleNamespace(tcp_rotation_task=lambda side:np.eye(3)),act=act),commands


def test_rotation_continues_original_target_and_stops_at_public_one_degree(monkeypatch):
    p,commands=policy([8,4,1.2,.9]);guard=Guard()
    monkeypatch.setattr(rotation,'accepted_pose_task',lambda *args:(np.zeros(3),np.eye(3)))
    assert rotation.finish_accepted_public_rotation(p,'right',guard)==3
    assert commands==[('right','STILL')]*3
    assert guard.checks>=4


def test_rotation_stops_when_public_feedback_has_real_persistent_plateau(monkeypatch):
    p,commands=policy([2]*30);monkeypatch.setattr(rotation,'accepted_pose_task',lambda *args:(np.zeros(3),np.eye(3)))
    with pytest.raises(ToolExecutionError,match='no actual progress'):rotation.finish_accepted_public_rotation(p,'right',Guard())
    assert len(commands)==12
