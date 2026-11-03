"""Support regions must be invariant under a shared yaw rotation."""
import numpy as np
import pytest
from videoicl_isaaclab.realworld_tool_evidence import ToolTaskEvaluator


def scene(yaw,kind='box',offset=(0.,0.),held=False,contact=True):
    c,s=np.cos(yaw),np.sin(yaw);r=np.array([[c,-s,0],[s,c,0],[0,0,1.]])
    e=ToolTaskEvaluator.__new__(ToolTaskEvaluator)
    e.e28_scoop=None  # Non-E28 region fixture, matching evaluator initialization.
    size=[.04,.015,.01] if kind=='box' else [.015]*3
    local_center=np.array([.007,0,0])
    anchor=np.array([.2,.1,.8]);center=anchor+r@np.array([*offset,size[2]])
    e.objects={'cargo':dict(kind=kind,size=size,local_bounds_center=local_center)}
    e.state={'tray':dict(pos=anchor,mat=r),'cargo':dict(pos=center-r@local_center,mat=r,grasp=[held,False])}
    e.initial={'tray':dict(pos=anchor.copy())}
    e.zones={'target':dict(anchor_object='tray',anchor_local_center=[0,0,0],half_size=[size[0]+.001,size[1]+.001],surface_z=.8,support='tray')}
    e.force=lambda a,b:1. if contact else 0.;e.source_tray_walls=None
    return e


@pytest.mark.parametrize('kind',['box','sphere'])
@pytest.mark.parametrize('yaw',[0.,.3,np.pi/4,1.2])
def test_common_rotation_preserves_containment_and_local_bounds_center(kind,yaw):
    assert scene(yaw,kind)._region('cargo')=='target'


@pytest.mark.parametrize('kind',['box','sphere'])
def test_genuine_overhang_is_rejected(kind):
    assert scene(np.pi/4,kind,offset=(.008,0))._region('cargo') is None


def test_held_or_unsupported_object_never_earns_region():
    assert scene(.5,held=True)._region('cargo') is None
    assert scene(.5,contact=False)._region('cargo') is None


def spatula(yaw,offset,kind='box',contact=True,hand_force=0.,tilt=0.):
    e=scene(yaw,kind);r=e.state['tray']['mat']
    ct,st=np.cos(tilt),np.sin(tilt);r=r@np.array([[1,0,0],[0,ct,-st],[0,st,ct]])
    e.tool=dict(actor='spatula',support_bounds=dict(lower=[-.02,-.02,-.003],upper=[.02,.02,0]),support_normal_local=[0,0,1],support_plane_offset=0.)
    e.state['spatula']=dict(pos=np.array([.2,.1,.9]),mat=r,grasp=[True,False])
    size=e.objects['cargo']['size'];e.state['cargo']['mat']=r
    e.state['cargo']['pos']=e.state['spatula']['pos']+r@np.array([offset,0,size[2]])-r@e.objects['cargo']['local_bounds_center']
    e.steps=1;e.active_transports={};e.transports={};e.force=lambda a,b:1. if contact else 0.
    e.hand_force=lambda name:hand_force;e._trace=lambda active,hist,name,sample:hist.update({name:sample});e._delivery_chain=lambda *args:None
    e._spatula_history(['cargo']);return e.transports['cargo']


@pytest.mark.parametrize('kind',['box','sphere'])
@pytest.mark.parametrize('yaw',[0.,.3,np.pi/4,1.2])
def test_spatula_direct_bounds_remove_rotated_world_aabb_false_support(kind,yaw):
    assert spatula(yaw,0.,kind) is not None
    # With real contact but outside the allowed blade footprint, geometry must
    # still reject. The old double-AABB admitted this at 45 degrees.
    assert spatula(yaw,.075,kind) is None


def test_spatula_tool_causal_constraints_unchanged():
    assert spatula(.5,0.,contact=False) is None
    assert spatula(.5,0.,hand_force=1.) is None
    assert spatula(.5,0.,tilt=1.) is None


@pytest.mark.parametrize('degrees',[0.,15.,-15.,30.])
@pytest.mark.parametrize('kind',['sphere','box'])
def test_anchor_support_plane_rotates_with_tray_and_body(degrees,kind):
    e=scene(0.,kind);theta=np.radians(degrees);c,s=np.cos(theta),np.sin(theta)
    r=np.array([[c,0,s],[0,1,0],[-s,0,c]])
    e.state['tray']['mat']=r;e.state['cargo']['mat']=r
    offset=np.array([0.,0.,e.objects['cargo']['size'][2]])
    e.state['cargo']['pos']=e.state['tray']['pos']+r@(offset-e.objects['cargo']['local_bounds_center'])
    assert e._region('cargo')=='target'
    # Positive synthetic contact cannot bypass a real 20mm plane gap.
    e.state['cargo']['pos']+=r@np.array([0,0,.020])
    assert e._region('cargo') is None


def test_actual_e45_reviewed_floor_tangency_survives_pitch():
    # Numbers from actual E45 circle zone, initial tray origin, and sphere.
    e=scene(0.,'sphere');r0=.014;e.objects['cargo']['size']=[r0]*3
    e.objects['cargo']['local_bounds_center']=[0,0,0]
    theta=np.radians(15);c,s=np.cos(theta),np.sin(theta);rot=np.array([[c,0,s],[0,1,0],[-s,0,c]])
    e.state['tray'].update(pos=np.array([0,-.09,.88]),mat=rot)
    e.initial['tray']['pos']=np.array([0,-.09,.822])
    e.zones={'circle':dict(anchor_object='tray',anchor_local_center=[-.0515,-.0405,0],half_size=[.0445,.0335],surface_z=.8086277848,support='tray')}
    local=np.array([-.07,-.0405,-.0133722152+r0])
    e.state['cargo']['pos']=e.state['tray']['pos']+rot@local
    assert e._region('cargo')=='circle'
    # True footprint excess is still rejected at the same tilted pose.
    e.state['cargo']['pos']=e.state['tray']['pos']+rot@(local+np.array([-.04,0,0]))
    assert e._region('cargo') is None
