import math
import numpy as np
import pytest
pytest.importorskip('robosuite')
from simulator.benchmark.catalog import task_spec
from simulator.benchmark.environment import DesktopDual

@pytest.fixture
def env():
    e=DesktopDual(task_spec('rt01'),render=False)
    yield e
    e.close()

def test_real_stack_contact_and_terminal_hold(env):
    a=env.items['red']; b=env.snapshot()['blue']['pos'].copy()
    env.sim.data.set_joint_qpos(a.joints[0],list(b+[0,0,.05])+[1,0,0,0])
    env.sim.forward()
    for _ in range(4): env.action()
    assert env.score()['success']
    # XY overlap alone must not pass when suspended without support.
    env.sim.data.set_joint_qpos(a.joints[0],list(b+[0,0,.2])+[1,0,0,0]); env.sim.forward()
    assert not env.predicate(env.spec['goals'][0],env.snapshot())

def test_actions_move_requested_arm_in_world_frame(env):
    before=[env._eef0_xpos.copy(),env._eef1_xpos.copy()]
    env.action('FWD','STILL')
    assert .01<env._eef0_xpos[0]-before[0][0]<.025
    assert np.linalg.norm(env._eef1_xpos-before[1])<.005
    assert not env.score()['success']

def test_upright_does_not_accept_upside_down_bottle():
    e=DesktopDual(task_spec('rt22'),render=False)
    try:
        goal=e.spec['goals'][0]; state=e.snapshot()
        assert not e.predicate(goal,state)
        state['bottle']['mat']=np.diag([1,-1,-1])
        assert not e.predicate(goal,state)
        state['bottle']['mat']=np.eye(3)
        assert e.predicate(goal,state)
    finally: e.close()

def test_handover_requires_event():
    e=DesktopDual(task_spec('rt07'),render=False)
    try:
        assert not e.predicate(e.spec['goals'][0],e.snapshot())
    finally: e.close()


def test_open_bowl_supports_food_but_rejects_hover():
    e=DesktopDual(task_spec('rc24'),render=False)
    try:
        b=e.snapshot()['bowl']['pos'].copy()
        p=b+[0,0,-.025+.008+.014]
        e.sim.data.set_joint_qpos(e.items['meat'].joints[0],list(p)+[1,0,0,0]);e.sim.forward()
        for _ in range(4):e.action()
        assert e.score()['success']
        e.sim.data.set_joint_qpos(e.items['meat'].joints[0],list(b+[0,0,.07])+[1,0,0,0]);e.sim.forward()
        assert not e.predicate(e.spec['goals'][0],e.snapshot())
    finally:e.close()


def test_handover_excludes_simultaneous_touch_and_table_relay(monkeypatch):
    e=DesktopDual(task_spec('rt07'),render=False)
    try:
        state=e.snapshot();state['item']['pos']=np.array([0,0,1.])
        state['item']['mat']=np.eye(3)
        monkeypatch.setattr(e,'snapshot',lambda:state)
        state['item']['grasp']=[True,False];e.track()
        state['item']['grasp']=[True,True]
        for _ in range(8):e.track()
        assert ('handover','item') not in e.events
        state['item']['grasp']=[False,True]
        for _ in range(3):e.track()
        assert ('handover','item') not in e.events
        e.track();assert ('handover','item') in e.events
        e.events.clear();e._left_airborne.clear();e._receive_hold.clear()
        state['item']['grasp']=[True,False];e.track()
        state['item']['pos'][2]=.825;state['item']['grasp']=[False,False];e.track()
        state['item']['pos'][2]=1.;state['item']['grasp']=[False,True]
        for _ in range(8):e.track()
        assert ('handover','item') not in e.events
    finally:e.close()

def test_phone_slot_requires_supported_bottom_and_rejects_hover():
    e=DesktopDual(task_spec('rt19'),render=False)
    try:
        stand=e.snapshot()['stand']['pos'];z=stand[2]-.04+.008+.075
        q=[stand[0],stand[1],z,.70710678,0,.70710678,0]
        e.sim.data.set_joint_qpos(e.items['phone'].joints[0],q);e.sim.forward()
        for _ in range(4):e.action()
        goal=e.spec['goals'][0]
        assert e.predicate(goal,e.snapshot())
        q[2]+=.12;e.sim.data.set_joint_qpos(e.items['phone'].joints[0],q);e.sim.forward()
        assert not e.predicate(goal,e.snapshot())
    finally:e.close()

def test_floating_bin_cannot_pass_with_contents_inside(monkeypatch):
    e=DesktopDual(task_spec('rc24'),render=False)
    try:
        state=e.snapshot()
        state['bowl']['pos']=np.array([.15,0,1.025])
        state['meat']['pos']=np.array([.15,0,1.022])
        for v in state.values():v['grasp']=[False,False];v['mat']=np.eye(3)
        e.last_positions={k:v['pos'].copy() for k,v in state.items()}
        monkeypatch.setattr(e,'snapshot',lambda:state)
        monkeypatch.setattr(e,'check_contact',lambda a,b:b!='table_collision')
        assert e.predicate(e.spec['goals'][0],state)
        for _ in range(20):e.track()
        assert not e.score()['success']
    finally:e.close()
