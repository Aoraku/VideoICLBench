"""Engineering candidate: approach each real branch from its exposed end.

No native pass is claimed by this route. Every move retains the actual grip
guard and the unchanged evaluator checks real cavity insertion after release.
"""
import numpy as np
from .realworld_structural_expert import StructuralAuthor
from .realworld_tool_expert import ToolExecutionError
from .realworld_tool_evidence import _unit


def branch_entry_geometry(base,tip,height):
    base=np.asarray(base,float);tip=np.asarray(tip,float)
    if base.shape!=(3,) or tip.shape!=(3,) or not np.isfinite([*base,*tip,height]).all() or height<=.008:
        raise ValueError('Finite measured branch and cup dimensions required')
    axis=_unit(tip-base)
    # Mouth stays beyond the exposed tip until the final axial insertion.
    return dict(axis=axis,exterior=tip+axis*(height+.045),
                entry=tip+axis*.03,target=tip-axis*(height-.008))


def solve_e23_reference(author):
    return _solve_e23_reference(author,'positive')


def solve_e23_negative_reference(author,control):
    """Independent public-action counterexample attempt, not a pass flag."""
    if control not in ('wrong_rule','wrong_destination','not_released'):
        raise ValueError('Unreviewed E23 physical counterexample')
    return _solve_e23_reference(author,control)


def _solve_e23_reference(author,control):
    control_kind=control
    if control!='positive':
        from .execution_design import REVISION_V3,source_sha256
        design=author.scene.spec.get('execution_design',{})
        if (design.get('revision')!=REVISION_V3 or design.get('source_sha256')!=source_sha256(REVISION_V3)
                or not getattr(author,'control_report',{}).get('engineering_reference_only')):
            raise ValueError('E23 counterexample requires explicit v3 independent engineering authorization')
    p=StructuralAuthor(author)
    if p.task!='E23':raise ValueError('E23 branch reference only')
    branches=p.s['branches'];heights={k:p.body_point(v['ref'],v['tip_local'])[2] for k,v in branches.items()};groups=[]
    for key in sorted(heights,key=heights.get,reverse=True):
        if not groups or abs(heights[key]-heights[groups[-1][0]])>.01:groups.append([])
        groups[-1].append(key)
    if len(groups)!=3:raise ToolExecutionError('Three actual branch levels required')
    order=(['red','green','blue'],['red','blue','green'],['blue','green','red'])[p.index]
    original_order=list(order);order=list(order)
    if control=='wrong_rule':order[0],order[1]=order[1],order[0]
    for index,(label,group) in enumerate(zip(order,groups)):
        name=p.identity[label];branch=branches[group[0]];cup=p.s['cups'][name]
        ref,side=p.pickup(name)
        g=branch_entry_geometry(p.body_point(branch['ref'],branch['base_local']),
                               p.body_point(branch['ref'],branch['tip_local']),
                               float(np.linalg.norm(np.asarray(cup['rim_local'])-cup['bottom_local'])))
        from .execution_design_e23_orientation import align_cup_axis_incremental as align_cup_axis
        from .execution_design_e23_clearance import prepare_rotation_workspace,verify_rotation_clearance,restore_rotation_station
        prepare_rotation_workspace(p,name,side)
        align_cup_axis(p,name,side,cup['axis_local'],-g['axis'],
            clearance_guard=lambda phase:verify_rotation_clearance(p,name,side,phase),
            maintain_position=lambda:restore_rotation_station(p,name,side))
        control=dict(actor=name,local=cup['rim_local'])
        support=branch['ref'].get('actor',branch['ref'].get('contact_body'))
        def held():p.require_held(ref,side)
        def free_approach():
            held()
            if p.contact(name,support):raise ToolExecutionError('Premature cup/tree contact before axial insertion')
        # The old route demanded a horizontal-wrist cup mouth at z=1.15m,
        # although the highest real branch is ~1.05m. Move outside its end
        # first, then descend along the measured branch axis. This is a
        # physically guarded attempt, not an assumption of collision freedom.
        p.stage('branch-exterior-approach-'+label)
        level=max(float(p.point(control)[2]),float(g['exterior'][2])+.025)
        p.move_point(side,control,[*p.point(control)[:2],level],free_approach)
        p.move_point(side,control,[*g['exterior'][:2],level],free_approach)
        p.move_point(side,control,g['exterior'],free_approach)
        p.stage('cup-mouth-over-real-branch-'+label)
        p.move_point(side,control,g['entry'],free_approach)
        # Counterexamples change only the independent reference's real moves.
        # Preserve the first two correct insertions for endpoint/release tests.
        omit_insertion=control_kind=='wrong_destination'and index==2
        keep_held=control_kind=='not_released'and index==2
        if not omit_insertion:p.move_point(side,control,g['target'],held)
        if keep_held:
            p.stage('negative-retain-third-cup-actual-grip');p.wait(4);held()
            continue
        p.release(ref,side)
        p.move(side,p.tip(side)+g['axis']*.03+[0,0,.04]);p.wait(3)
        if not omit_insertion and not p.contact(name,support):raise ToolExecutionError('Released cup lacks real branch support')
    p.wait(4)
    return dict(task=p.task,variant=p.variant,actions=p.c.steps-p.start,
                operations=p.operations,execution_finished=True,
                physics_success_not_asserted=True,route='exterior_branch_axis',
                control=control_kind,perturbation=None if control_kind=='positive'else dict(
                    control=control_kind,expected_color_order=original_order,attempted_color_order=order,
                    third_cup_stops_before_insertion=control_kind=='wrong_destination',
                    third_cup_release_omitted=control_kind=='not_released',
                    native_condition_observed=None))
