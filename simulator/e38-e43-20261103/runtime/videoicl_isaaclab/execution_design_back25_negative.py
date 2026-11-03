"""Reviewed E33/E35/E41 physical counterexamples; private author plan only."""
from copy import deepcopy
import math
from .execution_design import REVISION_V3, source_sha256

CAPABILITIES={
    'E28':frozenset(('wrong_rule','hand_loaded_spatula_without_scoop')), 'E42':frozenset(('wrong_rule',)), 'E46':frozenset(('wrong_rule',)),
    'E47':frozenset(('wrong_members','wrong_destination','not_released','unrevealed_cards_disturbed')),
    'E48':frozenset(('wrong_members','wrong_destination','not_released')),
    'E49':frozenset(('wrong_members','wrong_destination','wrong_rule','not_released','unrevealed_cards_disturbed')),
    'E27':frozenset(('wrong_members','wrong_destination','wrong_rule','not_released')),
    'E31':frozenset(('wrong_members','wrong_rule','not_released')),
    'E32':frozenset(('wrong_members','wrong_destination','not_released')),
    'E34':frozenset(('wrong_members','wrong_destination','not_released','unselected_cutlery_moved')),
    'E36':frozenset(('wrong_members','wrong_destination','not_released')),
    'E38':frozenset(('wrong_members','wrong_destination','wrong_rule','not_released')),
    'E33':frozenset(('wrong_members','wrong_destination','not_released')),
    'E35':frozenset(('wrong_members','wrong_rule','not_released')),
    'E41':frozenset(('wrong_members','wrong_destination','wrong_rule','not_released')),
}


EXTRA_CONTROLS=('unselected_cutlery_moved','unrevealed_cards_disturbed','hand_loaded_spatula_without_scoop')

