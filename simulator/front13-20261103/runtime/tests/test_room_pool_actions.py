"""Actual Controller methods and barrier lifecycle with CPU adapters only."""
import ast
from copy import deepcopy
import importlib.util
import math
from pathlib import Path
from types import SimpleNamespace

import pytest

from videoicl_isaaclab.room_pool import RoomPool, global_scene_signature
from test_room_pool import setup_pool


def config(**physics):
    return dict(physics=dict(dt=.004, action_seconds=.4, render_hz=25,
        solver_position_iterations=16, solver_velocity_iterations=4,
        disable_gravity=True, self_collision=True, max_joint_delta=.08, **physics),
        layout=dict(kind='robotwin', background=dict(ambient_color=[1, 1, 1])),
        control=dict(step_mm=[.5, 50], rotation_deg=[.5, 20]))


def actual_methods():
    source = Path(__file__).resolve().parents[1]/'videoicl_isaaclab/control.py'
    tree = ast.parse(source.read_text())
    cls = next(n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == 'Controller')
    selected = [n for n in cls.body if isinstance(n, ast.FunctionDef) and n.name in {'validate_action', 'begin_action', 'action'}]
    namespace = dict(math=math, TOKENS={'STILL', 'GRASP', 'RELEASE'}, MOTION={},__package__='videoicl_isaaclab')
    exec(compile(ast.Module(body=selected, type_ignores=[]), str(source), 'exec'), namespace)
    return namespace


ACTUAL = actual_methods()


def active_pool():
    controllers, sim, events = setup_pool()
    sim.current_time = 0.
    original = sim.step
    def step(render):
        original(render)
        sim.current_time += .004
    sim.step = step
    for c in controllers.values():
        c.scene.embodiment = SimpleNamespace(config=config())
        c.steps = 0
        c.grips = dict(left=.04, right=.04)
        c.evaluator.result = lambda c=c: dict(success=False, conditions=[dict(passed=False)], tick=c.physics_ticks)
        for name in ('validate_action', 'begin_action', 'action'):
            setattr(c, name, ACTUAL[name].__get__(c))
    return RoomPool(sim, controllers), controllers, sim, events


def test_barrier_requires_all_replies_before_mutation_or_physics():
    pool, controllers, sim, events = active_pool()
    with pytest.raises(ValueError, match='every active|active room'):
        pool.action_batch({'E05': {'left': 'GRASP'}})
    assert sim.current_time == 0 and events == []
    assert all(c.grips['left'] == .04 for c in controllers.values())
    with pytest.raises(ValueError, match='Unknown action'):
        pool.action_batch({'E05': {'left': 'GRASP'}, 'E32': {'right': 'INVALID'}})
    assert sim.current_time == 0 and events == []
    assert all(c.grips['left'] == .04 for c in controllers.values())


def test_two_pairs_share_one_duration_and_hooks_follow_render():
    pool, controllers, sim, events = active_pool()
    receipts = pool.action_batch({'E05': {'left': 'GRASP'}, 'E32': {'right': 'GRASP'}})
    assert sim.current_time == pytest.approx(.4)
    assert pool.physics_ticks == 100 and events.count('step') == 100
    assert controllers['E05'].grips == dict(left=0., right=.04)
    assert controllers['E32'].grips == dict(left=.04, right=0.)
    for room, c in controllers.items():
        assert c.steps == 1 and c.physics_ticks == 100
        assert receipts[room]['simulation_seconds'] == pytest.approx(.4)
        assert sum(e[0] == 'hook' for e in c.events) == 100
        assert sum(e == ('hook', True) for e in c.events) == 10


def test_bounded_settle_waits_for_all_rooms_without_restarting_or_early_receipts():
    pool,controllers,sim,events=active_pool()
    calls={room:0 for room in controllers}
    for room,c in controllers.items():
        c.scene.embodiment.config['physics'].update(public_action_max_seconds=1.2,public_action_check_seconds=.1)
        begin=c.begin_action
        def once(*args,room=room,begin=begin,**kwargs):
            calls[room]+=1
            return begin(*args,**kwargs)
        c.begin_action=once
        c.public_action_converged=lambda c=c,room=room:c.physics_ticks>=(100 if room=='E05' else 175)
    receipts=pool.action_batch({room:{} for room in controllers})
    assert calls=={'E05':1,'E32':1}
    assert sim.current_time==pytest.approx(.7)
    assert events.count('step')==175
    for room,c in controllers.items():
        assert c.steps==1 and c.physics_ticks==175
        assert receipts[room]['physics_ticks']==175 and receipts[room]['settle_ticks']==75
        assert receipts[room]['maximum_action_ticks']==300
        assert receipts[room]['shared_tick_after']==175
        # The early room stays physically active and holds through the same
        # write/step/read loop; it is not reset, retired or captured early.
        assert sum(e[0]=='hook' for e in c.events)==175


def test_unconverged_room_reaches_cap_once_with_honest_final_tick():
    pool,controllers,sim,events=active_pool()
    for c in controllers.values():
        c.scene.embodiment.config['physics'].update(public_action_max_seconds=1.2,public_action_check_seconds=.1)
        c.public_action_converged=lambda:False
    receipts=pool.action_batch({room:{} for room in controllers})
    assert sim.current_time==pytest.approx(1.2) and events.count('step')==300
    for room,c in controllers.items():
        assert c.steps==1 and receipts[room]['physics_ticks']==300
        assert receipts[room]['settle_ticks']==200


