"""Reference regression for native E26 IA4201: contact during lateral move."""
from types import SimpleNamespace
import numpy as np
import pytest
from videoicl_isaaclab.realworld_mechanism_expert import _Author,MechanismExecutionError


def author():
    p=object.__new__(_Author)
    p.roles={'right':dict(open_threshold=.002,closed_tolerance=.001)}
    p.motion={'right':dict(max_travel=.01)}
    p.a=SimpleNamespace(stage='mechanism-press-right-1')
    p.q=0.;p.contact=False
    p.tip=lambda side:np.array([0.,0.,.86])
    p.point=lambda role:np.array([.004,0.,.86])
    p.axis=lambda role:np.array([0.,0.,-1.])
    p.displacement=lambda role:p.q
    p.touching=lambda role,side:p.contact
    return p


def test_press_reached_during_transverse_motion_stops_before_extra_down():
    p=author();moves=[];actions=[]
    def move(side,target,tolerance,done):
        assert not done()
        p.q=.002216818;p.contact=True
        assert done()
        moves.append(target)
    p.move=move;p.act=lambda *a,**kw:actions.append(a)
    p.press_steps('right','right',p.tip('right'))
    assert len(moves)==1 and actions==[]


def test_displacement_without_actual_contact_is_still_rejected():
    p=author()
    def move(side,target,tolerance,done):
        p.q=.0023
        done()
    p.move=move
    with pytest.raises(MechanismExecutionError,match='without observed plunger contact'):
        p.press_steps('right','right',p.tip('right'))


def test_transverse_arrival_without_press_continues_public_down():
    p=author();actions=[]
    p.move=lambda side,target,tolerance,done:None
    def act(side,token,mm):
        actions.append((side,token,mm));p.q=.0023;p.contact=True
    p.act=act
    p.press_steps('right','right',p.tip('right'))
    assert actions==[('right','DOWN',2.)]


def test_reentering_reviewed_lateral_corridor_does_not_assert_press():
    p=author();tip=np.array([0.,0.,.86]);p.tip=lambda side:tip.copy();actions=[]
    def move(side,target,tolerance,done):
        assert not done()
        # The native failure oscillated across 1.5mm axial tolerances while
        # already inside the original 3mm lateral corridor. It should resume
        # the measured downward press, never infer an event from alignment.
        tip[0]=.0012
        assert done()
        assert p.q==0.
    p.move=move
    def act(side,token,mm):
        actions.append(token);p.q=.0023;p.contact=True
    p.act=act;p.press_steps('right','right',tip.copy())
    assert actions==['DOWN']
