"""Contract checks for the on-demand native health controller; no GPU calls."""
from copy import deepcopy
import importlib.util
import json
from pathlib import Path

import pytest


spec=importlib.util.spec_from_file_location('native_health',Path(__file__).resolve().parents[1]/'scripts/native_health_probe.py')
health=importlib.util.module_from_spec(spec);spec.loader.exec_module(health)


def observations():
    feedback=dict(arms={side:dict(tcp_position=[0.,0.,1.]) for side in ('left','right')})
    before=dict(shared_tick=240,robot_feedback=feedback)
    after=deepcopy(before);after['shared_tick']=340;after['robot_feedback']['arms']['left']['tcp_position'][2]+=.0074
    action=dict(receipt=dict(step_before=0,step_after=1,shared_tick_before=240,
        shared_tick_after=340,simulation_seconds=.400000019))
    ready=dict(metadata=dict(global_signature=dict(settings=dict(global_physics=dict(dt=.004),
        cohort_timing=dict(action_seconds=.4)))))
    return before,action,after,ready


def test_prepare_never_starts_native_or_queries_gpu(tmp_path,monkeypatch):
    def forbidden(*args,**kwargs):raise AssertionError('prepare touched runtime')
    monkeypatch.setattr(health,'gpu_snapshot',forbidden)
    monkeypatch.setattr(health.subprocess,'Popen',forbidden)
    out=tmp_path/'health'
    plan=health.prepare(out,native_python='/shared/sim-python50',bindings='/shared/bindings.json',
        experience='/shared/isaac5.0.kit',expected_gpu_uuid='GPU-test')
    assert plan['prepared_only'] and not plan['auto_start'] and not plan['counts_toward_450']
    assert plan['deadline_seconds']==300
    assert plan['configuration']['expected_gpu_uuid']=='GPU-test'
    case=json.loads((out/'cases.private.json').read_text())[0]
    assert (case['task'],case['variant'],case['seed'])==('E05','A',4201)
    assert '--defer-stage-creation' in plan['command']
    index=plan['command'].index('--capture-passes');assert plan['command'][index+1]=='64'
    assert not (out/'started.private.json').exists()
    fresh=health.prepare(tmp_path/'next-attempt',**plan['configuration'])
    assert fresh['identity']['run_id']!=plan['identity']['run_id']
    assert fresh['configuration']==plan['configuration']
    with pytest.raises(FileExistsError):
        health.prepare(out,native_python='/shared/sim-python50',bindings='/shared/bindings.json',experience='/shared/isaac5.0.kit')


def test_health_identity_rejects_bool_seed_and_foreign_run():
    identity=dict(run_id='health-run',task_id='E05',variant='A',seed=4201,suite='health',epoch='test')
    assert health.exact_identity(deepcopy(identity),identity)
    wrong=dict(identity,seed=True);assert not health.exact_identity(wrong,identity)
    assert not health.exact_identity(dict(identity,run_id='another-room'),identity)


def test_clock_receipt_alone_cannot_pass_without_measured_movement():
    before,action,after,ready=observations()
    assert health.verify_action(before,action,after,ready)['tracking_error_m']==pytest.approx(.0001)
    after['robot_feedback']=deepcopy(before['robot_feedback'])
    with pytest.raises(ValueError,match='Measured'):
        health.verify_action(before,action,after,ready)


def test_health_requires_one_physical_duration_and_still_other_arm():
    before,action,after,ready=observations()
    wrong=deepcopy(action);wrong['receipt']['step_after']=True
    with pytest.raises(ValueError,match='physical clock'):health.verify_action(before,wrong,after,ready)
    wrong=deepcopy(action);wrong['receipt']['shared_tick_after']=440
    with pytest.raises(ValueError,match='physical clock'):health.verify_action(before,wrong,after,ready)
    after['robot_feedback']['arms']['right']['tcp_position'][1]=.01
    with pytest.raises(ValueError,match='Measured'):health.verify_action(before,action,after,ready)


def test_pid_ownership_survives_reparenting_but_rejects_pid_reuse(monkeypatch):
    records={100:dict(pid=100,parent=10,start_ticks=123)}
    monkeypatch.setattr(health,'process_stamp',lambda pid:dict(pid=pid,parent=1,start_ticks=123))
    assert health.owned_alive(records)=={100}
    monkeypatch.setattr(health,'process_stamp',lambda pid:dict(pid=pid,parent=1,start_ticks=124))
    assert health.owned_alive(records)==set()
