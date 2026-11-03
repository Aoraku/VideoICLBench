from videoicl_isaaclab.execution_design_e28_scoop import ScoopWitness,enabled,REVISION


def sample(w,step,**kw):
    args=dict(step=step,table_supported=True,held=True,hand_grasp=False,
        hand_contact=False,tool_contact=True,edge_under=True,relative_edge=-.02,
        food_bottom=.8,supported_on_blade=True)
    args.update(kw)
    return w.observe('food',**args)


def test_true_insertion_and_lift():
    w=ScoopWitness()
    assert not sample(w,1)
    assert not sample(w,2,relative_edge=-.01)
    assert sample(w,3,table_supported=False,food_bottom=.81,relative_edge=-.01)
    assert w.records['food']['insertion_m']==.01
    assert w.records['food']['entry_step']<w.records['food']['lift_step']


def test_hand_loading_never_establishes_entry():
    w=ScoopWitness()
    assert not sample(w,1,hand_grasp=True)
    assert not sample(w,2,table_supported=False,food_bottom=.88,hand_grasp=True)
    assert not sample(w,3,table_supported=False,food_bottom=.88)
    assert not w.records


def test_side_push_without_relative_insertion_does_not_count():
    w=ScoopWitness()
    for i in range(20):assert not sample(w,i,food_bottom=.8)
    assert not sample(w,21,table_supported=False,food_bottom=.82)


def test_air_drop_or_top_contact_does_not_count():
    for changes in ({'table_supported':False},{'edge_under':False}):
        w=ScoopWitness()
        assert not sample(w,1,**changes)
        assert not sample(w,2,relative_edge=.01,**changes)
        assert not sample(w,3,table_supported=False,food_bottom=.82)


def test_hand_assistance_cannot_lift_food():
    w=ScoopWitness();sample(w,1);sample(w,2,relative_edge=-.01)
    assert not sample(w,3,table_supported=False,food_bottom=.82,hand_contact=True)
    assert not sample(w,4,table_supported=False,food_bottom=.82)


def test_lost_tool_grip_requires_new_entry():
    w=ScoopWitness();sample(w,1);sample(w,2,relative_edge=-.01)
    assert not sample(w,3,held=False)
    assert not sample(w,4,table_supported=False,food_bottom=.82)


def test_stabilizing_hand_on_table_allowed_but_real_blade_required():
    w=ScoopWitness();sample(w,1,hand_contact=True);sample(w,2,relative_edge=-.01,hand_contact=True)
    assert not sample(w,3,table_supported=False,food_bottom=.82,supported_on_blade=False)
    assert sample(w,4,table_supported=False,food_bottom=.82)


def test_scoped_to_e28_v3():
    assert enabled({'id':'E28','execution_design':{'revision':REVISION}})
    assert not enabled({'id':'E46','execution_design':{'revision':REVISION}})
    assert not enabled({'id':'E28'})


def test_historical_scoop_does_not_license_later_hand_loading():
    w=ScoopWitness();sample(w,1);sample(w,2,relative_edge=-.01)
    assert sample(w,3,table_supported=False,food_bottom=.82)
    assert not sample(w,4,hand_grasp=True,table_supported=False,food_bottom=.82)
    assert not sample(w,5,table_supported=False,food_bottom=.82)
    assert not w.records


def test_actual_collector_blocks_hand_loaded_transport_credit():
    from pathlib import Path
    import numpy as np
    from videoicl_isaaclab.realworld_scenes import load
    from videoicl_isaaclab.realworld_tool_evidence import ToolTaskEvaluator
    from videoicl_isaaclab.realworld_tool_expert import _push_rotation
    spec=load('E28','A',4201,Path(__file__).parents[1]/'configs/realworld_full50_bindings.json',verify_files=False)
    spec['execution_design']={'revision':REVISION}
    e=ToolTaskEvaluator(spec);tool=e.tool;name=e.group('cargo')[0]
    r=_push_rotation(tool['support_normal_local'],[1,0,0],[1,0,0])
    e.state={n:dict(pos=np.zeros(3),mat=np.eye(3),grasp=(False,False))for n in e.objects}
    e.state[tool['actor']]=dict(pos=np.array([0,0,.9]),mat=r,grasp=(False,True))
    normal=np.asarray(tool['support_normal_local'],float);normal/=np.linalg.norm(normal)
    local=np.asarray(tool['working_local'],float)
    local+=normal*(tool['support_plane_offset']+e.objects[name]['size'][2]-float(normal@local))
    e.forces={frozenset((name,tool['actor'])):1.};e.contacts=set(e.forces)
    for step in range(5):
        e.steps=step
        e.state[tool['actor']]['pos'][0]=step*.02
        e.state[name]['pos']=e.state[tool['actor']]['pos']+r@local
        e._spatula_history([name])
    assert not e.transports
    assert not e.progress_causal[e.label(name)]['transport_achieved']
    assert not e.progress_causal[e.label(name)]['delivery_chain_valid']
    # The exact same measured blade carry remains allowed by the legacy
    # transport collector; the new gate is confined to E28 v3.
    e.e28_scoop=None
    for step in range(5,10):
        e.steps=step;e.state[tool['actor']]['pos'][0]=step*.02
        e.state[name]['pos']=e.state[tool['actor']]['pos']+r@local
        e._spatula_history([name])
    assert e.progress_causal[e.label(name)]['transport_achieved']


