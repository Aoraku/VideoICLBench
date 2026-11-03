"""CPU measured-state replays for v2 atoms; these do not certify live PhysX."""
from copy import deepcopy
import json
import hashlib
import numpy as np
import pytest
from videoicl_isaaclab.realworld_native_evidence import NativeTaskEvaluator
from videoicl_isaaclab.realworld_tool_evidence import ToolTaskEvaluator
from videoicl_isaaclab.realworld_structural_evidence import StructuralTaskEvaluator
from videoicl_isaaclab.realworld_progress import score_progress
from videoicl_isaaclab.realworld_progress_evidence import seal_initial


def obj(name,size=(.01,.01,.01),**kw):
    return dict(id=name,semantic_identity=name,size=list(size),**kw)

def pose(x=0,y=0,z=.81,held=False):
    return dict(pos=np.array([x,y,z],float),mat=np.eye(3),grasp=[held,False])

def pair(a,b):return frozenset((a,b))

def tick(e,state,contacts=(),dt=.1):
    contacts=set(contacts)
    if hasattr(e,'update_contact_forces'):e.update_contact_forces({p:2. for p in contacts})
    e.update(deepcopy(state),contacts,dt)
    return e.result()

def settle(e,state,contacts=()):
    for _ in range(8):r=tick(e,state,contacts)
    return r

def points(result):
    return score_progress(result['progress_evidence']['task'],result['progress_evidence']['variant'],result['progress_evidence'])


def test_local_release_and_stability_survive_other_object_motion_and_serialize():
    spec=dict(id='E05',variant='A',objects=[obj(n) for n in ('cube','sphere','triangle')],
        zones=[dict(id=n,xy=[i*.2,0],half_size=[.05,.05]) for i,n in enumerate(('square','circle','triangle'))],
        semantic=dict(groups=dict(pieces=['cube','sphere','triangle'])))
    e=NativeTaskEvaluator(spec)
    state=dict(cube=pose(),sphere=pose(.2),triangle=pose(.4,held=True))
    contacts=[pair('cube','table'),pair('sphere','table')]
    for i in range(8):
        state['triangle']['pos'][1]=i*.02
        r=tick(e,state,contacts)
    status=r['progress_evidence']['object_status']
    assert status['cube']['stable'] and status['sphere']['stable']
    assert not status['triangle']['released'] and not r['success']
    scored=points(r)
    assert scored['progress_available'],scored
    assert abs(scored['task_score_100']-200/3)<1e-8
    json.dumps(r,allow_nan=False)
    r['progress_evidence']['object_status']['cube']['stable']=False
    assert e.result()['progress_evidence']['object_status']['cube']['stable']


def tool_scene():
    spec=dict(id='E46',variant='A',objects=[obj('spatula'),obj('yellow_block')],
        zones=[dict(id=n,xy=[.3,i*.12],half_size=[.05,.05],surface_z=.8) for i,n in enumerate(('circle','triangle','square'))],
        semantic=dict(tools=dict(main=dict(actor='spatula',support_bounds=dict(lower=[-.05,-.04,-.005],upper=[.05,.04,0]),support_normal_local=[0,0,1],support_plane_offset=0.,edge_segment=[[0,-.04,0],[0,.04,0]])),groups=dict(cargo=['yellow_block'])))
    return ToolTaskEvaluator(spec),dict(spatula=pose(z=.9,held=True),yellow_block=pose(z=.91))

def transport(e,state,start=0):
    for x in [start,start+.015,start+.03,start+.045]:
        state['spatula']=pose(x,z=.9,held=True);state['yellow_block']=pose(x,z=.91)
        tick(e,state,[pair('yellow_block','spatula')])

def test_old_valid_tool_trace_cannot_be_reused_after_hand_delivery():
    e,state=tool_scene();transport(e,state)
    state['yellow_block']=pose(.2,z=.9,held=True)
    tick(e,state,[pair('yellow_block','left_finger1')])
    state['spatula']=pose(-.2);state['yellow_block']=pose(.3)
    r=settle(e,state,[pair('yellow_block','table'),pair('spatula','table')])
    assert r['history_valid'] and not r['success']
    causal=r['observation']['progress_causal']['yellow_block']
    assert causal['transport_achieved'] and not causal['delivery_chain_valid']
    assert points(r)['task_score_100']==40
    assert 'delivery_has_continuous_tool_cause' in r['failed_checks']
    # A new genuine transport repairs the causal chain; the actor cannot set it.
    transport(e,state,.15)
    state['spatula']=pose(-.2);state['yellow_block']=pose(.3)
    r=settle(e,state,[pair('yellow_block','table'),pair('spatula','table')])
    assert r['success'] and points(r)['task_score_100']==100


