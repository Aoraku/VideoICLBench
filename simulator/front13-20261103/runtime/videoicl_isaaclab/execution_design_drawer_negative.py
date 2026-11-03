"""E30 counterexamples executed by the real public-action drawer reference."""
from copy import deepcopy
from .execution_design import REVISION_V3,source_sha256
from .realworld_mechanism_expert import _Author,MechanismExecutionError

CONTROLS=frozenset(('wrong_rule','not_released'))
SELECTED={'A':('upper',),'B':('lower',),'C':('upper','lower')}

class DrawerNegativeAuthor(_Author):
    def __init__(self,author,control):
        spec=author.scene.spec;design=spec.get('execution_design',{})
        if (spec.get('id')!='E30' or control not in CONTROLS
                or design.get('revision')!=REVISION_V3
                or design.get('source_sha256')!=source_sha256(REVISION_V3)
                or spec.get('author_smooth_recording') or getattr(author,'smooth',False)):
            raise ValueError('Explicit v3 E30 public-action negative required')
        super().__init__(author);self.control=control
        attempted={'A':'B','B':'A','C':'A'}[self.variant]if control=='wrong_rule'else self.variant
        self.perturbation=dict(control=control,task='E30',expected_variant=self.variant,
            expected_open=list(SELECTED[self.variant]),attempted_open=list(SELECTED[attempted]),
            attempted_reference_variant=attempted,held_role=SELECTED[self.variant][0]if control=='not_released'else None,
            native_spec_unchanged=True,validation='native_observation_required',
            not_applicable=['wrong_members','wrong_destination'])

    def solve_negative(self):
        source_variant=self.variant
        # Change only the private reference strategy. The original scene,
        # evaluator, source goals, initial joints and revision remain untouched.
        self.variant=self.perturbation['attempted_reference_variant']
        try:super().solve()
        finally:self.variant=source_variant
        role=self.perturbation['held_role']
        if role is not None:
            side=self.acquire(role);self.stage('engineering-negative-drawer-held-'+role)
            for _ in range(3):
                self.act()
                if not self.touching(role,side,both=True):
                    raise MechanismExecutionError('Negative drawer hold lacks actual bilateral contact')
            self.operations.append(dict(operation='hold_selected_handle',role=role,side=side,
                actual_bilateral_contact=True,measured_displacement=self.displacement(role)))
        return dict(task=self.task,variant=source_variant,control=self.control,
            actions=self.c.steps-self.start_steps,operations=self.operations,
            perturbation=deepcopy(self.perturbation),execution_finished=True,
            negative_condition_observed=None,native_validation_required=True,
            engineering_reference_only=True,eligible_as_model_demo=False)
