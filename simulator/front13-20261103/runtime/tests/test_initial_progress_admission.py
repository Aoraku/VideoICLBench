"""Bounded native-state replay tests for initial-score evidence admission."""
from copy import deepcopy
import importlib.util
import json
from pathlib import Path
import sys
from types import SimpleNamespace
import pytest
from videoicl_isaaclab.realworld_native_evidence import NativeTaskEvaluator
from videoicl_isaaclab.realworld_progress_evidence import initial_diagnostics,seal_initial
from test_realworld_progress_native_v2 import obj,pose,pair,tick

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'scripts'))
SPEC=importlib.util.spec_from_file_location('pool_initial_admission',ROOT/'scripts/serve_realworld_room_pool.py')
POOL_SCRIPT=importlib.util.module_from_spec(SPEC);SPEC.loader.exec_module(POOL_SCRIPT)


def dynamic_scene():
    names=['b'+str(k) for k in range(1,6)]
    spec=dict(id='E07',variant='A',objects=[obj(n,rank=k) for k,n in enumerate(names,1)],zones=[],semantic=dict(groups=dict(blocks=names)))
    e=NativeTaskEvaluator(spec);state={n:pose(k*.1) for k,n in enumerate(names)};contacts=[pair(n,'table') for n in names]
    tick(e,state,contacts)
    return e,state,contacts


def ordinary_scene():
    names=['cube','sphere','triangle']
    spec=dict(id='E05',variant='A',objects=[obj(n) for n in names],zones=[dict(id=n,xy=[i*.2,0],half_size=[.05,.05]) for i,n in enumerate(('square','circle','triangle'))],semantic=dict(groups=dict(pieces=names)))
    e=NativeTaskEvaluator(spec);state={n:pose(k*.2,held=n=='triangle') for k,n in enumerate(names)};contacts=[pair(n,'table') for n in names]
    tick(e,state,contacts)
    return e,state,contacts


class ReplayPool:
    def __init__(self,scenes,moving=False):self.scenes=scenes;self.physics_ticks=1;self.moving=moving
    def tick(self):
        self.physics_ticks+=1
        for e,state,contacts in self.scenes:
            if self.moving:state[next(iter(state))]['pos'][1]+=.01
            tick(e,state,contacts)


def test_ordinary_tasks_seal_actual_unstable_state_without_faking_flags():
    e,state,contacts=ordinary_scene();d=initial_diagnostics(e,room_id='ordinary')
    assert d['can_seal'] and not d['dynamic_denominator'] and d['unstable_actors']
    seal_initial(e)
    initial=e.result()['progress_evidence']['initial']
    assert initial['sealed'] and initial['object_status']['triangle']['released'] is False
    assert initial['object_status']['triangle']['stable'] is False
    for _ in range(8):
        state['triangle']['grasp']=[False,False];tick(e,state,contacts)
    assert e.result()['progress_evidence']['initial']==initial


def test_dynamic_task_error_names_exact_unstable_actors():
    e,_,_=dynamic_scene();d=initial_diagnostics(e,room_id='dynamic')
    assert not d['can_seal'] and len(d['required_unstable_actors'])==5
    with pytest.raises(ValueError,match=r'E07/A.*b1.*released=True.*stable=False'):
        seal_initial(e)


def test_pool_bounded_true_ticks_settle_dynamic_and_capture_all_rooms(tmp_path):
    dynamic=dynamic_scene();ordinary=ordinary_scene();pool=ReplayPool([dynamic,ordinary])
    controllers={'dynamic':SimpleNamespace(evaluator=dynamic[0]),'ordinary':SimpleNamespace(evaluator=ordinary[0])}
    result=POOL_SCRIPT.prepare_initial_progress(pool,controllers,tmp_path,physics_dt=.1,initial_window_ticks=1,max_extra_settle_seconds=.8)
    assert 1<=result['extra_physics_ticks']<=8 and result['all_rooms_can_seal']
    assert (tmp_path/'initial-progress/dynamic.pre-seal.private.json').is_file()
    assert (tmp_path/'initial-progress/ordinary.pre-seal.private.json').is_file()
    final=json.loads((tmp_path/'initial-progress-evidence.private.json').read_text())
    assert final['rooms']['dynamic']['sealed']
    assert final['rooms']['ordinary']['object_status']['triangle']['stable'] is False


