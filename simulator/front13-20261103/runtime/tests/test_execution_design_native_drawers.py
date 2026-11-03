"""E30 v3 half-open inputs and contact history, CPU fixtures only."""
from copy import deepcopy
from types import SimpleNamespace
import importlib.util
from pathlib import Path
import pytest
from videoicl_isaaclab.execution_design import REVISION_V3
from videoicl_isaaclab.execution_design_inputs import apply_execution_inputs
from videoicl_isaaclab.execution_design_drawers import initial_displacements,matches_initial,SCHEMA
from videoicl_isaaclab.realworld_scenes import load
from videoicl_isaaclab.realworld_mechanism_evidence import MechanismTaskEvaluator
from videoicl_isaaclab.realworld_mechanism_expert import _Author
from videoicl_isaaclab.realworld_progress_evidence import seal_initial
source=Path(__file__).resolve().parents[3]/'isaaclab_tasks/tests/test_realworld_mechanism_evidence.py'
specmod=importlib.util.spec_from_file_location('drawer_fixtures',source);f=importlib.util.module_from_spec(specmod);specmod.loader.exec_module(f)
BINDINGS=Path(__file__).parents[1]/'configs/realworld_full50_bindings.json'

def spec(variant='A',seed=4201):
    s=f.mechanism_spec('E30',variant)
    values={side:(.007,.009,.011)[(seed+i)%3]for i,side in enumerate(('lower','upper'))}
    s['execution_design']=dict(revision=REVISION_V3,condition='I')
    s['semantic']['execution_design_drawer_input']=dict(schema=SCHEMA,normalized_displacements=values)
    s['mechanisms']=[dict(id='machine',initial_joint_positions={side+'_joint':q for side,q in values.items()})]
    return s

def start(s):
    e=MechanismTaskEvaluator(s);state=f.state_for(s);q=initial_displacements(s)
    f.settle(e,state,positions=q);seal_initial(e)
    assert e.initial_valid and e.progress_initial_sealed
    assert not e.result()['success']
    return e,state,q

def finish(e,state,q,contact=True):
    selected=({'upper'},{'lower'},{'upper','lower'})['ABC'.index(e.variant)]
    for side in ('lower','upper'):
        q[side]=.04 if side in selected else 0.
        touch=f.contact(('machine/'+side,'left_finger1'))if contact else set()
        f.tick(e,state,touch,positions=q)
        f.tick(e,state,positions=q)
    return f.settle(e,state,positions=q)

@pytest.mark.parametrize('seed',(4201,4202,4203))
@pytest.mark.parametrize('condition',('I','E'))
def test_actual_scene_joint_map_and_ABC_pairing(seed,condition):
    states=[]
    for variant in 'ABC':
        original=load('E30',variant,0,BINDINGS,verify_files=False)
        s=apply_execution_inputs(original,condition=condition,seed=seed,revision=REVISION_V3)
        values=initial_displacements(s);states.append(values)
        assert s['semantic']['joint_roles']['lower']['joint']=='joint_1'
        assert s['semantic']['joint_roles']['upper']['joint']=='joint_2'
        assert all(.005<q<.015 for q in values.values())
        paired=apply_execution_inputs(original,condition='E'if condition=='I'else'I',seed=seed,revision=REVISION_V3)
        assert values==initial_displacements(paired)
    assert states[0]==states[1]==states[2]

@pytest.mark.parametrize('variant',list('ABC'))
@pytest.mark.parametrize('seed',(4201,4202,4203))
def test_new_input_requires_real_open_and_close_contact(variant,seed):
    s=spec(variant,seed);e,state,q=start(s);r=finish(e,state,q)
    assert r['success'],r['failed_checks']
    assert r['progress_result']['task_score_100']==100
    needed={'upper','lower'}-({'upper'},{'lower'},{'upper','lower'})['ABC'.index(variant)]
    assert set(r['observation']['closed_with_contact'])==needed

