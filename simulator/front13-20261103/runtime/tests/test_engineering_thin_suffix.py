from types import SimpleNamespace
import pytest
from videoicl_isaaclab.engineering_thin_suffix import solve


def test_thin_suffix_refuses_unrestored_or_formal_entry_before_any_actions():
    a=SimpleNamespace(scene=SimpleNamespace(spec={'id':'E50'}),control_report={'engineering_reference_only':True})
    with pytest.raises(ValueError,match='startup restore required'):
        solve(a,{},dict(entry='e50-seated-push'))
    a._engineering_resume_checkpoint={'state_quality':'measured_pose_fixture'};a.control_report={}
    with pytest.raises(ValueError,match='Engineering-only'):
        solve(a,{},dict(entry='e50-seated-push'))


def test_restored_checkpoint_cannot_cross_task_suffix_identity():
    a=SimpleNamespace(scene=SimpleNamespace(spec={'id':'E44'}),control_report={'engineering_reference_only':True},_engineering_resume_checkpoint={'stage':'old'})
    with pytest.raises(ValueError,match='Unknown thin-task'):
        solve(a,{},dict(entry='e50-pre-pinch'))


def test_native_raycast_object_hits_do_not_require_dictionary_items(monkeypatch):
    import sys
    import numpy as np
    from videoicl_isaaclab.engineering_thin_suffix import _ray_queries
    hit=SimpleNamespace(position=(0.,.1,.8),normal=(0.,0.,1.),rigid_body=123,collision=456)
    query=SimpleNamespace(raycast_all=lambda origin,direction,distance,callback:callback(hit))
    physx=SimpleNamespace(get_physx_scene_query_interface=lambda:query)
    monkeypatch.setitem(sys.modules,'omni',SimpleNamespace(physx=physx))
    monkeypatch.setitem(sys.modules,'omni.physx',physx)
    monkeypatch.setitem(sys.modules,'carb',SimpleNamespace(Float3=lambda *x:x,settings=SimpleNamespace(get_settings=lambda:SimpleNamespace(get=lambda key:True))))
    monkeypatch.setitem(sys.modules,'pxr',SimpleNamespace(PhysicsSchemaTools=SimpleNamespace(intToSdfPath=lambda value:'/World/Props/card')))
    a=SimpleNamespace(scene=SimpleNamespace(task_to_world=lambda p:np.asarray(p)))
    p=SimpleNamespace(frame=lambda ref:(np.array([0.,.1,.8]),np.eye(3)))
    r=_ray_queries(a,p,{})
    assert r['available']and r['scene_query_support']and len(r['rays'])==3
    assert all(x['hits'][0]['rigid_body']=='/World/Props/card'for x in r['rays'])


def test_suspended_checkpoint_approaches_near_table_before_bounded_toe_refinement():
    import numpy as np
    from videoicl_isaaclab.engineering_thin_suffix import _lower_to_table_band
    low=[.805];tcp=np.array([0.,0.,.86]);moves=[];actions=[]
    a=SimpleNamespace(finger_geometry=lambda side:dict(lowest_z_task_m=low[0]))
    def move(side,target,tolerance):
        moves.append(target.copy());low[0]+=float(target[2]-tcp[2]);tcp[:]=target
    def act(side,token,mm):
        actions.append(token);low[0]=max(.80002,low[0]-.0005)
    p=SimpleNamespace(a=a,tip=lambda side:tcp.copy(),move=move,act=act)
    assert _lower_to_table_band(p,'left',.8)<=.80005
    assert len(moves)==1 and moves[0][2]==pytest.approx(.8552)
    assert actions==['DOWN']
