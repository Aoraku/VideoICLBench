"""Boundary identity, completed-prefix preservation and public-only E17 tail."""
from copy import deepcopy
from pathlib import Path
from types import SimpleNamespace
import math
import numpy as np
import pytest
from scipy.spatial.transform import Rotation
from videoicl_isaaclab import execution_design_segments_e17 as segment
from videoicl_isaaclab.execution_design import REVISION_V3,source_sha256
from videoicl_isaaclab.execution_design_e17_stand import descriptor
from videoicl_isaaclab import execution_design_e17_stand as stand
from videoicl_isaaclab.realworld_tool_expert import ToolExecutionError


class Policy:
    def __init__(self,a):
        self.a=a;self.c=a.c;self.spec=a.scene.spec;self.d=self.spec['execution_design'];self.s=self.spec['semantic']
        self.objects={o['id']:o for o in self.spec['objects']};self.grasps=deepcopy(a.grasps);self.geometry=self.s['structural_expert'];self.operations=[];self.start=self.c.steps
        a.policy=self
    def snapshot(self):return self.c.snapshot()
    def frame(self,ref):
        r=self.a.state[ref['actor']];return r['pos'].copy(),r['mat'].copy()
    def stage(self,name):self.a.stage=name;self.operations.append(dict(stage=name))
    def ref(self,name):return {'actor':name,**deepcopy(self.grasps.get(name,{}))}
    def acquire_chip_with_wrist_margin(self,ref,side):self.a.events.append(('original-acquire',ref['actor'],deepcopy(ref)));self.a.act()
    def place_lower_shelf(self,name,actor,target):self.place(name,actor,target)
    def place(self,name,actor,target):
        self.a.events.append(('place',name));self.acquire_chip_with_wrist_margin(self.ref(name),'right');self.a.contacts.add(frozenset((name,actor)));self.a.act()
    def package_stage(self):self.a.events.append(('package',));self.a.act()
    def deliver(self):
        self.a.events.append(('deliver',));self.a.state['stand']['pos'][0]+=.01
        for name in self.a.state:
            if frozenset((name,'stand'))in self.a.contacts:self.a.state[name]['pos'][0]+=.01
    def local_stage(self):pytest.fail('completed lid/first placement must not replay')


def context(variant='A',mode='good'):
    completed='green_square'if variant=='A'else'blue_square';remaining='green_triangle'if variant=='A'else'green_square'
    objects=[dict(id='stand',size=[.105,.103,.173],e17_stand_geometry=descriptor()),dict(id='packing_lid',size=[.10,.2,.003]),dict(id=completed,size=[.02,.02,.003]),dict(id=remaining,size=[.02,.017320508,.003],source_asset={'sha256':segment.TRIANGLE_SHA}),dict(id='last',size=[.02,.02,.003])]
    d=dict(revision=REVISION_V3,source_sha256=source_sha256(REVISION_V3),condition='I',local_regions=[dict(id='lower',actor='stand',members=[completed,remaining]),dict(id='upper',actor='stand',members=['last'])])
    s=dict(id='E17',variant=variant,seed=4201,objects=objects,execution_design=d,semantic=dict(structural_expert={'shelf_positions':{'last':[.038,.038,.14]}},shelves={'upper':{'center_local':[0,0,.21]}}))
    a=SimpleNamespace(scene=SimpleNamespace(spec=s,embodiment=SimpleNamespace(name='franka',config={})),control_report={'engineering_reference_only':True},_execution_design_reference_authorized=True,smooth=False,
        _engineering_resume_checkpoint={'diagnostic_only':True,'source':{'steps':842 if variant=='A'else 822,'physics_ticks':85040 if variant=='A'else 83040}},events=[],completed=completed,stage='restored')
    a.state={o['id']:dict(pos=np.array([0.,0.,.82]),mat=np.eye(3),grasp=[False,False])for o in objects};a.state['stand']['pos']=np.array([.04,.05,.8]);a.state[completed]['pos']=np.array([-.004,.006,.82])
    a.contacts={frozenset((completed,'stand')),frozenset(('packing_lid','table'))};a.grasps={o['id']:{'local':[0,0,0],'jaw_axis_local':[1,0,0]}for o in objects};a.c=SimpleNamespace(steps=0,snapshot=lambda:(a.state,a.contacts))
    def act(*args,**kwargs):
        a.c.steps+=1
        if mode=='move_prefix':a.state[completed]['pos'][0]+=.003
        if mode=='stand_moves':a.state['stand']['pos'][0]+=.0011
        if mode=='support_lost':a.contacts.discard(frozenset((completed,'stand')))
        if mode=='first_failure':raise RuntimeError('native actuator rejected')
    a.act=act
    return a


