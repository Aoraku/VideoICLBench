import numpy as np
from videoicl_isaaclab.execution_design_e46_finite_backstop import face_candidates

def box(half,center):
    return np.array([[x,y,z]for x in (-half[0],half[0])for y in (-half[1],half[1])for z in (-half[2],half[2])])+center

def test_finite_low_faces_reach_food_without_downward_normals():
    meshes=[box([.02,.02,.02],[0,0,0]),box([.005,.005,.02],[0,.04,.05]),box([.005,.005,.02],[0,-.04,.05])]
    rows=face_candidates(meshes,np.array([1.,0,0]),.8,np.array([.1,0,.803]),np.array([.02,.02,.003]))
    assert rows
    for row in rows:
        assert abs(row['normal'][2])<.12
        assert row['finite_z_band'][1]<=.8055+1e-12
        assert row['finite_z_band'][0]>=.8005-1e-12

def test_high_face_cannot_be_used_as_infinite_support_plane():
    meshes=[box([.02,.02,.10],[0,0,0]),box([.005,.005,.005],[0,.04,-.05]),box([.005,.005,.005],[0,-.04,-.05])]
    assert not face_candidates(meshes,np.array([1.,0,0]),.8,np.array([.1,0,.803]),np.array([.02,.02,.003]))


def test_oblique_face_offset_keeps_entire_food_outside_actual_pad_plane():
    meshes=[box([.02,.02,.02],[0,0,0]),box([.005,.005,.02],[0,.04,.05]),box([.005,.005,.02],[0,-.04,.05])]
    food=np.array([.1,0,.803]);half=np.array([.02,.02,.003])
    rows=face_candidates(meshes,np.array([1.,0,0]),.8,food,half)
    assert any(abs(row['normal'][1])>.2 for row in rows)
    for row in rows:
        n=np.asarray(row['normal']);rotation=np.asarray(row['rotation']);position=np.asarray(row['position'])
        pad=(meshes[row['finger']]@rotation.T+position)@n
        assert food@n-pad.max()-np.abs(n)@half>=.0006-1e-10
