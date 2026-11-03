"""Engineering ingress must preserve live grip, stand pose and real support."""
from types import SimpleNamespace
import numpy as np
import pytest
from scipy.spatial.transform import Rotation
from videoicl_isaaclab.execution_design_e17_insertion import front_lower_slot,place_lower
from videoicl_isaaclab.execution_design_e17_stand import descriptor
from videoicl_isaaclab.realworld_tool_expert import ToolExecutionError


def sample(mode='good'):
    a=SimpleNamespace(task='E17',spec={'execution_design':{'condition':'I'}},
        objects={'stand':{'e17_stand_geometry':descriptor()},'piece':{'size':[.02,.02,.003]}},
        a=SimpleNamespace(control_report={'engineering_reference_only':True}))
    state={'stand':{'pos':np.array([.04,.05,.8]),'mat':np.eye(3)},
           'piece':{'pos':np.array([-.17,-.08,.9]),'mat':np.eye(3),'grasp':[False,True]}}
    tip=np.array([-.17,-.08,.91]);events=[];released=False
    a.frame=lambda ref:(state[ref['actor']]['pos'].copy(),state[ref['actor']]['mat'].copy())
    a.tip=lambda side:tip.copy();a.point=lambda ref:state[ref['actor']]['pos'].copy()
    a.snapshot=lambda:(state,set())
    a.stage=lambda s:events.append(('stage',s))
    a.pickup=lambda name,side_override:({'actor':name},side_override)
    def held(ref,side):
        if not state[ref['actor']]['grasp'][1]:raise ToolExecutionError('actual grip lost')
    a.require_held=held
    def move_point(side,ref,target,guard,tolerance=.002):
        if mode=='stand_moves':state['stand']['pos'][0]+=.0011
        if mode=='grip_lost':state['piece']['grasp'][1]=False
        guard();delta=np.asarray(target)-state['piece']['pos'];state['piece']['pos']+=delta;tip[:]+=delta
        events.append(('point',np.asarray(target).copy(),tolerance))
    a.move_point=move_point
    def act(side,token,degrees):
        index,sign={'ROLL_LEFT':(0,1),'ROLL_RIGHT':(0,-1),'PITCH_UP':(1,1),
                    'PITCH_DOWN':(1,-1),'ROTATE_CCW':(2,1),'ROTATE_CW':(2,-1)}[token]
        delta=np.zeros(3);delta[index]=np.deg2rad(max(.5,degrees))*sign
        state['piece']['mat']=Rotation.from_rotvec(delta).as_matrix()@state['piece']['mat']
        events.append(('rotate',token))
    a.act=act
    def release(ref,side):
        nonlocal released
        released=True;state['piece']['grasp'][1]=False;events.append(('release',))
    a.release=release
    a.wait=lambda n:None
    a.contact=lambda name,actor:released and mode!='no_support' and not(mode=='retreat_support_lost' and any(e[0]=='empty'for e in events))
    def empty(side,target):tip[:]=target;events.append(('empty',np.asarray(target).copy()))
    a.move=empty
    return a,events,state


def test_two_lower_slots_are_separated_and_capacity_rejected():
    p=[front_lower_slot(None,i,2)for i in range(2)]
    assert np.linalg.norm(np.array(p[0])-p[1])>.08
    with pytest.raises(ToolExecutionError):front_lower_slot(None,0,3)


def test_supported_release_and_full_empty_retreat_use_south_corridor():
    a,events,state=sample();place_lower(a,'piece','stand',front_lower_slot(a,0,2))
    points=[e for e in events if e[0]=='point']
    assert points[-2][1][1]<-.17
    assert points[-2][2]==points[-1][2]==.006
    assert events.index(next(e for e in events if e[0]=='release'))<next(i for i,e in enumerate(events)if e[0]=='empty')
    assert not any(state['piece']['grasp'])
    assert np.linalg.norm(state['stand']['pos']-[.04,.05,.8])==0


@pytest.mark.parametrize('mode,reason',[('stand_moves','stand moved'),('grip_lost','grip lost'),
    ('no_support','real stand support'),('retreat_support_lost','survive empty-hand retreat')])
def test_actual_failure_is_not_filled_as_a_success(mode,reason):
    a,events,_=sample(mode)
    with pytest.raises(ToolExecutionError,match=reason):place_lower(a,'piece','stand',[-.044,-.044,.016795216])
    if mode in ('stand_moves','grip_lost'):assert not any(e[0]=='release'for e in events)


@pytest.mark.parametrize('change',['condition','geometry','nonengineering','slot'])
def test_unreviewed_world_rejected_before_pickup(change):
    a,events,_=sample();target=[-.044,-.044,.016795216]
    if change=='condition':a.spec['execution_design']['condition']='E'
    elif change=='geometry':a.objects['stand']['e17_stand_geometry']['derived_geometry_sha256']='bad'
    elif change=='nonengineering':a.a.control_report.clear()
    else:target[0]=0
    a.pickup=lambda *args,**kwargs:pytest.fail('must reject before pickup')
    with pytest.raises(ToolExecutionError):place_lower(a,'piece','stand',target)
