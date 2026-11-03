"""Shared hooks must be inert for tasks owned by other reference authors."""
from types import SimpleNamespace
import pytest
from videoicl_isaaclab.execution_design_e09_liftoff import piece_transport_steps


@pytest.mark.parametrize('task',['E14','E17','E20','E25'])
def test_e09_transport_hook_does_not_read_or_write_other_task_policy(task):
    policy=SimpleNamespace(task=task)
    with piece_transport_steps(policy,'some_piece'):
        assert vars(policy)=={'task':task}
    assert vars(policy)=={'task':task}


def test_non_e09_exception_does_not_add_transport_state():
    policy=SimpleNamespace(task='E17')
    with pytest.raises(RuntimeError,match='original failure'):
        with piece_transport_steps(policy,'piece'):raise RuntimeError('original failure')
    assert vars(policy)=={'task':'E17'}