@pytest.mark.parametrize('fault',('no_contact','wrong_initial_closed','wrong_initial_open','wrong_initial_offset','earlier_touch_only','invalid_history','held'))
def test_cannot_accept_false_initial_or_unactuated_terminal(fault):
    s=spec();e=MechanismTaskEvaluator(s);state=f.state_for(s);q=initial_displacements(s)
    if fault.startswith('wrong_initial'):
        q['upper']={'wrong_initial_closed':0.,'wrong_initial_open':.04,'wrong_initial_offset':.014}[fault]
        f.settle(e,state,positions=q)
        assert not e.initial_valid
        with pytest.raises(ValueError):seal_initial(e)
        r=finish(e,state,q)
    else:
        e,state,q=start(s)
        if fault=='earlier_touch_only':
            q['lower']-=.0002
            f.tick(e,state,f.contact(('machine/lower','left_finger1')),positions=q)
            # End the previous/current contact window before passive closure.
            f.tick(e,state,positions=q);f.tick(e,state,positions=q)
            q['lower']=0.;f.tick(e,state,positions=q)
            q['upper']=.04;f.tick(e,state,f.contact(('machine/upper','left_finger1')),positions=q)
            r=f.settle(e,state,positions=q)
        else:
            r=finish(e,state,q,contact=fault!='no_contact')
            if fault=='invalid_history':e.update(state,set(),float('nan'));r=e.result()
            if fault=='held':r=f.settle(e,state,f.contact(('machine/upper','left_finger1')),positions=q)
    assert not r['success']
    assert r['progress_result']['task_score_100'] is None or r['progress_result']['task_score_100']<100

@pytest.mark.parametrize('variant',list('ABC'))
def test_private_expert_closes_non_target_only_for_explicit_new_input(variant):
    for new in (False,True):
        a=_Author.__new__(_Author);a.task='E30';a.variant=variant;a.spec=spec(variant)if new else f.mechanism_spec('E30',variant);a.operations=[]
        a.drawer=lambda role,close=False:a.operations.append((role,close));a.act=lambda:None;a.stage=lambda v:None
        got=a.solve()['operations'];selected=(('upper',),('lower',),('upper','lower'))['ABC'.index(variant)]
        ordered=('lower','upper')if new and variant=='C'else selected
        expected=([(r,True)for r in ('lower','upper')if r not in selected]if new else[])+[(r,False)for r in ordered]
        assert got==expected

@pytest.mark.parametrize('revision',('legacy','embodied50-execution-v2-20261102'))
def test_old_episodes_still_require_initially_closed_drawers(revision):
    s=f.mechanism_spec('E30')
    if revision!='legacy':s['execution_design']=dict(revision=revision,condition='I')
    assert initial_displacements(s)is None
    e=MechanismTaskEvaluator(s);f.tick(e,f.state_for(s),positions={'upper':.009,'lower':.007})
    assert not e.initial_valid

@pytest.mark.parametrize('fault',('missing','reset_mismatch','terminal_open','terminal_closed','nan'))
def test_input_declaration_must_match_real_joint_reset(fault):
    s=spec();entry=s['semantic']['execution_design_drawer_input']
    if fault=='missing':del s['semantic']['execution_design_drawer_input']
    elif fault=='reset_mismatch':s['mechanisms'][0]['initial_joint_positions']['upper_joint']+=.001
    else:entry['normalized_displacements']['upper']={'terminal_open':.04,'terminal_closed':0.,'nan':float('nan')}[fault]
    with pytest.raises(ValueError):MechanismTaskEvaluator(s)

@pytest.mark.parametrize('variant',list('ABC'))
@pytest.mark.parametrize('raised',(False,True))
def test_full_feedback_expert_starts_from_half_open_and_closes_wrong_drawer(variant,raised):
    path=source.with_name('test_realworld_mechanism_expert.py')
    mod=importlib.util.spec_from_file_location('drawer_expert_plant',path);g=importlib.util.module_from_spec(mod);mod.loader.exec_module(g)
    s=g.spec('E30',variant);cal=spec(variant)
    s['execution_design']=cal['execution_design'];s['mechanisms']=cal['mechanisms']
    if raised:s['mechanisms'][0]['instance_support_lift_m']=.045
    s['semantic']['execution_design_drawer_input']=cal['semantic']['execution_design_drawer_input']
    a=g.Author(s);a.c.q=initial_displacements(s)
    a.align_gripper_axis=lambda side,axis:None  # Plant has no wrist dynamics.
    a.tcp_rotation_task=lambda side:__import__('numpy').eye(3)
    result=g.solve_mechanism(a)
    selected=({'upper'},{'lower'},{'upper','lower'})['ABC'.index(variant)]
    assert {r for r,q in a.c.q.items()if q>=.015}==selected
    assert all(a.c.q[r]<=.005 for r in {'upper','lower'}-selected)
    assert [x['role']for x in result['operations']if x['operation']=='close']==[r for r in('lower','upper')if r not in selected]
    assert all(a.c.held[s]is None for s in('left','right'))
    assert not result['physics_success_evaluated']
    bad=g.Author(s)
    with pytest.raises(g.MechanismExecutionError,match='declared half-open'):_Author(bad)
    assert bad.c.steps==0


