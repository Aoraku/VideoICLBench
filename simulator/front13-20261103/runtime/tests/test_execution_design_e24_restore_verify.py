from types import SimpleNamespace
import pytest
from videoicl_isaaclab.execution_design_e24_layout import verify_native_restore,VERSION


def author():
    state={name:dict(pos=[-.03,.365,.824],grasp=[False,False])for name in('lid','blue','green','red')}
    contacts={frozenset((name,'box'))for name in('blue','green','red')}
    c=SimpleNamespace(_engineering_diagnostic_only=True,_engineering_checkpoint_readback_passed=True,
        snapshot=lambda:(state,contacts),contact_forces={})
    a=SimpleNamespace(scene=SimpleNamespace(spec=dict(variant='A',seed=4201,e24_lid_initial_layout=dict(version=VERSION))),
        c=c,_engineering_resume_checkpoint=dict(context=dict(e24_layout_migration=dict(history_reconstructed=False))))
    return a,state,contacts


def test_declared_fixture_verification_reads_actual_pose_contacts_without_actions():
    a,state,contacts=author();result=verify_native_restore(a)
    assert result['local_completed']and result['actions']==0 and result['initialization_only']
    assert result['actual_lid_contacts']==[]
    assert not result['lid_picked_up_or_full_task_completed']


def test_missing_real_cup_support_is_never_filled():
    a,state,contacts=author();contacts.remove(frozenset(('red','box')))
    with pytest.raises(ValueError,match='support missing'):verify_native_restore(a)


def test_wrong_actual_lid_location_is_not_reclassified_as_migration():
    a,state,_=author();state['lid']['pos']=[.04,.315,.824]
    with pytest.raises(ValueError,match='startup XY'):verify_native_restore(a)
