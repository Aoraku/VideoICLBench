"""E26-only engineering counterexamples via public actions; never policy input."""
from copy import deepcopy
from .execution_design import REVISION_V3, source_sha256
from .execution_design_inputs import e26_targets
from .realworld_mechanism_expert import _Author, MechanismExecutionError

CONTROLS = frozenset(('wrong_rule', 'not_released'))


class BellNegativeAuthor(_Author):
    def __init__(self, author, control):
        spec = author.scene.spec
        design = spec.get('execution_design', {})
        if (spec.get('id') != 'E26' or control not in CONTROLS
                or design.get('revision') != REVISION_V3
                or design.get('source_sha256') != source_sha256(REVISION_V3)
                or spec.get('author_smooth_recording') or getattr(author, 'smooth', False)):
            raise ValueError('Explicit v3 E26 public-action negative required')
        super().__init__(author)
        self.control = control
        expected = e26_targets(spec)
        attempted = deepcopy(expected)
        # A guaranteed mismatch even when the two digit cards are equal.
        if control == 'wrong_rule':
            attempted['left'] += 1
            held_role = None
        else:
            held_role = next(r for r in ('right', 'left') if expected[r] > 0)
            attempted[held_role] -= 1
        self.perturbation = dict(control=control, task='E26', expected=expected,
            attempted_completed_cycles=attempted, held_role=held_role,
            validation='native_observation_required',
            not_applicable=['wrong_members', 'wrong_destination'])

    def solve_negative(self):
        for role, count in self.perturbation['attempted_completed_cycles'].items():
            for index in range(1, count + 1):
                self.press(role, index)
        role = self.perturbation['held_role']
        if role is not None:
            side = self.hand(role)
            self.stage('engineering-negative-bell-hold-' + role)
            self.act(side, 'GRASP')
            self.approach(role, side, button=True)
            if (abs(self.displacement(role)) > self.roles[role]['closed_tolerance']
                    or not self.no_touch(role)):
                raise MechanismExecutionError('Held negative must start from a released bell')
            self.press_steps(role, side, self.tip(side))
            # Do not retreat. Physical contact and displacement must persist
            # through real STILL ticks, rather than a commanded held flag.
            for _ in range(3):
                self.act()
                if (self.displacement(role) < self.roles[role]['open_threshold']
                        or not self.touching(role, side)):
                    raise MechanismExecutionError('Negative press was not physically held')
            self.operations.append(dict(operation='press_hold', role=role,
                pressed=self.displacement(role), actual_contact=True))
        else:
            for _ in range(3):
                self.act()
        return dict(task=self.task, variant=self.variant, control=self.control,
            actions=self.c.steps-self.start_steps, operations=self.operations,
            perturbation=deepcopy(self.perturbation), execution_finished=True,
            negative_condition_observed=None, native_validation_required=True,
            engineering_reference_only=True, eligible_as_model_demo=False)
