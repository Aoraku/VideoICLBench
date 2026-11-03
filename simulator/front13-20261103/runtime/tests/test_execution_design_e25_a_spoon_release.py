from copy import deepcopy
import numpy as np
import pytest
from test_execution_design_e25_b_release import fixture as held
from test_execution_design_e25_reference import scene
from videoicl_isaaclab import engineering_front25_suffix as dispatch
from videoicl_isaaclab.realworld_tool_expert import _axis_rotation


def current(tmp_path,fault=None):
    a,state,contacts,calls=held(tmp_path,fault);a.scene.spec=scene(tmp_path,'A')
    a._engineering_resume_checkpoint['source']={'steps':600,'physics_ticks':60840}
    state['spoon'].update(pos=np.array([.25554,.16161,.84542]),mat=_axis_rotation([0,1,0],np.deg2rad(4.2)))
    a.tip_array[:]=[.19167,.1604,.84836]
    return a,state,contacts,calls


def test_A600_releases_actual_offcentre_spoon_inside_original_zone(tmp_path):
    a,state,contacts,calls=current(tmp_path);old=deepcopy(a.scene.spec);xy=state['spoon']['pos'][:2].copy()
    result=dispatch.solve(a,a._engineering_resume_checkpoint,{'entry':'e25_a_release_spoon_from600','parameters':{}})
    assert result['segment_passed']and not result['full_task_acceptance']and calls==['RELEASE','STILL']
    np.testing.assert_array_equal(state['spoon']['pos'][:2],xy);assert a.scene.spec==old


@pytest.mark.parametrize('fault',['step','tick','grip','region','readback'])
def test_A600_keeps_native_boundary_and_real_grip_goal_admission(tmp_path,fault):
    a,state,contacts,calls=current(tmp_path)
    if fault=='step':a._engineering_resume_checkpoint['source']['steps']=601
    elif fault=='tick':a._engineering_resume_checkpoint['source']['physics_ticks']=60841
    elif fault=='grip':contacts.discard(frozenset(('spoon','left_finger2')))
    elif fault=='region':state['spoon']['pos'][0]=.3
    else:a.c._engineering_checkpoint_readback_passed=False
    with pytest.raises((ValueError,RuntimeError)):dispatch.solve(a,a._engineering_resume_checkpoint,{'entry':'e25_a_release_spoon_from600','parameters':{}})
    assert not calls


def test_A600_stops_at_real_release_without_support(tmp_path):
    a,state,contacts,calls=current(tmp_path,'support')
    with pytest.raises(RuntimeError,match='support'):dispatch.solve(a,a._engineering_resume_checkpoint,{'entry':'e25_a_release_spoon_from600','parameters':{}})
    assert calls==['RELEASE']


def test_future_full_stops_at_original_region_without_chasing_exact_centre(tmp_path):
    from videoicl_isaaclab.execution_design_e25_a_spoon_release import lower_until_original_goal
    a,state,contacts,calls=current(tmp_path);old=deepcopy(a.scene.spec)
    goal=next(g for g in a.scene.spec['goals']if g['object']=='spoon').copy();goal['_e07_after_relay']={}
    lower_until_original_goal(a,goal,[.165,.18,.82])
    assert not calls and a.scene.spec==old and a.control_report['e25_a_spoon_actual_goal_stop']['original_goal_unchanged']


def test_future_full_retains_actual_calibrated_public_axis_before_region_stop(tmp_path):
    from videoicl_isaaclab.execution_design_e25_a_spoon_release import lower_until_original_goal
    a,state,contacts,calls=current(tmp_path);state['spoon']['pos'][2]=.862;a.tip_array[2]=.865
    a.generated_axis_signs={'left':{2:-1}}
    def act(left,right,mm):
        assert left=='UP'and right=='STILL'and mm==5.
        calls.append(left);a.tip_array[2]-=.005;state['spoon']['pos'][2]-=.005
    a.act=act;goal=next(g for g in a.scene.spec['goals']if g['object']=='spoon').copy();goal['_e07_after_relay']={}
    lower_until_original_goal(a,goal,[*a.tip_array[:2],.8])
    assert calls==['UP']