def test_hand_loaded_negative_has_distinct_required_identity_and_route(monkeypatch):
    from pathlib import Path
    from copy import deepcopy
    from types import SimpleNamespace
    from videoicl_isaaclab.realworld_scenes import load
    from videoicl_isaaclab.execution_design_inputs import apply_execution_inputs
    from videoicl_isaaclab.execution_design_back25_acceptance import requirements
    from videoicl_isaaclab.execution_design_back25_negative import negative_plan,Back25NegativeAuthor
    from videoicl_isaaclab.execution_design_reference import reference_capability
    from videoicl_isaaclab import realworld_tool_expert
    s=apply_execution_inputs(load('E28','A',0,Path(__file__).parents[1]/'configs/realworld_full50_bindings.json',verify_files=False),condition='I',seed=4201,revision=REVISION)
    before=deepcopy(s);control='hand_loaded_spatula_without_scoop'
    plan,delta=negative_plan(s,control)
    assert s==before and plan['semantic']==s['semantic'] and plan['objects']==s['objects']
    rows={r['control']:r for r in requirements(s)}
    assert rows[control]['applicability']=='required'
    assert rows[control]['witness_key']!=rows['wrong_rule']['witness_key']
    assert reference_capability('E28',control)['implemented']
    assert delta['negative_condition_observed'] is None
    scene=SimpleNamespace(spec=s);a=SimpleNamespace(scene=scene,c=SimpleNamespace(scene=scene,steps=0),release_generated=lambda _:None)
    def disallowed():raise AssertionError('Must execute real hand-loading author, not direct placement')
    a.solve_generated=disallowed
    class Spy:
        def __init__(self,author):self.a=author
        def _handload_spatula_transport(self):
            assert self.a.c.scene is scene and self.a.scene is not scene
            assert self.a.scene.spec['semantic']==scene.spec['semantic']
            self.a.c.steps+=3
    monkeypatch.setattr(realworld_tool_expert,'ToolAuthor',Spy)
    result=Back25NegativeAuthor(a,control).solve_negative()
    assert a.scene is scene and a.c.scene is scene and s==before
    assert result['actions']==3 and result['negative_condition_observed'] is None


def inserted_witness():
    w=ScoopWitness();sample(w,1);sample(w,2,relative_edge=-.01)
    return w


def test_initial_lift_contact_dropout_preserves_history_without_credit():
    w=inserted_witness()
    for tick in (3,4):
        assert not sample(w,tick,table_supported=False,tool_contact=False,
            relative_edge=-.0099,food_bottom=.8006,supported_on_blade=False,blade_gap_m=.00026)
        assert 'food' in w.pending and not w.records
    # Credit still requires recovered actual blade contact and >=6mm lift.
    assert sample(w,5,table_supported=False,relative_edge=-.0099,food_bottom=.808)
    assert w.records['food']['entry_step']==1


def test_contact_dropout_never_licenses_airborne_hand_or_discontinuous_entry():
    invalid=[dict(hand_contact=True),dict(hand_grasp=True),dict(held=False),
        dict(edge_under=False),dict(food_bottom=.804),dict(food_bottom=.798),
        dict(blade_gap_m=.002),dict(blade_gap_m=None),dict(relative_edge=-.006)]
    for change in invalid:
        w=inserted_witness()
        kw=dict(table_supported=False,tool_contact=False,relative_edge=-.0099,
            food_bottom=.8006,supported_on_blade=False,blade_gap_m=.00026);kw.update(change)
        assert not sample(w,3,**kw)
        assert not w.pending and not w.records
        assert not sample(w,4,table_supported=False,food_bottom=.808)
    w=inserted_witness()
    assert not sample(w,4,table_supported=False,tool_contact=False,
        relative_edge=-.0099,food_bottom=.8006,supported_on_blade=False,blade_gap_m=.00026)
    assert not w.pending


def test_three_missing_contacts_require_fresh_real_insertion():
    w=inserted_witness()
    for tick in (3,4,5):
        assert not sample(w,tick,table_supported=False,tool_contact=False,
            relative_edge=-.0099,food_bottom=.8006,supported_on_blade=False,blade_gap_m=.00026)
    assert not w.pending
    assert not sample(w,6,table_supported=False,food_bottom=.808)


def test_successful_lift_still_invalidated_by_later_hand_contact():
    w=inserted_witness()
    assert not sample(w,3,table_supported=False,tool_contact=False,
        relative_edge=-.0099,food_bottom=.8006,supported_on_blade=False,blade_gap_m=.00026)
    assert sample(w,4,table_supported=False,relative_edge=-.0099,food_bottom=.808)
    assert not sample(w,5,table_supported=False,food_bottom=.865,hand_contact=True)
    assert not w.records and not w.pending


def test_measured_dropout_grace_not_enabled_for_shared_e46_collector():
    import numpy as np
    from types import SimpleNamespace
    tool=dict(actor='spatula',support_normal_local=[0,0,1],withdraw_local=[-1,0,0],
        edge_segment=[[0,-.01,0],[0,.01,0]],support_plane_offset=0.)
    e=SimpleNamespace(tool=tool,steps=3,state={
        'spatula':dict(pos=np.array([0.,0.,.8]),mat=np.eye(3),grasp=[True,False]),
        'food':dict(pos=np.array([0.,0.,.8106]),mat=np.eye(3),grasp=[False,False])},
        objects={'food':{'size':[.01,.01,.01]}},
        bounds=lambda n:(np.array([0.,0.,.8106]),np.array([.01,.01,.01])),
        force=lambda a,b:0.,held=lambda n:True,hand_force=lambda n:0.)
    for task,kept in [('E28',True),('E46',False)]:
        e.spec={'id':task,'execution_design':{'revision':REVISION}}
        w=ScoopWitness();sample(w,1,relative_edge=-.01);sample(w,2,relative_edge=0.)
        assert not w.measured(e,'food',False)
        assert bool(w.pending)==kept
        assert not w.records
