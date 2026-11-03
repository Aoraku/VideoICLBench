"""Actor-backed v3 cap role aliases, including incomplete physical evidence."""
from copy import deepcopy
from types import SimpleNamespace
import pytest
from videoicl_isaaclab.execution_design import REVISION_V3
from videoicl_isaaclab.realworld_progress_evidence import finish_observation
from videoicl_isaaclab.realworld_progress import score_progress


def evaluator(revision=REVISION_V3):
    colors=('yellow','white','red')
    names={'bottle_sprite':'sprite_bottle','bottle_water':'water_bottle','bottle_cola':'cola_bottle'}
    names.update({'actual_'+c:c for c in colors})
    status={name:dict(released=True,stable=True,supported=True,hold_seconds=.9)for name in names}
    e=SimpleNamespace(task='E19',spec=dict(execution_design=dict(revision=revision)),
        semantic=dict(caps={name:{}for name in names if name.startswith('actual_')}),
        objects={name:dict(role='movable')for name in names},label=names.__getitem__,
        progress_status_by_actor=status,progress_extra_status={},progress_initial_sealed=True)
    obs=dict(cap_for_bottle=dict(zip(('sprite_bottle','water_bottle','cola_bottle'),colors)),
        seated=['sprite_bottle','water_bottle','cola_bottle'],
        contacts=[['sprite_bottle','cap_yellow'],['water_bottle','cap_white'],['cola_bottle','cap_red']])
    return e,obs


def test_colour_roles_bind_actual_actor_without_changing_existing_evidence():
    e,o=evaluator();before=deepcopy(e.progress_status_by_actor)
    result=finish_observation(e,o)
    assert result['progress_physical']['cap_yellow']['actor_id']=='actual_yellow'
    assert result['progress_physical']['yellow']['actor_id']=='actual_yellow'
    assert e.progress_status_by_actor==before
    score=score_progress('E19','A',result)
    assert score['progress_available'] and score['task_score_100']==100


@pytest.mark.parametrize('flag',['released','stable','supported'])
def test_actual_unreleased_unstable_or_unsupported_cap_is_not_credited(flag):
    e,o=evaluator();e.progress_status_by_actor['actual_red'][flag]=False
    if flag=='supported':
        # No measured seating/contact can legitimately supplement support.
        del o['cap_for_bottle']['cola_bottle'];o['seated'].remove('cola_bottle')
        o['contacts'].remove(['cola_bottle','cap_red'])
    result=finish_observation(e,o)
    assert result['progress_physical']['cap_red'][flag]is False
    score=score_progress('E19','A',result)
    assert score['task_score_100']==pytest.approx(200/3)


def test_missing_physical_measurement_remains_unscored():
    e,o=evaluator();del e.progress_status_by_actor['actual_yellow']
    score=score_progress('E19','A',finish_observation(e,o))
    assert score['task_score_100']is None and score['missing_evidence']


def test_legacy_revision_is_unchanged():
    e,o=evaluator('old');result=finish_observation(e,o)
    assert 'cap_yellow'not in result['progress_physical']
    assert score_progress('E19','A',result)['task_score_100']is None


def test_conflicting_colour_identity_fails_explicitly():
    e,o=evaluator();e.objects['collision']={'role':'movable'}
    labels={name:e.label(name)for name in e.objects if name!='collision'}
    labels['collision']='yellow';e.label=labels.__getitem__
    e.progress_status_by_actor['collision']=dict(released=True,stable=True,supported=True,hold_seconds=1)
    with pytest.raises(ValueError,match='Ambiguous'):finish_observation(e,o)
