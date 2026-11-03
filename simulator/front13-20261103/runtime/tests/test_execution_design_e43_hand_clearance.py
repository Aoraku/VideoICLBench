import json
from pathlib import Path

import numpy as np
import pytest

from videoicl_isaaclab.execution_design_e43_hand_clearance import (
    ball_corridor, box_points, equivalent_planes, hand_corridor_clear, public_route,
    first_route_failure, launcher_collision_parts, LAUNCHER_SOURCE_SHA, GUIDE_SOURCE_SHA,
    collision_shape_vertices,
)
from videoicl_isaaclab.realworld_tool_expert import _axis_rotation


def test_native_c31_opposite_winding_preserves_original_joint_margin():
    from scipy.spatial.transform import Rotation
    from videoicl_isaaclab.execution_design_local_pose_path import solve_local_pose_path
    from videoicl_isaaclab.execution_design_e43_hand_clearance import public_turns
    f=json.loads((Path(__file__).parent/'fixtures/e43_native_c_v31_winding.json').read_text())
    n=f['native'];root=f['guide_root'];actor=Rotation.from_quat([*root[4:7],root[3]]).as_matrix()
    current=np.asarray(n['rotation_task']);relative=actor.T@current
    target=np.asarray(f['target_actor_rotation']);position=np.asarray(n['position'])
    offset=actor.T@(position-np.asarray(root[:3]))
    intermediate=_axis_rotation([0,0,1],np.pi/2)@actor
    targets=[intermediate@relative,target@relative]
    turns,stopped=public_turns(position,current,targets)
    approach=np.asarray(f['working_point'])+(stopped@relative.T)@(offset-np.asarray(f['working_local']))
    moves,_=public_route(position,stopped,stopped,approach,.012,10.)
    path=solve_local_pose_path(n['position'],n['rotation_task'],n['jacobian'],n['q'],n['limits'],turns+moves)
    assert path['feasible'] and min(r['minimum_joint_margin_rad']for r in path['rows'])>.30
    assert path['constraints']['minimum_joint_margin_rad']==.06


def native_cases():
    path = Path(__file__).parent / 'fixtures/e43_native_v25_hand_corridors.json'
    return json.loads(path.read_text())['cases']


def fingers(case):
    result = []
    for row in case['finger_bounds']:
        lo, hi = np.asarray(row['aabb_min_task_m']), np.asarray(row['aabb_max_task_m'])
        result.append(box_points((lo + hi) / 2, (hi - lo) / 2))
    return result


def moved_fingers(case, *, flip=False, contact_local_x=0.):
    r, p = np.asarray(case['guide']['mat']), np.asarray(case['guide']['pos'])
    new = equivalent_planes(r)[int(flip)]
    return [((mesh - p) @ r) @ new.T + p - new @ np.array([contact_local_x, 0., 0.])
            for mesh in fingers(case)]


@pytest.mark.parametrize('case', native_cases(), ids=lambda c: c['variant'])
def test_actual_native_downstream_finger_contact_is_rejected(case):
    assert len(case['hand_contacts']) == 1
    assert case['hand_contacts'][0]['hand_contact_force'] > .3
    assert len(case['native_trajectory_sha256']) == 64
    corridors = ball_corridor(case['ball_start'], case['contact'], case['target'], .8, .014)
    assert not hand_corridor_clear(fingers(case), corridors)


def test_a_equivalent_plane_removes_actual_native_finger_bounds_from_ball_route():
    case = native_cases()[0]
    corridors = ball_corridor(case['ball_start'], case['contact'], case['target'], .8, .014)
    assert hand_corridor_clear(moved_fingers(case, flip=True), corridors)


@pytest.mark.parametrize('case', native_cases(), ids=lambda c: c['variant'])
def test_native_finger_bounds_allow_another_real_patch_on_the_same_guide_plane(case):
    # This CPU counterfactual leaves the entire plane unchanged. It is a
    # geometry proposal, not evidence that a robot executed or held this pose.
    corridors = ball_corridor(case['ball_start'], case['contact'], case['target'], .8, .014)
    assert hand_corridor_clear(moved_fingers(case, flip=True, contact_local_x=.020), corridors)
    old = np.asarray(case['guide']['mat']); new = equivalent_planes(old)[1]
    displacement = -new @ [.020, 0., 0.]
    assert float(displacement @ old[:, 1]) == pytest.approx(0., abs=1e-7)


