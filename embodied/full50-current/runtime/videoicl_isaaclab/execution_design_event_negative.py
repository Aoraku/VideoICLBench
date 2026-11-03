"""Native event counterexamples use actual mallet strikes and gravity launcher."""
from copy import deepcopy
from .execution_design import REVISION_V3,source_sha256
from .realworld_tool_expert import ToolAuthor
from .execution_design_back25_negative import _Proxy

CAPABILITIES={'E29':frozenset(('wrong_rule',)), 'E43':frozenset(('wrong_destination',)),
 'E28':frozenset(('wrong_members','wrong_destination','not_released')), 'E40':frozenset(('wrong_rule',)),
 'E42':frozenset(('wrong_members','wrong_destination',)), 'E44':frozenset(('wrong_rule','not_released')),
 'E45':frozenset(('wrong_destination','not_released')), 'E46':frozenset(('wrong_destination','not_released')),
 'E50':frozenset(('wrong_destination','not_released'))}
class _RetainedToolCargo(Exception):pass

METHODS={'E28':'spatula','E29':'mallet','E40':'clip_edges','E42':'push','E43':'guide',
         'E44':'fold','E45':'pour','E46':'spatula','E50':'clip_card'}


class EventNegativeAuthor:
    def __init__(self,author,control):
        self.author=author;self.control=control;spec=author.scene.spec;self.task=spec['id']
        d=spec.get('execution_design',{})
        if (control not in CAPABILITIES.get(self.task,()) or d.get('revision')!=REVISION_V3
                or d.get('source_sha256')!=source_sha256(REVISION_V3)
                or getattr(author,'smooth',False)or spec.get('author_smooth_recording')):
            raise ValueError('Explicit v3 public-action event counterexample required')
        self.perturbation=dict(task=self.task,control=control,negative_condition_observed=None,
            native_review_required=True,not_applicable=[])
        if self.task=='E29':
            seq={'A':list(range(1,9)),'B':list(range(8,0,-1)),
                 'C':list(range(1,9))+list(range(8,0,-1))}[spec['variant']]
            self.perturbation.update(expected_sequence=seq,
                attempted_sequence=[2 if k==1 else 1 if k==2 else k for k in seq],
                not_applicable=['wrong_members','wrong_destination','not_released'],
                required_native_review='Actual mallet/key impact order and separation, not target positions or action requests')
        elif self.task=='E43':
            old='ABC'.index(spec['variant']);self.perturbation.update(
                expected_region=('circle','triangle','square')[old],
                attempted_region=('circle','triangle','square')[(old+1)%3],aliases=['wrong_rule'],not_applicable=['wrong_members'],
                required_native_review='Actual launcher release, gravity trajectory, guide contact and crossing alternate region; final XY alone is insufficient')

        else:
            old='ABC'.index(spec['variant']);self.perturbation.update(
                source_variant=spec['variant'],attempted_private_rule_variant='ABC'[(old+1)%3],
                actual_public_tool_method=METHODS[self.task],
                required_native_review='Actual tool/target contact, release and event history must prove the task-specific wrong selection or geometry; method return is not proof')
            if self.task=='E44':self.perturbation.update(expected_angle_deg=(90,120,45)[old],attempted_angle_deg=(90,120,45)[(old+1)%3],not_applicable=['wrong_members','wrong_destination'])
            if self.task=='E40':self.perturbation['expected_clips_require_actual_open_release_bilateral_contact']=True
            if self.task=='E50':self.perturbation['requires_actual_flip_clip_transport_and_unclamp_history']=True

        if control=='not_released':
            self.perturbation.update(attempted_private_rule_variant=spec['variant'],
                attempt='retain actual task tool, folded panel, loaded blade or clipped card at original target before release/withdrawal',
                required_native_review='Actual cargo on blade or cup in hand at target with retained contact across physics ticks; completed method is not proof')
        if self.task=='E28'and control=='wrong_destination':
            self.perturbation.update(attempted_private_rule_variant=spec['variant'],
                attempt='use real spatula to return selected food to its original table support outside the plate')

    def solve_negative(self):
        a=self.author;scene=a.scene;original=deepcopy(scene.spec)
        if a.c.scene is not scene:raise ValueError('Original controller world identity required')
        config=deepcopy(scene.embodiment.config);record=config.setdefault('author_recording',{})
        # Existing continuous-recording branches bypass public action receipts;
        # these engineering controls use the existing discrete alternatives.
        record['mallet_single_contact_stroke']=False
        record['guide_stop_on_physical_release']=False
        record['e44_source_edge_fold']=False
        record['pour_return_upright_only']=False
        a.scene=_Proxy(scene,embodiment=_Proxy(scene.embodiment,config=config))
        try:
            policy=ToolAuthor(a)
            retained=False
            if self.task=='E42'and self.control=='wrong_members':
                policy.s=deepcopy(policy.s)
                balls=list(policy.s['groups']['balls'])
                if len(balls)!=2:raise ValueError('Source E42 must contain exactly two balls')
                policy.s['groups']['balls']=balls[:1]
                self.perturbation.update(omitted_member=balls[1],attempted_members=balls[:1],
                    attempted_private_rule_variant=scene.spec['variant'],
                    required_native_review='First ball truly edge-pushed into original region; second ball remains outside and untouched; original two-ball evaluator remains intact')
            if self.control=='not_released':
                if self.task=='E44':
                    def retain_fold(ref,side):
                        nonlocal retained
                        if side!='right':raise RuntimeError('Expected folded panel held by right hand')
                        for _ in range(3):policy.require_held(ref,side);policy.wait(1)
                        policy.require_held(ref,side);retained=True
                        raise _RetainedToolCargo()
                    policy.release=retain_fold
                elif self.task=='E50':
                    original_squeeze=policy.squeeze;squeeze_count=0
                    def retain_clipped_card(clip,ref,side):
                        nonlocal retained,squeeze_count
                        squeeze_count+=1
                        if squeeze_count==2:
                            name,=policy.s['groups']['cards'];body=policy.clip_ref(clip,'body_grasp')
                            for _ in range(3):
                                policy.require_held(body,'right')
                                if not policy.clip_contact(clip,name):raise RuntimeError('Actual two-jaw card clamp lost')
                                policy.wait(1)
                            policy.require_held(body,'right')
                            if not policy.clip_contact(clip,name):raise RuntimeError('Actual two-jaw card clamp lost')
                            retained=True;raise _RetainedToolCargo()
                        return original_squeeze(clip,ref,side)
                    policy.squeeze=retain_clipped_card
                elif self.task=='E45':
                    def retain_cup(ref,side,point=None):
                        nonlocal retained
                        for _ in range(3):policy.require_held(ref,side);policy.wait(1)
                        policy.require_held(ref,side);retained=True
                        raise _RetainedToolCargo()
                    policy.park=retain_cup
                else:
                    original_move=policy.move_point;calls={}
                    def retain_blade(side,ref,target,*args,**kwargs):
                        nonlocal retained
                        result=original_move(side,ref,target,*args,**kwargs)
                        stage=a.stage
                        if stage.startswith('transport-spatula-'):
                            calls[stage]=calls.get(stage,0)+1
                            if calls[stage]==3:
                                name=stage.removeprefix('transport-spatula-');tool=policy.s['tools']['main']
                                grip=dict(actor=tool['actor'],local=tool['grasp_local'])
                                for _ in range(3):
                                    policy.require_held(grip,side)
                                    if not policy.contact(name,tool['actor']):raise RuntimeError('Cargo not actually retained on blade')
                                    policy.wait(1)
                                if not policy.contact(name,tool['actor']):raise RuntimeError('Blade cargo contact lost')
                                retained=True;raise _RetainedToolCargo()
                        return result
                    policy.move_point=retain_blade
            if self.task=='E28'and self.control=='wrong_destination':
                import numpy as np
                values,_=policy.snapshot()
                original_xy={n:values[n]['pos'][:2].copy()for n in policy.s['groups']['cargo']}
                objects={o['id']:o for o in scene.spec['objects']}
                policy.destination=lambda name,slot=0:np.array([*original_xy[name],float(objects[name].get('bottom',.8))])
            if self.task=='E29':
                policy.s=deepcopy(policy.s)
                # Move real strike targets in the private planner only. The
                # original key geometry/labels/evaluator remain unchanged.
                for key in ('keys','key_points','key_frames'):
                    mapping=policy.s.get(key)
                    if mapping is not None:
                        mapping['1'],mapping['2']=mapping['2'],mapping['1']
                policy.mallet()
            else:
                if self.control!='not_released'and not(self.task=='E28'and self.control=='wrong_destination')and not(self.task=='E42'and self.control=='wrong_members'):
                    policy.index=(policy.index+1)%3
                try:getattr(policy,METHODS[self.task])()
                except _RetainedToolCargo:pass
                if self.control=='not_released'and not retained:raise RuntimeError('Negative tool route did not reach retained target state')
            policy.wait(4)
        finally:
            a.scene=scene
            if a.c.scene is not scene or scene.spec!=original:
                raise RuntimeError('Event negative changed original scene contract')
        return dict(task=self.task,control=self.control,actions=a.c.steps-policy.start,
            operations=policy.operations,perturbation=deepcopy(self.perturbation),
            execution_finished=True,negative_condition_observed=None,
            native_validation_required=True,engineering_reference_only=True,
            eligible_as_model_demo=False)
