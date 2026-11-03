"""The B/C candidate must fail on measured physical guard violations."""
from types import SimpleNamespace
import numpy as np
import pytest
from scipy.spatial.transform import Rotation
from videoicl_isaaclab.execution_design_e20_far_blue import applies,place,_lowest,_q4
from videoicl_isaaclab.realworld_tool_expert import ToolExecutionError


def sample(mode='good'):
    state={'blue_supply_2':dict(pos=np.array([-.29,-.12,.93]),mat=np.eye(3),grasp=[True,False]),
           'compartment_tray':dict(pos=np.array([0.,.1,.826]),mat=np.eye(3),grasp=[False,False])}
    objects={'blue_supply_2':dict(size=[.016,.016,.001]),'compartment_tray':dict(size=[.195,.065,.018])}
    tips={'left':np.array([-.29,-.12,.931]),'right':np.array([-.192,-.3,.902])}
    events=[];contacts=set()
    a=SimpleNamespace(task='E20',variant='B',d={'revision':'embodied50-execution-v3-20261102','condition':'I'},
        spec={'fixtures':[]},objects=objects)
    robot=SimpleNamespace(find_joints=lambda name:([0],['panda_joint4']),data=SimpleNamespace(joint_pos=np.array([[-1.1]])))
    a.a=SimpleNamespace(control_report={'engineering_reference_only':True},scene=SimpleNamespace(robots={'left':robot}))
    a.snapshot=lambda:(state,contacts)
    a.frame=lambda ref:(state[ref['actor']]['pos'].copy(),state[ref['actor']]['mat'].copy())
    a.tip=lambda side:tips[side].copy()
    a.bottom_local=lambda name:np.array([0.,0.,-.001])
    a.point=lambda ref:state[ref['actor']]['pos']+state[ref['actor']]['mat']@np.asarray(ref['local'])
    a.measured_lowest_z=lambda name:float(state[name]['pos'][2]-np.abs(state[name]['mat'][2])@objects[name]['size'])
    def fingers(side):
        toe=float(tips[side][2]-.010)
        return {'fingers':[{'aabb_min_task_m':[0,0,toe]},{'aabb_min_task_m':[0,0,toe]}]}
    a.a.finger_geometry=fingers
    def require(ref,side):
        if not state[ref['actor']]['grasp'][0]:raise ToolExecutionError('actual grip lost')
    a.require_held=require;a.stage=lambda name:events.append(('stage',name))
    def move(side,target,guard=None):
        if guard:guard()
        delta=np.asarray(target)-tips[side];tips[side]+=delta
        if side=='left'and state['blue_supply_2']['grasp'][0]:state['blue_supply_2']['pos']+=delta
        events.append(('move',side))
        if mode=='lost':state['blue_supply_2']['grasp'][0]=False
        if mode=='tray_moves':state['compartment_tray']['pos'][0]+=.003
    a.move=move
    def move_point(side,ref,target,guard,tolerance):
        guard();delta=np.asarray(target)-a.point(ref);tips[side]+=delta;state[ref['actor']]['pos']+=delta
        events.append(('point',np.asarray(target).copy()))
    a.move_point=move_point
    def act(side,token,degrees):
        i,sign={'ROLL_LEFT':(0,1),'ROLL_RIGHT':(0,-1),'PITCH_UP':(1,1),'PITCH_DOWN':(1,-1),
                'ROTATE_CCW':(2,1),'ROTATE_CW':(2,-1)}[token]
        delta=np.zeros(3);delta[i]=sign*np.deg2rad(max(.5,degrees))
        if mode!='rotation_stuck':state['blue_supply_2']['mat']=Rotation.from_rotvec(delta).as_matrix()@state['blue_supply_2']['mat']
        events.append(('rotate',token))
    a.act=act
    def release(ref,side):
        state[ref['actor']]['grasp'][0]=False;events.append(('release',))
        if mode!='no_support':contacts.add(frozenset((ref['actor'],'compartment_tray')))
    a.release=release;a.wait=lambda n:None
    if mode=='right_loaded':state['compartment_tray']['grasp'][1]=True
    if mode=='right_contact':contacts.add(frozenset(('blue_supply_2','right_finger1')))
    if mode=='q4':robot.data.joint_pos[0,0]=-.54
    return a,state,events