def test_equivalent_plane_keeps_actual_tilted_source_box_and_face():
    r = _axis_rotation([1., 0., 0.], .04) @ _axis_rotation([0., 0., 1.], .91)
    a, b = equivalent_planes(r)
    box = box_points([0., 0., 0.], [.09, .003, .015])
    def points(rotation):
        return sorted(tuple(np.round(p, 12)) for p in box @ rotation.T)
    assert points(a) == points(b)
    assert np.allclose(a[:, 1], -b[:, 1])
    assert np.allclose(a[:, 2], b[:, 2])
    assert np.linalg.det(b) == pytest.approx(1.)


def test_swept_ball_corridor_rejects_a_finger_between_clear_endpoints():
    hand = box_points([0., 0., .814], [.005, .005, .005])
    assert np.linalg.norm(hand.mean(0) - [-.1, 0., .814]) > .05
    assert np.linalg.norm(hand.mean(0) - [.1, 0., .814]) > .05
    corridor = ball_corridor([-.1, 0., .814], [.1, 0., .814], [.2, 0., .8], .8, .014)
    assert not hand_corridor_clear([hand], corridor)


def test_public_route_preserves_actual_four_degree_rotation_stop_before_descent():
    start = np.eye(3); desired = _axis_rotation([0., 0., 1.], np.deg2rad(123.))
    poses, stopped = public_route([0., 0., 1.1], start, desired, [-.1, .02, .84])
    # Public held-tool rotation stops at 120 degrees, within its real 4-degree
    # bound. All following translations retain that actual predicted stop.
    expected = _axis_rotation([0., 0., 1.], np.deg2rad(120.))
    assert np.allclose(stopped, expected, atol=1e-8)
    translated = [p for p in poses if not np.allclose(p['position'], [0., 0., 1.1])]
    assert translated and all(np.allclose(p['rotation'], expected) for p in translated)
    assert np.allclose(poses[-1]['position'], [-.1, .02, .84])


@pytest.mark.parametrize('value', [0., -.01, float('nan')])
def test_invalid_native_ball_radius_fails_closed(value):
    with pytest.raises(ValueError):
        ball_corridor([0., 0., .82], [.1, 0., .82], [.2, 0., .8], .8, value)


def test_actual_native_upstream_hand_passes_real_source_ramp_but_not_its_empty_bounds():
    from videoicl_isaaclab.execution_design_tool_route_clearance import swept_route_clear
    path = Path(__file__).parent / 'fixtures/e43_native_v26_launcher_empty_bounds.json'
    f = json.loads(path.read_text()); launcher = f['launcher']
    assert launcher['collision_type'] == 'Cube' and launcher['collision_enabled'] is True
    assert len(launcher['source_local']) == 8
    native_shapes = f['source_collision_dump']['prims']
    assert any(p['type'] == 'Mesh' and p.get('collision_enabled') is False for p in native_shapes)
    assert any(p['type'] == 'Cube' and p.get('collision_enabled') is True for p in native_shapes)
    assert f['source_launcher_sha256'] == LAUNCHER_SOURCE_SHA
    assert f['native_old_proxy_whole_route_clear'] is False
    assert f['native_ball_corridor_clear'] is True
    body = launcher['actual']; r, p = np.asarray(body['mat']), np.asarray(body['pos'])
    source = np.asarray(launcher['source_local']) @ r.T + p
    old_box = box_points(launcher['descriptor_center'], launcher['descriptor_half']) @ r.T + p
    named = [(m['name'], np.asarray(m['vertices'])) for m in f['carried_local']]
    local = [m for _, m in named]
    args = (local, f['initial_position'], f['initial_rotation'], f['route'])
    assert not swept_route_clear(*args, [old_box], f['floor'])
    assert swept_route_clear(*args, [source], f['floor'])
    failure = first_route_failure(named, f['initial_position'], f['initial_rotation'], f['route'],
                                  [('whole_launcher_empty_bounds', old_box)], f['floor'])
    assert failure['waypoint'] == 54 and failure['reason'] == 'obstacle'
    assert failure['carried'] == 'panda_rightfinger_conservative_aabb'
    assert first_route_failure(named, f['initial_position'], f['initial_rotation'], f['route'],
                               [('actual_source_ramp', source)], f['floor']) is None


