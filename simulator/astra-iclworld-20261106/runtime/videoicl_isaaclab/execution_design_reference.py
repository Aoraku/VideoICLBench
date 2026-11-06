"""Explicit engineering-only positive routing for the frozen 50-task panel.

An implemented route is an attempt using existing native public robot actions,
not evidence of reachability or scoring acceptance. No policy API is called.
"""
from .execution_design import WORKFLOW_TASKS, SUPPORTED_REVISIONS, source_sha256
from .execution_design_expert import solve_execution_design
from .realworld_structural_expert import SUPPORTED as STRUCTURAL, solve_structural
from .realworld_tool_expert import SUPPORTED as TOOL, solve_tool
from .realworld_mechanism_expert import solve_mechanism

TASKS=frozenset(f'E{i:02}' for i in range(1,51))
MECHANISM=frozenset(('E18','E26','E30'))  # E06 evaluator is mechanism-aware; its expert is not.
NEGATIVES=frozenset(('wrong_members','wrong_destination','wrong_rule','not_released'))


def solve_e03_reference(author):
    """Keep the real sequential cup route on the already-proven left arm."""
    from copy import deepcopy
    from .realworld_structural_expert import StructuralAuthor
    policy=StructuralAuthor(author)
    if policy.task!='E03':raise ValueError('E03-specific physical hand assignment')
    # The former sign(y) policy changed hands for a central cup at y=-0.1mm.
    # The first arm was still across the midline after its released placement;
    # native body poses and the final image showed the second arm blocked by it.
    # This changes only the private reference's hand choice, never world state.
    policy.grasps=deepcopy(policy.grasps)
    for grasp in policy.grasps.values():grasp['hand']='left'
    policy.nest();policy.wait(4)
    return dict(task=policy.task,variant=policy.variant,actions=policy.c.steps-policy.start,
                operations=policy.operations,hand_policy='left_for_all_cups',
                execution_finished=True,physics_success_not_asserted=True)


def reference_capability(task,control='positive'):
    if task not in TASKS:
        return dict(implemented=False,reason='outside_frozen_50_task_panel',native_validated=False)
    if control!='positive':
        from .execution_design_owned_hold_negative import CAPABILITIES as OWNED_HOLD_CAPABILITIES
        if control in OWNED_HOLD_CAPABILITIES.get(task,()):
            return dict(implemented=True,reason='owned_final_bilateral_hold_public_action_counterexample',native_validated=False,required_revision='embodied50-execution-v3-20261102')
        from .execution_design_pose_negative import CAPABILITIES as POSE_CAPABILITIES
        if task in POSE_CAPABILITIES:
            return dict(implemented=control in POSE_CAPABILITIES[task],reason='measured_pose_public_action_counterexample' if control in POSE_CAPABILITIES[task] else 'no_independent_wrong_identity_member',native_validated=False,required_revision='embodied50-execution-v3-20261102')
        from .execution_design_e03_negative import CAPABILITIES as E03_CAPABILITIES
        if control in E03_CAPABILITIES.get(task,()):
            return dict(implemented=True,reason='reviewed_e03_public_nesting_counterexample',native_validated=False,required_revision='embodied50-execution-v3-20261102')
        from .execution_design_front13_grasp_negative import CAPABILITIES as GRASP_CAPABILITIES
        if control in GRASP_CAPABILITIES.get(task,()):
            return dict(implemented=True,reason='reviewed_front13_grasp_public_action_counterexample',native_validated=False,required_revision='embodied50-execution-v3-20261102')
        from .execution_design_front13_negative import CAPABILITIES as FRONT13_CAPABILITIES
        if control in FRONT13_CAPABILITIES.get(task,()):
            return dict(implemented=True,reason='reviewed_front13_public_action_counterexample',native_validated=False,required_revision='embodied50-execution-v3-20261102')
        if task in ('E23','E24') and control in ('wrong_rule','wrong_destination','not_released'):
            return dict(implemented=True,reason='v3_engineering_public_action_counterexample',native_validated=False,required_revision='embodied50-execution-v3-20261102')
        from .execution_design_back25_negative import CAPABILITIES
        from .execution_design_event_negative import CAPABILITIES as EVENT_CAPABILITIES
        if control in EVENT_CAPABILITIES.get(task,()):
            return dict(implemented=True,reason='actual_event_counterexample_requires_native_history',native_validated=False)
        if task=='E43' and control=='wrong_rule':
            return dict(implemented=False,reason='duplicate_of_wrong_destination_not_an_independent_control',native_validated=False)
        if control in CAPABILITIES.get(task,()):
            return dict(implemented=True,reason='reviewed_back25_public_action_counterexample',native_validated=False)
        if task in ('E32','E33','E34','E36','E47','E48') and control=='wrong_rule':
            return dict(implemented=False,reason='duplicate_of_wrong_members_not_an_independent_control',native_validated=False)
        if task=='E30' and control in ('wrong_rule','not_released'):
            return dict(implemented=True,reason='drawer_negative_public_action_attempt',native_validated=False)
        implemented=(control in NEGATIVES and task in WORKFLOW_TASKS) or (task=='E26' and control in ('wrong_rule','not_released'))
        return dict(implemented=implemented,reason=('bell_negative_public_action_attempt' if task=='E26' else 'workflow_negative_public_action_attempt') if implemented else 'negative_public_action_route_not_implemented',native_validated=False)
    route=('workflow' if task in WORKFLOW_TASKS else 'structural' if task in STRUCTURAL
           else 'tool' if task in TOOL else 'mechanism' if task in MECHANISM else 'generated_placement')
    return dict(implemented=True,route=route,reason='existing_public_action_route_requires_native_validation',native_validated=False)