def test_new_e30_front_corridor_uses_actual_handle_plane_without_high_pose():
    import numpy as np
    for revision,condition,expected in [(REVISION_V3,'I',True),(REVISION_V3,'E',True),(REVISION_V3,'R',False),('embodied50-execution-v2-20261102','I',False)]:
        a=_Author.__new__(_Author);a.task='E30';a.spec={'execution_design':dict(revision=revision,condition=condition)};a.semantic={}
        assert a.front_corridor()is expected
    a.spec={'execution_design':dict(revision=REVISION_V3,condition='I')};a.points={'lower':{}};a.clearance=1.15
    a.a=SimpleNamespace(scene=SimpleNamespace(embodiment=SimpleNamespace(config={})))
    a.point=lambda r:np.array([-.04,0.,.878]);a.axis=lambda r:np.array([-1.,0.,0.]);current=np.array([-.19,-.30,.902]);a.tip=lambda s:current.copy()
    moves=[]
    def move(side,target,**kw):
        nonlocal current
        current=np.asarray(target).copy();moves.append((current,kw))
    a.move=move;a.approach('lower','right')
    assert all(p[2]==pytest.approx(.878)for p,k in moves)
    assert moves[0][0][0]<=-.15 and moves[1][0][0]<=-.15
    np.testing.assert_allclose(moves[-1][0],a.point('lower'))
    assert moves[-1][1]['tolerance']==.002


def test_v3_acquire_corrects_measured_jaw_before_handle_approach():
    import numpy as np
    a=_Author.__new__(_Author);a.spec=spec();a.task='E30';calls=[]
    a.hand=lambda r:'right';a.stage=lambda x:None;a.act=lambda *args:calls.append(('act',args))
    a.stage_drawer_orientation=lambda *args:calls.append(('stage_rotation',args))
    a.orient=lambda *args:calls.append(('coarse',args));a.approach=lambda *args:calls.append(('approach',args))
    a.touching=lambda *args,**kw:True;a.axis=lambda role:np.array([-1.,0.,0.]);a.points={'lower':{}} 
    a.a=SimpleNamespace(scene=SimpleNamespace(embodiment=SimpleNamespace(config={})),align_gripper_axis=lambda side,jaw:calls.append(('measured_align',jaw.tolist())))
    assert a.acquire('lower')=='right'
    names=[x[0]for x in calls]
    assert names.index('stage_rotation')<names.index('coarse')<names.index('measured_align')<names.index('approach')
    assert calls[names.index('measured_align')][1]==[0.,-1.,0.]


@pytest.mark.parametrize("tracking_fraction",(.45,.10))
def test_measured_drawer_orientation_converges_with_partial_public_rotations(tracking_fraction):
    import numpy as np
    from videoicl_isaaclab.realworld_tool_expert import _axis_rotation
    from videoicl_isaaclab.author_orientation import _axis_angle
    a=_Author.__new__(_Author);a.points={'lower':dict(wrist_yaw_deg=90.,wrist_pitch_deg=-90.)};a.start_steps=0;a.max_actions=1000;a.c=SimpleNamespace(steps=0)
    current=np.eye(3);tokens={'ROTATE_CCW':([0,0,1],1),'ROTATE_CW':([0,0,1],-1),'PITCH_UP':([0,1,0],1),'PITCH_DOWN':([0,1,0],-1),'ROLL_LEFT':([1,0,0],1),'ROLL_RIGHT':([1,0,0],-1)}
    def act(left,right,rotation_deg):
        nonlocal current
        token=right if right!='STILL'else left;axis,sign=tokens[token]
        current=_axis_rotation(axis,np.deg2rad(rotation_deg*sign*tracking_fraction))@current;a.c.steps+=1
    a.a=SimpleNamespace(scene=SimpleNamespace(embodiment=SimpleNamespace(config={})),tcp_rotation_task=lambda side:current.copy(),act=act)
    a.orient_drawer_measured('lower','right')
    target=_axis_rotation([0,1,0],-np.pi/2)@_axis_rotation([0,0,1],np.pi/2)@_axis_rotation([0,0,1],np.pi)
    assert _axis_angle(target@current.T)[1]<np.deg2rad(1.5)
    assert a.c.steps>18  # A fixed 18 nominal commands would stop far short.
    a.orient_drawer_measured('lower','right',inverse=True)
    assert _axis_angle(current)[1]<np.deg2rad(1.5)


