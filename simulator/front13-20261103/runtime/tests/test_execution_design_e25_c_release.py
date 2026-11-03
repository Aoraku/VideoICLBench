"""Pinned C209 actual upward clearance and original-goal gravity release."""
from copy import deepcopy
import numpy as np
import pytest
from test_execution_design_e25_c_relay import context
from videoicl_isaaclab.execution_design_segments_e19_e25 import run_segment
from videoicl_isaaclab.realworld_tool_expert import _axis_rotation


def fixture(tmp_path,monkeypatch,fault=None):
    a,state,contacts,calls=context(tmp_path,monkeypatch,fault)
    a._engineering_resume_checkpoint['source']={'steps':209,'physics_ticks':20911}
    state['knife']['pos']=np.array([.01383367,.2717855,.84066808]);state['knife']['mat']=np.eye(3)
    state['knife']['grasp']=[True,False];a.tip_array[:]=[-.04083642,.26788509,.84062522]
    contacts.discard(frozenset(('knife','table')))
    contacts.update(frozenset(('knife','left_finger'+str(i)))for i in(1,2))
    contacts.add(frozenset(('left_finger1','tray')))
    old=a.move_generated
    def move(*args,**kwargs):
        old(*args,**kwargs)
        if fault!='tray_contact':contacts.discard(frozenset(('left_finger1','tray')))
    a.move_generated=move
    def release(side):
        a.act('RELEASE','STILL');state['knife']['pos'][2]=.808
        if fault=='outside_after_release':state['knife']['pos'][0]=.05
    a.release_generated=release
    return a,state,contacts,calls


def test_C209_clears_actual_tray_contact_and_releases_at_original_goal(tmp_path,monkeypatch):
    a,state,contacts,calls=fixture(tmp_path,monkeypatch);before=deepcopy(a.scene.spec)
    result=run_segment(a,'e25_c_release_knife_from209',{})
    assert result['local_completed']and calls.count('RELEASE')==1 and 'GRASP'not in calls
    assert 'original_goal_rotation'not in calls
    assert frozenset(('knife','table'))in contacts and not any(state['knife']['grasp'])
    assert a.scene.spec==before and a.carried_payload is None
    assert not {'success','task_score_100','native_history'}&result.keys()


@pytest.mark.parametrize('fault',['source_step','source_tick','readback','mode','diagnostic','seed','parameters','mesh','no_grip','one_finger','outside','tilt','height'])
def test_C209_rejects_unpinned_or_unheld_geometry_before_actions(tmp_path,monkeypatch,fault):
    a,state,contacts,calls=fixture(tmp_path,monkeypatch);p={}
    if fault=='source_step':a._engineering_resume_checkpoint['source']['steps']=210
    elif fault=='source_tick':a._engineering_resume_checkpoint['source']['physics_ticks']=21011
    elif fault=='readback':a.c._engineering_checkpoint_readback_passed=False
    elif fault=='mode':a.c._engineering_diagnostic_only=False
    elif fault=='diagnostic':a._engineering_resume_checkpoint['diagnostic_only']=False
    elif fault=='seed':a.scene.spec['seed']=4202
    elif fault=='parameters':p={'force_release':True}
    elif fault=='mesh':next(o for o in a.scene.spec['objects']if o['id']=='knife')['source_asset']['sha256']='bad'
    elif fault=='no_grip':state['knife']['grasp'][0]=False
    elif fault=='one_finger':contacts.discard(frozenset(('knife','left_finger2')))
    elif fault=='outside':state['knife']['pos'][0]=.05
    elif fault=='tilt':state['knife']['mat']=_axis_rotation([0,1,0],np.deg2rad(7))
    else:state['knife']['pos'][2]=1.0
    with pytest.raises((ValueError,RuntimeError)):run_segment(a,'e25_c_release_knife_from209',p)
    assert not calls


@pytest.mark.parametrize('fault',['tray_contact','slip','no_support','outside_after_release'])
def test_C209_stops_on_first_real_contact_grip_or_release_failure(tmp_path,monkeypatch,fault):
    a,state,contacts,calls=fixture(tmp_path,monkeypatch,fault)
    with pytest.raises(RuntimeError):run_segment(a,'e25_c_release_knife_from209',{})
    if fault in('tray_contact','slip'):assert 'RELEASE'not in calls
    else:assert len(calls)==2


@pytest.mark.parametrize('overlap',[True,False])
def test_future_full_C_preserves_target_and_uses_actual_finger_tray_clearance(tmp_path,monkeypatch,overlap):
    from videoicl_isaaclab.execution_design_e25_c_release import release_height_for_knife
    a,state,contacts,calls=fixture(tmp_path,monkeypatch);before=deepcopy(a.scene.spec)
    state['tray']['pos']=np.array([0.,.117,.820]);state['tray']['mat']=np.eye(3)
    a.finger_geometry=lambda side:dict(source='actual_collision_mesh_current_body_pose',
        fingers=[dict(aabb_min_task_m=[-.07,.20 if overlap else .50,.85],aabb_max_task_m=[-.01,.28 if overlap else .55,.90])])
    floors=[];a.floor_clear_tcp=lambda side,floor:floors.append(floor)or(floor+.020)
    goal=next(g for g in a.scene.spec['goals']if g['object']=='knife')
    zone=next(z for z in a.scene.spec['zones']if z['id']==goal['target'])
    height=release_height_for_knife(a,goal,zone,.815)
    assert (height>.84 and floors)if overlap else(height==.815 and not floors)
    assert not calls and a.scene.spec==before
