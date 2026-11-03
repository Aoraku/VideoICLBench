"""Valid physical mistakes remain scoreable; inconsistent logs remain null."""
import pytest
from progress_v2_fixtures import progress_example
from videoicl_isaaclab.realworld_progress import score_progress
from videoicl_isaaclab.realworld_tool_evidence import ToolTaskEvaluator
from videoicl_isaaclab.realworld_semantic_checks import check_task


def note(key,start,end):
    return dict(key=key,step=start,release_step=end,tool='mallet',contact_impulse=.1)


def score(events,pending=()):
    obs,_=progress_example('E29','A');obs.update(strike_events=events,pending_strikes=list(pending))
    return score_progress('E29','A',obs)


@pytest.mark.parametrize('events,expected',[
    ([note(1,1,3),note(2,5,9),note(3,8,11)],12.5),
    ([note(2,1,3),note(1,1,5)],0),
    ([note(2,3,5),note(1,1,9)],0), # Native release order differs from onset order.
    ([note(1,1,3),note(2,3,5)],0), # Existing contract requires strict separation.
    ([note(1,1,3),note(1,5,7)],12.5), # A real duplicate note is a wrong note.
    ([note(1,1,3),note(3,5,7),note(2,9,11)],12.5),
])
def test_physical_sequence_mistakes_are_valid_failures(events,expected):
    result=score(events)
    assert result['progress_available'] and not result['missing_evidence']
    assert result['task_score_100']==expected
    assert not check_task('E29','A',dict(strike_events=events))['success']


def test_pending_overlap_blocks_incomplete_note_but_keeps_finished_prefix():
    assert score([note(1,1,3),note(2,5,10)],[dict(key=3,step=8)])['task_score_100']==12.5
    assert score([note(1,1,3)],[dict(key=2,step=5)])['task_score_100']==12.5


@pytest.mark.parametrize('events',[
    [note(1,1,3),note(1,1,3)], # Repeated record, not a later physical repeat.
    [note(1,1,5),note(1,3,7)], # One key cannot start again before releasing.
    [note(1,1,1)],
    [note(1,-1,3)],
    [note(1,1,9),note(2,3,5)], # Collector never appends decreasing release ticks.
    [note(1,1,3),dict(key=2,step=5)],
])
def test_inconsistent_or_incomplete_logs_remain_null(events):
    assert score(events)['task_score_100'] is None


def test_actual_collector_can_generate_well_formed_overlapping_records():
    # Drive the real contact-history collector, not a hand-sorted event list.
    evaluator=ToolTaskEvaluator.__new__(ToolTaskEvaluator)
    evaluator.tool={'actor':'mallet'};evaluator.semantic={'keys':{'1':'key1','2':'key2'}}
    evaluator.pending_strikes={};evaluator.strikes=[];evaluator.events=[];evaluator.dt=.004
    evaluator.held=lambda _:True
    for step,touching in [(1,{'key1'}),(2,{'key1','key2'}),(3,{'key1'}),(4,set())]:
        evaluator.steps=step;evaluator.force=lambda tool,key:1. if key in touching else 0.
        evaluator._strike_history()
    assert [x['key'] for x in evaluator.strikes]==[2,1]
    result=score(evaluator.strikes)
    assert result['progress_available'] and result['task_score_100']==0