def negative_plan(spec,control):
    task=spec['id'];d=spec.get('execution_design',{})
    if (control not in CAPABILITIES.get(task,()) or d.get('revision')!=REVISION_V3
            or d.get('source_sha256')!=source_sha256(REVISION_V3)):
        raise ValueError('Unsupported or non-v3 reviewed physical counterexample')
    plan=deepcopy(spec);goals=plan['goals'];objects={o['id']:o for o in plan['objects']}
    zones={z['id']:z for z in plan['zones']}
    perturb=dict(task=task,control=control,original_goals=deepcopy(goals),
                 negative_condition_observed=None,native_review_required=True)
    plan['expert_preserve_goal_order']=True
    if task=='E28' and control=='hand_loaded_spatula_without_scoop':
        perturb.update(attempted_mechanism='actual_hand_loading_then_blade_supported_transport',
            attempted_goals=deepcopy(goals),
            required_native_review='Verify actual hand pickup, release onto physically held blade, blade-supported carry and final plate placement. Must have no native edge-entry/table-lift witness; a failed pickup or failed delivery is not the intended counterexample.')
        return plan,perturb
    if control in EXTRA_CONTROLS:
        group='cutlery'if task=='E34'else'cards'
        protected=set(spec['semantic']['groups'].get('active',()))if group=='cards'else {g['object']for g in goals}
        name=next(n for n in spec['semantic']['groups'][group]if n not in protected)
        obj=objects[name]
        goal=dict(type='place',object=name,yaw=float(obj.get('yaw',0.)),pitch=0.,roll=math.pi if group=='cards'else 0.)
        zone=source_return_goal(plan,goal);zone['xy'][0]+=.04
        plan['goals'].append(goal)
        perturb.update(disturbed_unselected_member=name,original_selected_goals=deepcopy(spec['goals']),
            displacement_task_m=[.04,0,0],attempted_goals=deepcopy(plan['goals']),
            required_native_review='Original selected goals must succeed with actual flip history where applicable and actual placement events; separately verify real unselected body moved at least rule threshold. Unrevealed card remains face-down; no world/evaluator edits.')
        return plan,perturb
    if task in ('E28','E42','E46'):
        if not goals or any(g['type']!='place'for g in goals):
            raise ValueError('Reviewed direct-hand physical placement goals required')
        perturb.update(attempted_goals=deepcopy(goals),
            attempted_mechanism='direct_hand_pick_and_place_without_tool_use',
            required_native_review='Actual target placement and release with no required spatula support/edge-push history; do not treat failed grasp as counterexample')
        return plan,perturb
    if task in ('E47','E48','E49'):
        return card_plan(spec,control,plan,perturb)
    if task in ('E27','E31','E32','E34','E36','E38'):
        return additional_plan(spec,control,plan,perturb)
    if control=='wrong_members':
        if task=='E33':
            expected=spec['semantic']['selected']
            alternate=next(n for n in spec['semantic']['groups']['bottles']if n!=expected)
            goals[0]['object']=alternate
            perturb.update(expected_member=expected,substitute_member=alternate,
                           aliases=['wrong_rule'])
        else:
            omitted=goals.pop()['object'];perturb['omitted_member']=omitted
    elif control=='wrong_rule':
        if task=='E35':
            goals[-1]['object'],goals[-2]['object']=goals[-2]['object'],goals[-1]['object']
            height=float(zones[goals[0]['target']]['surface_z']);previous='table'
            for g in goals:
                zones[g['target']]['surface_z']=height;zones[g['target']]['support']=previous
                g['required_support']=previous
                height+=2*objects[g['object']]['size'][2];previous=g['object']
            perturb['attempted_bottom_to_top']=[g['object']for g in goals]
        else:
            mapping=spec['semantic']['mapping'];refs=list(mapping);pieces=[mapping[r]for r in refs]
            pieces[0],pieces[1]=pieces[1],pieces[0]
            goals=[]
            for ref,piece in zip(refs,pieces):
                original_piece=mapping[ref];zone=deepcopy(zones[original_piece+'_target'])
                # Same measured reference end but wrong ranked extension;
                # recompute new center so mismatch is rank, not a stale gap.
                zone['id']='negative-'+ref
                zone['xy'][0]=objects[ref]['xy'][0]-objects[ref]['size'][0]-objects[piece]['size'][0]-.001
                plan['zones'].append(zone)
                goals.append(dict(type='place',object=piece,target=zone['id'],yaw=0))
            plan['goals']=goals;perturb['attempted_mapping']=dict(zip(refs,pieces))
    elif control=='wrong_destination':
        goal=goals[0];zone=deepcopy(zones[goal['target']]);zone['id']='negative-outside-target'
        if task=='E33':
            obj=objects[goal['object']];zone.update(xy=list(obj['xy']),surface_z=float(obj.get('bottom',.8)),support='table')
            goal['required_support']='table'
            perturb['attempt']='lift selected bottle and replace at its original outside-bin support'
        else:
            gap=max(.04,4*float(spec['semantic']['max_endpoint_gap']))
            zone['xy'][0]-=gap;perturb['extra_endpoint_gap_m']=gap
        goal['target']=zone['id'];plan['zones'].append(zone)
    else:
        perturb['held_member']=goals[-1]['object']
    perturb['attempted_goals']=deepcopy(plan['goals'])
    return plan,perturb


def source_return_goal(plan,goal):
    """Physical pickup/lift/replace at original support, never zero-action failure."""
    obj=next(o for o in plan['objects']if o['id']==goal['object'])
    target=dict(id='negative-source-'+obj['id'],xy=list(obj['xy']),
        surface_z=float(obj.get('bottom',.8)),half_size=list(obj['size'][:2]),
        hidden=True,support='table')
    plan['zones'].append(target);goal['target']=target['id'];goal['required_support']='table'
    goal.pop('placement_xy',None)
    return target


