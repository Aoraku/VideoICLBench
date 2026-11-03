import importlib.util
import json
from pathlib import Path
from types import SimpleNamespace
import subprocess
import sys
import types

import numpy as np
import pytest

from videoicl_isaaclab.execution_design_probe import (
    matrix_case_batches,validate_execution_cases,pooled_author_class,classify_result)
from videoicl_isaaclab.execution_design import REVISION

ROOT=Path(__file__).parents[1]


def bindings(tmp_path):
    result={}
    for condition in ('I','E'):
        data=json.loads((ROOT/'configs/realworld_full50_bindings.json').read_text())
        data['execution_design']=dict(revision=REVISION,condition=condition)
        p=tmp_path/(condition+'.json');p.write_text(json.dumps(data));result[condition]=p
    return result


def test_matrix_covers_fixed_90_identities_without_dispatch(tmp_path):
    batches=matrix_case_batches(bindings(tmp_path));cases=sum(batches,[])
    assert len(batches)==6 and all(len(b)==15 for b in batches)
    assert len(cases)==len({c['episode_id'] for c in cases})==90
    assert {c['seed'] for c in cases}=={4201,4202,4203}
    rows=sum((validate_execution_cases(batch,'positive') for batch in batches),[])
    assert len({r['assignment_identity_sha256'] for r in rows})==90
    assert {r['condition'] for r in rows}=={'I','E'}
    assert all(r['native_acceptance']=='not_run' for r in rows)


def test_execution_validate_only_exits_before_native_import_or_output_creation(tmp_path):
    batch=matrix_case_batches(bindings(tmp_path),tasks=['E01'],rooms_per_batch=3)[0]
    case_file=tmp_path/'cases.json';case_file.write_text(json.dumps(batch))
    output=tmp_path/'must-not-be-created'
    result=subprocess.run([sys.executable,str(ROOT/'scripts/probe_realworld_room_pool.py'),
        '--cases',str(case_file),'--out',str(output),'--execution-control','positive','--validate-only'],
        capture_output=True,text=True,timeout=30)
    assert result.returncode==0,result.stderr
    payload=json.loads(result.stdout)
    assert len(payload['execution_controls'])==3
    assert payload['model_launch_enabled'] is False and not output.exists()


def test_default_capacity_validate_only_keeps_original_mode(tmp_path):
    result=subprocess.run([sys.executable,str(ROOT/'scripts/probe_realworld_room_pool.py'),
        '--bindings',str(ROOT/'configs/realworld_full50_bindings.json'),'--tasks','E05',
        '--out',str(tmp_path/'unused'),'--validate-only'],capture_output=True,text=True,timeout=30)
    assert result.returncode==0,result.stderr
    assert 'execution_controls' not in json.loads(result.stdout)
    assert not (tmp_path/'unused').exists()


def test_public_action_adapter_routes_only_through_room_batch_and_keeps_receipt(tmp_path):
    calls=[]
    def action_batch(actions):
        calls.append(actions);return {'room':dict(step_before=0,step_after=1,physics_ticks=120)}
    base=type('Base',(),{})
    author=pooled_author_class(base,SimpleNamespace(action_batch=action_batch),'room')()
    author.scene=SimpleNamespace(spec={},embodiment=SimpleNamespace(config={'control':{'step_mm':[.5,50.],'rotation_deg':[.5,20.]}}));author.c=SimpleNamespace(steps=0)
    author.out=tmp_path;author.stage='test';author.tip=lambda side:np.array([0,0,1.])
    receipt=author.act('FWD','STILL',mm=10,rotation_deg=2)
    assert calls==[{'room':dict(left='FWD',right='STILL',step_mm=10,rotation_deg=2)}]
    row=json.loads((tmp_path/'demo-actions.private.jsonl').read_text())
    assert row['physics_ticks']==receipt['physics_ticks']==120
    author.c.steps=1500
    with pytest.raises(RuntimeError,match='budget'):author.act()
    assert len(calls)==1


