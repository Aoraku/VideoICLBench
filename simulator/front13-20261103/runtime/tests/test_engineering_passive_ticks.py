from types import SimpleNamespace
import pytest
from videoicl_isaaclab.execution_design_probe import pooled_author_class


def fixture(tmp_path):
    c=SimpleNamespace(steps=0,physics_ticks=31,_engineering_diagnostic_only=True,_engineering_checkpoint_readback_passed=True)
    pool=SimpleNamespace(controllers={'room':c},terminal={},physics_ticks=31)
    def tick():c.physics_ticks+=1;pool.physics_ticks+=1
    pool.tick=tick
    a=pooled_author_class(SimpleNamespace,pool,'room')()
    a.c=c;a.out=tmp_path;a.control_report={'engineering_reference_only':True}
    return a,c,pool


def test_passive_ticks_use_original_clock_without_public_actions(tmp_path):
    a,c,pool=fixture(tmp_path);events=[]
    r=a.engineering_passive_ticks(5,guard=lambda:events.append(c.physics_ticks))
    assert c.steps==0 and c.physics_ticks==36 and pool.physics_ticks==36
    assert len(events)==10 and r['actual_physics_ticks']==5 and r['public_actions_issued']==0


@pytest.mark.parametrize('mode',['unverified','sibling','active','failed','count'])
def test_passive_ticks_cannot_bypass_startup_or_active_actions(tmp_path,mode):
    a,c,pool=fixture(tmp_path)
    if mode=='unverified':c._engineering_checkpoint_readback_passed=False
    if mode=='sibling':pool.controllers['other']=c
    if mode=='active':c._public_action_in_flight=True
    if mode=='failed':a._engineering_failure_latched=True
    with pytest.raises(RuntimeError,match='idle verified'):a.engineering_passive_ticks(251 if mode=='count'else 10)
    assert c.physics_ticks==31 and c.steps==0
