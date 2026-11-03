"""Predicate tests only; these do not establish physical task feasibility."""
from copy import deepcopy
import numpy as np
import pytest
from videoicl_isaaclab.execution_design_evidence import ExecutionDesignEvaluator


def fixture(task='E01'):
    objects=[dict(id=n,size=[.01,.01,.01],kind='box') for n in ('cargo','box','lid','reference')]
    spec=dict(id=task,variant='A',objects=objects,zones=[dict(id='delivery',xy=[0.,0.],half_size=[.3,.3],support='table')],execution_design=dict(schema='execution-design-v1',delivery_actor='box',destination_zone='delivery',target_members=['cargo'],reference_objects=['reference'],unused_members=[],initial_preserved={},packages=[dict(container='box',lid='lid',members=['cargo'],lower=[-.1,-.1,0],upper=[.1,.1,.2],lid_local_center=[0,0,.21])],local_regions=[dict(id='inner',actor='box',candidates=['cargo'],members=['cargo'],lower=[-.1,-.1,0],upper=[.1,.1,.2])]))
    state={n:dict(pos=np.array(p,float),mat=np.eye(3),grasp=(False,False)) for n,p in dict(cargo=[0,0,.825],box=[0,0,.81],lid=[0,0,1.02],reference=[.5,0,.81]).items()}
    contacts={frozenset(x) for x in [('cargo','box'),('lid','box'),('box','table'),('reference','table')]}
    return spec,state,contacts


def run(e,state,contacts,n=6):
    if not e.initial_sealed:
        for _ in range(6): e.update(state,contacts,.1)
        if e.initial_diagnostics()['can_seal']:e.seal_initial()
    for _ in range(n):e.update(state,contacts,.1)
    return e.result()


def test_positive_and_stability():
    s,x,c=fixture();e=ExecutionDesignEvaluator(s)
    assert run(e,x,c,1)['process_score']==0
    r=run(e,x,c);assert r['strict_success'] and r['process_score']==100
    assert len(r['milestones'])==3 and r['milestones'][0]['contacts']
    assert not r['task_score_native_physics_verified']


def test_wrong_endpoint_retains_only_60():
    s,x,c=fixture();s['zones'][0]['xy']=[1,0]
    r=run(ExecutionDesignEvaluator(s),x,c)
    assert not r['strict_success'] and r['process_score']==60


def test_no_contact_and_unreleased_fail():
    for mode in ['contact','grasp','finger']:
        s,x,c=fixture();e=ExecutionDesignEvaluator(s);run(e,x,c)
        if mode=='contact':c.remove(frozenset(('cargo','box')))
        elif mode=='grasp':x['cargo']['grasp']=(True,False)
        else:c.add(frozenset(('cargo','left_finger1')))
        assert run(e,x,c)['process_score']==0


def test_missing_lid_limits_score():
    s,x,c=fixture();e=ExecutionDesignEvaluator(s);run(e,x,c)
    c.remove(frozenset(('lid','box')));c.add(frozenset(('lid','table')))
    x['lid']['pos']=np.array([.5,.3,.81])
    r=run(e,x,c)
    assert r['process_score']==35 and not r['strict_success']


def test_recursive_packaging_rejects_cycles_and_excludes_own_cap():
    s,x,c=fixture();e=ExecutionDesignEvaluator(s);run(e,x,c)
    outer=e.design['packages'][0]
    assert e.package_correct(outer)
    # The cap seals above its cavity and is intentionally not cavity contents.
    assert not e.contained('lid',dict(outer,actor='box'))
    e.design['packages'].append(dict(container='cargo',members=['box'],lower=[-.1]*3,upper=[.1]*3))
    assert not e.package_correct(outer)


def test_lost_cargo_revokes_milestones():
    s,x,c=fixture();e=ExecutionDesignEvaluator(s);assert run(e,x,c)['strict_success']
    x['cargo']['pos'][0]=.8
    r=run(e,x,c);assert r['process_score']==0 and len(r['milestones'])==3


def test_reference_move_then_restore_is_failure():
    s,x,c=fixture();e=ExecutionDesignEvaluator(s);run(e,x,c)
    x['reference']['pos'][0]+=.1;e.update(x,c,.1)
    x['reference']['pos'][0]-=.1
    assert run(e,x,c)['process_score']==0