def test_legal_tool_delivery_and_then_destroyed_terminal_goal():
    e,state=tool_scene();transport(e,state)
    state['spatula']=pose(-.2);state['yellow_block']=pose(.3)
    r=settle(e,state,[pair('yellow_block','table'),pair('spatula','table')])
    assert r['success'] and points(r)['task_score_100']==100
    state['yellow_block']=pose(-.3,held=True)
    r=tick(e,state,[pair('yellow_block','left_finger1')])
    assert not r['success'] and points(r)['task_score_100']==40


def test_partial_nested_edge_is_exported_before_complete_three_cup_chain():
    names=['red','green','blue']
    geometry=dict(axis_local=[0,0,1],bottom_local=[0,0,-.05],rim_local=[0,0,.05],inner_profile=[[0,.018],[.1,.048]],outer_profile=[[0,.02],[.1,.05]])
    spec=dict(id='E03',variant='A',objects=[obj(n,(.05,.05,.05)) for n in names],zones=[],
        semantic=dict(groups=dict(cups=names),cups={n:deepcopy(geometry) for n in names}))
    e=StructuralTaskEvaluator(spec)
    state=dict(red=pose(z=.85),green=pose(z=.87),blue=pose(.3,z=.85))
    r=settle(e,state,[pair('red','table'),pair('red','green'),pair('blue','table')])
    assert not r['success']
    assert r['observation']['nested_pairs']==[]
    assert r['observation']['progress_nested_pairs']==['red>green']
    scored=points(r)
    assert scored['progress_available'],scored
    assert scored['task_score_100']==50


def test_partial_same_car_side_map_does_not_overwrite_other_blocks():
    spec=dict(id='E22',variant='A',objects=[obj(n) for n in ('car','red','green','blue')],zones=[],
        semantic=dict(car='car',car_frame=np.eye(3).tolist(),groups=dict(blocks=['red','green','blue'])))
    e=NativeTaskEvaluator(spec)
    state=dict(car=pose(),red=pose(.2),green=pose(.3),blue=pose(y=-.2))
    r=settle(e,state,[pair(n,'table') for n in state])
    assert r['observation']['object_sides']=={'red':'front','green':'front','blue':'right'}
    # The legacy inverse map remains unchanged for binary-checker compatibility.
    assert r['observation']['car_sides']['front']=='green'


def test_missing_native_tick_remains_unscored_not_synthetic_progress():
    e,state=tool_scene()
    e.update(state,{pair('yellow_block','spatula')},.1) # required force snapshot absent
    r=e.result();scored=points(r)
    assert not r['history_valid'] and not scored['progress_available']
    assert scored['task_score_100'] is None


def test_initial_seal_freezes_real_snapshot_then_never_tracks_actor_changes():
    e,state=tool_scene()
    with pytest.raises(ValueError,match='invalid or missing'):seal_initial(e)
    state['spatula']=pose(-.2);state['yellow_block']=pose(-.4)
    contacts=[pair('spatula','table'),pair('yellow_block','table')]
    tick(e,state,contacts)
    # Non-dynamic tasks preserve measured unstable flags rather than gaining a new admission gate.
    r=settle(e,state,contacts);seal_initial(e)
    before=e.result()['progress_evidence']['initial']
    assert before['sealed'] and before['physics_step']>1
    transport(e,state)
    state['spatula']=pose(-.2);state['yellow_block']=pose(.3)
    r=settle(e,state,contacts)
    assert r['progress_evidence']['initial']==before
    with pytest.raises(ValueError,match='already sealed'):seal_initial(e)
    evidence=r['progress_evidence']
    expected=hashlib.sha256(json.dumps(evidence,sort_keys=True,separators=(',',':'),ensure_ascii=False,allow_nan=False).encode()).hexdigest()
    assert r['progress_result']['evidence_sha256']==expected
    assert r['progress_result']['task_score_100']==100