def test_measured_drawer_orientation_does_not_accept_static_pose_after_requests():
    import numpy as np
    a=_Author.__new__(_Author);a.points={'lower':dict(wrist_yaw_deg=90.)};a.start_steps=0;a.max_actions=1000;a.c=SimpleNamespace(steps=0)
    def act(*args,**kw):a.c.steps+=1
    a.a=SimpleNamespace(scene=SimpleNamespace(embodiment=SimpleNamespace(config={})),tcp_rotation_task=lambda side:np.eye(3),act=act)
    from videoicl_isaaclab.realworld_mechanism_expert import MechanismExecutionError
    with pytest.raises(MechanismExecutionError,match='stalled'):a.orient_drawer_measured('lower','right')
    assert a.c.steps==12


def test_drawer_rotation_staging_uses_actual_front_and_keeps_neutral():
    import numpy as np
    a=_Author.__new__(_Author)
    neutral=np.eye(3)
    a.a=SimpleNamespace(tcp_rotation_task=lambda side:neutral.copy())
    a.point=lambda role:np.array([-.04,0.,.878])
    a.axis=lambda role:np.array([-1.,0.,0.])
    current=np.array([-.19,-.3,.902]);a.tip=lambda side:current.copy()
    moves=[]
    def move(side,target):
        nonlocal current
        current=np.array(target);moves.append(current.copy())
    a.move=move
    a.stage_drawer_orientation('lower','right')
    assert all(float((p-a.point('lower'))@a.axis('lower'))>=.17-1e-9 for p in moves)
    np.testing.assert_allclose(current,[-.21,0.,.978])
    neutral[:]=np.diag([-1.,-1.,1.])
    a.stage_drawer_orientation('lower','right')
    np.testing.assert_allclose(a.drawer_neutral_rotations['right'],np.eye(3))


def test_bell_parking_geometry_is_room_translation_invariant():
    import numpy as np
    a=_Author.__new__(_Author)
    robots={'left':{'position':[0.,.3,0.]},'right':{'position':[0.,-.3,0.]}}
    def points(origin):
        a.a=SimpleNamespace(scene=SimpleNamespace(origin=origin,world_to_task=lambda p:np.array(p)-np.array(origin),embodiment=SimpleNamespace(config={'robots':robots})))
        return a.bell_parking_geometry()
    first=points([0.,0.,0.]);shifted=points([8.4,2.2,0.])
    for side in first:np.testing.assert_allclose(first[side],shifted[side])


def test_v3_cabinet_instances_are_physical_pinned_and_paired():
    from pathlib import Path
    import hashlib
    ids=[]
    for seed in (4201,4202,4203):
        hashes=[]
        for variant in 'ABC':
            for condition in ('I','E'):
                original=load('E30',variant,0,BINDINGS,verify_files=False)
                adapted=apply_execution_inputs(original,condition=condition,seed=seed,revision=REVISION_V3)
                before=original['mechanisms'][0]['mechanical_asset'];after=adapted['mechanisms'][0]['mechanical_asset']
                assert after['sha256']!=before['sha256']
                assert after['joint_roles']==before['joint_roles']
                assert after['linear_limits_m']==before['linear_limits_m']
                lift=adapted['mechanisms'][0]['instance_support_lift_m']
                assert lift in (.04,.045,.05)
                assert adapted['mechanisms'][0]['position'][2]==pytest.approx(original['mechanisms'][0]['position'][2]+lift)
                root=Path(__file__).parents[1]/'execution-design-v3/assets'
                assert hashlib.sha256((root/after['relative_path']).read_bytes()).hexdigest()==after['sha256']
                assert after['bounds'][1][1]-after['bounds'][0][1]>before['bounds'][1][1]-before['bounds'][0][1]
                hashes.append(after['sha256'])
        assert len(set(hashes))==1
        ids.append(hashes[0])
    assert len(set(ids))==3
    original=load('E30','A',0,BINDINGS,verify_files=False)
    r=apply_execution_inputs(original,condition='R',seed=4201,revision=REVISION_V3)
    assert r['mechanisms'][0]['mechanical_asset']==original['mechanisms'][0]['mechanical_asset']
    assert r['mechanisms'][0]['position']==original['mechanisms'][0]['position']
    assert 'instance_support_lift_m' not in r['mechanisms'][0]


