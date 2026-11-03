"""Check shared-clock ordering with the actual Controller.tick method body."""
from types import SimpleNamespace

import pytest

from videoicl_isaaclab.room_pool import RoomPool
from test_controller_render_updates_cpu import Controller


def setup_pool():
    controllers = {'E05': Controller(), 'E32': Controller()}
    events = []

    def step(render):
        events.append('step')
        for controller in controllers.values():
            controller.scene.actual_wrist += 1

    sim = SimpleNamespace(get_physics_dt=lambda: .004, step=step,
                          render=lambda: events.append('render'))
    for name, controller in controllers.items():
        controller.sim = sim
        controller.scene.root_path = '/World/Rooms/' + name
    return controllers, sim, events


def test_two_rooms_advance_the_world_once_and_keep_separate_evidence():
    controllers, sim, events = setup_pool()
    pool = RoomPool(sim, controllers)
    for _ in range(11):
        pool.tick()
    pool.tick(render=True)
    assert events.count('step') == 12
    assert events.count('render') == 1
    assert pool.physics_ticks == 12
    for controller in controllers.values():
        assert controller.physics_ticks == 12
        assert controller.scene.actual_wrist == 12
        assert controller.scene.camera_pose == 12
        assert sum(event[0] == 'evidence' for event in controller.events) == 12
        assert sum(event[0] == 'effort' for event in controller.events) == 12
        assert [event[1] for event in controller.events if event[0] == 'camera'] == pytest.approx([.048])


def test_all_room_targets_written_before_shared_step():
    controllers, sim, events = setup_pool()
    for name, controller in controllers.items():
        controller.scene.apply_passive_efforts = lambda name=name: events.append('write-' + name)
    RoomPool(sim, controllers).tick()
    assert events == ['write-E05', 'write-E32', 'step']


def test_reject_separate_context_or_timestep_before_claiming_room():
    for fault in ('context', 'dt', 'nested'):
        controllers, sim, _ = setup_pool()
        if fault == 'context':
            controllers['E32'].sim = SimpleNamespace()
        elif fault == 'dt':
            controllers['E32'].dt = .002
        else:
            controllers['E32'].scene.root_path = '/World/Rooms/E05/nested'
        with pytest.raises(ValueError):
            RoomPool(sim, controllers)
        assert not hasattr(controllers['E05'], '_room_pool')


def test_single_room_full_tick_cannot_double_advance_a_bound_pool():
    controllers, sim, events = setup_pool()
    RoomPool(sim, controllers)
    with pytest.raises(RuntimeError, match='RoomPool'):
        controllers['E05'].tick()
    assert events == []


def test_split_tick_rejects_render_and_unknown_phase():
    controller = Controller()
    with pytest.raises(ValueError):
        controller.tick(phase='write', render=True)
    with pytest.raises(ValueError):
        controller.tick(phase='other')
    assert controller.events == []
