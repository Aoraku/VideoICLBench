import numpy as np
from videoicl_isaaclab.execution_design_pour_acquire import side_staging,approach_poses


def test_narrow_body_is_entered_sideways_below_wider_than_gripper_rim():
    point=np.array([0.,0.,.822]);r=np.eye(3)
    staging=side_staging(point,r,np.array([[0,.08,.08],[0,.10,.10]]))
    assert np.allclose(staging,[0,.13,.822])
    poses,end=approach_poses([-.19,-.3,.96],r,point,staging,.96,.012)
    assert np.allclose(end,point)
    # Within the 82.55mm source mouth projection, no descent through the rim:
    # the fingers enter only after reaching the safe lower body height.
    near=[np.array(row['position'])for row in poses if np.linalg.norm(np.array(row['position'])[:2])<.055]
    assert near and all(abs(p[2]-.822)<1e-12 for p in near)
    assert all(np.allclose(row['rotation'],r)for row in poses)


def test_approach_side_tracks_actual_palm_yaw_not_a_fixed_world_direction():
    r=np.array([[0.,-1.,0.],[1.,0.,0.],[0.,0.,1.]])
    stage=side_staging([0,0,.822],r,[[0,.08,.08]])
    assert np.allclose(stage,[-.13,0,.822])


def test_centred_upright_palm_is_not_misclassified_as_missing_geometry():
    stage=side_staging([0,0,.822],np.eye(3),[[0,0,.1]])
    assert np.allclose(stage,[.13,0,.822])


def test_recorded_cup_requires_small_exterior_offset_for_whole_side_sweep():
    import gzip,json
    from pathlib import Path
    from videoicl_isaaclab.execution_design_clip_grasp import convex_meshes_clear
    f=json.loads(gzip.decompress((Path(__file__).parent/'fixtures/e45_native_v17_exterior_geometry.json.gz').read_bytes()))
    d=f['recorded'];c=f['candidate'];r=np.asarray(c['rotation']);body=np.asarray(d['cup_position']);br=np.asarray(d['cup_rotation'])
    meshes=[np.asarray(x)for x in d['hand_meshes_relative_tcp'].values()];cup=np.asarray(d['cup_collision_vertices_task'])
    centred=body+br@np.array([0,0,c['z']]);point=body+br@np.asarray(c['grasp_local'])
    assert not convex_meshes_clear(meshes[0]@r.T+centred,cup)
    assert all(convex_meshes_clear(m@r.T+point,cup)for m in meshes)
    start=np.asarray(d['native_kinematics']['position']);staging=side_staging(point,r,meshes[0],br[:,0])
    poses,_=approach_poses(start,r,point,staging,.98,.012)
    waypoints=[start,*[np.asarray(row['position'])for row in poses]]
    assert all(convex_meshes_clear(np.vstack((m@r.T+a,m@r.T+b)),cup)
        for a,b in zip(waypoints,waypoints[1:])for m in meshes)
    assert min((m@r.T+point)[:,2].min()for m in meshes)>d['table_top_m']+.0002
    assert all(((m@r.T+point-body)@br)[:,2].max()<d['source_cup_bounds']['upper'][2]-d['ball_radius_m']+.002
        for m in meshes[1:])


def test_greedy_major_axis_is_preceded_by_outside_lateral_alignment():
    from videoicl_isaaclab.execution_design_pour_acquire import side_entry_waypoints
    staging=np.array([.003,-.13,.834]);point=np.array([0.,-.008,.834])
    align,end=side_entry_waypoints(staging,point)
    assert np.allclose(align,[0.,-.13,.834])and np.allclose(end,point)
