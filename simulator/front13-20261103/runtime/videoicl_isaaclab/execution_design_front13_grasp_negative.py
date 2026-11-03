"""Private E02/E05/E11 counterexample recipes; native evaluator unchanged."""
from copy import deepcopy
from .execution_design import REVISION_V3,source_sha256
from .execution_design_back25_negative import Back25NegativeAuthor,source_return_goal

CONTROLS=frozenset(('wrong_members','wrong_destination','wrong_rule','not_released'))
CAPABILITIES={task:CONTROLS for task in ('E02','E05','E11')}


def negative_plan(spec,control):
    task=spec['id'];design=spec.get('execution_design',{})
    if (control not in CAPABILITIES.get(task,()) or design.get('revision')!=REVISION_V3
            or design.get('source_sha256')!=source_sha256(REVISION_V3)):
        raise ValueError('Reviewed v3 grasp-task counterexample required')
    plan=deepcopy(spec);goals=plan['goals']
    if len(goals)!=(4 if task=='E11' else 3) or any(g['type']!='place' for g in goals):
        raise ValueError('Original placement goal set required')
    plan['expert_preserve_goal_order']=True
    delta=dict(task=task,control=control,original_goals=deepcopy(goals),
        negative_condition_observed=None,native_review_required=True)
    if control=='wrong_members':
        delta['omitted_member']=goals.pop()['object']
        delta['required_native_review']='Remaining members genuinely placed, released and stable; omitted member outside destination.'
    elif control=='wrong_destination':
        source_return_goal(plan,goals[-1]);delta['outside_member']=goals[-1]['object']
        delta['required_native_review']='Final member genuinely picked/lifted then released at original table source outside target; no zero-action witness.'
    elif control=='wrong_rule':
        if task=='E02':
            # Keep the physical level heights. All original plates have the
            # same thickness. Alternate actual support must follow swapped
            # identities, not the correct original named support chain.
            objects={o['id']:o for o in plan['objects']}
            sizes=[objects[g['object']]['size'][2] for g in goals]
            if max(sizes)-min(sizes)>1e-10:raise ValueError('Equal original plate thickness required')
            goals[0]['object'],goals[1]['object']=goals[1]['object'],goals[0]['object']
            previous='table'
            for g in goals:g['required_support']=previous;previous=g['object']
            delta['attempted_bottom_to_top']=[g['object']for g in goals]
        else:
            targets=[g['target']for g in goals]
            if len(set(targets))!=len(goals):raise ValueError('Distinct original target cells required')
            for g,t in zip(goals,targets[1:]+targets[:1]):g['target']=t
            delta['attempted_mapping']={g['object']:g['target']for g in goals}
        delta['required_native_review']='All real members released, supported and stable in alternative rule arrangement; original native rule must reject.'
    else:
        delta['held_member']=goals[-1]['object']
        delta['required_native_review']='Final member at intended target with actual bilateral grasp; original native release must reject.'
    delta['attempted_goals']=deepcopy(goals)
    return plan,delta


class GraspNegativeAuthor(Back25NegativeAuthor):
    def __init__(self,author,control):
        if getattr(author,'smooth',False) or author.scene.spec.get('author_smooth_recording'):
            raise ValueError('Counterexample requires public actions')
        self.author=author;self.control=control
        self.plan,self.perturbation=negative_plan(author.scene.spec,control)
