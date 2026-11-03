import numpy as np
import pytest
from videoicl_isaaclab.public_gripper_contact_hold import parameters,brake


def step(force,active=None,anchor=None,closing=True,q=None,reference=None):
    ref=np.array([[.032,.033]])if reference is None else reference
    proposed=ref-.00004;v=np.full_like(ref,-.01)
    return brake(ref,proposed,v,ref if q is None else q,np.array([force]),
        ref.copy()if anchor is None else anchor,np.zeros_like(ref)if active is None else active,
        closing,.00005,np)


def test_first_finger_freezes_independently_while_other_continues():
    out,vel,anchor,mask=step([.1,0.])
    assert np.allclose(out,[[.032,.03296]])
    assert np.allclose(vel,[[0.,-.01]])
    assert mask.tolist()==[[True,False]]


def test_two_contacted_fingers_have_bounded_preload_and_no_measured_q_reset():
    anchor=np.array([[.032,.033]]);active=np.ones((1,2))
    out,vel,_,mask=brake(anchor,np.array([[.030,.031]]),np.array([[-.01,-.01]]),
        np.array([[.0318,.0328]]),np.array([[.2,.1]]),anchor,active,True,.00005,np)
    assert np.allclose(out,anchor-.00005)
    assert np.all(vel==0)and mask.all()


@pytest.mark.parametrize('closing,force,q',[(False,[.2,.2],None),(True,[0.,0.],None),(True,[.2,.2],np.array([[.0005,.0005]]))])
def test_release_empty_contact_and_closed_pusher_continue_normal_reference(closing,force,q):
    out,vel,_,mask=step(force,active=np.ones((1,2))if not closing else np.zeros((1,2)),closing=closing,q=q)
    assert not mask.any()
    assert np.allclose(out,[[.03196,.03296]])
    assert np.allclose(vel,-.01)


def test_contact_dropout_hysteresis_preserves_existing_contact_only():
    _,_,_,mask=step([.005,.005],active=np.array([[1.,0.]]))
    assert mask.tolist()==[[True,False]]


def test_default_off_and_parameters_reject_unbounded_or_unconfigured_preload():
    assert parameters({})is None
    assert parameters({'public_gripper_payload_contact_hold':False})is None
    with pytest.raises(ValueError):parameters({'public_gripper_payload_contact_hold':True})
    with pytest.raises(ValueError):parameters({'public_gripper_payload_contact_hold':True,'public_gripper_reference_speed_m_s':.01,'public_gripper_payload_preload_m':.001})



def test_speculative_positive_gap_force_cannot_freeze_the_reference():
    from videoicl_isaaclab.public_gripper_contact_hold import surface_contact_force
    buffers=(np.array([[10.],[.03],[.04]]),np.zeros((3,3)),np.zeros((3,3)),
             np.array([[.0009],[.00006],[-.000001]]),np.array([[3]]),np.array([[0]]))
    assert surface_contact_force(buffers,np)==pytest.approx(.04)


def test_only_movable_rigid_payload_pair_views_are_read():
    from types import SimpleNamespace as S
    from videoicl_isaaclab.public_gripper_contact_hold import payload_forces
    class Physics:
        calls=[]
        def create_rigid_contact_view(self,path,filter_patterns,max_contact_data_count):
            self.calls.append((path,filter_patterns))
            force=.1 if filter_patterns[0].endswith('finger1') else .2
            data=(np.array([[force]]),np.zeros((1,3)),np.zeros((1,3)),np.array([[-.000001]]),np.array([[1]]),np.array([[0]]))
            return S(sensor_count=1,filter_count=1,get_contact_data=lambda dt:data)
    physics=Physics();sensor=S(_physics_sim_view=physics)
    moving=S(cfg=S(spawn=S(rigid_props=S(kinematic_enabled=False))))
    fixed=S(cfg=S(spawn=S(rigid_props=S(kinematic_enabled=True))))
    scene=S(root_path='/Room',embodiment=S(fingers=['finger1','finger2']),objects={'card':moving,'fixed_prop':fixed},contacts={
        name:(sensor,['left_finger1','left_finger2'])for name in ['card','fixed_prop','clip/positive_jaw','table']})
    controller=S(scene=scene,grips={'left':0.},dt=.004)
    assert np.allclose(payload_forces(controller,'left',np.zeros((1,2)),np),[[.1,.2]])
    assert len(physics.calls)==2 and all(path=='/Room/Props/card'for path,_ in physics.calls)
    controller.grips['left']=.04
    assert not payload_forces(controller,'left',np.zeros((1,2)),np).any()



def test_missing_warm_cache_samples_do_not_reanchor_or_add_another_preload():
    anchor=np.array([[.032,.033]]);active=np.ones((1,2),dtype=bool);reference=anchor-.00005
    for force in ([0.,0.],)*5+([.1,.1],):
        bounded,velocity,saved,active=brake(reference,reference-.001,np.full_like(reference,-.01),np.full_like(reference,.039),np.array([force]),anchor,active,True,.00005,np)
        assert np.allclose(bounded,reference)and np.array_equal(saved,anchor)and active.all()
    _,_,_,released=brake(reference,reference+.001,np.full_like(reference,.01),np.full_like(reference,.039),np.array([[.1,.1]]),anchor,active,False,.00005,np)
    assert not released.any()