def test_actual_e30_pinch_calibration_uses_thin_handle_cross_section():
    import numpy as np
    original=load('E30','A',0,BINDINGS,verify_files=False)
    adapted=apply_execution_inputs(original,condition='I',seed=4201,revision=REVISION_V3)
    for entry in adapted['semantic']['handle_points'].values():
        assert entry['pinch_axis_local']==[0.,1.,0.]
        assert np.dot(entry['pinch_axis_local'],entry['approach_local'])==0
    # Source-native board geometry: long width cannot fit an 80mm gripper.
    import json
    evidence=Path(__file__).parents[2]/'verification/task-design-revision-20261102/e30-handle-pinch-geometry.private.json'
    for row in json.loads(evidence.read_text())['roles']:
        assert row['actual_body_local_extent_m'][0]>row['maximum_panda_opening_m']
        assert row['actual_body_local_extent_m'][1]<.004<row['maximum_panda_opening_m']


@pytest.mark.parametrize('actual_start',(.009,0.))
def test_v3_contact_closure_during_acquire_counts_actual_full_motion(actual_start):
    from videoicl_isaaclab.realworld_mechanism_expert import MechanismExecutionError
    a=_Author.__new__(_Author);a.task='E30';a.spec=spec();a.roles={'lower':dict(closed_tolerance=.005,open_threshold=.015)};a.motion={'lower':dict(open_distance=.06)};a.operations=[]
    q=[actual_start];a.displacement=lambda role:q[0]
    def acquire(role,**kwargs):
        assert kwargs=={'closing_push':True};q[0]=0.;return 'right'
    a.acquire=acquire;a.stage=lambda name:None;a.act=lambda *args:None;a.retreat=lambda *args:None;a.orient=lambda *args,**kwargs:None
    a.a=SimpleNamespace(scene=SimpleNamespace(embodiment=SimpleNamespace(config={})))
    if actual_start:
        a.drawer('lower',close=True)
        assert a.operations==[dict(operation='close',role='lower',start=.009,end=0.)]
    else:
        with pytest.raises(MechanismExecutionError,match='No measured drawer travel'):a.drawer('lower',close=True)


def test_contact_push_close_tracks_measured_joint_without_fabricating_grip():
    import numpy as np
    a=_Author.__new__(_Author);a.task='E30';a.spec=spec();a.roles={'upper':dict(closed_tolerance=.005,open_threshold=.015)};a.motion={'upper':dict(open_distance=.06)};a.operations=[]
    q=[.011];calls=[];a.displacement=lambda role:q[0];a.acquire=lambda role,**kwargs:'right'
    a.stage=lambda name:None;a.act=lambda *args:None;a.retreat=lambda *args:None;a.orient=lambda *args,**kwargs:None
    a.axis=lambda role:np.array([-1.,0.,0.]);a.tip=lambda side:np.array([-.05,0.,.96]);a.touching=lambda *args,**kwargs:False
    a.a=SimpleNamespace(scene=SimpleNamespace(embodiment=SimpleNamespace(config={})))
    def push(side=None,token='STILL',mm=1.):
        if token not in ('STILL','RELEASE'):
            assert side=='right' and token=='FWD' and 0.<mm<=2.;calls.append(mm);q[0]-=mm/1000.
    a.act=push;a.move=lambda *args,**kwargs:pytest.fail('Closing must not chase a free-space micro-waypoint at contact')
    a.drawer('upper',close=True)
    assert calls
    assert a.operations[0]['end']<=.005 and a.operations[0]['start']==.011
    q[0]=.011;a.act=lambda *args,**kwargs:None
    with pytest.raises(Exception,match='stalled'):a.drawer('upper',close=True)


