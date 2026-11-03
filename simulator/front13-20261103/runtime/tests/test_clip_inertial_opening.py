"""Force-driven opening can peak after release; passive contacts do not count."""
import pytest
from videoicl_isaaclab.realworld_semantic_checks import _clip_record
from videoicl_isaaclab.realworld_tool_evidence import ToolTaskEvaluator


def record(gaps=(.001,.010,.011,.003),forces=(0.,1.,0.,0.)):
    samples=[dict(step=i,jaw_gap_m=g,joint_pos=g,handle_contact_force=f) for i,(g,f) in enumerate(zip(gaps,forces))]
    samples[-1].update(handles_released=True,left_jaw_contact_force=1.,right_jaw_contact_force=1.,edge_between_jaws=True)
    return dict(clip_id='clip',samples=samples)


def test_inertial_peak_after_driven_opening_accepts_actual_released_clamp():
    assert _clip_record(record())
    assert _clip_record(record(gaps=(.001,.010,.009,.003)))
    assert _clip_record(record(gaps=(.001,.010,.011,.0101)))


@pytest.mark.parametrize('gaps,forces',[
    ((.001,.010,.011,.003),(0.,0.,0.,0.)), # Entirely passive opening.
    ((.001,.010,.011,.003),(1.,0.,0.,0.)), # Force before motion is not force-driven motion.
    ((.001,.010,.009,.003),(0.,0.,1.,0.)), # Force only while closing.
    ((.001,.0019,.002,.001),(0.,1.,0.,0.)), # Insufficient driven opening.
    ((.001,.010,.011,.0106),(0.,1.,0.,0.)), # Insufficient released closure.
])
def test_opening_and_closing_thresholds_and_force_causality_remain(gaps,forces):
    assert not _clip_record(record(gaps,forces))


@pytest.mark.parametrize('field,value',[('handles_released',False),('handle_contact_force',1.),('left_jaw_contact_force',0.),('right_jaw_contact_force',0.),('edge_between_jaws',False)])
def test_final_physical_clamp_guards_remain(field,value):
    r=record();r['samples'][-1][field]=value
    assert not _clip_record(r)


@pytest.mark.parametrize('forces,expected',[(None,True),((0.,0.,0.,0.),False),((1.,0.,0.,0.),False)])
def test_native_collector_records_inertial_peak_after_release(forces,expected):
    e=ToolTaskEvaluator.__new__(ToolTaskEvaluator);e.task='E40';e.steps=0
    clip=dict(mechanism='clip',left={'contact_body':'left'},right={'contact_body':'right'},handle_contacts=['handle'])
    e.clips={'clip':clip};e.clip_records={};e.clip_samples={};e.clip_driven={}
    for s in (record() if forces is None else record(forces=forces))['samples']:
        e.steps=s['step'];e.joint=lambda _:s['joint_pos'];e.hand_force=lambda _:s['handle_contact_force']
        e._jaw_geometry=lambda clip,point:(s['jaw_gap_m'],s.get('edge_between_jaws',False))
        e.force=lambda body,target:s.get('left_jaw_contact_force' if body=='left' else 'right_jaw_contact_force',0.)
        e._clip_history({'circle':('tray',None)})
    assert ('circle' in e.clip_records) is expected
    if expected:assert e.clip_driven[('clip','circle')]


def slow_record(mode='valid'):
    samples=[]
    for i in range(56):
        gap=.001+i*.00005
        force=0. if i==0 else 1.
        joint=i*.000001
        if mode=='passive':force=0.
        if mode=='dropouts' and i%8==0:force=0.
        if mode=='gap_only':joint=0.
        if mode=='joint_only':gap=.001
        if mode=='oscillation':gap=.001+(i%10)*.00005;joint=(i%10)*.000001
        samples.append(dict(step=i,jaw_gap_m=gap,joint_pos=joint,handle_contact_force=force))
    samples.append(dict(step=56,jaw_gap_m=.0038,joint_pos=.000056,handle_contact_force=0.))
    samples.append(dict(step=57,jaw_gap_m=.0025,joint_pos=.00004,handle_contact_force=0.,handles_released=True,left_jaw_contact_force=1.,right_jaw_contact_force=1.,edge_between_jaws=True))
    return dict(clip_id='clip',samples=samples)


@pytest.mark.parametrize('mode,expected',[('valid',True),('passive',False),('dropouts',False),('gap_only',False),('joint_only',False),('oscillation',False)])
def test_slow_opening_requires_net_gap_and_joint_motion_under_continuous_force(mode,expected):
    r=slow_record(mode)
    assert _clip_record(r) is expected
    e=ToolTaskEvaluator.__new__(ToolTaskEvaluator);e.task='E40'
    clip=dict(mechanism='clip',left={'contact_body':'left'},right={'contact_body':'right'},handle_contacts=['handle'])
    e.clips={'clip':clip};e.clip_records={};e.clip_samples={};e.clip_driven={}
    for s in r['samples']:
        e.steps=s['step'];e.joint=lambda _:s['joint_pos'];e.hand_force=lambda _:s['handle_contact_force']
        e._jaw_geometry=lambda clip,point:(s['jaw_gap_m'],s.get('edge_between_jaws',False))
        e.force=lambda body,target:s.get('left_jaw_contact_force' if body=='left' else 'right_jaw_contact_force',0.)
        e._clip_history({'circle':('tray',None)})
    assert ('circle' in e.clip_records) is expected


@pytest.mark.parametrize('task',['E40','E50'])
@pytest.mark.parametrize('field',['joint_pos','jaw_gap_m','handle_contact_force'])
@pytest.mark.parametrize('bad',['missing',float('nan')])
def test_missing_nested_measured_clip_fields_remain_unscored(task,field,bad):
    from progress_v2_fixtures import progress_example
    from videoicl_isaaclab.realworld_progress import score_progress
    obs,_=progress_example(task,'A')
    trace=(obs['clip_records']['circle'] if task=='E40' else obs['clip_sequence'])
    if bad=='missing':del trace['samples'][1][field]
    else:trace['samples'][1][field]=bad
    assert score_progress(task,'A',obs)['task_score_100'] is None


def test_unestablished_clip_is_still_a_scored_zero_not_missing_history():
    from progress_v2_fixtures import progress_example
    from videoicl_isaaclab.realworld_progress import score_progress
    obs,_=progress_example('E40','A');obs.update(clipped_markers=[],clip_records={})
    assert score_progress('E40','A',obs)['task_score_100']==0


def test_forced_closure_followed_by_release_without_further_closure_is_rejected():
    assert not _clip_record(record(gaps=(.001,.010,.003,.003),forces=(0.,1.,1.,0.)))
    # There is still >.5mm measured spring closure after the final forced frame.
    assert _clip_record(record(gaps=(.001,.010,.004,.003),forces=(0.,1.,1.,0.)))


def test_unmeasured_gap_at_release_cannot_prove_spring_closure():
    r=record();r['samples'][-1]['step']+=2
    assert not _clip_record(r)