def test_reference_grip_then_release_is_not_ignored():
    s,x,c=fixture();e=ExecutionDesignEvaluator(s);assert run(e,x,c)['strict_success']
    x['reference']['grasp']=(True,False);e.update(x,c,.1)
    x['reference']['grasp']=(False,False)
    assert run(e,x,c)['process_score']==0


def test_initial_chips_removal_then_restore_is_failure():
    s,x,c=fixture('E20');s['execution_design']['initial_preserved']={'inner':['cargo']}
    e=ExecutionDesignEvaluator(s);run(e,x,c)
    x['cargo']['pos'][0]=.5;e.update(x,c,.1);x['cargo']['pos'][0]=0
    assert run(e,x,c)['process_score']==0


def test_initial_chip_contact_dropout_is_not_removal_but_restarts_stability():
    s,x,c=fixture('E20');s['execution_design']['initial_preserved']={'inner':['cargo']}
    s['execution_design']['unused_supply_bounds']=dict(lower=[-1,-1,.8],upper=[1,1,1.2])
    e=ExecutionDesignEvaluator(s);assert run(e,x,c)['strict_success']
    dropped=c-{frozenset(('cargo','box'))}
    for _ in range(8):e.update(x,dropped,.1)
    assert not e.preservation_failed and e.hold_seconds==0
    e.update(x,c,.1)
    assert not e.result()['strict_success'] and e.hold_seconds<.5
    assert run(e,x,c)['strict_success']


def test_count_rule_cannot_use_same_color_from_wrong_batch():
    s,x,c=fixture('E20');e=ExecutionDesignEvaluator(s)
    e.objects['other_batch_red']=dict(identity='red_99',color_name='red')
    region=dict(id='inner',count=1,required_color='red')
    assert not e.region_correct(region,{'other_batch_red'})


def test_invalid_snapshot_fails_closed():
    s,x,c=fixture();e=ExecutionDesignEvaluator(s);run(e,x,c)
    x['cargo']['mat'][0,0]=float('nan');r=run(e,x,c)
    assert not r['history_valid'] and r['process_score'] is None
    assert r['task_score_100'] is None and r['engineering_score_100'] is None
    assert r['unscored'] and not r['progress_available']


def test_floating_contact_cluster_cannot_score():
    s,x,c=fixture()
    for n in ('cargo','box','lid'): x[n]['pos'][2]+=.3
    r=run(ExecutionDesignEvaluator(s),x,c)
    assert r['process_score'] is None and r['unscored']


def test_wrong_member_inside_detected():
    s,x,c=fixture();s['objects'].append(dict(id='wrong',size=[.01]*3,kind='box'))
    s['execution_design']['distractor_members']=['wrong']
    x['wrong']=dict(pos=np.array([.5,0,.81]),mat=np.eye(3),grasp=(False,False))
    c.add(frozenset(('wrong','table')));e=ExecutionDesignEvaluator(s);run(e,x,c)
    x['wrong']['pos']=np.array([.04,0,.86]);c.remove(frozenset(('wrong','table')));c.add(frozenset(('wrong','box')))
    assert run(e,x,c)['process_score']==0


def test_empty_and_unsealed_state_are_unscored():
    s,x,c=fixture();e=ExecutionDesignEvaluator(s)
    assert not e.initial_diagnostics()['native_evidence_valid']
    r=e.result()
    assert not r['native_evidence_valid'] and r['task_score_100'] is None
    assert not r['history_valid'] and r['unscored']
    e.update(x,c,.1);r=e.result()
    assert r['task_score_100'] is None and 'initial_state_not_sealed' in r['missing_evidence']


def test_valid_task_failure_is_scored_zero():
    s,x,c=fixture();e=ExecutionDesignEvaluator(s);run(e,x,c)
    x['cargo']['pos'][0]+=1
    r=run(e,x,c)
    assert r['history_valid'] and r['native_evidence_valid'] and r['scored']
    assert r['task_score_100']==r['process_score']==r['engineering_score_100']==0


def test_measured_static_fixture_support_root():
    s,x,c=fixture();s['fixtures']=[dict(type='box',xy=[0,0],z=.99,size=[.2,.2,.01])]
    for n in ('box','cargo','lid'):x[n]['pos'][2]+=.2
    c.remove(frozenset(('box','table')));c.add(frozenset(('box','fixture0')))
    e=ExecutionDesignEvaluator(s);r=run(e,x,c)
    assert r['process_score']==60 and not r['strict_success']
    c.remove(frozenset(('box','fixture0')))
    assert run(e,x,c)['process_score']==0


