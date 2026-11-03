"""Resume only the explicit physical E40 stage in a diagnostic checkpoint."""
import json
from .engineering_checkpoint import capture
from .execution_design_clip_handover import handover_supported_clip, squeeze_after_handover, plan_direct_handles, squeeze_direct_handles, open_clip_hand
from .realworld_tool_expert import ToolAuthor


def solve(author, checkpoint, request):
    if author.scene.spec['id'] != 'E40' or not hasattr(author, '_engineering_resume_checkpoint'):
        raise ValueError('Explicit E40 checkpoint diagnostic required')
    entry = request['entry']; context = request.get('context', {})
    if entry not in ('e40-jaw-handover', 'e40-handle-squeeze', 'e40-cooked-only', 'e40-remaining-from-supported-clip', 'e40-remaining-from-jaw-hold', 'e40-table-supported-remainder', 'e40-clamp-from-open-handles', 'e40-remaining-from-table-clip'):
        raise ValueError('Unknown E40 checkpoint suffix')
    policy = ToolAuthor(author)
    clip_id = context.get('clip_id', 'clip1')
    clip = policy.s['clips'][clip_id]
    if entry == 'e40-cooked-only':
        from .engineering_e40_geometry_audit import audit
        return audit(author, policy, clip)
    first = context.get('first', 'right'); holder = context.get('holder', 'left')
    if {first, holder} != {'left', 'right'}:
        raise ValueError('Distinct actual E40 hands required')
    handle_ref = policy.clip_ref(clip, 'handle_grasp')
    source_body_ref = policy.clip_ref(clip, 'body_grasp')
    body_ref = source_body_ref if policy.held(source_body_ref, first) else dict(
        source_body_ref, grasp_contacts=handle_ref['grasp_contacts'])
    if entry in ('e40-remaining-from-supported-clip', 'e40-remaining-from-jaw-hold', 'e40-table-supported-remainder', 'e40-clamp-from-open-handles', 'e40-remaining-from-table-clip'):
        marker_index = context.get('marker_index', 0)
        if type(marker_index) is not int or not 0 <= marker_index < (3 if policy.index == 2 else 2):
            raise ValueError('Actual E40 marker continuation index required')
        if list(policy.s['clips'])[marker_index] != clip_id:
            raise ValueError('Distinct physical clip must match its marker continuation')
        if marker_index:
            from .execution_design_clip_edge_alignment import require_prior_physical_clamps
            require_prior_physical_clamps(policy,marker_index)
        if entry == 'e40-remaining-from-table-clip':
            from .execution_design_clip_table_support import squeeze_table_clip
            policy._e40_table_supported_reference = True
            active = squeeze_table_clip(policy, clip, handle_ref, body_ref, holder)
        elif entry == 'e40-clamp-from-open-handles':
            policy._e40_table_supported_reference = True
            active = holder
            policy.require_held(handle_ref, active)
        elif entry == 'e40-table-supported-remainder':
            from .execution_design_clip_table_support import squeeze_from_table
            policy._e40_table_supported_reference = True
            active = squeeze_from_table(policy, clip, handle_ref, body_ref, first, holder)
        elif entry == 'e40-remaining-from-jaw-hold':
            plan = context.get('handover_plan')
            if not isinstance(plan, dict) or not isinstance(plan.get('holder_ref'), dict):
                raise ValueError('Actual preceding jaw-hold plan required')
            policy.require_held(plan['holder_ref'], holder)
            from .engineering_e40_robot_contact_readback import install
            contacts = install(author)
            try:
                active = squeeze_after_handover(policy, clip, handle_ref, first, holder, body_ref, plan)
            finally:
                contacts['flush']()
        else:
            active = _squeeze_from_back(policy, clip, handle_ref, body_ref, first, holder)
        _finish_remaining(policy, clip, handle_ref, active, marker_index)
        context = dict(context, remaining_clip_sequence_completed=True)
    elif entry == 'e40-jaw-handover':
        policy.require_held(body_ref, first)
        plan = handover_supported_clip(policy, clip, handle_ref, first, holder, body_ref)
        policy.require_held(plan.get('holder_ref', body_ref), holder)
        context = dict(context, handover_plan=plan)
    else:
        plan = context.get('handover_plan') or checkpoint.get('context', {}).get('handover_plan')
        if not isinstance(plan, dict):
            raise ValueError('Actual preceding handover plan required for checked retreat')
        policy.require_held(plan.get('holder_ref', body_ref), holder)
        squeeze_after_handover(policy, clip, handle_ref, first, holder, body_ref, plan)
        policy.require_held(handle_ref, first)
        if policy.clip_gap(clip)[0] < clip['expert']['open_gap_m']:
            raise ValueError('Actual clip handles did not open the mouth')
    saved = capture(author.c, entry + '-passed', context=context)
    path = author.out / 'checkpoint-stage-passed.private.json'
    path.write_text(json.dumps(saved, indent=2) + '\n'); path.chmod(0o600)
    return dict(task='E40', entry=entry, local_stage_passed=True, segment_passed=True,
                diagnostic_only=True, checkpoint=str(path), actions=author.c.steps,
                execution_finished=True, physics_success_not_asserted=True)


def _squeeze_from_back(policy, clip, handle_ref, body_ref, first, holder):
    policy.require_held(body_ref, first)
    open_clip_hand(policy, holder, lambda: policy.require_held(body_ref, first))
    direct = plan_direct_handles(policy, clip, first, holder)
    if direct is not None:
        active = squeeze_direct_handles(policy, clip, handle_ref, body_ref, first, holder, direct)
    else:
        plan = handover_supported_clip(policy, clip, handle_ref, first, holder, body_ref)
        active = squeeze_after_handover(policy, clip, handle_ref, first, holder, body_ref, plan)
    return active


def _finish_remaining(policy, clip, handle_ref, active, marker_index=0):
    if getattr(policy, '_e40_table_supported_reference', False):
        from .execution_design_clip_edge_alignment import align_open_clip
        align_open_clip(policy, clip, handle_ref, active)
    policy.stage('clip-first-marker-from-checkpoint')
    marker = (['circle','cross'], ['square','triangle'], ['circle','triangle','cross'])[policy.index][marker_index]
    zone = next(z for z in policy.spec['zones'] if z['id'] == marker)
    import numpy as np
    point = np.asarray(zone['edge_point']); axis = np.asarray(clip['expert']['insert_direction_task'], float)
    if getattr(policy, '_e40_table_supported_reference', False):
        from .execution_design_clip_edge_alignment import insertion_point
        point = insertion_point(policy, clip, point)
    axis /= np.linalg.norm(axis)
    policy.clip_move(clip, handle_ref, active, point - axis * .03)
    policy.clip_move(clip, handle_ref, active, point)
    policy.release(handle_ref, active); policy.wait(3)
    if not policy.clip_contact(clip, zone['support']):
        raise ValueError('Actual clip jaws did not clamp first marked tray edge')
    policy.move(active, policy.tip(active) - axis * .03 + [0.,0.,.04])
    policy.clip_edges(start_index=marker_index+1)