def test_physical_support_instance_uses_horizontal_grasp_without_old_offset(monkeypatch):
    import numpy as np
    monkeypatch.setenv('VIC_ENGINEERING_DRAWER_IK_PROBE','1')
    original=load('E30','A',0,BINDINGS,verify_files=False)
    adapted=apply_execution_inputs(original,condition='I',seed=4201,revision=REVISION_V3)
    a=_Author.__new__(_Author);a.spec=adapted;a.axis=lambda role:np.array([-1.,0.,0.]);a.drawer_jaw_axis=lambda role:np.array([0.,0.,1.]);a.point=lambda role:np.array([-.04,0.,.923])
    outward,jaw=a.engineering_drawer_grasp_axes('lower')
    np.testing.assert_array_equal(outward,a.axis('lower'));np.testing.assert_array_equal(jaw,a.drawer_jaw_axis('lower'))
    np.testing.assert_array_equal(a.engineering_drawer_capture_target('lower'),a.point('lower'))


def test_raised_cabinet_retreat_preserves_released_pose_without_extra_rotation():
    a=_Author.__new__(_Author);a.task='E30';a.spec=spec();a.spec['mechanisms'][0]['instance_support_lift_m']=.045
    a.roles={'lower':dict(closed_tolerance=.005,open_threshold=.015)};a.motion={'lower':dict(open_distance=.06)};a.operations=[]
    q=[.009];a.displacement=lambda role:q[0]
    def acquire(role,**kwargs):q[0]=0.;return 'right'
    a.acquire=acquire;a.stage=lambda name:None;calls=[];a.act=lambda *args:calls.append(args);a.retreat=lambda *args:calls.append(('retreat',*args))
    a.orient=lambda *args,**kwargs:pytest.fail('Source does not require neutral wrist after a released clear retreat')
    a.a=SimpleNamespace(scene=SimpleNamespace(embodiment=SimpleNamespace(config={})))
    a.drawer('lower',close=True)
    assert calls[0]==('right','RELEASE') and calls[1]==('retreat','lower','right')
    assert a.operations==[dict(operation='close',role='lower',start=.009,end=0.)]


def test_closed_panel_push_is_explicit_engineering_only_and_keeps_opening_grasp(monkeypatch):
    import numpy as np
    a=_Author.__new__(_Author);a.task='E30';a.spec=spec();a.spec['mechanisms'][0]['instance_support_lift_m']=.045;a.drawer_closing_role='lower'
    a.point=lambda role:np.array([-.04,0.,.923]);a.axis=lambda role:np.array([-1.,0.,0.]);a.drawer_jaw_axis=lambda role:np.array([0.,0.,1.])
    assert not a.engineering_drawer_panel_push('lower')
    monkeypatch.setenv('VIC_ENGINEERING_DRAWER_PANEL_PUSH','1')
    assert a.engineering_drawer_panel_push('lower')
    np.testing.assert_allclose(a.engineering_drawer_grasp_axes('lower')[1],[0.,1.,0.])
    np.testing.assert_allclose(a.engineering_drawer_capture_target('lower'),[-.044,0.,.89])
    assert not a.engineering_drawer_panel_push('upper')
    a.drawer_closing_role=None
    np.testing.assert_allclose(a.engineering_drawer_capture_target('lower'),a.point('lower'))
    np.testing.assert_allclose(a.engineering_drawer_grasp_axes('lower')[1],[0.,0.,1.])


@pytest.mark.parametrize('crossing_contact',(True,False))
@pytest.mark.parametrize('established_contact_push',(True,False))
def test_real_contact_closure_counts_slow_threshold_crossing(crossing_contact,established_contact_push):
    # PhysX approaches a contact stop asymptotically. A genuine millimetre
    # push must not disappear merely because the final threshold step is 7um.
    s=spec();e,state,q=start(s);touch=f.contact(('machine/lower','left_finger1'))
    initial_touch=touch if established_contact_push else set()
    q['lower']=.006;f.tick(e,state,initial_touch,positions=q)
    q['lower']=.005006;f.tick(e,state,initial_touch,positions=q)
    if not crossing_contact:
        f.tick(e,state,positions=q);f.tick(e,state,positions=q)
    q['lower']=.004999;f.tick(e,state,touch if crossing_contact else set(),positions=q)
    assert ('lower' in e.closed_initial_drawers)==(crossing_contact and established_contact_push)