def test_initial_storage_requires_named_support_chain_only_before_seal():
    s,x,c=fixture()
    s['fixtures']=[dict(type='box',xy=[0,0],z=.99,size=[.2,.2,.01])]
    s['execution_design']['initial_storage']={n:'fixture0' for n in ('box','cargo','lid')}
    for n in ('box','cargo','lid'):x[n]['pos'][2]+=.2
    c.remove(frozenset(('box','table')));c.add(frozenset(('box','fixture0')))
    e=ExecutionDesignEvaluator(s)
    for _ in range(6):e.update(x,c,.1)
    assert e.initial_diagnostics()['can_seal']
    assert {'box','cargo','lid'}<=e.grounded('fixture0')
    # Cargo has no direct rack contact: the measured box contact carries it.
    assert frozenset(('cargo','fixture0')) not in c
    e.seal_initial()
    # Storage is a source precondition, not a permanent runtime constraint.
    for n in ('box','cargo','lid'):x[n]['pos'][2]-=.2
    c.remove(frozenset(('box','fixture0')));c.add(frozenset(('box','table')))
    assert run(e,x,c)['strict_success']
    # The identical final table placement must NOT qualify as an initial rack placement.
    fallen=ExecutionDesignEvaluator(s)
    for _ in range(6):fallen.update(x,c,.1)
    d=fallen.initial_diagnostics()
    assert not d['can_seal'] and not d['missing_required_groups']
    assert set(d['source_initial_failures'])=={'initial_storage:'+n+':fixture0' for n in ('box','cargo','lid')}
    assert fallen.result()['task_score_100'] is None


def test_world_supply_region_requires_its_actual_storage_support():
    s,x,c=fixture();s['fixtures']=[dict(type='box',xy=[.5,0],z=.99,size=[.2,.2,.01])]
    s['execution_design']['initial_storage']={'reference':'fixture0'}
    x['reference']['pos'][2]+=.2
    c.remove(frozenset(('reference','table')));c.add(frozenset(('reference','fixture0')))
    region=dict(actor=None,lower=[.4,-.1,.8],upper=[.6,.1,1.1],candidates=['reference'])
    e=ExecutionDesignEvaluator(s)
    for _ in range(6):e.update(x,c,.1)
    assert e.members(region)=={'reference'}
    # A table-supported actor inside the same broad XY/Z region is not returned to its rack.
    x['reference']['pos'][2]-=.2
    c.remove(frozenset(('reference','fixture0')));c.add(frozenset(('reference','table')))
    e.update(x,c,.1)
    assert e.members(region)==set()


def test_native_e17_packing_floor_contact_snapshot_replay():
    import json
    from pathlib import Path
    from videoicl_isaaclab.realworld_scenes import load
    from videoicl_isaaclab.execution_design_scenes import build_execution_scene
    root=Path(__file__).parents[1]
    captured=json.loads((Path(__file__).parent/'fixtures/execution_e17_initial_contacts.json').read_text())
    spec=build_execution_scene(load('E17','A',1,root/'configs/realworld_full50_bindings.json',verify_files=False))
    e=ExecutionDesignEvaluator(spec)
    contacts={frozenset(p) for p in captured['contacts']}
    e.update(captured['state'],contacts,.1)
    assert not e.initial_diagnostics()['source_initial_failures']
    assert set(spec['execution_design']['target_members']) <= e.grounded('fixture1')
    # One captured snapshot does not establish a new continuous stability history.
    assert not e.initial_diagnostics()['can_seal']
    for name in spec['execution_design']['target_members']:
        assert frozenset((name,'packing_box')) in contacts
        missing=contacts-{frozenset((name,'packing_box'))}
        e.update(captured['state'],missing,.1)
        assert name not in e.grounded('fixture1')
    # Counterfactual elevated pose with the original contacts must fail support.
    elevated=deepcopy(captured['state'])
    for name in spec['execution_design']['target_members']:elevated[name]['pos'][2]+=.1
    e.update(elevated,contacts,.1)
    assert not set(spec['execution_design']['target_members']) & e.grounded('fixture1')