@pytest.mark.parametrize('change', ['source', 'dependency', 'path'])
def test_launcher_source_scope_is_checked_before_any_stage_read(change):
    from videoicl_isaaclab.realworld_tool_expert import ToolExecutionError
    obj = dict(id='launcher', mechanical_asset=dict(sha256=LAUNCHER_SOURCE_SHA,
               relative_path='source_plank_gravity_ramp_v2.usda', dependencies=[dict(sha256=GUIDE_SOURCE_SHA)]))
    if change == 'source':
        obj['mechanical_asset']['sha256'] = '0' * 64
    elif change == 'dependency':
        obj['mechanical_asset']['dependencies'] = []
    else:
        obj['mechanical_asset']['relative_path'] = 'another_task.usda'
    with pytest.raises(ToolExecutionError, match='Exact source E43 inclined plank'):
        launcher_collision_parts(None, obj, None)


class _Attr:
    def __init__(self, value): self.value = value
    def Get(self): return self.value


class _Collision:
    def __init__(self, prim): self.prim = prim
    def GetCollisionEnabledAttr(self): return _Attr(self.prim.enabled)


class _Cube:
    kind = 'Cube'
    def __init__(self, prim): self.prim = prim
    def GetSizeAttr(self): return _Attr(self.prim.size)


class _Mesh:
    kind = 'Mesh'
    def __init__(self, prim): self.prim = prim
    def GetPointsAttr(self): return _Attr(self.prim.points)


class _Prim:
    def __init__(self, kind, enabled, size=1., points=None):
        self.kind, self.enabled, self.size, self.points = kind, enabled, size, points
    def HasAPI(self, api): return True
    def IsA(self, schema): return self.kind == schema.kind
    def GetPath(self): return '/launcher/collider'
    def GetParent(self): raise AssertionError('collisionEnabled is not an ancestor-inherited flag')


def test_disabled_visual_mesh_and_enabled_cube_are_distinguished_without_parent_flags():
    from types import SimpleNamespace
    geom = SimpleNamespace(Cube=_Cube, Mesh=_Mesh)
    physics = SimpleNamespace(CollisionAPI=_Collision)
    visual = _Prim('Mesh', False, points=box_points([0., 0., 0.], [.5] * 3))
    collider = _Prim('Cube', True, size=1.)
    assert collision_shape_vertices(visual, geom, physics) is None
    points = collision_shape_vertices(collider, geom, physics)
    assert points.shape == (8, 3)
    assert np.allclose(points.min(0), -.5) and np.allclose(points.max(0), .5)
    # The exact composed nonuniform source scale and slope are applied once.
    f = json.loads((Path(__file__).parent / 'fixtures/e43_native_v26_launcher_empty_bounds.json').read_text())
    m = np.asarray(f['launcher']['source_cube_matrix_body_local'])
    transformed = points @ m[:3, :3] + m[3, :3]
    assert np.allclose(transformed, f['launcher']['source_local'], atol=1e-12)


def test_unknown_enabled_collision_shape_fails_closed():
    from types import SimpleNamespace
    from videoicl_isaaclab.realworld_tool_expert import ToolExecutionError
    with pytest.raises(ToolExecutionError, match='Unsupported enabled source launcher'):
        collision_shape_vertices(_Prim('Sphere', True), SimpleNamespace(Cube=_Cube, Mesh=_Mesh),
                                 SimpleNamespace(CollisionAPI=_Collision))
