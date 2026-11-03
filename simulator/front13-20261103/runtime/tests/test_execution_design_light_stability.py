"""User-approved small wobble: retain release/support/placement failures."""
from copy import deepcopy
import math
import numpy as np
import pytest
from videoicl_isaaclab.realworld_native_evidence import NativeTaskEvaluator
from videoicl_isaaclab.realworld_stability import for_evaluator,LIGHT,LEGACY


def scene(revised=True):
    spec=dict(id='E34',variant='B',zones=[],objects=[dict(id='spoon',size=[.08,.015,.009]),dict(id='tray',size=[.12,.1,.02])],
        semantic=dict(groups=dict(active=['spoon'],cutlery=['spoon']),container='tray',selected='spoon',
            handle_points=dict(spoon=[-.04,0,0]),compartment_bounds_local=dict(lower=[.005,.005,-.012],upper=[.098,.076,.019])))
    if revised:spec['execution_design']=dict(revision='embodied50-execution-v3-20261102')
    return spec


def replay(*,revised=True,wobble_degrees=2.,held=False,supported=True,outside=False,drift=False):
    e=NativeTaskEvaluator(scene(revised))
    for step in range(12):
        angle=math.radians(wobble_degrees*(1 if step%2 else-1));c,s=math.cos(angle),math.sin(angle)
        x=.08+(step*.02 if drift else(.0003 if step%2 else-.0003))
        state=dict(spoon=dict(pos=np.array([x,.04 if not outside else.30,.83]),mat=np.array([[1,0,0],[0,c,-s],[0,s,c]]),grasp=[held,False]),
            tray=dict(pos=np.array([0.,0.,.82]),mat=np.eye(3),grasp=[False,False]))
        contacts={frozenset(('tray','table'))}
        if supported:contacts.add(frozenset(('spoon','tray')))
        if held:contacts.add(frozenset(('spoon','left_finger1')))
        e.update(deepcopy(state),contacts,.1)
    return e.result()


def test_small_wobble_is_allowed_only_in_revised_task_scope():
    relaxed=replay();old=replay(revised=False)
    assert relaxed['success']and relaxed['stability_policy']['version']==LIGHT.version
    assert not old['success']and'stable'in old['failed_checks']


@pytest.mark.parametrize('change',[dict(held=True),dict(supported=False),dict(outside=True),dict(wobble_degrees=12.),dict(drift=True)])
def test_relaxing_small_wobble_does_not_accept_unfinished_placement(change):
    assert not replay(**change)['success']


def test_other_tasks_and_old_contracts_keep_the_existing_policy():
    from types import SimpleNamespace
    for task,revision in [('E25','embodied50-execution-v3-20261102'),('E38','embodied50-execution-v3-20261102'),('E34','old')]:
        assert for_evaluator(SimpleNamespace(spec=dict(id=task,execution_design=dict(revision=revision))))is LEGACY
