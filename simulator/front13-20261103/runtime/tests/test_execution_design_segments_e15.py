"""E15C local-tail scope, completed-blue protection and original method order."""
from copy import deepcopy
from types import SimpleNamespace
import math
import numpy as np
import pytest
from videoicl_isaaclab.execution_design import REVISION_V3,source_sha256
from videoicl_isaaclab import execution_design_e15_wrist as wrist
from videoicl_isaaclab.execution_design_segments_e15 import run_segment


def rotation(yaw):
    c,s=math.cos(yaw),math.sin(yaw);return np.array([[c,-s,0.],[s,c,0.],[0.,0.,1.]])


class Author:
    def __init__(self,mode='good'):
        self.mode=mode;self.events=[];self.actions=[];self.carried_payload=None;self.smooth=False
        self._execution_design_reference_authorized=True;self.control_report={'engineering_reference_only':True}
        self._engineering_resume_checkpoint={'diagnostic_only':True,'source':{'steps':716,'physics_ticks':72440}}
        red=dict(id='red_t',size=[.026,.0195,.004875],grasp_point_local=[0,0,0],
                 source_asset={'sha256':'98bae9ae3dddf67e58004695930c09f3d36f715dfa2bf5d65d1ed2b7179fa493'})
        blue=dict(id='blue_t',size=[.026,.0195,.004875])
        spec=dict(id='E15',variant='C',seed=4201,task_adapter='full50-source-v1',objects=[red,blue],
            execution_design={'revision':REVISION_V3,'condition':'I','source_sha256':source_sha256(REVISION_V3)},
            zones=[dict(id='temporary',xy=[-.19,-.15],surface_z=.8),dict(id='red_t_target',xy=[-.06,.06],surface_z=.8),dict(id='blue_t_target',xy=[.065,-.04],surface_z=.8)],
            goals=[dict(type='place',object='red_t',target='temporary',yaw=math.pi/2),dict(type='place',object='blue_t',target='blue_t_target',yaw=math.pi/2),dict(type='place',object='red_t',target='red_t_target',yaw=3*math.pi/2)])
        self.scene=SimpleNamespace(spec=spec,embodiment=SimpleNamespace(name='franka',config={}))
        self.state={'red_t':dict(pos=np.array([-.19,-.15,.804875]),mat=rotation(math.pi/2),grasp=[False,False]),
                    'blue_t':dict(pos=np.array([.065,-.04,.804875]),mat=rotation(math.pi/2),grasp=[False,False])}
        self.contacts={frozenset((name,'table'))for name in self.state}
        self.c=SimpleNamespace(steps=0,snapshot=lambda:(self.state,self.contacts))
        self.tips={'right':np.array([.0663,-.0303,1.10]),'left':np.array([-.49,.52,1.24])};self.stage='restored'
    def tip(self,side):return self.tips[side].copy()
    def floor_clear_tcp(self,side):return .81
    def prepare_generated_gripper(self,side):self.events.append(('prepare_gripper',side))
    def act(self,left='STILL',right='STILL',mm=20.,**kwargs):
        self.actions.append((left,right));self.c.steps+=1
        if self.mode=='move_blue'and self.c.steps==1:self.state['blue_t']['pos'][0]+=.003
        if right=='GRASP'and self.mode!='grasp_fail':
            self.state['red_t']['grasp'][1]=True;self.contacts.discard(frozenset(('red_t','table')))
            self.contacts.update(frozenset(('red_t','right_finger'+str(i)))for i in (1,2))
        if right=='RELEASE':
            self.state['red_t']['grasp'][1]=False
            for i in (1,2):self.contacts.discard(frozenset(('red_t','right_finger'+str(i))))
            if self.mode!='no_support':self.contacts.add(frozenset(('red_t','table')))
    def move_generated(self,targets,tolerance=.004):
        self.events.append(('move',deepcopy(targets),tolerance))
        for side,target in targets.items():
            delta=np.asarray(target)-self.tips[side];self.tips[side]+=delta
            if self.carried_payload is not None:self.state['red_t']['pos']+=delta
        self.act()
    def rotate_held(self,name,side,goal):
        assert name=='red_t'and side=='right';self.events.append(('rotate_held',name,deepcopy(goal)))
        self.act('STILL','ROTATE_CW');self.state[name]['mat']=rotation(goal['yaw'])
        if self.mode=='lost_grip':self.state[name]['grasp'][1]=False
    def release_generated(self,side):
        self.events.append(('release',side));self.act('STILL','RELEASE')


def prepare(monkeypatch,fail=False):
    def original(a,side,name,goal,clearance):
        a.events.append(('original_prepare_empty',side,name,deepcopy(goal),clearance))
        if fail:raise RuntimeError('original measured IK rejected')
    monkeypatch.setattr(wrist,'prepare_empty',original)


def test_resume_calls_original_prepare_and_only_the_red_transfer_tail(monkeypatch):
    prepare(monkeypatch);a=Author();spec=deepcopy(a.scene.spec);blue=deepcopy(a.state['blue_t'])
    result=run_segment(a,'e15_resume_empty_wrist_then_place',{'object':'red_t','side':'right','clearance':1.10})
    assert set(result)=={'local_completed','operations','active_actions'}and result['local_completed']
    assert a.events[0][0]=='original_prepare_empty'and a.events[0][2]=='red_t'
    assert [x for x in a.actions if x[1]=='GRASP']==[('STILL','GRASP')]*3
    assert [x for x in a.events if x[0]=='rotate_held'][0][2]==spec['goals'][-1]
    assert a.scene.spec==spec and np.array_equal(a.state['blue_t']['pos'],blue['pos'])
    assert np.array_equal(a.state['blue_t']['mat'],blue['mat'])and not any(a.state['blue_t']['grasp'])
    assert not any(a.state['red_t']['grasp'])and a.carried_payload is None
    assert not hasattr(a,'generated_axis_signs')and 'act'not in a.__dict__
    assert all(row.get('actor')=='red_t'for row in result['operations'])