def test_cooperative_adapter_submits_once_without_serial_scope_or_direct_batch(tmp_path):
    calls=[]
    def forbidden(*args,**kwargs):raise AssertionError('Cooperative reference entered serial batch/render scope')
    def submit(room,command):
        calls.append((room,command));return dict(step_before=0,step_after=1,physics_ticks=100)
    pool=SimpleNamespace(action_batch=forbidden,engineering_reference_rendering=forbidden)
    author=pooled_author_class(type('Base',(),{}),pool,'room',SimpleNamespace(submit=submit))()
    author.scene=SimpleNamespace(spec={},embodiment=SimpleNamespace(config={'control':{'step_mm':[.5,50.],'rotation_deg':[.5,20.]}}))
    author.c=SimpleNamespace(steps=0);author.out=tmp_path;author.stage='test'
    author.tip=lambda side:np.zeros(3)
    receipt=author.act('FWD',mm=10)
    assert len(calls)==1 and receipt['step_after']==1
    rows=[json.loads(x)for x in (tmp_path/'demo-actions.private.jsonl').read_text().splitlines()]
    assert len(rows)==1 and rows[0]['physics_ticks']==100


def test_reference_return_or_failed_score_never_certifies_negative():
    native=dict(task_score_100=0,strict_success=False,history_valid=True,native_evidence_valid=True)
    for control in ('wrong_members','wrong_destination','wrong_rule','not_released'):
        result=classify_result(control,native,[],True)
        assert result['control_execution_completed'] is True
        assert result['native_positive_passed'] is None and result['negative_condition_observed'] is None
    assert classify_result('positive',native,[],True)['native_positive_passed'] is False
    native.update(task_score_100=100,strict_success=True)
    assert classify_result('positive',native,[],True)['native_positive_passed'] is True
    assert classify_result('positive',native,[{'error':'route stalled'}],True)['native_positive_passed'] is False
    assert classify_result('positive',native,[],False)['native_positive_passed'] is False


def test_legacy_bindings_rejected_for_execution_controls(tmp_path):
    rows=[dict(episode_id='legacy',task='E01',variant='A',seed=4201,
        bindings=str(ROOT/'configs/realworld_full50_bindings.json'))]
    with pytest.raises(ValueError,match='Explicit revision'):validate_execution_cases(rows,'positive')


