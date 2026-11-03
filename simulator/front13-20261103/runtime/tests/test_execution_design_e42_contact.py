from types import SimpleNamespace
import numpy as np
import pytest
from videoicl_isaaclab.execution_design_e42_contact import seek_edge_contact
from videoicl_isaaclab.realworld_tool_expert import ToolExecutionError


class PhysicalStub:
    task='E42'
    def __init__(self, contact_after=5, table=True):
        self.a=SimpleNamespace(control_report={'engineering_reference_only':True})
        self.actions=[];self.contact_after=contact_after;self.table=table
        self.edge=np.array([0.,0.,.811]);self.ball=np.array([.015,.015,.812])
    def point(self,ref):return self.edge.copy()
    def snapshot(self):return {'ball':{'pos':self.ball.copy()}},set()
    def contact(self,name,other):
        return self.table if other=='table' else len(self.actions)>=self.contact_after
    def act(self,side,token,mm):
        self.actions.append((token,mm))
        axis,sign={'FWD':(0,1),'BACK':(0,-1),'LEFT':(1,1),'RIGHT':(1,-1),'UP':(2,1),'DOWN':(2,-1)}[token]
        self.edge[axis]+=sign*mm*.001
        self.edge[2]+=.0006*(-1)**len(self.actions)


def run(a,guard=lambda:None):
    return seek_edge_contact(a,'right',{'actor':'spatula'},'ball',np.array([.14,.13,.812]),guard)


def test_contact_stops_without_submillimetre_pose_convergence():
    a=PhysicalStub();run(a)
    assert len(a.actions)==5
    assert all(0<mm<=2 for _,mm in a.actions)


def test_absent_contact_is_bounded_and_never_claimed_success():
    a=PhysicalStub(contact_after=10000)
    with pytest.raises(ToolExecutionError,match='No actual blade-edge contact'):run(a)
    assert len(a.actions)<=27


def test_lost_table_support_and_grasp_fail_before_more_actions():
    a=PhysicalStub(table=False)
    with pytest.raises(ToolExecutionError,match='table support'):run(a)
    assert not a.actions
    def lost_grasp():raise ToolExecutionError('lost grasp')
    a=PhysicalStub()
    with pytest.raises(ToolExecutionError,match='lost grasp'):run(a,lost_grasp)
    assert not a.actions


def test_formal_mode_cannot_invoke_reference_contact_seek():
    a=PhysicalStub();a.a.control_report={}
    with pytest.raises(ToolExecutionError,match='isolated'):run(a)


def test_native_transient_true_edge_ends_seek_even_after_settle_separates():
    a=PhysicalStub(contact_after=10000);record={}
    a.c=SimpleNamespace(steps=0,evaluator=SimpleNamespace(progress_causal={'ball':record},label=lambda n:n))
    act=a.act
    def transient(side,token,mm):
        act(side,token,mm);a.c.steps+=1
        if a.c.steps==3:record.update(effective_push_valid_increments=12,effective_push_fragment_count=4)
    a.act=transient;run(a)
    assert a.c.steps==3 and not a.contact('ball','spatula')
    assert a._engineering_recent_edge_contacts['ball']['counters']==(12,4)


def test_native_forbidden_intervention_cannot_create_recent_contact():
    from videoicl_isaaclab.execution_design_e42_contact import native_edge_progress,remember_native_contact
    a=PhysicalStub();a.c=SimpleNamespace(steps=0,evaluator=SimpleNamespace(label=lambda n:n,
        progress_causal={'ball':dict(effective_push_forbidden_intervention=True,effective_push_valid_increments=999)}))
    assert native_edge_progress(a,'ball')is None
    assert not remember_native_contact(a,{'actor':'spatula'},'ball',(0,0))
