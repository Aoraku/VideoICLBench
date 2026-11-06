"""Private engineering counterexamples through public physical robot actions.

This module is deliberately not used by model input or positive-demo dispatch.
Plans are attempts only: native scoring/history must independently establish the
requested negative condition. Neither evaluator state nor scene poses are edited.
"""
from copy import deepcopy
import math
import numpy as np

from .execution_design_expert import ExecutionDesignAuthor
from .realworld_tool_expert import ToolExecutionError

CONTROLS=('wrong_members','wrong_destination','wrong_rule','not_released')
TASKS=('E01','E09','E17','E20','E39')


class UnsupportedNegativeControl(ToolExecutionError):
    pass


class ExecutionDesignNegativeAuthor(ExecutionDesignAuthor):
    def __init__(self,author,control):
        if control not in CONTROLS:raise UnsupportedNegativeControl('Unknown engineering control: '+str(control))
        super().__init__(author)
        self.control=control
        # Mutable private controller plan, separate from the live scene/scorer.
        self.d=deepcopy(self.d)
        self.member_substitution={}
        self.extra_member=None
        self.perturbation=dict(control=control,task=self.task,variant=self.variant,
                              validation='native_observation_required')
        self._configure_plan()

    def _configure_plan(self):
        if self.control=='wrong_destination':
            wanted=self.d['destination_zone']
            other=[z['id'] for z in self.spec['zones'] if z['id'].startswith('delivery_') and z['id']!=wanted]
            if len(other)!=1:raise UnsupportedNegativeControl('Exactly one distinct destination required')
            self.d['destination_zone']=other[0]
            self.perturbation.update(expected_destination=wanted,attempted_destination=other[0])
        elif self.control=='not_released':
            self.perturbation.update(actor=self.d['delivery_actor'],attempt='retain measured grip at receiving station')
        elif self.control=='wrong_members':
            spares=self.d.get('batch_members',{}).get('distractor',[])
            if len(spares)!=1 or spares[0] not in self.grasps:
                raise UnsupportedNegativeControl('One physically graspable distractor batch member required')
            spare=spares[0];prototype=spare.removeprefix('other_batch_')
            candidates=list(self.d['target_members'])
            if self.task=='E20':
                # Do not disturb the preserved initial members: substitute one
                # of the planned additions, even when the clone's original is
                # already in the tray.
                candidates=[]
                for r in self.d['local_regions']:
                    preserved=set(self.d['initial_preserved'][r['id']])
                    additions=[n for n in r['candidates'] if n.startswith(r['required_color']+'_') and n not in preserved]
                    candidates.extend(additions[:r['count']-len(preserved)])
            if not candidates and self.task=='E20':
                # Some fixed cases already contain every requested chip. Keep
                # them intact and attempt one extra clone in a measured free
                # cell. The four-cell geometry is checked again at execution.
                region=next((r for r in self.d['local_regions'] if r['count']<4),None)
                if region is None:raise UnsupportedNegativeControl('No substitution or extra-member capacity')
                self.extra_member=dict(member=spare,region=region['id'])
                self.perturbation.update(mode='extra_member',extra_member=spare,
                    region=region['id'],attempt='preserve initial chips and add other-batch chip in measured free cell')
                if prototype in self.grasps:self.grasps={**self.grasps,spare:deepcopy(self.grasps[prototype])}
                return
            if not candidates:raise UnsupportedNegativeControl('No non-preserved member can be substituted')
            original=prototype if prototype in candidates else candidates[0]
            self.member_substitution={original:spare}
            # The distractor is an authored clone; reuse reviewed local grasp
            # only for a matching source geometry, never teleport/attach it.
            if prototype in self.grasps:self.grasps={**self.grasps,spare:deepcopy(self.grasps[prototype])}
            self.perturbation.update(omitted_member=original,substitute_member=spare,
                                     mode='substitution',attempt='physically place other-batch member instead of requested member')
        elif self.task=='E01':
            self.index=(self.index+1)%3
            self.perturbation.update(attempt='use a different local food-selection rule',control_rule_variant='ABC'[self.index])
        elif self.task=='E09':
            groups=self.d['unordered_expected_groups']
            if len(groups)<2 or not all(groups[:2]):raise UnsupportedNegativeControl('Two nonempty groups required')
            first,second=groups[0][0],groups[1][0]
            groups[0][0],groups[1][0]=second,first
            self.perturbation.update(attempt='swap one member across two groups',swapped_members=[first,second])
        elif self.task=='E17':
            regions=self.d['local_regions'];source=next((r for r in regions if r['members']),None)
            target=next((r for r in regions if source is not None and r['id']!=source['id']),None)
            if source is None or target is None:raise UnsupportedNegativeControl('Two shelf layers required')
            member=source['members'].pop(0);target['members'].append(member)
            self.perturbation.update(attempt='place one member on the opposite shelf',member=member,
                                     correct_layer=source['id'],attempted_layer=target['id'])
        elif self.task=='E20':
            r=self.d['local_regions'][0];before=r['count'];after=before+1 if before<4 else before-1
            if after<len(self.d['initial_preserved'][r['id']]):raise UnsupportedNegativeControl('Wrong count would remove a preserved member')
            r['count']=after
            self.perturbation.update(attempt='fill one compartment to a different total',region=r['id'],correct_count=before,attempted_count=after)
        elif self.task=='E39':
            self.perturbation.update(attempt='violate one enforced measured order or orientation rule')
        else:raise UnsupportedNegativeControl('No physical wrong-rule strategy for '+self.task)

    def place(self,name,*args,**kwargs):
        return super().place(self.member_substitution.get(name,name),*args,**kwargs)

    def local_stage(self):
        super().local_stage()
        if self.extra_member is not None:
            r=next(r for r in self.d['local_regions'] if r['id']==self.extra_member['region'])
            name=self.extra_member['member']
            target=self.free_chip_slot(r,name)
            # Uses ordinary pickup/physical lower_place, with measured contact
            # and grip guards; no native pose or preserved-chip edits.
            self.place(name,r['actor'],target)

    def place_lower_shelf(self,name,*args,**kwargs):
        return super().place_lower_shelf(self.member_substitution.get(name,name),*args,**kwargs)

    def food(self):
        if not self.member_substitution:return super().food()
        selected=(['burger','fries'],['burger','drink'],['fries','drink'])[self.index]
        container=self.s['containers']['plate'];support=container['ref'].get('actor',container['ref'].get('contact_body'))
        for label in selected:
            intended=self.identity[label];name=self.member_substitution.get(intended,intended)
            self.stage('negative-food-member-'+name);ref,side=self.pickup(name)
            target=self.body_point(container['ref'],self.geometry['plate_positions'][intended])
            self.lower_place(name,ref,side,self.bottom_local(name),target,support=support)

    def order_rule(self):
        rule=super().order_rule()
        if self.control!='wrong_rule':return rule
        if rule.get('match_order',self.d['local_order'].get('match_order')):
            if len(rule['expected_order'])<2:raise UnsupportedNegativeControl('Two pieces needed for wrong ordering')
            rule['expected_order'][0],rule['expected_order'][1]=rule['expected_order'][1],rule['expected_order'][0]
            self.perturbation.update(attempted_order=list(rule['expected_order']))
        else:
            name=rule['pieces'][0];rule['expected_yaws'][name]+=math.pi/2
            self.perturbation.update(rotated_member=name,orientation_delta_radians=math.pi/2)
        return rule

    def deliver(self):
        if self.control!='not_released':return super().deliver()
        name=self.d['delivery_actor'];zone=next(z for z in self.spec['zones'] if z['id']==self.d['destination_zone'])
        self.stage('negative-retain-delivery-grip-'+name)
        ref,side=self.pickup(name);guard=lambda:self.require_held(ref,side)
        control=dict(actor=name,local=self.bottom_local(name))
        self.move_point(side,control,[*self.point(control)[:2],self.clearance],guard)
        self.rotate_actor(name,side,np.eye(3));control['local']=self.bottom_local(name)
        self.move_point(side,control,[*zone['xy'],self.clearance],guard)
        self.move_point(side,control,[*zone['xy'],zone.get('surface_z',.8)+.001],guard)
        self.wait(6);guard()
        # Deliberately no RELEASE. This records a requested control attempt,
        # not proof that the final native not_released predicate was observed.


def solve_execution_design_negative(author,control):
    policy=ExecutionDesignNegativeAuthor(author,control)
    policy.local_stage();policy.package_stage();policy.deliver()
    return dict(task=policy.task,variant=policy.variant,control=control,
                actions=policy.c.steps-policy.start,operations=policy.operations,
                perturbation=policy.perturbation,execution_finished=True,
                negative_condition_observed=None,native_validation_required=True,
                receipt_file=str(author.out/'demo-actions.private.jsonl'))