@pytest.mark.parametrize('advance_initial_clock',[False,True])
@pytest.mark.parametrize('cooperative',[False,True])
@pytest.mark.parametrize('gray_views',[False,True])
@pytest.mark.parametrize('task',['E13','E17','E20'])
def test_runner_seals_all_initials_before_actions_and_keeps_failed_room_evidence(tmp_path,monkeypatch,advance_initial_clock,cooperative,gray_views,task):
    from videoicl_isaaclab import execution_design_probe as probe
    from videoicl_isaaclab import execution_design_expert as expert
    if cooperative:pytest.importorskip('greenlet')
    monkeypatch.setenv('VIC_ENGINEERING_COOPERATIVE_REFERENCES','1'if cooperative else'0')
    events=[];controllers={}
    native=dict(task_score_100=100,strict_success=True,success=True,history_valid=True,native_evidence_valid=True)
    class Evaluator:
        initial_sealed=False
        def __init__(self,room):self.room=room
        def initial_diagnostics(self,**kwargs):return dict(ready=True)
        def seal_initial(self):self.initial_sealed=True;events.append(('initial_seal',self.room))
        def result(self):return dict(native)
    class Tensor:
        def __getitem__(self,key):return self
        def cpu(self):return self
        def numpy(self):
            image=np.zeros((8,8,3),dtype=np.uint8)
            if not gray_views:image[:4,:,0]=255
            return image
    for room in ('first','second'):
        cameras={n:SimpleNamespace(update=lambda *args,**kwargs:None,data=SimpleNamespace(output={'rgb':Tensor()})) for n in ('head','left_wrist','right_wrist')}
        scene=SimpleNamespace(spec=dict(id=task,variant='A',seed=4201,goals=[dict(type='place')],execution_design={'revision':REVISION,'grasps':{'object':{'local':[0,0,0],'jaw_axis_local':[1,0,0]}}}),
            cameras=cameras,embodiment=SimpleNamespace(config={'control':{'step_mm':[.5,50.],'rotation_deg':[.5,20.]}}),contact_diagnostics=lambda:dict(bodies={},sensors={}))
        controllers[room]=SimpleNamespace(scene=scene,evaluator=Evaluator(room),steps=0,physics_ticks=0,
            contact_forces={frozenset(('object','table')):1.},public_feedback=lambda:{},
            snapshot=lambda:({'object':dict(pos=np.zeros(3),mat=np.eye(3),grasp=[False,False])},{frozenset(('object','table'))}))
        controllers[room].evaluator.spec=scene.spec
        scene.rgb_camera_calibration=lambda name:dict(available=True,T_world_from_camera_optical=np.eye(4).tolist(),T_task_from_camera_optical=np.eye(4).tolist())
        controllers[room].validate_action=lambda **kwargs:None
    class Pool:
        from videoicl_isaaclab.room_pool import RoomPool as _RealPool
        engineering_recording_render_passes=_RealPool.engineering_recording_render_passes
        physics_ticks=0
        def __init__(self):self.controllers=controllers;self.terminal={}
        def tick(self):self.physics_ticks+=1
        def action_batch(self,actions):
            receipts={}
            for room in actions:
                events.append(('action',room));controllers[room].steps+=1
                receipts[room]=dict(step_before=controllers[room].steps-1,step_after=controllers[room].steps,physics_ticks=120)
            return receipts
        def render_room(self,room,*,passes,capture):
            events.append(('render',room))
            if advance_initial_clock:self.physics_ticks+=1
            return capture()
        def seal(self,room):
            events.append(('seal',room));self.terminal[room]=dict(native=native,room=room)
            return self.terminal[room]
    class Capture:
        def __init__(self,c,out):self.closed=False;self.room=c.evaluator.room
        def close(self,**kwargs):self.closed=True;events.append(('capture_close',self.room))
    class Author:
        def __init__(self,c,out,**kwargs):self.c=c;self.scene=c.scene;self.out=out;self.stage='engineering'
        def tip(self,side):return np.zeros(3)
        def close(self):events.append(('author_close',self.c.evaluator.room))
    module=types.ModuleType('videoicl_isaaclab.demonstration');module.Demonstration=Author
    monkeypatch.setitem(sys.modules,'videoicl_isaaclab.demonstration',module)
    monkeypatch.setattr(probe,'NativeCapture',Capture)
    def solve(author):
        author.act('FWD',mm=1)
        if author.c.evaluator.room=='first':raise RuntimeError('physical movement stalled')
        author.act('FWD',mm=1)
        return dict(execution_finished=True)
    monkeypatch.setattr(expert,'solve_execution_design',solve)
    from videoicl_isaaclab import execution_design_reference as reference
    monkeypatch.setattr(reference,'solve_execution_reference',solve)
    cases=[dict(episode_id=room,task=task,variant='A',seed=4201) for room in controllers]
    pool=Pool()
    report=probe.run_controls(pool,controllers,cases,tmp_path,control='positive',settle_ticks=2)
    assert events[:2]==[('initial_seal','first'),('initial_seal','second')]
    # E17/E20 now retry only the unchanged all-gray admission error, without
    # advancing any physics. A changed counter rejects on the first attempt.
    retry_enabled=task in ('E17','E20')
    render_count=3 if gray_views and retry_enabled and not advance_initial_clock else 1
    assert events[2:2+2*render_count]==[('render','first')]*render_count+[('render','second')]*render_count
    if advance_initial_clock or gray_views:
        assert not any(kind=='action' for kind,_ in events)
        assert not report['positive_native_passed']
        expected=('advanced physics/actions'if advance_initial_clock and retry_enabled
                  else'Initial camera evidence rejected'if gray_views else'advanced physics/actions')
        assert all(expected in row['error'][0]['error'] for row in report['rooms'])
        assert not list(tmp_path.rglob('reference-initial-media.private.json'))
        return
    assert ('action','second') in events
    assert report['positive_native_passed'] is False
    assert report['rooms'][0]['error'][0]['phase']=='control'
    assert report['rooms'][1]['native_positive_passed'] is True
    boundary=json.loads((tmp_path/'first'/'failure-boundary.private.json').read_text())
    assert boundary['no_post_failure_physics_or_actions'] and boundary['post_failure_public_actions']==0
    assert boundary['sibling_rooms_not_interrupted'] and not boundary['physics_world_frozen']
    assert not (tmp_path/'second'/'failure-boundary.private.json').exists()
    if cooperative:
        assert report['scheduling']['native_batches']==2
        assert report['scheduling']['isolated_recording_render_passes']==12
        assert pool._engineering_recording_render_passes==1
        assert events.index(('capture_close','first'))<events.index(('seal','first'))
        second_actions=[i for i,event in enumerate(events)if event==('action','second')]
        assert events.index(('seal','first'))<second_actions[1]
    for room in controllers:
        assert len(list((tmp_path/room).glob('reference-initial-*.png')))==3
        initial_media=json.loads((tmp_path/room/'reference-initial-media.private.json').read_text())
        assert initial_media['before_any_action'] and initial_media['initial_sealed']
        assert initial_media['shared_tick']==2 and initial_media['actions']==0
        assert len(initial_media['artifacts'])==3
        assert len(list((tmp_path/room).glob('reference-final-*.png')))==3
        state=json.loads((tmp_path/room/'reference-final-state.private.json').read_text())
        assert state['contact_forces']==[dict(bodies=['object','table'],force=1.)]
        assert (tmp_path/room/'reference-final-score.private.json').exists()
        assert (tmp_path/room/'engineering-reference/demo-actions.private.jsonl').exists()


