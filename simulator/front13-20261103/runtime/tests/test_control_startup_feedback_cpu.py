"""Read-only feedback must work before any public action and after private hold."""
import torch
from test_control_smoothness_cpu import NS,controller


def idle_controller():
    c=controller();c._public_blocked={};c._public_limit_seen={}
    c.scene.embodiment.arm_joints=['joint1']
    c._public_action=None
    c.targets={side:tuple(x.clone()for x in c.pose(side))for side in c.scene.robots}
    return c


def test_startup_before_first_public_action_has_no_uninitialized_start():
    c=idle_controller()
    if hasattr(c,'_public_start'):del c._public_start
    result=NS['action_feedback'](c)['control_feedback']['left']
    assert result['actual_delta_m']==[0.,0.,0.]
    assert result['requested_delta_m']==[0.,0.,0.]
    assert result['continuing_rotation_target']is False


def test_private_to_idle_feedback_does_not_reuse_old_public_action_start():
    c=idle_controller();NS['begin_action'](c,left='UP',step_mm=10.)
    position,rotation=c.pose('left');position=position+torch.tensor([[.02,0.,.03]])
    c.pose=lambda side:(position,rotation)
    c.targets['left']=(position.clone(),rotation.clone())
    c._public_action=None;c._public_rotation_intent={'left':True}
    result=NS['action_feedback'](c)['control_feedback']['left']
    assert result['actual_delta_m']==[0.,0.,0.]
    assert result['requested_delta_m']==[0.,0.,0.]
    assert result['continuing_rotation_target']is False
