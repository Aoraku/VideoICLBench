"""Small E17C short-segment scope and first-failure checks."""
from copy import deepcopy
from types import SimpleNamespace
import numpy as np
import pytest
from videoicl_isaaclab import execution_design_segments_e17_upper as segment
from videoicl_isaaclab import execution_design_e17_stand as stand
from videoicl_isaaclab import execution_design_e17_reference as reference
from videoicl_isaaclab.execution_design import REVISION_V3,source_sha256
from videoicl_isaaclab.realworld_tool_expert import ToolExecutionError


class Policy:
    def __init__(self,a):
        self.a=a;self.c=a.c;self.spec=a.scene.spec;self.objects={o['id']:o for o in self.spec['objects']};self.operations=[];a.policy=self
    def snapshot(self):return self.c.snapshot()
    def frame(self,ref):
        r=self.a.state[ref['actor']];return r['pos'].copy(),r['mat'].copy()
    def ref(self,name):return {'actor':name,'local':[0,0,0]}
    def bottom_local(self,name):return [0,0,-.003]
    def point(self,ref):return self.a.state[ref['actor']]['pos']+ref['local']
    def tip(self,side):return self.a.tip.copy()
    def require_held(self,ref,side):
        if not self.a.state['blue_square']['grasp'][1]:raise ToolExecutionError('Actual grip lost')
    def stage(self,name):self.operations.append({'stage':name});self.a.stage=name
    def release(self,ref,side):
        self.a.events.append(('release',));self.a.state['blue_square']['grasp'][1]=False
        self.a.contacts={frozenset(('stand','table'))}
        if self.a.mode!='no_support':self.a.contacts.add(frozenset(('blue_square','stand')))
        self.a.act()
    def pickup(self,*args,**kwargs):pytest.fail('Never repeat pickup')
    def package_stage(self):pytest.fail('Short segment never packages')
    def deliver(self):pytest.fail('Short segment never delivers')


def context(mode='good'):
    d=dict(revision=REVISION_V3,source_sha256=source_sha256(REVISION_V3),condition='I',local_regions=[dict(id='upper',members=['blue_square'])])
    spec=dict(id='E17',variant='C',seed=4201,execution_design=d,objects=[dict(id='stand',e17_stand_geometry=stand.descriptor()),dict(id='blue_square',source_asset={'sha256':'fed57b9b0e69a5b8b98d75324ed6856c0cdb21ebc56c8f98cb372670255b61bb'})])
    a=SimpleNamespace(scene=SimpleNamespace(spec=spec),control_report={'engineering_reference_only':True},_execution_design_reference_authorized=True,smooth=False,
        _engineering_resume_checkpoint={'diagnostic_only':True,'source':{'steps':490,'physics_ticks':49840}},mode=mode,events=[],tip=np.array([-.2,-.24,.907]))
    a.state={'stand':dict(pos=np.array([.04,.05,.8]),mat=np.eye(3),grasp=[False,False]),'blue_square':dict(pos=np.array([-.2,-.24,.906]),mat=np.eye(3),grasp=[False,True])}
    a.contacts={frozenset(('stand','table')),frozenset(('blue_square','right_finger1')),frozenset(('blue_square','right_finger2'))}
    a.c=SimpleNamespace(steps=0,snapshot=lambda:(a.state,a.contacts))
    def act(*args,**kwargs):
        a.c.steps+=1
        if mode=='stand_moves':a.state['stand']['pos'][1]+=.003
        if mode=='lost_grip':a.state['blue_square']['grasp'][1]=False
    a.act=act
    return a


def prepared(monkeypatch):
    monkeypatch.setattr(segment,'ExecutionDesignAuthor',Policy)
    monkeypatch.setattr(stand,'native_readback',lambda scene:dict(measured=True,derived_geometry_sha256=stand.GEOMETRY_SHA,kinematic_enabled=False,gravity_disabled=False))
    monkeypatch.setattr(reference,'collision_shelf_target',lambda p,actor,layer,target:[*target[:2],.21980625])
    monkeypatch.setattr(reference,'measured_shelf_release',lambda p,name,side,actor,layer,target:[*target[:2],target[2]+.01])
    monkeypatch.setattr(segment,'_check',lambda *args,**kwargs:None)
    def move(p,material,target,**kwargs):
        p.a.events.append(('move',np.asarray(target).copy(),material is not None))
        if material is not None:
            delta=np.asarray(target)-p.point(material);p.a.state['blue_square']['pos']+=delta;p.a.tip+=delta
        else:p.a.tip[:]=target
        p.a.act()
    monkeypatch.setattr(segment,'_move',move)


def test_only_held_blue_south_upper_release_without_optional_exit(monkeypatch):
    prepared(monkeypatch);a=context();spec=deepcopy(a.scene.spec);old=a.act
    result=segment.run_segment(a,'e17_c_place_held_blue_upper_south',{})
    moves=[e for e in a.events if e[0]=='move']
    assert result['local_completed']and set(result)=={'local_completed','operations','active_actions'}
    assert moves[1][1][1]==pytest.approx(-.180)
    assert np.allclose(moves[4][1][:2],[-.004,.006])
    assert len(moves)==5 and all(e[2]for e in moves)
    assert len([e for e in a.events if e[0]=='release'])==1 and not any(a.state['blue_square']['grasp'])
    assert frozenset(('blue_square','stand'))in a.contacts and a.scene.spec==spec and a.act is old


@pytest.mark.parametrize('mode,reason',[('stand_moves','stand moved'),('lost_grip','grip lost'),('no_support','actual stand support')])
def test_first_actual_failure_ends_short_tail(monkeypatch,mode,reason):
    prepared(monkeypatch);a=context(mode);old=a.act
    with pytest.raises(ToolExecutionError,match=reason):segment.run_segment(a,'e17_c_place_held_blue_upper_south',{})
    assert a.act is old
    if mode!='no_support':assert a.c.steps==1 and not any(e[0]=='release'for e in a.events)


@pytest.mark.parametrize('fault',['boundary','variant','bilateral','stand_pose','parameter'])
def test_wrong_boundary_or_missing_actual_guard_fails_before_action(monkeypatch,fault):
    prepared(monkeypatch);a=context();params={}
    if fault=='boundary':a._engineering_resume_checkpoint['source']['steps']=815
    elif fault=='variant':a.scene.spec['variant']='B'
    elif fault=='bilateral':a.contacts.discard(frozenset(('blue_square','right_finger2')))
    elif fault=='stand_pose':a.state['stand']['pos'][1]+=.035
    else:params={'assume_held':True}
    with pytest.raises(ToolExecutionError):segment.run_segment(a,'e17_c_place_held_blue_upper_south',params)
    assert not a.c.steps