def test_full50_plan_has_only_legal_cells_and_fixed_scope(tmp_path):
    from videoicl_isaaclab.execution_design_probe import full50_matrix_case_batches
    from videoicl_isaaclab.execution_design import metadata
    files=bindings(tmp_path)
    data=json.loads((ROOT/'configs/realworld_full50_bindings.json').read_text());data['execution_design']=dict(revision=REVISION,condition='R')
    r=tmp_path/'R.json';r.write_text(json.dumps(data));files['R']=r
    batches=full50_matrix_case_batches(files);cases=sum(batches,[])
    assert len(cases)==1233 and len({c['episode_id']for c in cases})==1233
    assert all(len(b)<=5 for b in batches)
    for c in cases:
        condition=c['episode_id'].split('-')[2]
        assert condition in metadata(c['task'])['support_mask']
    assert not any(c['task']=='E01'and'-R-'in c['episode_id']for c in cases)
    assert not any(c['task']=='E37'and'-I-'in c['episode_id']for c in cases)
    assert any(c['task']=='E37'and'-E-'in c['episode_id']for c in cases)
    for task in ('E06','E26','E37','E45'):
        case=next(c for c in cases if c['task']==task)
        assert validate_execution_cases([case],'positive')[0]['native_acceptance']=='not_run'
        if task in ('E06','E26'):
            assert validate_execution_cases([case],'wrong_rule')[0]['native_acceptance']=='not_run'
        else:
            with pytest.raises(NotImplementedError):validate_execution_cases([case],'wrong_rule')