def test_engineering_timing_changes_compatibility_and_invalid_windows_fail():
    from videoicl_isaaclab.room_pool import action_tick_limits
    a=config();b=deepcopy(a);b['physics']['public_action_max_seconds']=1.2
    assert global_scene_signature(a)!=global_scene_signature(b)
    assert action_tick_limits(a['physics'],.004)==(100,100,100)
    for value in (.3,0,float('nan'),.401):
        b['physics']['public_action_max_seconds']=value
        with pytest.raises(ValueError):action_tick_limits(b['physics'],.004)


def test_single_room_bad_timing_fails_before_begin_mutates_targets():
    began=[]
    c=SimpleNamespace(scene=SimpleNamespace(embodiment=SimpleNamespace(config=config(public_action_max_seconds=.1))),
                      dt=.004,begin_action=lambda *args:began.append(args))
    with pytest.raises(ValueError,match='bounded public action timing'):
        ACTUAL['action'](c)
    assert began==[]


def test_terminal_native_receipt_and_recorder_stop_without_physics_restore():
    pool, controllers, sim, _ = active_pool()
    pool.action_batch({room: {} for room in controllers})
    terminal = pool.seal('E05')
    hooks_before = len([e for e in controllers['E05'].events if e[0] == 'hook'])
    pool.action_batch({'E32': {'left': 'GRASP'}})
    assert controllers['E05'].physics_ticks == 200  # Physical world continues.
    assert controllers['E05'].steps == 1 and controllers['E32'].steps == 2
    assert pool.terminal_result('E05') == terminal
    assert len([e for e in controllers['E05'].events if e[0] == 'hook']) == hooks_before
    terminal['native']['success'] = True
    assert pool.terminal_result('E05')['native']['success'] is False
    assert pool.terminal_result('E05')['physical_world_frozen'] is False


def test_bound_controller_action_fails_before_targets_change():
    pool, controllers, sim, _ = active_pool()
    with pytest.raises(RuntimeError, match='RoomPool'):
        controllers['E05'].action(left='GRASP')
    assert controllers['E05'].grips['left'] == .04 and sim.current_time == 0


def test_isolated_render_hooks_read_their_own_room_before_next_render():
    pool, controllers, sim, events = active_pool()
    pool.render_isolation = True
    viewed = []
    current = [None]
    for room, controller in controllers.items():
        controller.tick_hooks = [lambda controller, render, room=room:
            viewed.append((room, current[0], render, pool.physics_ticks))]
    def render_room(room, *, passes=1, capture=None):
        current[0] = room
        sim.render()
        return capture()
    pool.render_room = render_room
    pool.tick(render=True)
    assert events.count('step') == 1
    assert viewed == [('E05', 'E05', True, 1), ('E32', 'E32', True, 1)]


def test_global_compatibility_allows_actor_differences_but_not_world_changes():
    a = config();b = deepcopy(a)
    b['physics']['solver_position_iterations'] = 32
    b['control']['step_mm'] = [1, 10]
    assert global_scene_signature(a) == global_scene_signature(b)
    for change in [('dt', .002), ('enable_stabilization', False), ('action_seconds', .8)]:
        b = deepcopy(a);b['physics'][change[0]] = change[1]
        assert global_scene_signature(a) != global_scene_signature(b)
    b = deepcopy(a);b['layout']['background']['ambient_color'] = [0, 0, 0]
    assert global_scene_signature(a) != global_scene_signature(b)


def test_mismatched_profile_refused_before_any_controller_is_claimed():
    controllers, sim, _ = setup_pool()
    for c in controllers.values():c.scene.embodiment = SimpleNamespace(config=config())
    controllers['E32'].scene.embodiment.config['physics']['enable_stabilization'] = False
    with pytest.raises(ValueError, match='incompatible'):
        RoomPool(sim, controllers)
    assert not any(hasattr(c, '_room_pool') for c in controllers.values())


def test_case_ids_allow_same_task_ABC_and_fifteen_rooms(tmp_path):
    source = Path(__file__).resolve().parents[1]/'scripts/probe_realworld_room_pool.py'
    spec = importlib.util.spec_from_file_location('native_pool_probe_test', source)
    module = importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    bindings = tmp_path/'bindings.json';bindings.write_text('{}')
    rows = [dict(episode_id=f'episode-{i}', task='E05', variant='ABC'[i%3], seed=i, bindings='bindings.json') for i in range(15)]
    checked = module.normalize_cases(rows, base=tmp_path)
    assert len(checked) == 15 and len({r['episode_id'] for r in checked}) == 15
    assert {r['variant'] for r in checked} == {'A', 'B', 'C'}
    rows[-1]['episode_id'] = rows[0]['episode_id']
    with pytest.raises(ValueError, match='episode_id'):
        module.normalize_cases(rows, base=tmp_path)


@pytest.mark.parametrize('field,value', [('task', 'E51'), ('variant', 'AB'), ('seed', False), ('episode_id', '../escape')])
def test_invalid_probe_case_is_rejected_before_native_start(tmp_path, field, value):
    source = Path(__file__).resolve().parents[1]/'scripts/probe_realworld_room_pool.py'
    spec = importlib.util.spec_from_file_location('invalid_pool_probe_test', source)
    module = importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    bindings = tmp_path/'bindings.json';bindings.write_text('{}')
    row = dict(task='E05', variant='A', seed=0, episode_id='one', bindings=str(bindings));row[field] = value
    with pytest.raises(ValueError):module.normalize_cases([row], base=tmp_path)
