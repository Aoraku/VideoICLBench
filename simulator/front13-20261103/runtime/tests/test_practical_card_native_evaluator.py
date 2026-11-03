"""Approximate cards must initialize their actual native evaluator before Kit."""
from pathlib import Path
from copy import deepcopy
import numpy as np
import pytest
from videoicl_isaaclab.realworld_scenes import load
from videoicl_isaaclab.realworld_evaluator_selector import create_evaluator
from videoicl_isaaclab.execution_design_practical_cards import configure_spec
from videoicl_isaaclab.realworld_clip_card_geometry import collision_entity

V=Path(__file__).resolve().parents[2]/'verification/task-design-revision-20261102'


@pytest.mark.parametrize('task',('E47','E48','E49','E50'))
@pytest.mark.parametrize('variant',tuple('ABC'))
def test_practical_tasks_construct_and_reset_actual_native_evaluator(task,variant):
    spec=load(task,variant,4201,V/'e38-e50-matrix/bindings-R.private.json',verify_files=False)
    configure_spec(spec);create_evaluator(spec).reset_episode()


def test_e50_clamp_entity_uses_labelled_one_mm_surface_and_keeps_xy():
    spec=load('E50','A',4201,V/'e38-e50-matrix/bindings-R.private.json',verify_files=False)
    obj=next(o for o in spec['objects']if o['id']=='card');original=collision_entity(obj)
    configure_spec(spec);actual=collision_entity(obj)
    assert np.array_equal(actual.vertices[:,:2],original.vertices[:,:2])
    assert np.ptp(actual.vertices[:,2])==pytest.approx(.001)
    assert np.array_equal(actual.triangles,original.triangles)
    unlabelled=deepcopy(obj);unlabelled.pop('engineering_practical_card')
    with pytest.raises(ValueError,match='fit differs'):collision_entity(unlabelled)