def additional_plan(spec,control,plan,perturb):
    task=spec['id'];goals=plan['goals'];sem=spec['semantic']
    if control=='wrong_members':
        if task in ('E32','E34'):
            candidates=(('sprite_bottle','cola_bottle','pink_cube')if task=='E32'else sem['groups']['cutlery'])
            alternate=next(n for n in candidates if n!=sem['selected'])
            goals[0]['object']=alternate
            perturb.update(expected_member=sem['selected'],substitute_member=alternate,aliases=['wrong_rule'])
        elif task in ('E31','E36') and len(goals)==1:
            # Omitting the sole placement would be a zero-action baseline;
            # actually lift and return the required body outside the relation.
            source_return_goal(plan,goals[0]);perturb['omitted_from_target']=goals[0]['object']
        else:perturb['omitted_member']=goals.pop()['object']
    elif control=='wrong_destination':
        source_return_goal(plan,goals[-1]);perturb['outside_member']=goals[-1]['object']
        if task=='E36':
            perturb['overlap_note']='For count=1 this shares the wrong_members physical witness; do not count twice'
    elif control=='wrong_rule':
        if task=='E27':
            goals[0]['target'],goals[1]['target']=goals[1]['target'],goals[0]['target']
            perturb['attempted_placements']={g['object']:g['target']for g in goals}
        elif task=='E31':
            goals[0]['pitch']=float(goals[0].get('pitch',0))+math.pi
            perturb['orientation_delta_rad']=math.pi
            perturb['required_native_review']='Actual local-up dot world-up and real support; XY alone is insufficient'
        elif task=='E38':
            goals[0]['object'],goals[1]['object']=goals[1]['object'],goals[0]['object']
            perturb['attempted_bottom_to_top']=[g['object']for g in goals]
            perturb['required_native_review']='Actual post through every ring hole plus measured height order and support; XY alone is insufficient'
        else:raise ValueError('No independent wrong_rule control for this task')
    else:perturb['held_member']=goals[-1]['object']
    if task=='E31':perturb['not_applicable']=['wrong_destination']
    if task=='E38'and control=='wrong_destination':
        perturb['required_native_review']='Show the selected ring is actually outside the post, released and supported; compare local hole/post geometry'
    perturb['attempted_goals']=deepcopy(goals)
    return plan,perturb


def card_plan(spec,control,plan,perturb):
    task=spec['id'];goals=plan['goals']
    deliveries=[g for g in goals if not g['target'].endswith('_flip')]
    if control=='wrong_members':
        if task=='E47':
            if len(deliveries)>1:
                goals.remove(deliveries[-1]);perturb['omitted_member']=deliveries[-1]['object']
            else:
                goal=deliveries[0];other=next(n for n in spec['semantic']['groups']['active']if n!=goal['object'])
                goal['object']=other;perturb['substitute_member']=other
                # Existing source catalog defines both interior slots even
                # when only one is selected; no new container geometry.
                target=other+'_in_box'
                if any(z['id']==target for z in plan['zones']):goal['target']=target
        elif len(deliveries)>1:
            name=deliveries[-1]['object'];plan['goals']=[g for g in goals if g['object']!=name]
            perturb['omitted_member']=name
        else:
            name=deliveries[0]['object'];other=next(n for n in spec['semantic']['groups']['cards']if n!=name)
            obj=next(o for o in plan['objects']if o['id']==other)
            for goal in goals:
                goal['object']=other
                if goal['target'].endswith('_flip'):
                    zone=deepcopy(next(z for z in plan['zones']if z['id']==goal['target']))
                    zone.update(id='negative-flip-'+other,xy=list(obj['xy']))
                    plan['zones'].append(zone);goal['target']=zone['id']
            perturb.update(expected_leftmost=name,substitute_member=other)
    elif control=='wrong_destination':
        source_return_goal(plan,deliveries[-1]);deliveries[-1]['pitch']=0
        perturb['outside_member']=deliveries[-1]['object']
    elif control=='wrong_rule':
        if task!='E49':raise ValueError('Card selection/count rule duplicates membership control')
        a,b=deliveries[:2]
        a['target'],b['target']=b['target'],a['target']
        a['required_support'],b['required_support']=b['required_support'],a['required_support']
        perturb['attempted_plate_mapping']={g['object']:g['required_support']for g in deliveries}
    else:perturb['held_member']=deliveries[-1]['object']
    perturb.update(attempted_goals=deepcopy(plan['goals']),
        required_native_review='Actual prefix flip history and unrevealed-card preservation, then real box/slot/plate geometry and support; final XY is not proof')
    if task=='E48':perturb['slot_review']='Measure insertion-axis lower section inside native slot bounds with holder contact and released stable support'
    return plan,perturb


