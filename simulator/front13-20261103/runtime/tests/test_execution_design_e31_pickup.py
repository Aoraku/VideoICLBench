from types import SimpleNamespace
import copy
import numpy as np
import pytest
from videoicl_isaaclab.execution_design import REVISION_V3
from videoicl_isaaclab import execution_design_e31_pickup as m


def ry(deg):
 a=np.deg2rad(deg);return np.array([[np.cos(a),0,np.sin(a)],[0,1,0],[-np.sin(a),0,np.cos(a)]])


def test_relative_delta_tracks_physical_slip_and_is_frame_equivariant():
 # A rim rotated10deg against an unmoved hand calls for10deg follow.
 assert np.allclose(m.relative_grasp_delta(np.eye(3),ry(20),ry(10),ry(20)),ry(10))
 # Matching real hand motion removes the error; this never changes object pose.
 assert np.allclose(m.relative_grasp_delta(np.eye(3),ry(20),ry(10),ry(30)),np.eye(3))
 q=ry(35);assert np.allclose(m.relative_grasp_delta(q,q@ry(20),q@ry(10),q@ry(20)),q@ry(10)@q.T)
 with pytest.raises(ValueError):m.relative_grasp_delta(np.eye(3),np.eye(3),np.zeros((3,3)),np.eye(3))


def make_author(tmp_path,monkeypatch,*,lost=False,onefinger=False,collision=False,slip=0):
 spec=dict(id='E31',execution_design=dict(revision=REVISION_V3),semantic=dict(plate='plate'),objects=[dict(id='plate',size=[.094,.094,.012]),dict(id='bowl')])
 tcp=np.array([-.09,-.12,.824]);hand=[0.];angle=[0.];moves=[];acts=[]
 def snapshot():
  contacts={frozenset(('plate','right_finger1'))}
  if not onefinger:contacts.add(frozenset(('plate','right_finger2')))
  if tcp[2]<.86:contacts.add(frozenset(('plate','table')))
  if collision:contacts.add(frozenset(('plate','bowl')))
  return {'plate':dict(grasp=[False,not lost],pos=tcp-ry(angle[0])@np.array([-.09,0,.01]),mat=ry(angle[0]))},contacts
 c=SimpleNamespace(steps=0,snapshot=snapshot)
 def move(goals,**kwargs):
  dest=np.asarray(goals['right']);assert dest[2]-tcp[2]<=.004001
  rising=dest[2]>tcp[2]+.0001
  tcp[:]=dest
  if tcp[2]<.86 and rising:angle[0]+=slip
  c.steps+=1;moves.append(dest.copy())
 def act(left,right,**kwargs):
  assert left=='STILL' and right in ('PITCH_UP','PITCH_DOWN')
  hand[0]+=kwargs['rotation_deg']*(1 if right=='PITCH_UP' else -1);acts.append((left,right,kwargs));c.steps+=1
 a=SimpleNamespace(scene=SimpleNamespace(spec=spec),_execution_design_reference_authorized=True,smooth=False,c=c,out=tmp_path,carried_payload=('plate','right'),tip=lambda s:tcp.copy(),move_generated=move,act=act)
 monkeypatch.setattr(m,'hand_rotation',lambda a,s:ry(hand[0]));return a,moves,acts


def test_public_lift_follows_small_actual_rim_pivots_without_editing_spec(tmp_path,monkeypatch):
 a,moves,acts=make_author(tmp_path,monkeypatch,slip=.8);before=copy.deepcopy(a.scene.spec)
 m.lift_plate(a,'plate','right',.90)
 assert moves and acts and a.scene.spec==before
 assert max(cmd[2]['rotation_deg'] for cmd in acts)<=3
 assert a.tip('right')[2]>=.897
 assert 'two_finger_contact' in (tmp_path/'e31-plate-pivot-pickup.private.jsonl').read_text()


@pytest.mark.parametrize('options,message',[(dict(lost=True),'actual plate grasp'),(dict(onefinger=True),'both actual finger'),(dict(collision=True),'another task object')])
def test_real_grip_contact_and_collision_guards_prevent_commands(tmp_path,monkeypatch,options,message):
 a,moves,acts=make_author(tmp_path,monkeypatch,**options)
 with pytest.raises(RuntimeError,match=message):m.lift_plate(a,'plate','right',.90)
 assert not moves and not acts


def test_excessive_slip_aborts_instead_of_forcing_completion(tmp_path,monkeypatch):
 a,moves,acts=make_author(tmp_path,monkeypatch,slip=25)
 with pytest.raises(RuntimeError,match='slip exceeded'):m.lift_plate(a,'plate','right',.90)
 assert len(moves)==1 and not acts


def test_scope_guard_never_changes_formal_or_other_task(tmp_path,monkeypatch):
 a,moves,acts=make_author(tmp_path,monkeypatch);a._execution_design_reference_authorized=False
 with pytest.raises(ValueError,match='Explicit E31'):m.lift_plate(a,'plate','right',.9)
 assert not moves


def test_airborne_fixed_contact_offset_does_not_cause_repeated_spinning(tmp_path,monkeypatch):
 a,moves,acts=make_author(tmp_path,monkeypatch)
 snapshot=a.c.snapshot
 def airborne():
  state,contacts=snapshot();contacts.discard(frozenset(('plate','table')));return state,contacts
 a.c.snapshot=airborne
 monkeypatch.setattr(m,'relative_grasp_delta',lambda *args:ry(4))
 m.lift_plate(a,'plate','right',.9)
 assert len(moves)>10 and acts==[]


def test_native235_failure_translation_requires_z_before_xy_correction():
 # Actual last held pose from E31B v3:8.55mm normal pullout despite1deg angle.
 R=np.array([[.5440869927,-.0018768311,.8390268683],[-.0859247446,.9946152568,.0579448193],[-.8346175551,-.1036202386,.5409958363]])
 body=np.array([-.0579203144,-.1309958845,.8776435232])
 tcp=np.array([-.0909806937,-.1207646653,.9649797058])
 original=np.array([-.088780720261,-.000694301524,.011556345745])
 desired=m.contact_point(body,R,original)
 assert desired==pytest.approx([-.0965273618,-.1233883563,.9580653495],abs=1e-9)
 drift=R.T@(tcp-body)-original
 assert drift[2]==pytest.approx(.008546465,abs=1e-9)
 target=m.reseat_waypoint(tcp,desired)
 assert target[:2]==pytest.approx(tcp[:2]) and target[2]==pytest.approx(tcp[2]-.002)
 # A lateral-only correction pushes the already near-edge radial grip outward.
 lateral=tcp.copy();lateral[:2]=desired[:2]
 assert (R.T@(lateral-body))[0]<(R.T@(tcp-body))[0]
 with pytest.raises(ValueError):m.contact_point(body,np.eye(3),[0,0,float('nan')])


def test_reseat_waypoint_moves_one_axis_at_most_two_millimeters():
 current=np.array([.1,.2,1.])
 target=m.reseat_waypoint(current,[.108,.195,1.0004])
 assert target==pytest.approx([.102,.2,1.])
 with pytest.raises(ValueError):m.reseat_waypoint(current,[0,float('inf'),0])
