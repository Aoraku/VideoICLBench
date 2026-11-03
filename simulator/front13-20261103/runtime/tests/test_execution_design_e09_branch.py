"""A checkpoint branch must preserve case identity, cumulative steps and lineage."""
from copy import deepcopy
from pathlib import Path
import pytest
from videoicl_isaaclab.realworld_scenes import load
from videoicl_isaaclab.execution_design_e09_branch import validate_context,remaining_group_instructions
from videoicl_isaaclab.realworld_tool_expert import ToolExecutionError
V=Path(__file__).resolve().parents[2]/'verification/task-design-revision-20261102'
def spec(variant='A'):return load('E09',variant,4201,V/'release-v3-full50-r1/bindings/I.private.json',verify_files=False)
def context(s,steps=3813):return dict(parent_checkpoint='native-source-sha',assignment_identity_sha256=s['execution_design']['assignment_identity_sha256'],source_cumulative_steps=steps)
def test_original_pre_blue_boundary_is_admitted_without_count_reset():
    s=spec();validate_context(s,'pre_blue',3813,context(s))
@pytest.mark.parametrize('change',['missing_lineage','identity','steps','new_seed','variant','condition'])
def test_wrong_source_or_physical_case_is_rejected(change):
    s=spec();c=context(s)
    if change=='missing_lineage':c.pop('parent_checkpoint')
    if change=='identity':c['assignment_identity_sha256']='other'
    if change=='steps':c['source_cumulative_steps']=0
    if change=='new_seed':s['seed']=4202
    if change=='variant':s['variant']='B'
    if change=='condition':s['execution_design']['condition']='E'
    with pytest.raises(ToolExecutionError):validate_context(s,'pre_blue',3813,c)
def test_uncreated_post_local_state_is_rejected():
    s=spec();c=context(s,4500)
    with pytest.raises(ToolExecutionError):validate_context(s,'post_local_all',4500,c)
def test_saved_actual_post_local_boundary_keeps_cumulative_steps():
    s=spec();c=context(s,4500);c.update(e09_entry='post_local_all',local_stage_native_completed=True,created_by='physical_e09_pre_blue_branch')
    validate_context(s,'post_local_all',4500,c)

def test_saved_pre_collision_native_prefix_keeps_original_cumulative_lineage():
    s=spec();c=context(s);c.update(e09_entry='pre_blue',branch_name='pre_blue',branch_start_step=3813,branch_local_actions=59)
    validate_context(s,'park_blue',3872,c)
    c['branch_local_actions']-=1
    with pytest.raises(ToolExecutionError):validate_context(s,'park_blue',3872,c)

def test_blue_continuation_requires_actual_park_boundary_and_current_counter():
    s=spec();c=context(s,3950);c.update(e09_entry='blue_local',created_by='physical_e09_park_blue_branch',actual_empty_arm_parked=True)
    validate_context(s,'blue_local',3950,c)
    c['actual_empty_arm_parked']=False
    with pytest.raises(ToolExecutionError):validate_context(s,'blue_local',3950,c)
@pytest.mark.parametrize('variant',list('ABC'))
def test_remaining_stage_uses_only_original_third_group_and_original_slots(variant):
    s=spec(variant);before=deepcopy(s);d=s['execution_design'];steps=remaining_group_instructions(d)
    assert {x['actor']for x in steps}==set(d['unordered_expected_groups'][2])
    assert all(x['container']==d['local_regions'][2]['actor']for x in steps)
    if any('triangle'in n for n in d['unordered_expected_groups'][2]):
        assert 'triangle'in steps[0]['actor']
    assert s==before