def prepared(monkeypatch):
    monkeypatch.setattr(segment,'ExecutionDesignAuthor',Policy)
    monkeypatch.setattr(stand,'native_readback',lambda scene:dict(measured=True,derived_geometry_sha256=stand.GEOMETRY_SHA,mass_kg=[[stand.MASS_KG]],kinematic_enabled=False,gravity_disabled=False))
    monkeypatch.setattr(segment,'relevel_empty',lambda p,side:p.a.events.append(('public-empty-level',side)))


@pytest.mark.parametrize('variant',['A','B'])
def test_suffix_skips_lid_and_first_piece_then_calls_remaining_original_flow(monkeypatch,variant):
    prepared(monkeypatch);a=context(variant);before=deepcopy(a.scene.spec);original_act=a.act
    result=segment.run_segment(a,f'e17_{variant.lower()}_resume_after_lower_first',{})
    assert set(result)=={'local_completed','operations','active_actions'}and result['local_completed']
    assert [e[1]for e in a.events if e[0]=='place']==(['green_triangle','last']if variant=='A'else['green_square','last'])
    assert a.events[-2:]==[('package',),('deliver',)]
    assert all(e[1]!=a.completed for e in a.events if e[0]=='original-acquire')
    assert len([e for e in a.events if e[0]=='public-empty-level'])==2
    assert a.act is original_act and a.scene.spec==before


@pytest.mark.parametrize('fault',['task','variant','seed','revision','condition','source','permission','engineering','smooth','robot','diagnostic','steps','tick','assignment','lid','held'])
def test_incompatible_boundary_fails_before_actions(monkeypatch,fault):
    prepared(monkeypatch);a=context();s=a.scene.spec;cp=a._engineering_resume_checkpoint
    if fault=='task':s['id']='E18'
    elif fault=='variant':s['variant']='B'
    elif fault=='seed':s['seed']=4202
    elif fault in ('revision','condition'):s['execution_design'][fault]='wrong'
    elif fault=='source':s['execution_design']['source_sha256']='bad'
    elif fault=='permission':a._execution_design_reference_authorized=False
    elif fault=='engineering':a.control_report.clear()
    elif fault=='smooth':a.smooth=True
    elif fault=='robot':a.scene.embodiment.name='other'
    elif fault=='diagnostic':cp['diagnostic_only']=False
    elif fault=='steps':cp['source']['steps']=841
    elif fault=='tick':cp['source']['physics_ticks']=85039
    elif fault=='assignment':s['execution_design']['local_regions'][0]['members'].reverse()
    elif fault=='lid':a.contacts.discard(frozenset(('packing_lid','table')))
    else:a.state['green_square']['grasp'][1]=True
    with pytest.raises(ToolExecutionError):segment.run_segment(a,'e17_a_resume_after_lower_first',{})
    assert not a.c.steps and not a.events


@pytest.mark.parametrize('parameters',[None,{'skip':['green_triangle']},{'pose':[0,0,0]},{'task_score_100':100},{'assume_held':True}])
def test_suffix_has_no_state_or_goal_override_parameters(monkeypatch,parameters):
    prepared(monkeypatch);a=context()
    with pytest.raises(ToolExecutionError):segment.run_segment(a,'e17_a_resume_after_lower_first',parameters)
    assert not a.c.steps