@pytest.mark.parametrize('variant,condition,x,color,expected',[
    ('A','I',.149,'blue',False),('B','I',.149,'blue',True),('C','I',.149,'blue',True),
    ('B','E',.149,'blue',False),('B','I',.111,'blue',False),('B','I',.149,'red',False)])
def test_exact_scope_keeps_A_and_near_cells_on_existing_route(variant,condition,x,color,expected):
    a,_,_=sample();a.variant=variant;a.d['condition']=condition
    assert applies(a,color+'_supply_2','compartment_tray',[x,.019,-.012])is expected


def test_candidate_requires_public_empty_retreat_and_real_supported_release():
    a,state,events=sample();place(a,'blue_supply_2',{'actor':'blue_supply_2'},'left','compartment_tray',[.149,.019,-.012])
    assert next(e for e in events if e[0]=='move')==('move','right')
    assert any(e[0]=='rotate'for e in events)
    report=a.a.control_report['e20_far_blue_candidate'][0]
    assert report['real_support_verified'] and report['minimum_transit_clearance_m']==.050
    assert report['minimum_opening_clearance_m']==.010 and not report['native_task_acceptance']
    assert not any(state['blue_supply_2']['grasp'])


@pytest.mark.parametrize('mode,reason',[('lost','grip lost'),('tray_moves','tray moved'),
    ('right_loaded','actually empty'),('right_contact','actually empty'),('q4','stall warning'),
    ('rotation_stuck','pitch stopped progressing'),('no_support','real tray support')])
def test_measured_failures_propagate_and_never_add_success_report(mode,reason):
    a,_,events=sample(mode)
    with pytest.raises(ToolExecutionError,match=reason):
        place(a,'blue_supply_2',{'actor':'blue_supply_2'},'left','compartment_tray',[.149,.019,-.012])
    assert 'e20_far_blue_candidate'not in a.a.control_report
    if mode!='no_support':assert ('release',)not in events
    if mode=='rotation_stuck':assert sum(e[0]=='rotate'for e in events)==3


@pytest.mark.parametrize('value',[-.55,-.54,np.nan])
def test_conservative_native_q4_warning_never_relaxed(value):
    a,_,_=sample();a.a.scene.robots['left'].data.joint_pos[0,0]=value
    with pytest.raises(ToolExecutionError,match='stall warning'):_q4(a)


def test_both_actual_fingers_and_finite_payload_geometry_required():
    a,_,_=sample();a.a.finger_geometry=lambda side:{'fingers':[]}
    with pytest.raises(ToolExecutionError,match='both actual'):_lowest(a,'blue_supply_2')
    a,_,_=sample();a.measured_lowest_z=lambda name:np.nan
    with pytest.raises(ToolExecutionError,match='nonfinite'):_lowest(a,'blue_supply_2')


def test_actual_payload_clearance_is_checked_before_horizontal_transit():
    a,_,events=sample();original=a.measured_lowest_z
    a.measured_lowest_z=lambda name:(.88 if any(e[0]=='point'for e in events)else original(name))
    with pytest.raises(ToolExecutionError,match='50mm body clearance'):
        place(a,'blue_supply_2',{'actor':'blue_supply_2'},'left','compartment_tray',[.149,.019,-.012])
    assert ('release',)not in events


def test_actual_opening_clearance_is_required_after_final_approach():
    a,_,events=sample();original=a.a.finger_geometry
    def measured_fingers(side):
        if sum(e[0]=='point'for e in events)>=3:
            return {'fingers':[{'aabb_min_task_m':[0,0,.85]},{'aabb_min_task_m':[0,0,.85]}]}
        return original(side)
    a.a.finger_geometry=measured_fingers
    with pytest.raises(ToolExecutionError,match='10mm opening clearance'):
        place(a,'blue_supply_2',{'actor':'blue_supply_2'},'left','compartment_tray',[.149,.019,-.012])
    assert ('release',)not in events


def test_wrong_side_rejected_before_any_action():
    a,_,events=sample()
    with pytest.raises(ToolExecutionError,match='left-hand'):
        place(a,'blue_supply_2',{'actor':'blue_supply_2'},'right','compartment_tray',[.149,.019,-.012])
    assert not events
