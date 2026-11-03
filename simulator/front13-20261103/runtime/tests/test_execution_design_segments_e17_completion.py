"""One native222 release, actual support and exact source admission."""
import numpy as np
import pytest
from test_execution_design_segments_e17_e20 import context
from videoicl_isaaclab import execution_design_segments_e17_completion as segment
from videoicl_isaaclab.realworld_tool_expert import ToolExecutionError


def prepared(mode='good'):
    a,state,contacts=context('E17','C');a._execution_design_reference_authorized=True;a.smooth=False
    a._engineering_resume_checkpoint={'diagnostic_only':True,'state_quality':'measured_native_state','source':{'steps':222,'physics_ticks':22211}}
    state['stand']['pos']=np.array([.04,.05,.8]);state['blue_square']['pos']=np.array([-.004,.006,1.023])
    contacts.update([frozenset(('stand','table')),frozenset(('blue_square','stand'))]);calls=[]
    def act(left='STILL',right='STILL',**kwargs):
        calls.append((left,right));a.c.steps+=1
        if mode=='support_lost':contacts.discard(frozenset(('blue_square','stand')))
        if mode=='stand_moved':state['stand']['pos'][1]+=.0011
    a.act=act
    return a,state,contacts,calls


def test_exactly_one_public_release_then_actual_support_without_exit():
    a,state,contacts,calls=prepared();r=segment.run_segment(a,'e17_c_confirm_released_upper_blue_222',{})
    assert calls==[('STILL','RELEASE')]and r['active_actions']==1 and r['local_completed']
    assert set(r)=={'local_completed','operations','active_actions'}


@pytest.mark.parametrize('fault',['old_boundary','wrong_tick','held','unsupported','outside','parameter'])
def test_unadmitted_or_not_actually_completed_state_cannot_pass(fault):
    a,state,contacts,calls=prepared();params={}
    if fault=='old_boundary':a._engineering_resume_checkpoint['source']['steps']=490
    elif fault=='wrong_tick':a._engineering_resume_checkpoint['source']['physics_ticks']=22311
    elif fault=='held':state['blue_square']['grasp'][1]=True
    elif fault=='unsupported':contacts.discard(frozenset(('blue_square','stand')))
    elif fault=='outside':state['blue_square']['pos'][0]+=.2
    else:params={'success':True}
    with pytest.raises(ToolExecutionError):segment.run_segment(a,'e17_c_confirm_released_upper_blue_222',params)
    assert not calls


@pytest.mark.parametrize('mode',['support_lost','stand_moved'])
def test_actual_post_release_failure_stays_failure(mode):
    a,state,contacts,calls=prepared(mode)
    with pytest.raises(ToolExecutionError):segment.run_segment(a,'e17_c_confirm_released_upper_blue_222',{})
    assert len(calls)==1
