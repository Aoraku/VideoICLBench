"""Actual empty-wrist call signature and exact native149 continuation."""
from types import SimpleNamespace as N
import math
import numpy as np
import pytest
from videoicl_isaaclab import execution_design_segments_e23_e24 as segments
from videoicl_isaaclab import realworld_structural_expert as structural
from videoicl_isaaclab.realworld_tool_expert import ToolExecutionError,_axis_rotation
from test_execution_design_segments_e23_e24 import handoff_policy,patch_handoff_geometry,author


def test_real_air_rotate_call_keeps_orientation_and_object_target_distinct(monkeypatch):
    p,calls,holds,positions,cup=handoff_policy();current=np.eye(3);checks=[]
    target=_axis_rotation([0,0,1],math.radians(5));p.min_deg=.5
    p.a.tcp_rotation_task=lambda side:current.copy()
    old=p.act
    def act(side,token,**kwargs):
        nonlocal current
        assert side=='left'and token=='ROTATE_CCW'and kwargs['degrees']==5.
        old(side,token,**kwargs);current=target.copy()
    p.act=act
    monkeypatch.setattr(segments,'_air_check',lambda *args,**kwargs:checks.append(kwargs)or{})
    monkeypatch.setattr(segments,'_air_feedback',lambda *args:None)
    segments._air_rotate_empty(p,'left',target,held_guards=(({'actor':'red'},'right'),),target='red')
    assert len(calls)==1 and all(row['target']=='red'for row in checks)
    assert holds=={'left':False,'right':True}


def fixture149(monkeypatch):
    p,calls,holds,positions,cup=handoff_policy();patch_handoff_geometry(monkeypatch,p,positions,cup)
    p.c.steps=149;p.start=149
    contacts={frozenset(('red','right_finger'+str(i)))for i in(1,2)}
    p.snapshot=lambda:({'red':dict(cup,grasp=[holds['left'],holds['right']])},contacts)
    a=author('E23');a.scene.spec.update(variant='A',seed=4201)
    a.scene.spec['execution_design']['condition']='I';a.c=p.c
    a.c._engineering_diagnostic_only=True;a.c._engineering_checkpoint_readback_passed=True
    a._engineering_resume_checkpoint={'diagnostic_only':True,'source':{'steps':149,'physics_ticks':14902}}
    monkeypatch.setattr(structural,'StructuralAuthor',lambda actual:p)
    return a,p,calls,holds,contacts


def test_native149_only_finishes_receiver_handoff_and_retreat(monkeypatch):
    a,p,calls,holds,contacts=fixture149(monkeypatch);moves=[]
    old=segments._air_move
    def move(policy,side,point,**kwargs):
        moves.append((side,np.asarray(point).copy()));old(policy,side,point,**kwargs)
    monkeypatch.setattr(segments,'_air_move',move)
    monkeypatch.setattr(segments,'_air_resume_handoff',lambda *args:pytest.fail('must not replay CCW recovery'))
    monkeypatch.setattr(segments,'_air_handoff_red',lambda *args:pytest.fail('must not replay carry/staging prefix'))
    result=segments.run_segment(a,'e23_complete_handoff_from149',{})
    assert result['local_completed']and result['segment']=='e23_complete_handoff_from149'
    assert holds=={'left':True,'right':False}
    assert [(s,t)for s,t,_ in calls if t!='STILL']==[('left','GRASP'),('right','RELEASE')]
    release=next(before for s,t,before in calls if s=='right'and t=='RELEASE')
    assert release=={'left':True,'right':True}
    assert [s for s,_ in moves]==['left','left','right','right']
    assert not {'success','task_score_100','native_history'}&result.keys()


@pytest.mark.parametrize('fault',['variant','seed','condition','steps','tick','diagnostic','readback','mode','parameters','no_right_grip','one_finger','left_held','mesh'])
def test_native149_admission_and_actual_hold_fail_before_actions(monkeypatch,fault):
    a,p,calls,holds,contacts=fixture149(monkeypatch);parameters={}
    if fault=='variant':a.scene.spec['variant']='B'
    elif fault=='seed':a.scene.spec['seed']=4202
    elif fault=='condition':a.scene.spec['execution_design']['condition']='E'
    elif fault=='steps':a._engineering_resume_checkpoint['source']['steps']=150
    elif fault=='tick':a._engineering_resume_checkpoint['source']['physics_ticks']=15002
    elif fault=='diagnostic':a._engineering_resume_checkpoint['diagnostic_only']=False
    elif fault=='readback':a.c._engineering_checkpoint_readback_passed=False
    elif fault=='mode':a.c._engineering_diagnostic_only=False
    elif fault=='parameters':parameters={'recover_right_again':True}
    elif fault=='no_right_grip':holds['right']=False
    elif fault=='one_finger':contacts.remove(frozenset(('red','right_finger2')))
    elif fault=='left_held':holds['left']=True
    else:p.objects['red']['source_asset']['sha256']='bad'
    with pytest.raises(ToolExecutionError):segments.run_segment(a,'e23_complete_handoff_from149',parameters)
    assert calls==[]