def test_B118_preserves_unfinished_source_blue_without_claiming_goal_completion(monkeypatch):
    prepare(monkeypatch);a=Author();a.scene.spec['variant']='B'
    a._engineering_resume_checkpoint['source']={'steps':118,'physics_ticks':12640}
    a.scene.spec['zones'][1]['xy']=[.065,-.04];a.scene.spec['zones'][2]['xy']=[-.06,.06]
    a.state['red_t']['pos']=np.array([.065,-.04,.804875])
    a.state['blue_t']['pos']=np.array([-.06,.06,.804875]);a.state['blue_t']['mat']=rotation(3*math.pi/2)
    original=deepcopy(a.state['blue_t'])
    result=run_segment(a,'e15_b_resume_red_from_empty_boundary',{})
    assert result['local_completed']
    assert np.array_equal(a.state['blue_t']['pos'],original['pos'])
    assert np.array_equal(a.state['blue_t']['mat'],original['mat'])
    assert not any(a.state['blue_t']['grasp'])
    assert all(row['actor']=='red_t'for row in result['operations'])


def test_B_entry_cannot_accept_the_C_boundary(monkeypatch):
    prepare(monkeypatch);a=Author();a.scene.spec['variant']='B'
    with pytest.raises(ValueError,match='boundary'):run_segment(a,'e15_b_resume_red_from_empty_boundary',{})
    assert not a.actions


@pytest.mark.parametrize('fault',['task','variant','seed','revision','source','condition','permission','nonengineering','smooth','steps','tick','carried','branch','red_support','blue_not_done','source_mesh'])
def test_incompatible_or_incomplete_prefix_is_rejected_before_new_actions(monkeypatch,fault):
    prepare(monkeypatch);a=Author();s=a.scene.spec
    if fault=='task':s['id']='E16'
    elif fault=='variant':s['variant']='B'
    elif fault=='seed':s['seed']=4202
    elif fault=='revision':s['execution_design']['revision']='old'
    elif fault=='source':s['execution_design']['source_sha256']='bad'
    elif fault=='condition':s['execution_design']['condition']='E'
    elif fault=='permission':a._execution_design_reference_authorized=False
    elif fault=='nonengineering':a.control_report.clear()
    elif fault=='smooth':a.smooth=True
    elif fault=='steps':a._engineering_resume_checkpoint['source']['steps']=715
    elif fault=='tick':a._engineering_resume_checkpoint['source']['physics_ticks']=72439
    elif fault=='carried':a.carried_payload=('blue_t','right')
    elif fault=='branch':a._e15_wrist_branch={'object':'red_t'}
    elif fault=='red_support':a.contacts.discard(frozenset(('red_t','table')))
    elif fault=='blue_not_done':a.state['blue_t']['pos'][0]+=.03
    else:s['objects'][0]['source_asset']['sha256']='bad'
    with pytest.raises((ValueError,RuntimeError)):run_segment(a,'e15_resume_empty_wrist_then_place',{})
    assert not a.actions and not a.events and 'act'not in a.__dict__


@pytest.mark.parametrize('parameters',[{'object':'blue_t'},{'side':'left'},{'clearance':.90},{'goal':{}},{'yaw':0}])
def test_original_actor_hand_goal_and_clearance_cannot_be_overridden(monkeypatch,parameters):
    prepare(monkeypatch);a=Author()
    with pytest.raises(ValueError):run_segment(a,'e15_resume_empty_wrist_then_place',parameters)
    assert not a.actions


def test_original_prepare_rejection_stops_without_regrasp_or_blue_replay(monkeypatch):
    prepare(monkeypatch,True);a=Author()
    with pytest.raises(RuntimeError,match='original measured IK'):run_segment(a,'e15_resume_empty_wrist_then_place',{})
    assert len(a.events)==1 and not a.actions and 'act'not in a.__dict__


@pytest.mark.parametrize('mode,reason',[('move_blue','blue T moved'),('grasp_fail','physically bilaterally'),('lost_grip','lost actual grip'),('no_support','real table support')])
def test_first_measured_failure_ends_the_suffix_and_restores_the_action_method(monkeypatch,mode,reason):
    prepare(monkeypatch);a=Author(mode)
    with pytest.raises(RuntimeError,match=reason):run_segment(a,'e15_resume_empty_wrist_then_place',{})
    assert 'act'not in a.__dict__
    if mode in ('move_blue','grasp_fail'):assert not any(e[0]=='release'for e in a.events)


def test_B_local_uses_screened_empty_plane_then_original_loaded_clearance(monkeypatch):
    def original(a,side,name,goal,clearance):
        a._e15_wrist_branch=dict(object=name,side=side,goal_yaw=goal['yaw'],loaded_turn=math.pi,empty_height=.96)
    monkeypatch.setattr(wrist,'prepare_empty',original)
    a=Author();a.scene.spec['variant']='B';a._engineering_resume_checkpoint['source']={'steps':118,'physics_ticks':12640}
    result=run_segment(a,'e15_b_resume_red_from_empty_boundary',{})
    moves=[e[1]['right']for e in a.events if e[0]=='move']
    assert result['local_completed']and moves[0][2]==moves[1][2]==.96
    assert moves[4][2]==1.10 and moves[5][2]==1.10
