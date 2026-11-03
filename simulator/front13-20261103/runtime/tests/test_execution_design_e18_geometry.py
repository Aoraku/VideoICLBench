"""Complete-hand geometry tests; CPU checks never imply native acceptance."""
import json,math,sys
from pathlib import Path
from types import SimpleNamespace
import numpy as np
import pytest
from videoicl_isaaclab.execution_design_e18_geometry import actual_hand_clouds,candidate_clearance
from videoicl_isaaclab.realworld_tool_expert import _axis_rotation


def fixture():
    palm=json.loads((Path(__file__).parent/'data/e18-panda-native-palm-hull.json').read_text())
    return dict(source='actual_native_collision_mesh_current_body_pose',table_top=.8,jaw_axis_tcp=[0,1,0],
        clouds_tcp=[np.array([[0,.05,0],[.005,.04,-.01]]),np.array([[0,-.05,0],[.005,-.04,-.01]]),np.array(palm['vertices_tcp'])])


def test_native_palm_hull_rejects_vertical_grip_despite_clear_fingers():
    base=np.array([[0,0,1],[1,0,0],[0,1,0.]])
    for sign in (1.,-1.):
        rotation=base@np.diag([sign,sign,1.])
        got=candidate_clearance(fixture(),rotation,[-.084,.075,.878],[-1,0,0],[0,-1,0])
        assert min(got['hand_floor_clearances_m'][:2])>.02
        assert got['hand_floor_clearances_m'][2]<-.02
        assert not got['feasible'] and not got['collision_verified']


@pytest.mark.parametrize('roll,tilt',[(45,15),(-45,15),(30,25),(-30,25)])
def test_oblique_grasp_preserves_opening_and_real_palm_table_margin(roll,tilt):
    base=np.array([[0,0,1],[1,0,0],[0,1,0.]])
    rotation=_axis_rotation([0,1,0],math.radians(tilt))@_axis_rotation([1,0,0],math.radians(roll))@base
    got=candidate_clearance(fixture(),rotation,[-.084,.075,.878],[-1,0,0],[0,-1,0])
    assert min(got['hand_floor_clearances_m'])>.01
    assert got['bar_projected_width_m']<.078 and got['feasible']
    assert got['palm_outside_handle_plane_m']>.003
    assert not got['collision_verified']
    # The long97.94mm axis itself cannot fit through the80mm Panda opening.
    long_axis=_axis_rotation([1,0,0],math.pi/2)@base
    assert not candidate_clearance(fixture(),long_axis,[-.084,.075,1.2],[-1,0,0],[0,-1,0])['feasible']


def test_unmeasured_geometry_cannot_enable_candidate():
    with pytest.raises(RuntimeError,match='Actual native'):
        candidate_clearance({'source':'nominal_size'},np.eye(3),[0,0,1],[-1,0,0],[0,-1,0])


class Tensor(np.ndarray):
    def cpu(self):return self
    def numpy(self):return np.asarray(self)


def test_cached_meshes_are_reprojected_from_actual_room_body_poses(monkeypatch):
    monkeypatch.setitem(sys.modules,'pxr',SimpleNamespace(Usd=None,UsdGeom=None,UsdPhysics=None))
    usd=SimpleNamespace();monkeypatch.setitem(sys.modules,'omni',SimpleNamespace(usd=usd));monkeypatch.setitem(sys.modules,'omni.usd',usd)
    origin=np.array([12.,-6.,0.]);task=_axis_rotation([0,0,1],math.pi/2);tcp_rotation=_axis_rotation([1,0,0],math.pi/2)
    points=np.array([[.01,.02,.03],[-.02,.03,.04]])
    pose=np.array([[origin+[.1,.2,1.],origin+[.15,.2,1.],origin+[.125,.2,1.05]]]).view(Tensor)
    quat=np.tile([1.,0.,0.,0.],(1,3,1)).view(Tensor)
    robot=SimpleNamespace(data=SimpleNamespace(body_pos_w=pose,body_quat_w=quat))
    scene=SimpleNamespace(root_path='/World/Rooms/room_09',robots={'left':robot},origin=origin,
        layout=SimpleNamespace(task_rotation=task,config={'table':dict(position=[0,0,.775],size=[1,1,.05])}),
        world_to_task=lambda p:task.T@(p-origin))
    author=SimpleNamespace(scene=scene,_e18_palm_mesh={'left':(2,points)},_finger_collision_points={'left':[(0,points),(1,points)]},
        finger_geometry=lambda side:None,tip=lambda side:np.array([.2,-.125,.95]),tcp_rotation_task=lambda side:tcp_rotation)
    got=actual_hand_clouds(author,'left');expected=(points@task+scene.world_to_task(pose[0,2])-author.tip('left'))@tcp_rotation
    assert got['table_top']==pytest.approx(.8)
    np.testing.assert_allclose(got['clouds_tcp'][2],expected)
    pose[0,2,2]+=.08
    new=actual_hand_clouds(author,'left')
    np.testing.assert_allclose(new['clouds_tcp'][2]-got['clouds_tcp'][2],np.tile(np.array([0,0,.08])@tcp_rotation,(2,1)),atol=1e-12)


def test_rotation_sphere_bounds_entire_hand_at_staging():
    g=fixture();r=np.array([[0,0,1],[1,0,0],[0,1,0.]])
    got=candidate_clearance(g,r,[-.084,.075,.878],[-1,0,0],[0,-1,0])
    rng=np.random.default_rng(4201)
    for _ in range(30):
        turn=_axis_rotation(rng.normal(size=3),rng.uniform(-math.pi,math.pi))
        minimum=min(float((np.array(c)@turn.T)[:,2].min())for c in g['clouds_tcp'])
        assert got['rotation_safe_z_m']+minimum-g['table_top']>=.014999
