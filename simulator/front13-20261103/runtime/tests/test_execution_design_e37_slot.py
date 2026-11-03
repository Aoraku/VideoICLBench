from types import SimpleNamespace
import json
import math
import numpy as np
import pytest
from videoicl_isaaclab.execution_design_e37_slot import run
from videoicl_isaaclab.realworld_tool_expert import ToolExecutionError


def fixture(tmp_path,monkeypatch,actual_turn_degrees,contact_force):
    pitch=.0029904088
    state=dict(angle=0.,axial=0.,depth=.0018,cos=1.,aligned=np.bool_(True),
               driver_force=0.,fixture_contact=1.,overlap=.019)
    c=SimpleNamespace(steps=0,physics_ticks=0,tick_hooks=[],_engineering_diagnostic_only=True)
    c.evaluator=SimpleNamespace(screw_measure=lambda entry:dict(state),thread_history_valid=np.bool_(True))
    p=SimpleNamespace(a=SimpleNamespace(out=tmp_path,control_report={'engineering_reference_only':True}),
        c=c,task='E37',variant='A',spec=dict(seed=4201,execution_design=dict(condition='R',revision='embodied50-execution-v3-20261102')),
        start=0,point=lambda tip:np.array([0.,0.,1.03]),require_held=lambda *args:None,
        _e37_table_readback=lambda:dict(read_errors={},all_link_table_peak_force_n={'left/panda_link6':0.}))
    p.stage=lambda name:setattr(p.a,'stage',name)
    monkeypatch.setattr('videoicl_isaaclab.execution_design_e37_handoff.move_tip',lambda *args,**kw:args[4]())
    monkeypatch.setattr('videoicl_isaaclab.engineering_checkpoint.capture',lambda *args,**kw:dict(source={'steps':0},checkpoint_sha256='native-checkpoint'))
    monkeypatch.setattr('videoicl_isaaclab.execution_design_jacobian_reference.capture',lambda *args:{})
    def motor(*args,**kwargs):
        kwargs['extra_guard']()
        state.update(angle=math.radians(actual_turn_degrees),axial=pitch*actual_turn_degrees/360.,driver_force=contact_force)
        for hook in list(c.tick_hooks):hook(c,False)
        c.steps+=1;c.physics_ticks+=100
        kwargs['extra_guard']()
        return dict(target_reached=True,executed_physics_ticks=100)
    monkeypatch.setattr('videoicl_isaaclab.execution_design_e37_regrip.helical_turn',motor)
    entry=dict(driver=dict(actor='driver',tip_local=[0,0,0]),screw='screw_left',socket_depth=.003,pitch_m=pitch,unscrew_direction=1)
    return p,entry


def test_torque_pilot_uses_actual_screw_rotation_and_native_pitch(tmp_path,monkeypatch):
    p,entry=fixture(tmp_path,monkeypatch,2.,.8)
    result=run(p,{'actor':'driver'},'left',entry,[0,0,1],lambda:np.array([0,0,1.]))
    assert result['requested_turn_degrees']==5.
    assert result['actual_screw_turn_degrees']==pytest.approx(2.)
    assert result['actual_screw_axial_travel_m']==pytest.approx(entry['pitch_m']*2/360.)
    assert result['segment_passed'] and not result['native_task_acceptance']
    assert result['real_driver_contact_observations']['engaged_driver_contact_samples']==1
    assert p.c.tick_hooks==[]


def test_completed_motor_without_real_screw_motion_never_passes(tmp_path,monkeypatch):
    p,entry=fixture(tmp_path,monkeypatch,0.,0.)
    with pytest.raises(ToolExecutionError,match='no confirmed'):
        run(p,{'actor':'driver'},'left',entry,[0,0,1],lambda:np.array([0,0,1.]))
    evidence=json.loads((tmp_path/'E37-original-slot-torque-pilot.private.json').read_text())
    assert evidence['actual_screw_turn_degrees']==0.
    assert evidence['actual_screw_axial_travel_m']==0.
    assert 'segment_passed'not in evidence and p.c.tick_hooks==[]


def test_numpy_false_native_history_is_retained_without_claiming_native_pass(tmp_path,monkeypatch):
    p,entry=fixture(tmp_path,monkeypatch,2.,.8);p.c.evaluator.thread_history_valid=np.bool_(False)
    with pytest.raises(ToolExecutionError,match='no confirmed'):
        run(p,{'actor':'driver'},'left',entry,[0,0,1],lambda:np.array([0,0,1.]))
    evidence=json.loads((tmp_path/'E37-original-slot-torque-pilot.private.json').read_text())
    assert p.c.steps==1 and evidence['native_thread_history_valid']is False
    assert evidence['actual_screw_turn_degrees']==pytest.approx(2.)
    assert 'segment_passed'not in evidence


def test_actual_seated_contact_never_repeats_public_insertion(tmp_path,monkeypatch):
    p,entry=fixture(tmp_path,monkeypatch,2.,.8)
    monkeypatch.setattr('videoicl_isaaclab.execution_design_e37_handoff.move_tip',
        lambda *args,**kwargs:pytest.fail('Already native-seated tool must not be driven farther'))
    result=run(p,{'actor':'driver'},'left',entry,[0,0,1],lambda:np.array([0,0,1.]),already_seated=True)
    assert result['insertion_skipped_for_existing_seating']and result['segment_passed']
    assert not result['already_seated_by_actual_native_contact']
