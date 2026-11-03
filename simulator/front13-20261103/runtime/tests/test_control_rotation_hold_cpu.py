"""STILL continues only an existing unfinished public rotation, never a new one."""
import json
import math
from pathlib import Path

import pytest
import torch
from test_control_smoothness_cpu import NS, controller, linearized_test_plant, qz


def test_still_retains_exact_goal_and_small_rotation_tolerance_across_waits():
    c=controller()
    NS['begin_action'](c,left='ROTATE_CCW',rotation_deg=.5)
    target=tuple(x.clone() for x in c.targets['left'])
    tolerance=c._public_tolerances['left']
    for _ in range(3):
        NS['begin_action'](c,left='STILL',rotation_deg=20.)
        assert c._public_rotation_intent=={'left':True}
        assert c._public_tolerances['left']==tolerance
        assert tolerance[1]==pytest.approx(math.radians(.05))
        for a,b in zip(c.targets['left'],target):torch.testing.assert_close(a,b)
    assert not c._public_rotation_intent.get('right',False)


@pytest.mark.parametrize('token',['FWD','MV_UP','GRASP','RELEASE'])
def test_explicit_nonrotation_breaks_continuation_without_erasing_orientation(token):
    c=controller()
    NS['begin_action'](c,left='ROTATE_CCW',rotation_deg=5.)
    target=c.targets['left'][1].clone()
    NS['begin_action'](c,left=token)
    NS['begin_action'](c,left='STILL')
    assert not c._public_rotation_intent.get('left',False)
    torch.testing.assert_close(c.targets['left'][1],target)


def test_private_transition_and_reached_goal_clear_continuation():
    c=controller()
    NS['begin_action'](c,left='ROTATE_CCW',rotation_deg=5.)
    c._public_action=None
    NS['begin_action'](c,left='STILL')
    assert not c._public_rotation_intent.get('left',False)
    NS['begin_action'](c,left='ROTATE_CCW',rotation_deg=5.)
    measured=tuple(x.clone() for x in c.targets['left'])
    c.pose=lambda side:measured
    NS['begin_action'](c,left='STILL')
    assert not c._public_rotation_intent.get('left',False)


def test_plain_still_does_not_authorize_stale_orientation():
    c=controller()
    NS['begin_action'](c,left='STILL')
    assert not c._public_rotation_intent
    e=NS['pose_residual'](*c.pose('left'),*c.targets['left'])
    assert not NS['public_motion_guard'](e,e*.1,torch.tensor([True]),False).item()


def test_production_tick_receives_rotation_intent_for_continued_wait(monkeypatch):
    c,_,_=linearized_test_plant();seen=[]
    original=NS['guarded_cartesian_delta']
    def capture(J,e,lo,hi,rotation):
        seen.append(rotation)
        return original(J,e,lo,hi,rotation)
    monkeypatch.setitem(NS,'guarded_cartesian_delta',capture)
    NS['begin_action'](c,left='ROTATE_CCW',rotation_deg=5.)
    NS['begin_action'](c,left='STILL')
    NS['tick'](c,phase='write')
    assert seen==[True]
    feedback=NS['action_feedback'](c)['control_feedback']['left']
    assert feedback['continuing_rotation_target'] is True
    assert feedback['orientation_tolerance_rad']==pytest.approx(math.radians(.5))
    NS['begin_action'](c,left='UP',step_mm=2.)
    NS['tick'](c,phase='write')
    assert seen[-1] is False


def test_actual_e08_guard_sample_with_identical_joint_bounds():
    """Guard isolation, not native PhysX/rolling-reference servo replay."""
    f=Path(__file__).parent/'fixtures/e08_still_rotation_guard.json'
    d=json.loads(f.read_text());J=torch.tensor([d['jacobian_task']],dtype=torch.float64)
    e=torch.tensor([d['residual_task']],dtype=torch.float64)
    lo=torch.full((1,7),-.02,dtype=torch.float64);hi=-lo
    solve=NS['guarded_cartesian_delta']
    old,old_ok=solve(J,e,lo,hi,False)
    corrected,ok=solve(J,e,lo,hi,True)
    assert not old_ok.item() and torch.count_nonzero(old)==0
    assert ok.item() and ((corrected>=lo)&(corrected<=hi)).all()
    predicted=(J@corrected[...,None]).squeeze(-1)
    assert (e[:,:3]-predicted[:,:3]).norm()<.002
    assert (e[:,3:]*predicted[:,3:]).sum()>0
    assert (e[:,3:]-predicted[:,3:]).norm()<e[:,3:].norm()
