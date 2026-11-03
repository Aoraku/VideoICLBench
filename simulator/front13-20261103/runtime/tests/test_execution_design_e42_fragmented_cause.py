import numpy as np
from videoicl_isaaclab.realworld_tool_evidence import ToolTaskEvaluator
from videoicl_isaaclab.realworld_semantic_checks import check_task
from videoicl_isaaclab.execution_design_e42_push_cause import export


class EdgeHistory:
    def __init__(self):
        self.e=ToolTaskEvaluator.__new__(ToolTaskEvaluator)
        e=self.e;e.spec=dict(id='E42',execution_design=dict(revision='embodied50-execution-v3-20261102'));e.task='E42';e.progress_causal={};e.steps=0
        e.label=lambda name:name;e.state={'ball':dict(grasp=(False,False))};e.objects={'ball':{},'spatula':{},'other':{}}
        self.hand=False;self.other=False;self.source_contact=False;self.source_held=True
        e.hand_force=lambda name:float(self.hand)
        e.held=lambda actor:self.source_held if actor=='spatula'else self.other if actor=='other'else False
        e.force=lambda a,b:float(self.source_contact if b=='spatula'else self.other if b=='other'else False)
    def tick(self,x,*,edge=True,hand=False,other=False,wrong_edge=False,held=True,table=True,near_surface=True):
        self.hand,self.other,self.source_held=hand,other,held
        self.source_contact=edge or wrong_edge;self.e.steps+=1
        valid=edge and held and not hand and not other and table and near_surface
        sample=dict(step=self.e.steps,pos=[x,0.,.812])if valid else None
        self.e._delivery_chain('ball',sample,{},'push',{'spatula'},
            self.source_contact and held and (wrong_edge or not near_surface))
    def record(self):return self.e.progress_causal['ball']


def fragmented_drive(history,deltas):
    x=0.
    for dx in deltas:
        history.tick(x);x+=dx;history.tick(x);history.tick(x,edge=False)
    return x


def test_many_sub20mm_true_edge_fragments_form_real_net_drive():
    h=EdgeHistory();fragmented_drive(h,[.004]*8)
    r=h.record();assert r['delivery_chain_valid'] and r['transport_achieved']
    assert r['effective_push_valid_increments']==8 and r['effective_push_fragment_count']==8
    assert np.allclose(r['effective_push_net_delta_m'],[.032,0,0])


def test_back_and_forth_true_edge_motion_does_not_accumulate_distance():
    h=EdgeHistory();fragmented_drive(h,[.01,-.01]*8)
    assert np.linalg.norm(h.record()['effective_push_net_delta_m'])<1e-8
    assert not h.record()['delivery_chain_valid']


def test_rolling_motion_in_contact_gaps_is_never_added_to_driven_vector():
    h=EdgeHistory();h.tick(0);h.tick(.002)
    h.tick(.2,edge=False);h.tick(.21);h.tick(.212)
    assert np.allclose(h.record()['effective_push_net_delta_m'],[.004,0,0])
    assert not h.record()['delivery_chain_valid']


def test_true_edge_table_contact_flicker_preserves_cause_without_crediting_gap_motion():
    h=EdgeHistory();h.tick(0);h.tick(.015)
    h.tick(.05,table=False);h.tick(.08,table=False)
    h.tick(.10);h.tick(.11)
    assert np.allclose(h.record()['effective_push_net_delta_m'],[.025,0,0])
    assert h.record()['effective_push_valid_increments']==2
    assert h.record()['delivery_chain_valid']


def test_actual_lift_above_surface_band_invalidates_edge_chain():
    h=EdgeHistory();fragmented_drive(h,[.004]*8)
    assert h.record()['delivery_chain_valid']
    h.tick(.10,table=False,near_surface=False)
    assert not h.record()['delivery_chain_valid']
    h.tick(.12);h.tick(.125)
    assert np.allclose(h.record()['effective_push_net_delta_m'],[.005,0,0])
    assert not h.record()['delivery_chain_valid']


def test_hand_or_other_tool_then25mm_real_push_remains_invalid():
    for kind in ('hand','other'):
        h=EdgeHistory();fragmented_drive(h,[.004]*8)
        assert h.record()['delivery_chain_valid']
        h.tick(.2,edge=False,**{kind:True})
        for x in (.20,.21,.225,.235):h.tick(x)
        assert h.record()['direct_hand_intervention']is(kind=='hand')
        assert h.record()['other_held_tool_intervention']is(kind=='other')
        assert h.record()['effective_push_forbidden_intervention']
        assert not h.record()['delivery_chain_valid']
        assert not export(h.record())['no_forbidden_intervention']


def test_handle_contact_resets_drive_and_unheld_tool_never_drives():
    h=EdgeHistory();fragmented_drive(h,[.004]*8)
    h.tick(.2,edge=False,wrong_edge=True)
    assert not h.record()['delivery_chain_valid'] and h.record()['effective_push_valid_increments']==0
    for x in(.2,.25,.30):h.tick(x,held=False)
    assert not h.record()['delivery_chain_valid']
    assert np.allclose(h.record()['effective_push_net_delta_m'],[0,0,0])


def test_native_record_cannot_bypass_final_region_support_or_intervention():
    h=EdgeHistory();fragmented_drive(h,[.004]*8);record=export(h.record())
    observation=dict(released=True,stable=True,ball_ids=['a','b'],ball_regions={'a':'circle','b':'circle'},supported=['a','b'],native_fragmented_push_records={'a':record,'b':record})
    result=check_task('E42','A',observation)
    assert result['success']
    wrong=dict(observation,ball_regions={'a':'circle','b':None})
    assert not check_task('E42','A',wrong)['success']
    unsupported=dict(observation,supported=['a'])
    assert not check_task('E42','A',unsupported)['success']
    bad=dict(record,no_forbidden_intervention=False)
    assert not check_task('E42','A',dict(observation,native_fragmented_push_records={'a':bad,'b':record}))['success']

    assert not check_task('E42','A',dict(observation,released=False))['success']
    assert not check_task('E42','A',dict(observation,stable=False))['success']
