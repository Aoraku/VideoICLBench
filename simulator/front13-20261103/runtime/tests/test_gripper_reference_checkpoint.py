from copy import deepcopy
import numpy as np
import pytest
from test_engineering_checkpoint import controller,all_writes
from videoicl_isaaclab.engineering_checkpoint import capture,restore_startup,reseal


def enabled():
    c=controller();c.scene.embodiment.config['control']=dict(public_gripper_reference_speed_m_s=.01,public_gripper_reference_acceleration_m_s2=.05)
    c.ids['left']=([0,1],[0,1],0);c._public_gripper_limits=(.01,.05)
    c._public_gripper_reference={'left':np.array([[.031,.032]])};c._public_gripper_reference_velocity={'left':np.array([[-.004,-.004]])}
    return c


def test_new_native_reference_state_roundtrips_and_old_missing_state_clears_fresh_cache():
    source=enabled();source.steps=3;source.physics_ticks=500;p=capture(source,'slow-close')
    target=enabled();restore_startup(target,p);again=capture(target,'restored')
    assert again['controller']['gripper_reference']==p['controller']['gripper_reference']
    assert again['controller']['gripper_reference_velocity']==p['controller']['gripper_reference_velocity']
    old=deepcopy(p)
    for name in('gripper_reference','gripper_reference_velocity'):old['controller'].pop(name)
    target=enabled();restore_startup(target,reseal(old))
    assert target._public_gripper_reference==target._public_gripper_reference_velocity=={}


def test_new_profile_holding_cache_keeps_command_preload_instead_of_actual_finger_q():
    source=enabled();source.grips['left']=0.
    source.scene.robots['left'].data.joint_pos[:]=.017
    source.scene.robots['left'].data.joint_pos_target[:]=0.
    source._public_gripper_reference['left'][:]=0.
    source._public_gripper_reference_velocity['left'][:]=0.
    source.snapshot=lambda:({'object':{'grasp':[True,False]}},{frozenset(('object','left_finger1')),frozenset(('object','left_finger2'))})
    point=capture(source,'holding');target=enabled();restore_startup(target,point)
    assert np.all(target.scene.robots['left'].data.joint_pos==.017)
    assert np.all(target._public_gripper_reference['left']==0.)
    assert np.all(target.scene.robots['left'].data.joint_pos_target==0.)
    assert target.grips['left']==0.


@pytest.mark.parametrize('fault',('velocity','bounds','partial','actor','disabled_profile'))
def test_invalid_reference_cache_rejects_before_any_native_state_write(fault):
    source=enabled();p=capture(source,'slow-close');target=enabled()
    if fault=='velocity':p['controller']['gripper_reference_velocity']['left'][0][0]=.02
    elif fault=='bounds':p['controller']['gripper_reference']['left'][0][0]=.05
    elif fault=='partial':p['controller'].pop('gripper_reference_velocity')
    elif fault=='actor':p['controller']['gripper_reference']['alien']=[[.01,.01]]
    else:target.scene.embodiment.config.pop('control')
    with pytest.raises(ValueError):restore_startup(target,reseal(p))
    assert all_writes(target)==0


def test_contact_locked_native_checkpoint_restores_anchor_without_extra_preload():
    from videoicl_isaaclab.public_gripper_contact_hold import brake
    def contact_enabled():
        c=enabled();c._public_gripper_contact_preload=.00005
        c.scene.embodiment.config['control'].update(public_gripper_payload_contact_hold=True,public_gripper_payload_preload_m=.00005)
        c._public_gripper_contact_anchor={'left':np.array([[.03105,.03205]])}
        c._public_gripper_contact_active={'left':np.ones((1,2),dtype=bool)}
        c._public_gripper_reference_velocity['left'][:]=0.
        return c
    source=contact_enabled();source.grips['left']=0.
    point=capture(source,'contact-locked-held');target=contact_enabled()
    target._public_gripper_contact_anchor['left'][:]=.01
    restore_startup(target,point);again=capture(target,'restored-contact-lock')
    for key in('gripper_contact_anchor','gripper_contact_active','gripper_reference'):
        assert again['controller'][key]==point['controller'][key]
    ref=target._public_gripper_reference['left'];anchor=target._public_gripper_contact_anchor['left']
    bounded,_,_,_=brake(ref,ref-.001,np.full_like(ref,-.01),np.full_like(ref,.039),np.full_like(ref,.1),anchor,target._public_gripper_contact_active['left'],True,.00005,np)
    assert np.allclose(bounded,ref) # no second50um increment after continuation
