"""Native848 short-tail scope, existing support and30-action hard bound."""
import numpy as np
import pytest
from scipy.spatial.transform import Rotation
from test_execution_design_segments_e17_e20 import context,native_stand
from videoicl_isaaclab import execution_design_segments_e17_held_upper as segment
from videoicl_isaaclab import execution_design_segments_e17_upper as geometry
from videoicl_isaaclab import execution_design_e17_stand as stand
from videoicl_isaaclab import execution_design_e17_reference as reference
from videoicl_isaaclab import execution_design_e17_palm_escape as escape
from videoicl_isaaclab.realworld_tool_expert import ToolExecutionError


def prepared(monkeypatch,mode='good'):
    a,state,contacts=context('E17','B',('blue_triangle','right'));a._execution_design_reference_authorized=True;a.smooth=False
    a._engineering_resume_checkpoint={'diagnostic_only':True,'state_quality':'measured_native_state','source':{'steps':848,'physics_ticks':84811}}
    state['stand']['pos']=np.array([.04,.05,.8]);state['stand']['mat']=np.eye(3)
    for n,x in [('blue_square',-.004),('green_square',.078)]:
        state[n]['pos']=np.array([x,.014,.82]);contacts.add(frozenset((n,'stand')))
    state['blue_triangle']['pos']=np.array([.002,.012,1.08]);tip=state['blue_triangle']['pos'].copy();calls=[]
    a.tip=lambda side:tip.copy()
    monkeypatch.setattr(stand,'native_readback',lambda scene:native_stand())
    monkeypatch.setattr(reference,'measured_shelf_release',lambda p,name,side,actor,layer,target:[*target[:2],.22980625])
    def check(p,point=None,**kwargs):
        assert kwargs['payload']=='blue_triangle'and kwargs['wrist_only'];calls.append(('geometry',))
    monkeypatch.setattr(geometry,'_check',check)
    monkeypatch.setattr(escape,'escape_to_default_tilt',lambda p,payload,guard:guard())
    def act(left='STILL',right='STILL',mm=1.,rotation_deg=5.):
        a.c.steps+=1;calls.append((left,right,mm))
        if right=='RELEASE':
            state['blue_triangle']['grasp'][1]=False
            for i in(1,2):contacts.discard(frozenset(('blue_triangle','right_finger'+str(i))))
            if mode!='no_support':contacts.add(frozenset(('blue_triangle','stand')))
        elif right in('FWD','BACK','LEFT','RIGHT','UP','DOWN'):
            i,sign={'FWD':(0,1),'BACK':(0,-1),'LEFT':(1,1),'RIGHT':(1,-1),'UP':(2,1),'DOWN':(2,-1)}[right]
            tip[i]+=sign*mm/1000
            if mode!='budget':state['blue_triangle']['pos'][i]+=sign*mm/1000
        if mode=='move_stand':state['stand']['pos'][0]+=.0011
        elif mode=='lose_lower':contacts.discard(frozenset(('green_square','stand')))
        elif mode=='small_rotation':
            R=Rotation.from_rotvec([.00878,0,0]).as_matrix();state['stand']['mat']=R
            for n,x in [('blue_square',-.004),('green_square',.078)]:
                state[n]['pos']=np.array([.04,.05,.8])+R@(np.array([x,.014,.82])-[.04,.05,.8]);state[n]['mat']=R
    a.act=act
    return a,state,contacts,calls


def test_native848_continues_held_only_and_preserves_half_degree_supported_tilt(monkeypatch):
    a,state,contacts,calls=prepared(monkeypatch,'small_rotation');old=a.act
    result=segment.run_segment(a,'e17_b_resume_held_upper_triangle_848',{})
    assert result['local_completed']and result['active_actions']<=30 and a.act is old
    assert not any(x[1]=='GRASP'for x in calls if len(x)>1)
    assert not any(state['blue_triangle']['grasp'])and frozenset(('blue_triangle','stand'))in contacts
    assert any(x[0]=='geometry'for x in calls)


@pytest.mark.parametrize('fault',['source_steps','state_quality','parameter'])
def test_cannot_replace_native848_by_old822_or_quasistatic_record(monkeypatch,fault):
    a,state,contacts,calls=prepared(monkeypatch);params={}
    if fault=='source_steps':a._engineering_resume_checkpoint['source']['steps']=822
    elif fault=='state_quality':a._engineering_resume_checkpoint['state_quality']='measured_pose_fixture'
    else:params={'assume_held':True}
    with pytest.raises(ToolExecutionError):segment.run_segment(a,'e17_b_resume_held_upper_triangle_848',params)
    assert not a.c.steps


@pytest.mark.parametrize('mode,reason',[('move_stand','stand moved'),('lose_lower','lower square changed'),('no_support','actual stand support'),('budget','exhausted30')])
def test_first_failure_and30_action_budget_are_hard_limits(monkeypatch,mode,reason):
    a,state,contacts,calls=prepared(monkeypatch,mode);old=a.act
    with pytest.raises(ToolExecutionError,match=reason):segment.run_segment(a,'e17_b_resume_held_upper_triangle_848',{})
    assert a.act is old and a.c.steps<=30
    if mode=='budget':assert a.c.steps==30


def test_safe_native722_tilts_at_exterior_before_any_upper_descent(monkeypatch):
    from videoicl_isaaclab import execution_design_segments_e17_remaining as remaining
    a,state,contacts,calls=prepared(monkeypatch);a._engineering_resume_checkpoint['source']={'steps':722,'physics_ticks':72211}
    a.tip=lambda side:state['blue_triangle']['pos'].copy();events=[]
    def move(p,material,target,**kwargs):
        events.append(('move',np.asarray(target).copy()));state['blue_triangle']['pos']=np.asarray(target)-material['local'];a.act()
    monkeypatch.setattr(remaining,'_move',move)
    monkeypatch.setattr(escape,'escape_to_default_tilt',lambda *args:events.append(('tilt',)))
    result=segment.run_segment(a,'e17_b_place_held_upper_from_hover_722',{})
    assert result['local_completed']and result['active_actions']<=300
    assert [e[0]for e in events]==['move','move','move','tilt','move','move']
    assert events[2][1][1]==pytest.approx(-.180)and events[2][1][2]>=1.12
    assert events[4][1][1]==pytest.approx(-.180)and events[4][1][2]<1.12
