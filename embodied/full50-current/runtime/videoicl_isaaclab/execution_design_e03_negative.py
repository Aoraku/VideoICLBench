"""E03 engineering counterexamples through the proven public nesting route.

No world, semantic, goal or evaluator mutation. Physical acceptance requires independent
native review. Returning is never a physics
certificate; wrong_members and wrong_destination reject the same missing edge.
"""
from copy import deepcopy
import numpy as np
from .execution_design import REVISION_V3, source_sha256
from .realworld_structural_expert import StructuralAuthor
from .realworld_tool_expert import ToolExecutionError

CONTROLS=frozenset(('wrong_members','wrong_destination','wrong_rule','not_released'))
CAPABILITIES={'E03':CONTROLS}


def negative_plan(spec,control):
    design=spec.get('execution_design',{})
    if (spec.get('id')!='E03' or control not in CONTROLS or
            design.get('revision')!=REVISION_V3 or
            design.get('source_sha256')!=source_sha256(REVISION_V3)):
        raise ValueError('Reviewed v3 E03 physical counterexample required')
    order=(('red','green','blue'),('green','blue','red'),('blue','red','green'))['ABC'.index(spec['variant'])]
    identities={o.get('semantic_identity',o.get('identity',o['id'])):o['id'] for o in spec['objects']}
    names=[identities[n] for n in order]
    if set(names)!=set(spec['semantic']['cups']):raise ValueError('Three original measured cups required')
    original_names=list(names)
    if control=='wrong_rule':names=names[1:]+names[:1]
    return dict(task='E03',control=control,outer_to_inner=names,original_outer_to_inner=original_names,
        omitted_or_held_member=names[-1],native_review_required=True,
        negative_condition_observed=None,
        terminal_predicate=('release' if control=='not_released' else 'incorrect_full_nesting_order' if control=='wrong_rule' else 'missing_final_nesting_edge'),
        required_native_review=(
            'All three original cups genuinely form the alternative complete nesting chain, released, stable and supported on table; unchanged original order rule must reject.'
            if control=='wrong_rule' else
            'First pair genuinely nested with contact and table support; final inner cup actually held at intended nesting pose for three STILL actions; original release rejects.'
            if control=='not_released' else
            'First pair genuinely nested, released and stable; final inner cup remains outside with table support. '+
            ('Require actual pickup/lift and return trajectory.' if control=='wrong_destination' else 'Require original final-cup source pose unchanged.')),
        geometry_scope='Measured profiles admit alternative orders analytically; actual collision, support and stability remain unverified. Failed motion is never a counterexample.')


class _ExpectedStop(Exception):
    pass


class E03NegativeAuthor(StructuralAuthor):
    def __init__(self,author,control):
        self.perturbation=negative_plan(author.scene.spec,control)
        if (getattr(author,'smooth',False) or author.scene.spec.get('author_smooth_recording') or
                not getattr(author,'control_report',{}).get('engineering_reference_only')):
            raise ValueError('Explicit engineering public actions required')
        super().__init__(author)
        if control=='wrong_rule':self.index=(self.index+1)%3
        self.control=control;self.completed_pairs=0;self.last=self.perturbation['outer_to_inner'][-1]
        self.grasps=deepcopy(self.grasps)
        for grasp in self.grasps.values():grasp['hand']='left'
        self.source_bottom=None;self.source_rotation=None;self.final_target=None
        self.intentional_stop=False;self.hold_checks=0

    def pickup(self,name):
        if name==self.last:
            if self.completed_pairs!=1:raise ToolExecutionError('First real nesting pair has not completed')
            if self.control=='wrong_members':
                self.intentional_stop=True;raise _ExpectedStop()
            self.source_bottom=self.body_point({'actor':name},self.s['cups'][name]['bottom_local']).copy()
            self.source_rotation=self.snapshot()[0][name]['mat'].copy()
        return super().pickup(name)

    def lower_place(self,name,ref,side,local_point,target,rotation=None,support=None):
        if name==self.last:
            if self.control=='wrong_destination':
                if self.source_bottom is None:raise ToolExecutionError('Actual original source pose missing')
                target=self.source_bottom;rotation=self.source_rotation;support='table'
                self.stage('negative-lift-return-final-inner-cup')
            self.final_target=np.asarray(target,dtype=float).copy()
        super().lower_place(name,ref,side,local_point,target,rotation,support)
        self.completed_pairs+=1

    def release(self,ref,side):
        if self.control=='not_released' and ref.get('actor')==self.last:
            if self.final_target is None:raise ToolExecutionError('Intended destination was not reached')
            for _ in range(3):
                self.require_held(ref,side)
                actual=self.body_point({'actor':self.last},self.s['cups'][self.last]['bottom_local'])
                if np.max(np.abs(actual-self.final_target))>.006:
                    raise ToolExecutionError('Held inner cup is outside intended nesting pose')
                self.wait(1);self.require_held(ref,side)
                actual=self.body_point({'actor':self.last},self.s['cups'][self.last]['bottom_local'])
                if np.max(np.abs(actual-self.final_target))>.006:
                    raise ToolExecutionError('Held inner cup drifted outside intended nesting pose')
                self.hold_checks+=1
            self.intentional_stop=True;raise _ExpectedStop()
        return super().release(ref,side)

    def solve_negative(self):
        original=self.a.scene;before=deepcopy(original.spec)
        try:
            try:self.nest()
            except _ExpectedStop:
                if not self.intentional_stop:raise
            if self.control=='not_released':
                if self.hold_checks!=3:raise ToolExecutionError('Actual stable held witness missing')
            else:self.wait(4)
            return dict(task='E03',control=self.control,actions=self.c.steps-self.start,
                operations=self.operations,perturbation=self.perturbation,
                execution_finished=True,negative_condition_observed=None,
                native_validation_required=True,physics_success_not_asserted=True)
        finally:
            if self.a.scene is not original or original.spec!=before:
                raise RuntimeError('E03 counterexample changed original world specification')
