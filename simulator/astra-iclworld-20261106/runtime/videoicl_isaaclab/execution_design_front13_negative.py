"""E04/E06/E07 engineering counterexamples using unchanged public actions.

Only the private reference plan changes. A physical failure does not establish
a negative witness; native state, support, release and rule checks still need
independent review.
"""
from copy import deepcopy

from .execution_design import REVISION_V3, source_sha256
from .execution_design_back25_negative import Back25NegativeAuthor, source_return_goal

CONTROLS = frozenset(('wrong_members', 'wrong_destination', 'wrong_rule', 'not_released'))
CAPABILITIES = {task: CONTROLS for task in ('E04', 'E06')}
CAPABILITIES['E07'] = CONTROLS - {'not_released'}


def negative_plan(spec, control):
    task = spec['id']
    design = spec.get('execution_design', {})
    if (control not in CAPABILITIES.get(task, ())
            or design.get('revision') != REVISION_V3
            or design.get('source_sha256') != source_sha256(REVISION_V3)):
        raise ValueError('Reviewed explicit v3 front-half counterexample required')
    plan = deepcopy(spec)
    goals = plan['goals']
    if len(goals) != (5 if task == 'E07' else 3) or any(g['type'] != 'place' for g in goals):
        raise ValueError('Original physical placement goal count required')
    plan['expert_preserve_goal_order'] = True
    delta = dict(task=task, control=control, original_goals=deepcopy(goals),
                 negative_condition_observed=None, native_review_required=True)
    if control == 'wrong_members':
        delta['omitted_member'] = goals.pop()['object']
        delta['required_native_review'] = (
            'All other objects must actually reach their correct targets; '
            'the omitted body must remain outside the required target.')
    elif control == 'wrong_destination':
        source_return_goal(plan, goals[-1])
        delta['outside_member'] = goals[-1]['object']
        delta['required_native_review'] = (
            'Actual pickup and lift followed by released table support at the '
            'original source, outside every required destination; no zero-action witness.')
    elif control == 'wrong_rule':
        if task == 'E04':
            targets = [g['target'] for g in goals]
            if len(set(targets)) != 3:
                raise ValueError('Three distinct original shape destinations required')
            for goal, target in zip(goals, targets[1:] + targets[:1]):
                goal['target'] = target
            delta['attempted_mapping'] = {g['object']: g['target'] for g in goals}
        elif task == 'E06':
            zones = {z['id'] for z in plan['zones']}
            for goal in goals:
                prefix, suffix = goal['target'].split('_', 1)
                if prefix not in ('left', 'right'):
                    raise ValueError('Original six-hole left/right topology required')
                goal['target'] = ('right' if prefix == 'left' else 'left') + '_' + suffix
                if goal['target'] not in zones:
                    raise ValueError('Mirrored hole must already exist in the source scene')
            delta['attempted_cells'] = [g['target'] for g in goals]
        else:
            # Keep all five real sizes and final row locations. Only the
            # private policy puts two sizes into the opposite rank positions.
            goals[0]['target'], goals[1]['target'] = goals[1]['target'], goals[0]['target']
            delta['attempted_ranks'] = {g['object']: g['target'] for g in goals}
        delta['required_native_review'] = (
            'All required objects actually released, supported and stable in the '
            'planned alternative mapping; original native rule must reject it.')
    else:
        delta['held_member'] = goals[-1]['object']
        delta['required_native_review'] = (
            'Final body actually at its intended destination and held by both '
            'fingers; the original native release predicate must reject it.')
    delta['attempted_goals'] = deepcopy(goals)
    return plan, delta


class Front13NegativeAuthor(Back25NegativeAuthor):
    """Reuse the public-action runner and its scene-proxy restoration guards."""
    def __init__(self, author, control):
        if getattr(author, 'smooth', False) or author.scene.spec.get('author_smooth_recording'):
            raise ValueError('Counterexample requires recorded public actions')
        self.author = author
        self.control = control
        self.plan, self.perturbation = negative_plan(author.scene.spec, control)
