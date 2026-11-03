"""A sustained physical key contact is one pending strike, never repeated notes."""
from videoicl_isaaclab.realworld_tool_evidence import ToolTaskEvaluator


def collector():
    e=ToolTaskEvaluator.__new__(ToolTaskEvaluator)
    e.tool={'actor':'mallet'};e.semantic={'keys':{'1':'key1'}}
    e.pending_strikes={};e.strikes=[];e.events=[];e.dt=.004;e.held=lambda _:True
    return e


def advance(e,step,touching):
    e.steps=step;e.force=lambda tool,key:1. if touching else 0.
    e._strike_history()


def test_sustained_contact_only_counts_after_actual_separation():
    e=collector()
    for step in range(1,101):advance(e,step,True)
    assert e.strikes==[] and len(e.pending_strikes)==1
    pending=next(iter(e.pending_strikes.values()))
    assert pending['step']==1 and pending['key']==1 and pending['contact_impulse']>0
    advance(e,101,False)
    assert len(e.strikes)==1 and not e.pending_strikes
    assert e.strikes[0]['step']==1 and e.strikes[0]['release_step']==101
    for step in range(102,202):advance(e,step,False)
    assert len(e.strikes)==1
    for step in range(202,302):advance(e,step,True)
    assert len(e.strikes)==1 and len(e.pending_strikes)==1
    advance(e,302,False)
    assert len(e.strikes)==2 and not e.pending_strikes
    assert e.strikes[1]['step']==202 and e.strikes[1]['release_step']==302
