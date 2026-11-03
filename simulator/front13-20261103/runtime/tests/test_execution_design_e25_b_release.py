from copy import deepcopy
import numpy as np
import pytest
from test_execution_design_e25_a_receiver import fixture as basic
from test_execution_design_e25_reference import scene
from videoicl_isaaclab.execution_design_segments_e19_e25 import run_segment


def fixture(tmp_path,fault=None):
    a,state,contacts=basic(tmp_path);a.scene.spec=scene(tmp_path,'B');calls=[]
    a._engineering_resume_checkpoint={'diagnostic_only':True,'source':{'steps':187,'physics_ticks':18711}}
    a.c._engineering_diagnostic_only=True;a.c._engineering_checkpoint_readback_passed=True
    state['spoon'].update(pos=np.array([.22572182,.17928149,.88390136]),mat=np.diag([-1.,-1.,1.]),grasp=[True,False])
    a.tip_array[:]=[.16718113,.17986596,.88564592]
    contacts.clear();contacts.update(frozenset(('spoon','left_finger'+str(i)))for i in(1,2))
    a.floor_clear_tcp=lambda side,floor:floor+.011
    def act(left='STILL',right='STILL',*args,**kwargs):
        calls.append(left);a.c.steps+=1
        if left=='RELEASE':
            state['spoon']['grasp'][0]=False
            contacts.difference_update(frozenset(('spoon','left_finger'+str(i)))for i in(1,2))
            state['spoon']['pos'][2]=.8096
            if fault!='support':contacts.add(frozenset(('spoon','table')))
    a.act=act
    def move(goals):
        tip=np.asarray(goals['left']);delta=tip-a.tip_array
        if state['spoon']['grasp'][0]:state['spoon']['pos']+=delta
        a.tip_array[:]=tip;a.act()
        if fault=='slip':state['spoon']['grasp'][0]=False
    a.move_generated=move;a.release_generated=lambda side:a.act('RELEASE','STILL')
    return a,state,contacts,calls


def test_B187_actual_spoon_is_released_supported_without_repeating_winding(tmp_path):
    a,state,contacts,calls=fixture(tmp_path);before=deepcopy(a.scene.spec);xy=state['spoon']['pos'][:2].copy()
    result=run_segment(a,'e25_b_release_spoon_from187',{})
    assert result['local_completed']and calls==['STILL','RELEASE','STILL']
    np.testing.assert_array_equal(state['spoon']['pos'][:2],xy)
    assert frozenset(('spoon','table'))in contacts and not any(state['spoon']['grasp'])
    assert a.scene.spec==before and a.carried_payload is None


@pytest.mark.parametrize('fault',['step','tick','readback','mode','no_grip','one_finger','region','parameters'])
def test_B187_boundary_and_real_grip_fail_closed_before_any_action(tmp_path,fault):
    a,state,contacts,calls=fixture(tmp_path);p={}
    if fault=='step':a._engineering_resume_checkpoint['source']['steps']=188
    elif fault=='tick':a._engineering_resume_checkpoint['source']['physics_ticks']=18811
    elif fault=='readback':a.c._engineering_checkpoint_readback_passed=False
    elif fault=='mode':a.c._engineering_diagnostic_only=False
    elif fault=='no_grip':state['spoon']['grasp'][0]=False
    elif fault=='one_finger':contacts.discard(frozenset(('spoon','left_finger2')))
    elif fault=='region':state['spoon']['pos'][0]=.3
    else:p={'skip_winding':True}
    with pytest.raises((ValueError,RuntimeError)):run_segment(a,'e25_b_release_spoon_from187',p)
    assert not calls


@pytest.mark.parametrize('fault',['support','slip'])
def test_B187_first_actual_grip_or_support_failure_stops(tmp_path,fault):
    a,state,contacts,calls=fixture(tmp_path,fault)
    with pytest.raises(RuntimeError):run_segment(a,'e25_b_release_spoon_from187',{})
    assert calls==(['STILL']if fault=='slip'else['STILL','RELEASE'])
