"""Pure rubric tests; these fixtures are not native physics validation."""
from copy import deepcopy
import pytest
from videoicl_isaaclab.realworld_progress import score_progress
from progress_v2_fixtures import progress_example

TASKS=[f'E{i:02d}' for i in range(1,51)]


def score(task,variant='A',mutate=None):
    o,initial=progress_example(task,variant)
    if mutate:mutate(o)
    return score_progress(task,variant,o,initial_observation=initial)


@pytest.mark.parametrize('task',TASKS)
@pytest.mark.parametrize('variant',['A','B','C'])
def test_all_fifty_source_variants_have_full_rubric_example(task,variant):
    r=score(task,variant)
    assert r['progress_available'],r
    assert r['task_score_100']==100,r
    assert 0<=r['failure_ceiling_100']<100
    assert r['raw_score_numerator']/r['raw_score_denominator']==100
    assert not r['native_physics_verified']


@pytest.mark.parametrize('task',TASKS)
@pytest.mark.parametrize('variant',['A','B','C'])
def test_missing_evidence_is_not_model_failure(task,variant):
    r=score_progress(task,variant,{})
    assert r['task_score_100'] is None and r['missing_evidence']
    assert not r['progress_available']


@pytest.mark.parametrize('task',TASKS)
def test_invalid_history_never_scored_even_when_observation_looks_complete(task):
    o,initial=progress_example(task,'A')
    r=score_progress(task,'A',o,initial_observation=initial,history_valid=False)
    assert r['task_score_100'] is None


def test_stack_requires_grounded_bottom_prefix_and_rollback():
    o,_=progress_example('E02','A')
    o['support_edges']=[['table','green'],['green','blue']]
    assert score_progress('E02','A',o)['task_score_100']==0
    o['support_edges']=[['table','red'],['red','green']]
    assert score_progress('E02','A',o)['task_score_100']==50
    o['support_edges']=[['table','red']]
    assert score_progress('E02','A',o)['task_score_100']==0


def test_relative_layout_bonus_depends_on_all_three_local_placements():
    r=score('E16',mutate=lambda o:o['progress_physical']['a'].update(stable=False))
    assert r['task_score_100']==40
    assert r['failure_ceiling_100']==60


def test_group_initially_satisfied_is_guard_not_free_reward():
    o,initial=progress_example('E09','A');initial['groups']=[o['groups'][0],[],[]]
    o['groups']=[o['groups'][0],o['groups'][1],[]]
    r=score_progress('E09','A',o,initial_observation=initial)
    assert r['required_change_count']==2 and r['task_score_100']==50
    o['groups'][0]=[]
    assert score_progress('E09','A',o,initial_observation=initial)['task_score_100']==0


def test_all_already_satisfied_dynamic_initial_state_is_unscored():
    for task in ['E07','E09']:
        o,_=progress_example(task,'A')
        r=score_progress(task,'A',o,initial_observation=deepcopy(o))
        assert r['task_score_100'] is None and r['missing_evidence']==['empty_required_change_set']


def test_chips_do_not_reward_initial_two_and_charge_wrong_chip_once():
    o,_=progress_example('E20','A');o['zone_members']=deepcopy(o['initial_zone_members']);o['supported']=['yellow0','blue0'];o['unmoved_unused']=[n for n in o['chip_colors'] if n not in o['supported']]
    assert score_progress('E20','A',o)['task_score_100']==0
    o['zone_members']['circle'].append('yellow1');o['supported'].append('yellow1');o['unmoved_unused'].remove('yellow1')
    assert score_progress('E20','A',o)['task_score_100']==25
    o['zone_members']['square'].append('yellow2');o['supported'].append('yellow2');o['unmoved_unused'].remove('yellow2')
    assert score_progress('E20','A',o)['task_score_100']==0


def test_wrong_first_placement_is_not_repaired_by_correct_terminal_layout():
    o,_=progress_example('E21','A');o['placement_events'][1]['object']='green'
    assert score_progress('E21','A',o)['task_score_100']==25


def test_bell_pending_extra_press_invalidates_only_that_side():
    o,_=progress_example('E26','A');o['bell_events'].append(dict(side='left',event='press',step=100,contact=True))
    assert score_progress('E26','A',o)['task_score_100']==10
    o,_=progress_example('E26','C');o['bell_events'].append(dict(side='right',event='press',step=100,contact=True))
    assert score_progress('E26','C',o)['task_score_100']==0


def test_extra_pending_note_loses_last_note_not_all_prior_music():
    o,_=progress_example('E29','C');o['pending_strikes']=[dict(key=1,step=100)]
    assert score_progress('E29','C',o)['task_score_100']==93.75


@pytest.mark.parametrize('task,remaining',[('E28',30),('E42',0),('E45',0),('E46',40),('E50',60)])
def test_earlier_legal_transport_cannot_justify_later_hand_delivery(task,remaining):
    o,_=progress_example(task,'A')
    for c in o['progress_causal'].values():c['delivery_chain_valid']=False
    assert score_progress(task,'A',o)['task_score_100']==remaining