def test_rotated_collision_floor_supported_but_vertical_wall_rejected():
    from videoicl_isaaclab.task_recipes import box,qaxis
    import math
    s,x,c=fixture();s['objects'][1]['size']=[.1,.1,.1]
    s['objects'][1]['collision_shapes']=[box([.08,.08,.003],[0,0,-.097],quat=qaxis(2,math.pi/4))]
    x['box']['pos'][2]=.9;x['cargo']['pos'][2]=.816
    # Isolate the actual compound-floor edge from local task containment.
    s['execution_design']['local_regions'][0]['actor']='reference'
    s['execution_design']['packages'][0]['members']=[]
    e=ExecutionDesignEvaluator(s);e.update(x,c,.1)
    assert 'cargo' in e.grounded('table')
    s['objects'][1]['collision_shapes'][0]['quat']=qaxis(0,math.pi/2)
    wall=ExecutionDesignEvaluator(s);wall.update(x,c,.1)
    assert 'cargo' not in wall.grounded('table')


def test_open_hinge_initial_support_and_invalid_joint_evidence():
    import math
    from videoicl_isaaclab.realworld_tool_expert import _axis_rotation
    for angle in (0,45,90,100):
        s,x,c=fixture();j=dict(type='revolute',parent='box',child='lid',axis='X',anchor0=[0,-.1,.2],anchor1=[0,-.1,-.01],limits=[0,100])
        s['joints']=[j];s['execution_design']['packages'][0]['hinge_joint_index']=0
        c.remove(frozenset(('lid','box')))
        rotation=_axis_rotation([1,0,0],math.radians(angle))
        x['lid']['mat']=rotation;x['lid']['pos']=x['box']['pos']+j['anchor0']-rotation@np.asarray(j['anchor1'])
        e=ExecutionDesignEvaluator(s)
        for _ in range(6):e.update(x,c,.1)
        assert e.initial_diagnostics()['can_seal']
        assert 'lid' in e.grounded() and e.measured_joint_support('lid')
        e.seal_initial()
        if angle:assert not run(e,x,c)['strict_success']
        # Coincident anchors alone must not authorize an illegal hinge angle.
        rotation=_axis_rotation([1,0,0],math.radians(120));x['lid']['mat']=rotation
        x['lid']['pos']=x['box']['pos']+j['anchor0']-rotation@np.asarray(j['anchor1'])
        bad=ExecutionDesignEvaluator(s)
        for _ in range(6):bad.update(x,c,.1)
        assert not bad.initial_diagnostics()['can_seal']
        # Legal rotation with broken anchor must also be rejected.
        x['lid']['mat']=np.eye(3);x['lid']['pos']=x['box']['pos']+np.array([.03,0,.21])
        bad=ExecutionDesignEvaluator(s)
        for _ in range(6):bad.update(x,c,.1)
        assert not bad.initial_diagnostics()['can_seal']


@pytest.mark.parametrize('revision',['embodied50-execution-v2-20261102','embodied50-execution-v3-20261102'])
def test_pinned_contract_revision_and_source_are_validated(revision):
    from videoicl_isaaclab.execution_design import source_sha256
    s,_,_=fixture();s['execution_design'].update(schema='execution-design-v2',revision=revision,source_sha256=source_sha256(revision))
    s['task_revision']=revision
    e=ExecutionDesignEvaluator(s)
    assert e.design['revision']==revision
    assert e.result()['execution_design_revision']==revision
    assert e.result()['execution_design_source_sha256']==source_sha256(revision)
    assert e.result()['task_score_100'] is None
    s['execution_design']['source_sha256']='0'*64
    with pytest.raises(ValueError,match='checksum'):ExecutionDesignEvaluator(s)
    s['execution_design']['source_sha256']=source_sha256(revision)
    s['task_revision']='wrong'
    with pytest.raises(ValueError,match='revision mismatch'):ExecutionDesignEvaluator(s)
    s['task_revision']=revision;s['execution_design']['revision']='future-unknown'
    with pytest.raises(ValueError,match='contract revision'):ExecutionDesignEvaluator(s)