@pytest.mark.parametrize('mode',['move_prefix','stand_moves','support_lost','first_failure'])
def test_first_native_or_preservation_failure_stops_before_next_piece(monkeypatch,mode):
    prepared(monkeypatch);a=context(mode=mode);old=a.act
    with pytest.raises((ToolExecutionError,RuntimeError)):segment.run_segment(a,'e17_a_resume_after_lower_first',{})
    assert a.c.steps==1 and a.act is old
    assert not any(e[0]in('package','deliver')or e[:2]==('place','last')for e in a.events)


def test_tilted_triangle_candidate_uses_actual_horizontal_median_not_pose_edits():
    a=context();p=Policy(a);a.state['green_triangle']['mat']=Rotation.from_euler('y',37,degrees=True).as_matrix();original=deepcopy(a.state['green_triangle'])
    segment._tilted_triangle_reference(p,'green_triangle')
    assert p.grasps['green_triangle']['local']==[0,0,0]and p.grasps['green_triangle']['jaw_axis_local']==[0,1,0]
    assert a.grasps['green_triangle']['jaw_axis_local']==[1,0,0]
    assert np.array_equal(a.state['green_triangle']['mat'],original['mat'])
    assert p.operations[0]['native_validation_required']is True


@pytest.mark.parametrize('fault',['mesh','tilt','yaw','size'])
def test_unreviewed_triangle_is_rejected_instead_of_flattening_source(fault):
    a=context();p=Policy(a);a.state['green_triangle']['mat']=Rotation.from_euler('y',37,degrees=True).as_matrix()
    if fault=='mesh':p.objects['green_triangle']['source_asset']['sha256']='bad'
    elif fault=='tilt':a.state['green_triangle']['mat']=Rotation.from_euler('y',80,degrees=True).as_matrix()
    elif fault=='yaw':a.state['green_triangle']['mat']=Rotation.from_euler('xy',[15,37],degrees=True).as_matrix()
    else:p.objects['green_triangle']['size']=[.03,.03,.003]
    with pytest.raises(ToolExecutionError):segment._tilted_triangle_reference(p,'green_triangle')


def test_relevel_measures_actual_orientation_and_uses_only_public_axis_actions(monkeypatch):
    current=Rotation.from_euler('zyx',[90,-60,180],degrees=True).as_matrix();tip=np.array([0.,-.18,1.12]);events=[]
    p=SimpleNamespace(stage=lambda s:None,tip=lambda side:tip.copy())
    p.a=SimpleNamespace(tcp_rotation_task=lambda side:current.copy())
    def move(side,target):tip[:]=target;events.append(('move',np.asarray(target).copy()))
    def act(side,token,degrees):
        nonlocal current
        index,sign={'ROLL_LEFT':(0,1),'ROLL_RIGHT':(0,-1),'PITCH_UP':(1,1),'PITCH_DOWN':(1,-1),'ROTATE_CCW':(2,1),'ROTATE_CW':(2,-1)}[token]
        v=np.zeros(3);v[index]=sign*math.radians(max(.5,degrees));current=Rotation.from_rotvec(v).as_matrix()@current;events.append(('rotate',token))
    p.move=move;p.act=act
    monkeypatch.setattr(segment,'_empty',lambda p:None);monkeypatch.setattr(segment,'_rotation_clearance',lambda p,s:None)
    monkeypatch.setattr(segment,'_finger_axis',lambda p,s:current[:,1].copy())
    segment.relevel_empty(p)
    assert events[0][0]=='move'and events[0][1][1]==-.230
    assert abs(current[2,1])<.02 and current[2,2]<-.995 and any(e[0]=='rotate'for e in events)


def test_rotation_rejects_insufficient_native_height_before_motion(monkeypatch):
    monkeypatch.setattr(segment,'_empty',lambda p:None)
    p=SimpleNamespace(stage=lambda s:None,tip=lambda s:np.array([0,0,1.]))
    with pytest.raises(ToolExecutionError,match='high retreat'):segment.relevel_empty(p)