def test_existing_native_scores_are_bound_to_real_sealed_evidence():
    from copy import deepcopy
    from videoicl_isaaclab.execution_design_probe import normalized_native_result
    original=dict(success=True,history_valid=True,errors=[],
        progress_evidence=dict(source='trusted_native_per_physics_tick',initial=dict(sealed=True)),
        progress_result=dict(progress_available=True,task_score_100=100))
    result=normalized_native_result(original)
    assert result['strict_success'] and result['task_score_100']==100
    assert result['original_native_result']==original and 'task_score_100'not in original
    for field in ('history','initial','source','missing_score'):
        bad=deepcopy(original)
        if field=='history':bad['history_valid']=False
        elif field=='initial':bad['progress_evidence']['initial']['sealed']=False
        elif field=='source':bad['progress_evidence']['source']='model_claim'
        else:bad['progress_result']=dict(progress_available=False)
        result=normalized_native_result(bad)
        assert result['task_score_100']is None and not result['strict_success']


def test_back25_extra_control_cannot_enter_front25_or_old_revision(tmp_path):
    from videoicl_isaaclab.execution_design import REVISION_V3
    binding=json.loads((ROOT/'configs/realworld_full50_bindings.json').read_text())
    binding['execution_design']=dict(revision=REVISION_V3,condition='I')
    path=tmp_path/'v3.json';path.write_text(json.dumps(binding))
    def case(task):return dict(episode_id=task+'-A-I-s4201',task=task,variant='A',seed=4201,bindings=str(path),robot='franka')
    assert validate_execution_cases([case('E34')],'unselected_cutlery_moved')[0]['native_acceptance']=='not_run'
    for task in ('E01','E25','E39','E42'):
        with pytest.raises(ValueError,match='explicitly implemented back25 v3'):
            validate_execution_cases([case(task)],'unselected_cutlery_moved')
    from videoicl_isaaclab.execution_design import REVISION_V2
    binding['execution_design']['revision']=REVISION_V2;path.write_text(json.dumps(binding))
    with pytest.raises((ValueError,NotImplementedError)):validate_execution_cases([case('E34')],'unselected_cutlery_moved')


def test_checkpoint_global_renders_remain_inside_room_isolation_without_actions():
    events=[];scope={'room':None}
    class Base:
        def note(self,stage):
            for _ in range(2):
                assert scope['room']=='target';events.append(('native_render',stage))
            return 'captured'
    def render_room(room,*,passes,capture):
        assert scope['room']is None;scope['room']=room
        try:
            events.append(('scope',room,passes));return capture()
        finally:scope['room']=None
    def action_batch(*args):raise AssertionError('A checkpoint advanced native actions')
    author=pooled_author_class(Base,SimpleNamespace(render_room=render_room,action_batch=action_batch),'target')()
    assert author.note('measured')=='captured'
    assert events==[('scope','target',1),('native_render','measured'),('native_render','measured')]
    assert scope['room']is None


@pytest.mark.parametrize('task',['E23','E24'])
@pytest.mark.parametrize('control',['wrong_rule','wrong_destination','not_released'])
def test_front_structural_counterexamples_require_v3_not_legacy_revision(tmp_path,task,control):
    from videoicl_isaaclab.execution_design import REVISION_V2
    b=bindings(tmp_path)['I']
    cases=[dict(episode_id='candidate',task=task,variant='B',seed=4202,bindings=str(b))]
    rows=validate_execution_cases(cases,control)
    assert rows[0]['native_acceptance']=='not_run' and rows[0]['control']==control
    data=json.loads(b.read_text());data['execution_design'].update(revision=REVISION_V2,condition='R');b.write_text(json.dumps(data))
    with pytest.raises(ValueError,match='explicit v3'):validate_execution_cases(cases,control)
    with pytest.raises(NotImplementedError):validate_execution_cases(cases,'wrong_members')


def test_failed_engineering_author_rejects_any_further_public_action():
    from videoicl_isaaclab.execution_design_probe import pooled_author_class
    from types import SimpleNamespace
    import pytest
    calls=[]
    pool=SimpleNamespace(action_batch=lambda *args:calls.append(args))
    author=pooled_author_class(object,pool,'failed')()
    author._engineering_failure_latched=True
    with pytest.raises(RuntimeError,match='further public actions prohibited'):
        author.act('FWD',mm=1)
    assert not calls