def test_narrow_compound_cradle_requires_real_centered_vertical_support():
    s,state,contacts=fixture();objects={o['id']:o for o in s['objects']}
    objects['box']['size']=[.1,.1,.05]
    s['execution_design']['local_regions'][0].update(candidates=[],members=[])
    s['execution_design']['packages'][0]['members']=[]
    objects['box']['collision_shapes']=[dict(type='box',size=[.003,.024,.003],pos=[0,0,-.03],quat=[1,0,0,0])]
    objects['cargo']['size']=[.02,.02,.003]
    state['box']['pos']=np.array([0.,0.,.85]);state['cargo']['pos']=np.array([0.,0.,.826])
    e=ExecutionDesignEvaluator(s);e.update(state,contacts,.1)
    assert 'cargo'in e.grounded('table')
    absent={c for c in contacts if c!=frozenset(('cargo','box'))}
    e.update(state,absent,.1);assert 'cargo'not in e.grounded('table')
    e.update(state,contacts,.1);assert 'cargo'in e.grounded('table')
    # Mere edge overlap with a narrow rail is not centered support.
    state['cargo']['pos'][0]=.018;e.update(state,contacts,.1)
    assert 'cargo'not in e.grounded('table')
    state['cargo']['pos'][0]=0;state['cargo']['pos'][2]+=.03;e.update(state,contacts,.1)
    assert 'cargo'not in e.grounded('table')
    # A vertical side face with the same boolean parent contact is not a floor.
    state['cargo']['pos'][2]=.826
    objects['box']['collision_shapes'][0]['quat']=[2**-.5,0,2**-.5,0]
    e=ExecutionDesignEvaluator(s);e.update(state,contacts,.1)
    assert 'cargo'not in e.grounded('table')


def test_real_e17_narrow_cradle_frames_are_grounded_without_changing_contacts():
    import json
    from pathlib import Path
    d=json.loads((Path(__file__).parent/'fixtures/execution_e17_cradle_contacts.json').read_text())
    assert d['native_unchanged'] is True
    assert [f['tick']for f in d['native_frames']]==[477,531,600]
    for frame in d['native_frames']:
        e=ExecutionDesignEvaluator(d['spec'])
        e.update(frame['state'],{frozenset(p)for p in frame['contacts']},frame['dt'])
        assert e.grounded()==set(e.objects)
        assert e.history_valid
        # Three separated snapshots are not a continuous half-second proof.
        assert not e.initial_diagnostics()['can_seal']


def test_actual_e17_126_tick_cradle_window_seals_with_continuous_support():
    import json,gzip,hashlib
    from pathlib import Path
    raw=gzip.decompress((Path(__file__).parent/'fixtures/execution_e17_cradle_window.json.gz').read_bytes())
    assert hashlib.sha256(raw).hexdigest()=='d40ed0ab290b41266656086d36d17bca828dea99b012f32c9ec3c0833fffda72'
    d=json.loads(raw);frames=d['native_frames']
    assert [f['tick']for f in frames]==list(range(475,601))
    e=ExecutionDesignEvaluator(d['spec'])
    for frame in frames:e.update(frame['state'],{frozenset(p)for p in frame['contacts']},frame['dt'])
    assert e.hold_seconds>=.5 and e.initial_diagnostics()['can_seal']
    assert not e.initial_sealed  # Replaying evidence is not auto-accepting a live world.
    # Synthetic negative derived from the same window: a late actual support
    # dropout must invalidate continuous stability even when poses are steady.
    e=ExecutionDesignEvaluator(d['spec'])
    for frame in frames:
        contacts={frozenset(p)for p in frame['contacts']}
        if frame['tick']==597:contacts.discard(frozenset(('green_square','packing_box')))
        e.update(frame['state'],contacts,frame['dt'])
    assert e.hold_seconds<.5 and not e.initial_diagnostics()['can_seal']


def test_narrow_static_fixture_requires_centered_vertical_contact():
    s,state,contacts=fixture()
    s['fixtures']=[dict(type='box',xy=[.4,.3],z=.82,size=[.003,.024,.014])]
    obj=next(o for o in s['objects'] if o['id']=='cargo');obj['size']=[.02,.02,.003]
    state['cargo']['pos']=np.array([.4,.3,.837])
    contacts={c for c in contacts if 'cargo' not in c}|{frozenset(('cargo','fixture0'))}
    e=ExecutionDesignEvaluator(s);e.update(state,contacts,.1)
    assert 'cargo' in e.grounded('fixture0')
    for delta in ([.018,0,0],[0,0,.03]):
        bad=deepcopy(state);bad['cargo']['pos']+=np.asarray(delta)
        e.update(bad,contacts,.1)
        assert 'cargo' not in e.grounded('fixture0')
    e.update(state,{c for c in contacts if 'cargo' not in c},.1)
    assert 'cargo' not in e.grounded('fixture0')
