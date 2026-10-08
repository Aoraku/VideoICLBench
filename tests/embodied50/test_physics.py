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
