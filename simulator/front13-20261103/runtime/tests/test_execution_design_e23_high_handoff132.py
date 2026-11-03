"""A real receiver observation is required before giving up the original grip."""
import numpy as np
import pytest
from videoicl_isaaclab import execution_design_segments_e23_e24 as air
from videoicl_isaaclab import execution_design_e23_high_handoff as high
from videoicl_isaaclab.realworld_tool_expert import ToolExecutionError
from test_execution_design_e23_handoff149 import fixture149


def test_native132_skips_carry_and_requires_real_receiver_before_release(monkeypatch,tmp_path):
    a,p,calls,holds,contacts=fixture149(monkeypatch)
    a._engineering_resume_checkpoint['source']={'steps':132,'physics_ticks':13202}
    a.out=tmp_path;p.c.steps=p.start=132;moves=[];hang=[]
    old=air._air_move
    def move(policy,side,point,**kwargs):
        moves.append((side,np.asarray(point).copy(),dict(holds)))
        return old(policy,side,point,**kwargs)
    monkeypatch.setattr(air,'_air_move',move)
    monkeypatch.setattr(air,'_air_rotate_empty',lambda *args,**kwargs:pytest.fail('do not replay wrist prefix'))
    monkeypatch.setattr(high,'_hang_current_red',lambda policy:hang.append(dict(holds)))
    result=air.run_segment(a,'e23_finish_high_handoff_from132',{})
    assert result['local_completed'] and holds=={'left':True,'right':False}
    assert [side for side,_,_ in moves[:3]]==['left']*3
    release=next(before for side,token,before in calls if side=='right'and token=='RELEASE')
    assert release=={'left':True,'right':True}
    assert hang==[{'left':True,'right':False}]
    assert not {'success','task_score_100','native_history'}&result.keys()


def test_native132_failed_receiver_never_releases_right(monkeypatch,tmp_path):
    a,p,calls,holds,contacts=fixture149(monkeypatch)
    a._engineering_resume_checkpoint['source']={'steps':132,'physics_ticks':13202}
    a.out=tmp_path
    old=p.act
    def refused_receiver(side=None,token='STILL',**kwargs):
        old(side,token,**kwargs)
        if side=='left'and token=='GRASP':holds['left']=False
    p.act=refused_receiver
    with pytest.raises(ToolExecutionError,match='grip lost'):
        air.run_segment(a,'e23_finish_high_handoff_from132',{})
    assert len([1 for side,token,_ in calls if token=='GRASP'])==3
    assert not any(side=='right'and token=='RELEASE'for side,token,_ in calls)


def test_native12_closes_actual_pads_without_replaying_approach(monkeypatch,tmp_path):
    a,p,calls,holds,contacts=fixture149(monkeypatch)
    a._engineering_resume_checkpoint['source']={'steps':12,'physics_ticks':1202}
    a.out=tmp_path;moves=[]
    old=air._air_move
    def move(policy,side,point,**kwargs):
        assert holds['left'], 'no replay before actual receiver grip'
        moves.append(side);return old(policy,side,point,**kwargs)
    monkeypatch.setattr(air,'_air_move',move)
    monkeypatch.setattr(high,'_hang_current_red',lambda policy:None)
    result=air.run_segment(a,'e23_grasp_current_lowwall_from12',{})
    assert result['local_completed']and moves==['right','right']
    assert calls[0][:2]==('left','GRASP')and holds=={'left':True,'right':False}