def solve_execution_reference(author):
    spec=author.scene.spec;design=spec.get('execution_design',{});revision=design.get('revision')
    if revision not in SUPPORTED_REVISIONS or design.get('source_sha256')!=source_sha256(revision):
        raise ValueError('Explicit checksum-validated execution-design contract required')
    if spec.get('task_revision',revision)!=revision:
        raise ValueError('Task revision disagrees with engineering reference contract')
    if hasattr(author, '_engineering_resume_checkpoint'):
        from .engineering_checkpoint_reference import solve_suffix
        return solve_suffix(author)
    capability=reference_capability(spec['id'])
    if not capability['implemented']:raise NotImplementedError(capability['reason'])
    if spec.get('author_smooth_recording',False) or getattr(author,'smooth',False):
        raise ValueError('Engineering reference requires individually recorded public actions')
    author.control_report.update(engineering_reference_only=True,eligible_as_model_demo=False,
                                 local_rule_demo=False,execution_reference_route=capability['route'])
    task=spec['id'];start=author.c.steps
    import os
    if task=='E47'and os.environ.get('VIC_E47_FIXTURE_INITIAL_ONLY')=='1':
        from .execution_design_e47_fixture import verify_native_initial
        verify_native_initial(author)
        raise RuntimeError('E47 zero-action flip-device diagnostic only; not whole task acceptance')
    if task in ('E47','E48','E49') and os.environ.get('VIC_ENGINEERING_CARD_REFERENCE')=='1':
        from .execution_design_cards_reference import solve
        report=solve(author)
    elif task in WORKFLOW_TASKS:report=solve_execution_design(author)
    elif task=='E03':report=solve_e03_reference(author)
    elif task=='E08' and revision=='embodied50-execution-v3-20261102':
        from .execution_design_e08_reference import solve_e08_reference
        report=solve_e08_reference(author)
    elif task=='E13' and revision=='embodied50-execution-v3-20261102':
        from .execution_design_e13_functional import solve
        report=solve(author)
    elif task=='E23' and revision=='embodied50-execution-v3-20261102':
        from .execution_design_e23_reference import solve_e23_reference
        report=solve_e23_reference(author)
    elif task=='E24' and revision=='embodied50-execution-v3-20261102':
        from .execution_design_e24_reference import solve_e24_reference
        report=solve_e24_reference(author)
    elif task=='E37'and os.environ.get('VIC_ENGINEERING_E37_SOURCE_FULL')=='1':
        from .execution_design_e37_source import solve
        report=solve(author)
    elif task=='E37'and os.environ.get('VIC_ENGINEERING_E37_SOURCE_LEFT_PREFIX')=='1':
        from .execution_design_e37_source_left import acquire_left
        report=acquire_left(author)
    elif task in STRUCTURAL:report=solve_structural(author)
    elif task in TOOL:report=solve_tool(author)
    elif task=='E18' and revision=='embodied50-execution-v3-20261102':
        from .execution_design_e18_reference import solve_e18_reference
        old=getattr(author,'_execution_design_reference_authorized',False)
        author._execution_design_reference_authorized=True
        try:report=solve_e18_reference(author)
        finally:author._execution_design_reference_authorized=old
    elif task in MECHANISM:report=solve_mechanism(author)
    else:
        if not spec.get('goals') or any(g.get('type')!='place' for g in spec['goals']):
            raise NotImplementedError('Reviewed physical placement goals required: '+task)
        # Narrow temporary dispatch permission, not an evaluator success flag.
        old=getattr(author,'_execution_design_reference_authorized',False)
        author._execution_design_reference_authorized=True
        try:report=author.solve_generated()
        finally:author._execution_design_reference_authorized=old
    return dict(task=task,variant=spec['variant'],revision=revision,route=capability['route'],
                actions=author.c.steps-start,controller_report=report,execution_finished=True,
                engineering_reference_only=True,eligible_as_model_demo=False,
                physics_success_not_asserted=True,native_validation_required=True)
