"""CPU routing checks, never native physical acceptance."""
from pathlib import Path
from types import SimpleNamespace
import pytest
from videoicl_isaaclab import execution_design_reference as ref
from videoicl_isaaclab.execution_design import build_task_contract,REVISION,WORKFLOW_TASKS
from videoicl_isaaclab.realworld_scenes import load


def author(task='E06'):
    contract=build_task_contract(task,'A',4201,condition='R' if task not in WORKFLOW_TASKS else 'I')
    spec=dict(id=task,variant='A',execution_design=contract['execution_design'],goals=[dict(type='place')])
    a=SimpleNamespace(scene=SimpleNamespace(spec=spec),control_report={},c=SimpleNamespace(steps=0),smooth=False)
    a.solve_generated=lambda: {'controller_finished':True}
    return a


@pytest.mark.parametrize('task',[f'E{i:02}'for i in range(1,51)])
def test_fifty_positive_routes_are_attempts_and_actual_goal_contract_exists(task):
    c=ref.reference_capability(task);assert c['implemented'] and not c['native_validated']
    if c['route']=='generated_placement':
        s=load(task,'A',4201,Path(__file__).parents[1]/'configs/realworld_full50_bindings.json',verify_files=False)
        assert s['goals'] and all(g['type']=='place'for g in s['goals'])
    for negative in ref.NEGATIVES:
        from videoicl_isaaclab.execution_design_back25_negative import CAPABILITIES
        from videoicl_isaaclab.execution_design_event_negative import CAPABILITIES as EVENT_CAPABILITIES
        from videoicl_isaaclab.execution_design_front13_negative import CAPABILITIES as FRONT13_CAPABILITIES
        from videoicl_isaaclab.execution_design_front13_grasp_negative import CAPABILITIES as GRASP_CAPABILITIES
        from videoicl_isaaclab.execution_design_e03_negative import CAPABILITIES as E03_CAPABILITIES
        from videoicl_isaaclab.execution_design_pose_negative import CAPABILITIES as POSE_CAPABILITIES
        from videoicl_isaaclab.execution_design_owned_hold_negative import CAPABILITIES as OWNED_HOLD_CAPABILITIES
        assert ref.reference_capability(task,negative)['implemented']==((task in WORKFLOW_TASKS) or (task in ('E23','E24') and negative in ('wrong_rule','wrong_destination','not_released')) or (task in ('E26','E30') and negative in ('wrong_rule','not_released')) or negative in CAPABILITIES.get(task,()) or negative in EVENT_CAPABILITIES.get(task,()) or negative in FRONT13_CAPABILITIES.get(task,()) or negative in GRASP_CAPABILITIES.get(task,()) or negative in POSE_CAPABILITIES.get(task,()) or negative in E03_CAPABILITIES.get(task,()) or negative in OWNED_HOLD_CAPABILITIES.get(task,()))


def test_e06_uses_real_placement_not_unsupported_mechanism_policy(monkeypatch):
    a=author();calls=[]
    def generic():
        assert a._execution_design_reference_authorized
        calls.append('placement');a.c.steps+=1
        return {'controller_finished':True}
    a.solve_generated=generic
    monkeypatch.setattr(ref,'solve_mechanism',lambda a:pytest.fail('E06 mechanism expert unsupported'))
    result=ref.solve_execution_reference(a)
    assert calls==['placement'] and result['actions']==1
    assert not a._execution_design_reference_authorized
    assert result['physics_success_not_asserted'] and not result['eligible_as_model_demo']


@pytest.mark.parametrize('task,fn',[('E01','solve_execution_design'),('E03','solve_e03_reference'),('E18','solve_e18_reference'),('E40','solve_tool')])
def test_explicit_registered_routes(task,fn,monkeypatch):
    calls=[];a=author(task)
    if fn=='solve_e18_reference':
        from videoicl_isaaclab import execution_design_e18_reference as e18
        monkeypatch.setattr(e18,fn,lambda a:calls.append(task) or {'attempt_only':True})
    else:monkeypatch.setattr(ref,fn,lambda a:calls.append(task) or {'attempt_only':True})
    result=ref.solve_execution_reference(a)
    assert calls==[task] and result['native_validation_required']


def test_reference_permission_restored_after_native_control_failure():
    a=author()
    def fail():raise RuntimeError('actual grip lost')
    a.solve_generated=fail
    with pytest.raises(RuntimeError,match='grip lost'):ref.solve_execution_reference(a)
    assert a._execution_design_reference_authorized is False


def test_wrong_source_and_smooth_routes_fail_before_any_action():
    a=author();a.scene.spec['execution_design']['source_sha256']='bad'
    with pytest.raises(ValueError,match='checksum'):ref.solve_execution_reference(a)
    a=author();a.smooth=True
    with pytest.raises(ValueError,match='individually'):ref.solve_execution_reference(a)
    assert a.c.steps==0


def test_e03_single_hand_policy_is_local_and_still_runs_real_controller_route(monkeypatch):
    from copy import deepcopy
    from videoicl_isaaclab import realworld_structural_expert as structural
    original={'red':{'local':[0,0,0],'jaw_axis_local':[1,0,0]},'blue':{'local':[1,2,3],'jaw_axis_local':[0,1,0],'hand':'right'}}
    before=deepcopy(original);calls=[]
    class Policy:
        def __init__(self,a):
            self.task='E03';self.variant='A';self.grasps=original;self.c=a.c;self.start=self.c.steps;self.operations=[]
        def nest(self):
            assert all(g['hand']=='left' for g in self.grasps.values())
            assert self.grasps['blue']['local']==[1,2,3]
            calls.append('physical_nest');self.c.steps+=7
        def wait(self,n):assert n==4;calls.append('native_settle')
    monkeypatch.setattr(structural,'StructuralAuthor',Policy)
    result=ref.solve_e03_reference(author('E03'))
    assert original==before
    assert calls==['physical_nest','native_settle'] and result['actions']==7
    assert result['physics_success_not_asserted']