def test_unstable_dynamic_window_is_bounded_no_reset_and_diagnostics_survive(tmp_path):
    dynamic=dynamic_scene();ordinary=ordinary_scene();pool=ReplayPool([dynamic,ordinary],moving=True)
    original=deepcopy(dynamic[0].initial)
    controllers={'dynamic-room':SimpleNamespace(evaluator=dynamic[0]),'ordinary-room':SimpleNamespace(evaluator=ordinary[0])}
    with pytest.raises(ValueError,match=r'room=dynamic-room task=E07/A unstable_required_actors=.*b1'):
        POOL_SCRIPT.prepare_initial_progress(pool,controllers,tmp_path,physics_dt=.1,initial_window_ticks=1,max_extra_settle_seconds=.3)
    result=json.loads((tmp_path/'initial-progress-diagnostics.private.json').read_text())
    assert result['extra_physics_ticks']==3 and pool.physics_ticks==4
    assert not result['all_rooms_can_seal']
    assert (tmp_path/'initial-progress/ordinary-room.post-settle.private.json').is_file()
    assert not (tmp_path/'initial-progress-evidence.private.json').exists()
    assert (dynamic[0].initial['b1']['pos']==original['b1']['pos']).all()
    assert dynamic[0].state['b1']['pos'][1]>original['b1']['pos'][1]


def test_source_initial_guard_is_never_relaxed_or_retried(tmp_path):
    ordinary=ordinary_scene();ordinary[0].current_conditions.append(dict(type='source_initial_state',passed=False))
    pool=ReplayPool([ordinary])
    with pytest.raises(ValueError,match='source_initial_state'):
        POOL_SCRIPT.prepare_initial_progress(pool,{'source-room':SimpleNamespace(evaluator=ordinary[0])},tmp_path,physics_dt=.1,initial_window_ticks=1)
    assert pool.physics_ticks==1
    result=json.loads((tmp_path/'initial-progress-diagnostics.private.json').read_text())
    assert result['final_diagnostics']['source-room']['source_initial_failures']
    with pytest.raises(ValueError,match='source_initial_state'):seal_initial(ordinary[0])


def layout_evaluator(task):
    from videoicl_isaaclab.realworld_scenes import load
    spec=load(task,'C',4201,ROOT/'configs/realworld_full50_bindings.json',verify_files=False)
    objects={o['id']:o for o in spec['objects']}
    import numpy as np
    state={}
    for n,o in objects.items():
        c,s=np.cos(o['yaw']),np.sin(o['yaw'])
        state[n]=dict(pos=np.array([*o['xy'],o['bottom']+o['size'][2]]),
            mat=np.array([[c,-s,0],[s,c,0],[0,0,1]]),grasp=[False,False])
    return SimpleNamespace(task=task,objects=objects,state=state,
        progress_status_by_actor={n:dict(supported=True,released=True,stable=True) for n in objects})


@pytest.mark.parametrize('task',['E13','E25'])
def test_reviewed_initial_layout_accepts_supported_recipe_and_two_mm_settling(task):
    from videoicl_isaaclab.realworld_progress_evidence import initial_layout_failures
    e=layout_evaluator(task)
    for value in e.state.values():value['pos'][2]-=.002
    assert initial_layout_failures(e)==[]


def test_initial_layout_rejects_fallen_cutlery_even_if_first_snapshot_and_stable_are_wrong():
    from videoicl_isaaclab.realworld_progress_evidence import initial_layout_failures
    e=layout_evaluator('E25')
    for n in ('fork','spoon','knife'):
        e.state[n]['pos'][2]=-10.37
        e.progress_status_by_actor[n]['supported']=False
    e.initial=deepcopy(e.state)
    failures=initial_layout_failures(e)
    assert {x['actor_id'] for x in failures}=={'fork','spoon','knife'}
    assert all('initial_center_displaced' in x['reasons'] and 'no_measured_physical_support' in x['reasons'] for x in failures)
    assert e.state['fork']['pos'][2]==-10.37 and e.progress_status_by_actor['fork']['stable']


def test_initial_layout_rejects_stable_tilted_unsupported_stand():
    from videoicl_isaaclab.realworld_progress_evidence import initial_layout_failures
    import numpy as np
    e=layout_evaluator('E13');e.state['stand']['pos'][2]=.789616165
    e.state['stand']['mat']=np.array([[-.2501823,.3214374,.9132836],[-.9681865,-.0783124,-.2376596],[-.0048712,-.9436871,.3308036]])
    e.progress_status_by_actor['stand']['supported']=False
    f=initial_layout_failures(e)
    assert len(f)==1 and f[0]['actor_id']=='stand'
    assert {'initial_center_displaced','initial_orientation_displaced','no_measured_physical_support'}<=set(f[0]['reasons'])


def test_initial_layout_missing_measurement_fails_closed():
    from videoicl_isaaclab.realworld_progress_evidence import initial_layout_failures
    e=layout_evaluator('E25');del e.state['fork']
    assert initial_layout_failures(e)[0]['reasons']==['missing_actor_or_pose']
