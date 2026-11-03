from types import SimpleNamespace
import numpy as np
import pytest
from videoicl_isaaclab.execution_design import REVISION_V3
from videoicl_isaaclab.execution_design_e31_orientation import swept_radius,align_face


def test_measured_rim_pinch_requires_full_rotation_sweep_not_thickness():
    half=[.094,.09431978646613787,.012388977175874649]
    offset=[-.09178000006787367,.000791307046523443,.01093683756397879]
    radius=swept_radius([0,0,.812],np.eye(3),half,[0,0,0],np.array([0,0,.812])+offset)
    assert radius==pytest.approx(.210010529,abs=1e-8)
    assert .854018917509783+radius+.025>1.089


def test_swept_radius_is_invariant_under_rigid_frame_rotation():
    r=np.array([[0,0,1],[0,1,0],[-1,0,0]])
    p=np.array([.1,.2,.3]);tcp=np.array([.15,.19,.31]);half=[.1,.02,.01]
    a=swept_radius(p,np.eye(3),half,[.01,0,0],tcp)
    assert swept_radius(r@p,r,half,[.01,0,0],r@tcp)==pytest.approx(a)


def test_already_upright_held_plate_does_not_impose_yaw(tmp_path):
    yaw=.8;r=np.array([[np.cos(yaw),-np.sin(yaw),0],[np.sin(yaw),np.cos(yaw),0],[0,0,1]])
    state={'plate':dict(mat=r,grasp=[False,True])}
    spec=dict(id='E31',execution_design=dict(revision=REVISION_V3),semantic=dict(plate='plate',bowl='bowl',plate_face='up'),objects=[dict(id='plate')])
    a=SimpleNamespace(_execution_design_reference_authorized=True,scene=SimpleNamespace(spec=spec),c=SimpleNamespace(steps=10,snapshot=lambda:(state,set())),carried_payload=('plate','right'),out=tmp_path)
    align_face(a,'plate','right')
    assert 'rotation_needed' in (tmp_path/'e31-face-clearance.private.jsonl').read_text()
    state['plate']['grasp']=[False,False]
    with pytest.raises(RuntimeError,match='actual held'):align_face(a,'plate','right')


def test_reject_nonfinite_geometry():
    with pytest.raises(ValueError):swept_radius([0,0,0],np.eye(3),[1,1,float('nan')],[0,0,0],[0,0,0])


def test_actual_support_contact_blocks_rotation_after_lift(tmp_path,monkeypatch):
    from videoicl_isaaclab import execution_design_e33_grasp
    monkeypatch.setattr(execution_design_e33_grasp,'actual_mesh',lambda a,s,n:np.array([[-.09,0,1.1]]))
    state={'plate':dict(pos=np.array([0,0,.812]),mat=np.eye(3),grasp=[False,True])}
    contacts={frozenset(('plate','table'))};moves=[];tip=np.array([-.09,0,.83])
    spec=dict(id='E31',execution_design=dict(revision=REVISION_V3),semantic=dict(plate='plate',bowl='bowl',plate_face='down'),objects=[dict(id='plate',size=[.094,.094,.012])])
    scene=SimpleNamespace(spec=spec,embodiment=SimpleNamespace(hand='panda_hand',fingers=('finger1','finger2')))
    def move(targets,**kwargs):
        moves.append(np.array(targets['right']));tip[:]=targets['right']
    a=SimpleNamespace(_execution_design_reference_authorized=True,scene=scene,c=SimpleNamespace(steps=10,snapshot=lambda:(state,contacts)),carried_payload=('plate','right'),out=tmp_path,tip=lambda side:tip,move_generated=move)
    with pytest.raises(RuntimeError,match='still contacts'):align_face(a,'plate','right')
    assert len(moves)==1 and moves[0][2]>1.02


def test_private_wrong_face_goal_is_not_overridden_by_native_semantic():
    from videoicl_isaaclab.execution_design_e31_orientation import requested_face
    semantic={'plate_face':'up'}
    assert requested_face(semantic,'plate',{'pitch':0.})=='up'
    assert requested_face(semantic,'plate',{'pitch':np.pi})=='down'
    assert semantic=={'plate_face':'up'}
    with pytest.raises(ValueError):requested_face(semantic,'plate',{'pitch':np.pi/2})
