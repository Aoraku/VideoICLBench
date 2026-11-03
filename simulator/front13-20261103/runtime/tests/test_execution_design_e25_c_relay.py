from copy import deepcopy
import numpy as np
import pytest
from test_execution_design_e25_reference import source_palm_author,scene
from test_execution_design_e25_a_receiver import placement
from videoicl_isaaclab.execution_design_e25_reference import prepare_source_palm
from videoicl_isaaclab.realworld_tool_expert import _axis_rotation
from videoicl_isaaclab.execution_design_segments_e19_e25 import run_segment
from videoicl_isaaclab import execution_design_e25_c_relay as candidate


def test_C_rolled_supported_handle_uses_real_horizontal_pinch_candidate(tmp_path):
    a,state,contacts=source_palm_author(tmp_path);a.scene.spec=scene(tmp_path,'C');state['knife']['mat']=_axis_rotation([1,0,0],np.deg2rad(37));before=deepcopy(a.scene.spec);actual=state['knife']['mat'].copy()
    prepare_source_palm(a,'right','knife',{'_e07_after_relay':{}})
    assert a.actions==['move','ROLL_RIGHT','ROLL_RIGHT']
    proof=a.control_report['e25_c_rolled_knife_pinch_candidate']
    assert abs(proof['actual_source_jaw_axis_task'][2])>.6 and proof['horizontal_pinch_heading_task'][2]==0.
    assert proof['source_grasp_and_axis_unchanged']and not proof['native_grasp_validated']
    assert a.scene.spec==before;np.testing.assert_array_equal(state['knife']['mat'],actual)


@pytest.mark.parametrize('fault',['long_axis','no_support','held','A_scope'])
def test_projection_is_not_a_generic_tilt_or_contact_gate_relaxation(tmp_path,fault):
    a,state,contacts=source_palm_author(tmp_path);a.scene.spec=scene(tmp_path,'C');r=_axis_rotation([1,0,0],np.deg2rad(37));state['knife']['mat']=r
    if fault=='long_axis':state['knife']['mat']=_axis_rotation([0,1,0],np.deg2rad(40))@r
    elif fault=='no_support':contacts.clear()
    elif fault=='held':state['knife']['grasp'][0]=True
    else:a.scene.spec=scene(tmp_path,'A')
    with pytest.raises((RuntimeError,ValueError)):prepare_source_palm(a,'right','knife',{})
    if fault!='A_scope':assert a.actions==[]


def context(tmp_path,monkeypatch,fault=None):
    a,state,contacts,calls=placement(tmp_path,monkeypatch,fault);a.scene.spec=scene(tmp_path,'C')
    a._engineering_resume_checkpoint={'diagnostic_only':True,'source':{'steps':404,'physics_ticks':41240}}
    a.c._engineering_diagnostic_only=True;a.c._engineering_checkpoint_readback_passed=True
    def acquire(a,variant,name,p):
        assert variant=='C'and name=='knife'and p['side']=='left'
        a.act('GRASP','STILL');a.carried_payload=('knife','left')
        return [{'operation':'actual_source_acquisition','actor':'knife','side':'left'}]
    monkeypatch.setattr(candidate,'_acquire',acquire)
    return a,state,contacts,calls


def test_C404_native_segment_really_places_original_knife_goal(tmp_path,monkeypatch):
    a,state,contacts,calls=context(tmp_path,monkeypatch);before=deepcopy(a.scene.spec)
    result=run_segment(a,'e25_c_relay_knife_from404',{})
    assert result['local_completed']and set(result)=={'local_completed','operations','active_actions'}
    assert calls.count('GRASP')==1 and calls.count('RELEASE')==1
    assert a.scene.spec==before and a.carried_payload is None and not any(state['knife']['grasp'])
    assert frozenset(('knife','table'))in contacts


@pytest.mark.parametrize('fault',['steps','tick','diagnostic','readback','mode','seed','parameters'])
def test_native_C404_admission_cannot_expand_to_arbitrary_checkpoint(tmp_path,monkeypatch,fault):
    a,state,contacts,calls=context(tmp_path,monkeypatch);p={}
    if fault=='steps':a._engineering_resume_checkpoint['source']['steps']=405
    elif fault=='tick':a._engineering_resume_checkpoint['source']['physics_ticks']=41340
    elif fault=='diagnostic':a._engineering_resume_checkpoint['diagnostic_only']=False
    elif fault=='readback':a.c._engineering_checkpoint_readback_passed=False
    elif fault=='mode':a.c._engineering_diagnostic_only=False
    elif fault=='seed':a.scene.spec['seed']=4202
    else:p={'assume_held':True}
    with pytest.raises(ValueError,match='C404'):run_segment(a,'e25_c_relay_knife_from404',p)
    assert calls==[]


@pytest.mark.parametrize('fault',['slip','no_support'])
def test_C404_stops_on_actual_grip_or_support_failure(tmp_path,monkeypatch,fault):
    a,state,contacts,calls=context(tmp_path,monkeypatch,fault)
    with pytest.raises(RuntimeError):run_segment(a,'e25_c_relay_knife_from404',{})
    if fault=='slip':assert 'RELEASE'not in calls