class _Proxy:
    def __init__(self,original,**overrides):self._original=original;self.__dict__.update(overrides)
    def __getattr__(self,key):return getattr(self._original,key)


class _HeldAtDestination(Exception):pass


class Back25NegativeAuthor:
    def __init__(self,author,control):
        if getattr(author,'smooth',False)or author.scene.spec.get('author_smooth_recording'):
            raise ValueError('Counterexample requires recorded public actions')
        self.author=author;self.control=control
        self.plan,self.perturbation=negative_plan(author.scene.spec,control)

    def solve_negative(self):
        a=self.author;scene=a.scene;original=deepcopy(scene.spec);start=a.c.steps
        if a.c.scene is not scene:raise ValueError('Original author/controller scene identity required')
        # Only the author sees alternate waypoints. Controller scene and evaluator
        # remain the original real world and original target contract throughout.
        proxy=_Proxy(scene,spec=self.plan)
        if self.plan['id']=='E33' and self.control=='wrong_destination':
            cfg=deepcopy(scene.embodiment.config);record=cfg.setdefault('author_recording',{})
            for flag in ('e33_clear_bin_rim_on_release','e33_release_when_inside_near_floor'):
                record[flag]=False
            proxy.embodiment=_Proxy(scene.embodiment,config=cfg)
        old_permission=getattr(a,'_execution_design_reference_authorized',False)
        had_release='release_generated'in a.__dict__;old_instance_release=a.__dict__.get('release_generated')
        original_release=a.release_generated;releases=0;held=False
        def release(side):
            nonlocal releases,held
            # A real table handoff is released and regrasped before the final
            # placement. It must not consume a final-goal hold counter.
            if not getattr(a, '_engineering_release_is_relay', False):releases+=1
            if self.control=='not_released' and releases==len(self.plan['goals']):
                name=self.perturbation['held_member'];idx=0 if side=='left'else 1
                for _ in range(3):
                    values,_=a.c.snapshot()
                    if not values[name]['grasp'][idx]:raise RuntimeError('Negative cargo is not physically held')
                    a.act()
                values,_=a.c.snapshot()
                if not values[name]['grasp'][idx]:raise RuntimeError('Negative grip lost during final hold')
                held=True;raise _HeldAtDestination()
            return original_release(side)
        try:
            a.scene=proxy;a._execution_design_reference_authorized=True;a.release_generated=release
            try:
                if self.plan['id']=='E28' and self.control=='hand_loaded_spatula_without_scoop':
                    from .realworld_tool_expert import ToolAuthor
                    ToolAuthor(a)._handload_spatula_transport()
                else:a.solve_generated()
            except _HeldAtDestination:pass
            if self.control=='not_released'and not held:raise RuntimeError('Negative route did not reach final held placement')
        finally:
            a.scene=scene;a._execution_design_reference_authorized=old_permission
            if had_release:a.release_generated=old_instance_release
            else:a.__dict__.pop('release_generated',None)
            if a.c.scene is not scene or scene.spec!=original:
                raise RuntimeError('Private author counterexample changed original scene contract')
        return dict(task=self.plan['id'],control=self.control,actions=a.c.steps-start,
            perturbation=deepcopy(self.perturbation),execution_finished=True,
            negative_condition_observed=None,native_validation_required=True,
            engineering_reference_only=True,eligible_as_model_demo=False)