def test_extra_ball_is_quantity_error_not_missing_evidence():
    o,_=progress_example('E36','B');o['in_box']=o['in_box']+['z'];o['supported_in_box']=o['supported_in_box']+['z'];o['progress_physical']['z']=dict(released=True,stable=True,supported=True)
    assert score_progress('E36','B',o)['task_score_100']==0


def test_extra_rear_flip_cancels_reveal_points_but_not_selected_delivery():
    o,_=progress_example('E47','A');o['flipped'].append('card3');o['face_down'].remove('card3')
    assert score_progress('E47','A',o)['task_score_100']==80


def test_card_same_slot_may_be_any_slot_but_not_sum_across_slots():
    o,_=progress_example('E48','B');o['slot_for_card']={'card1':'slot_other','card2':'slot_other'}
    assert score_progress('E48','B',o)['task_score_100']==100
    o['slot_for_card']['card2']='slot_2'
    assert score_progress('E48','B',o)['task_score_100']==60
    o['flipped'].append('card3')
    assert score_progress('E48','B',o)['task_score_100']==10


def test_c27_relationship_requires_both_local_objects():
    o,_=progress_example('E27','C');o['regions']['spoon']='right'
    assert score_progress('E27','C',o)['task_score_100']==20


def test_raw_score_does_not_read_actor_or_native_success_fields():
    o,_=progress_example('E05','A');o['placements']={};o['success']=True;o['score']=100
    assert score_progress('E05','A',o)['task_score_100']==0


def test_inputs_are_not_mutated():
    o,initial=progress_example('E07','A');before=deepcopy((o,initial))
    score_progress('E07','A',o,initial_observation=initial)
    assert (o,initial)==before


@pytest.mark.parametrize('task',TASKS)
@pytest.mark.parametrize('variant',['A','B','C'])
def test_witnessed_absence_of_achievements_is_numeric_zero(task,variant):
    o,initial=progress_example(task,variant)
    for state in o['progress_physical'].values():state.update(released=False,stable=False,supported=False)
    o.update(released=False,stable=False)
    for key in ['bell_events','strike_events','pending_strikes','flipped']:
        if key in o:o[key]=[]
    for item in o.get('progress_causal',{}).values():
        for key in list(item):item[key]=False
    if task=='E18':o['drawer_opened_for_access']=False
    if task=='E37':o['screw_progress']={k:False for k in o['screw_progress']}
    if task=='E43':o['launcher_moved']=True
    if task=='E50':o['card_flipped']=False
    r=score_progress(task,variant,o,initial_observation=initial)
    assert r['progress_available'],r
    assert r['task_score_100']==0,r


def test_measured_no_region_or_no_release_is_zero_not_missing():
    o,_=progress_example('E46','A');o['block_region']=None
    assert score_progress('E46','A',o)['task_score_100']==40
    o,_=progress_example('E50','A');o['card_tray']=None
    assert score_progress('E50','A',o)['task_score_100']==60
    o,_=progress_example('E43','A');o['release']=None;o['trajectory']=[]
    assert score_progress('E43','A',o)['task_score_100']==0
    o,_=progress_example('E24','A');o['lid_closed']=False;o['lid_close_step']=None
    assert score_progress('E24','A',o)['task_score_100']==75


def test_uninitialized_native_envelope_is_unscored_not_exception():
    r=score_progress('E05','A',dict(schema='videoicl-native-progress-evidence-v2',task='E05',variant='A',history_valid=False,observation=None,initial=dict(observation=None),object_status={}))
    assert r['task_score_100'] is None
    assert r['missing_evidence']==['history_invalid_or_untrusted']

def test_envelope_identity_cannot_be_relabelled():
    o,_=progress_example('E05','A')
    env=dict(schema='videoicl-native-progress-evidence-v2',task='E05',variant='B',history_valid=True,observation=o,object_status=o['progress_physical'])
    assert score_progress('E05','A',env)['missing_evidence']==['native_evidence_identity_mismatch']

def test_unthreaded_third_ring_does_not_erase_valid_post_prefix():
    o,_=progress_example('E38','A')
    o['bottom_to_top']=['blue','red','green'];o['threaded']=['red','green'];o['post_for_ring']={'red':'rightmost','green':'rightmost'}
    o['support_edges']=[['rightmost','red'],['red','green'],['table','blue']]
    assert score_progress('E38','A',o)['task_score_100']==pytest.approx(200/3)


def test_dynamic_native_envelope_requires_locked_initial_denominator():
    o,initial=progress_example('E07','A')
    env=dict(schema='videoicl-native-progress-evidence-v2',task='E07',variant='A',history_valid=True,observation=o,object_status=o['progress_physical'],initial=dict(observation=initial,object_status=initial['progress_physical'],sealed=False))
    assert score_progress('E07','A',env)['missing_evidence']==['initial_denominator_not_sealed']
    env['initial']['sealed']=True
    assert score_progress('E07','A',env)['task_score_100']==100


def test_separated_screw_does_not_add_unrequested_table_support_requirement():
    o,_=progress_example('E37','A');o['progress_physical']['left']['supported']=False
    assert score_progress('E37','A',o)['task_score_100']==100
