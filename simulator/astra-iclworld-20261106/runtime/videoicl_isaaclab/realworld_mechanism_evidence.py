"""Native E06/E18/E26/E30 evidence; no torch, commands or planner flags.

Controller protocol: call update_mechanisms(actual_snapshot) immediately before
update(state, contact_pairs, dt) on *every* physics step for articulated tasks.
Snapshots use body_pos_task/body_mat_task dictionaries keyed by body_names.

Recipe schema (private; not appended to the actor prompt):
  semantic.groups.balls: three rigid-object IDs (E06/E18)
  semantic.holder: rigid tray ID (E06)
  semantic.cells: six operator-frame cells, each {center:[x,y,floor_z],radius:m}
  semantic.joint_roles: drawer (E18), upper/lower (E30), left/right (E26), each
    {mechanism, joint, body, contact_body, closed:float, direction:+1|-1,
     open_threshold:float, closed_tolerance:float}
  semantic.interactors: actual robot finger contact names; defaults to the four
    left/right_finger1/2 names used by Controller.snapshot().
  semantic.drawer_cavity: {mechanism,body,contact_body,lower:[3],upper:[3],
      floor_axis:2 (default),floor_side:'lower' (default)}
    The bounds are relative to the measured moving drawer body (E18).
    The source cabinet has body-local +Y up, so its floor_axis must be 1.
  zones: target with {id:'target',xy:[2],half_size:[2],surface_z:.8} (E18)

joint_roles contact_body is mandatory: it identifies the *moving link* in the
PhysX contact map, e.g. cabinet/upper or bells/left_button; base contact is not
button contact. body is the actual articulation body name, which may differ.
closed/open_threshold/closed_tolerance are in the joint's native units (metres
for these prismatic mechanisms). direction normalizes opening/pressing positive.

Initialize and reset after physical settling, then capture an initial snapshot
before the first action. All required joints must initially be closed/unpressed;
E18 balls must actually be inside the drawer. History is captured even while
event_enabled is false. Invalid/missing/nonfinite frames latch failure until
reset, so refreshing a snapshot cannot erase an unobserved action interval.
"""
from copy import deepcopy
from . import realworld_progress_evidence as progress_evidence
from collections.abc import Mapping
import math
import hashlib
import json
import numpy as np

from .realworld_contracts import provenance
from .realworld_semantic_checks import check_task

SUPPORTED=('E06','E18','E26','E30')
CELLS=('left_far','left_middle','left_near','right_far','right_middle','right_near')
FINGERS=('left_finger1','left_finger2','right_finger1','right_finger2')


def _finite(value,shape):
    array=np.asarray(value,float)
    if array.shape!=shape or not np.isfinite(array).all():
        raise ValueError('Malformed/nonfinite native vector')
    return array.copy()


def _rotation(value):
    array=_finite(value,(3,3))
    if not np.allclose(array.T@array,np.eye(3),atol=1e-4) or not np.isclose(np.linalg.det(array),1.,atol=1e-4):
        raise ValueError('Native body matrix is not a rotation')
    return array


def _number(value):
    return isinstance(value,(int,float,np.number)) and not isinstance(value,(bool,np.bool_)) and math.isfinite(value)


class MechanismTaskEvaluator:
    def __init__(self,spec):
        self.spec=deepcopy(spec)
        self.task,self.variant=spec['id'],spec['variant']
        from .execution_design_drawers import initial_displacements
        self.execution_v3_drawer_input=initial_displacements(spec)
        self.execution_v2_bells=(self.task=='E26' and spec.get('execution_design',{}).get('revision') in ('embodied50-execution-v2-20261102','embodied50-execution-v3-20261102'))
        if self.execution_v2_bells:
            from .execution_design_inputs import e26_targets
            e26_targets(self.spec)
        if self.task not in SUPPORTED:
            raise NotImplementedError(self.task+': mechanism native adapter not implemented')
        self.objects={o['id']:o for o in spec['objects']}
        if len(self.objects)!=len(spec['objects']):
            raise ValueError('Duplicate rigid object IDs')
        for obj in self.objects.values():
            if np.any(_finite(obj['size'],(3,))<=0):
                raise ValueError('Object bounds must be positive')
            _finite(obj.get('local_bounds_center',[0,0,0]),(3,))
        self.semantic=spec['semantic']
        self.interactors=self.semantic.get('interactors',list(FINGERS))
        if not isinstance(self.interactors,list) or not self.interactors or not all(isinstance(x,str) for x in self.interactors):
            raise ValueError('Explicit robot contact identities required')
        self.balls=self.semantic.get('groups',{}).get('balls',[])
        if self.task in ('E06','E18') and (len(self.balls)!=3 or len(set(self.balls))!=3 or not set(self.balls)<=set(self.objects)):
            raise ValueError('Three distinct ball actors required')
        self.roles=self.semantic.get('joint_roles',{})
        needed={'E18':{'drawer'},'E26':{'left','right'},'E30':{'upper','lower'}}.get(self.task,set())
        if set(self.roles)!=needed:
            raise ValueError('Missing or unexpected measured joint roles')
        role_joints=[]
        for role,entry in self.roles.items():
            for field in ('mechanism','joint','body','contact_body'):
                if not isinstance(entry.get(field),str) or not entry[field]:
                    raise ValueError(f'{role}: explicit {field} required')
            for field in ('closed','direction','open_threshold','closed_tolerance'):
                if not _number(entry.get(field)):
                    raise ValueError(f'{role}: finite {field} required')
            if entry['direction'] not in (-1,1) or not 0<=entry['closed_tolerance']<entry['open_threshold']:
                raise ValueError('Invalid signed joint thresholds')
            role_joints.append((entry['mechanism'],entry['joint']))
        if len(set(role_joints))!=len(role_joints):
            raise ValueError('Two roles cannot alias one physical joint')
        if self.task=='E06':
            if self.semantic.get('holder') not in self.objects:
                raise ValueError('Real holder actor required')
            cells=self.semantic.get('cells',{})
            if set(cells)!=set(CELLS):
                raise ValueError('Explicit operator-relative six-hole coordinates required')
            for cell in cells.values():
                _finite(cell['center'],(3,))
                if not _number(cell.get('radius')) or cell['radius']<=0:
                    raise ValueError('Positive cell radius required')
        if self.task=='E18':
            cavity=self.semantic.get('drawer_cavity',{})
            if not all(isinstance(cavity.get(k),str) and cavity[k] for k in ('mechanism','body','contact_body')):
                raise ValueError('Moving drawer cavity body and contact ID required')
            if np.any(_finite(cavity['upper'],(3,))<=_finite(cavity['lower'],(3,))):
                raise ValueError('Invalid drawer cavity')
            if (type(cavity.get('floor_axis',2))is not int or cavity.get('floor_axis',2) not in (0,1,2)
                    or cavity.get('floor_side','lower') not in ('lower','upper')):
                raise ValueError('Explicit local cavity floor axis/side invalid')
            self.target=next((z for z in spec.get('zones',[]) if z['id']=='target'),None)
            if self.target is None or np.any(_finite(self.target['half_size'],(2,))<=0):
                raise ValueError('Target paper region required')
            _finite(self.target['xy'],(2,))
            if not _number(self.target.get('surface_z',.8)):
                raise ValueError('Invalid target surface height')
        self.reset_episode()

    def reset_episode(self):
        progress_evidence.reset(self)
        self.steps=0;self.elapsed=0.;self.hold_seconds=0.;self.event_enabled=False
        self.events=[];self.event_history={'joint_events':[],'bell_events':[],'moved_objects':[]}
        self.initial=None;self.previous=None;self.anchor=None
        self.initial_mechanisms=None;self.previous_mechanisms=None;self.anchor_mechanisms=None
        self.pending_mechanisms=None;self.mechanisms={};self.state={};self.contacts=set()
        self.history_valid=True;self.errors=[];self.initial_valid=True;self.holder_fixed=True
        self.moved=set();self.previous_touched={role:False for role in self.roles}
        self.open_contact={role:False for role in self.roles};self.close_contact={role:False for role in self.roles}
        self.opened_seen=set();self.opened_measured=set();self.closed_after_open=set();self.bell_down={role:False for role in self.roles}
        self.closed_initial_drawers=set()
        self.observation={};self.current_conditions=[]
        self.progress_delivery_steps={};self.progress_in_target=set();self.progress_close_steps={}
        self.last={'success':False,'checks':{'native_snapshot':False}}
        self.provenance=provenance(self.task,self.variant)

    def _error(self,exc):
        self.history_valid=False;self.hold_seconds=0.;self.anchor=None;self.anchor_mechanisms=None
        if str(exc) not in self.errors:self.errors.append(str(exc))
        self.last={'success':False,'checks':{'native_snapshot':False}}
        self.current_conditions=[dict(index=0,type='native_snapshot',passed=False)]

    def update_mechanisms(self,snapshot):
        """Accept actual articulation tensors; never accepts target joint values."""
        try:
            if not isinstance(snapshot,Mapping):raise ValueError('Missing articulation snapshot')
            if self.pending_mechanisms is not None:raise ValueError('Unconsumed articulation snapshot')
            clean={}
            required={r['mechanism'] for r in self.roles.values()}
            if self.task=='E18':required.add(self.semantic['drawer_cavity']['mechanism'])
            if not required<=set(snapshot):raise ValueError('Incomplete articulation snapshot')
            for mid in required:
                value=snapshot[mid];names=value['joint_names'];bodies=value['body_names']
                if (not isinstance(names,list) or not names or not all(isinstance(n,str) for n in names) or len(set(names))!=len(names)
                        or not isinstance(bodies,list) or not bodies or not all(isinstance(n,str) for n in bodies) or len(set(bodies))!=len(bodies)):
                    raise ValueError('Invalid articulation joint/body identities')
                pos=_finite(value['joint_pos'],(len(names),));vel=_finite(value['joint_vel'],(len(names),))
                bp=value['body_pos_task'];br=value['body_mat_task']
                if not isinstance(bp,Mapping) or not isinstance(br,Mapping):
                    raise ValueError('Incomplete measured articulation bodies')
                if set(bp)!=set(bodies) or set(br)!=set(bodies):raise ValueError('Missing articulation body')
                clean[mid]=dict(joint_names=list(names),joint_pos=pos,joint_vel=vel,body_names=list(bodies),
                    body_pos_task={n:_finite(bp[n],(3,)) for n in bodies},body_mat_task={n:_rotation(br[n]) for n in bodies})
            for role,entry in self.roles.items():
                value=clean[entry['mechanism']]
                if entry['joint'] not in value['joint_names'] or entry['body'] not in value['body_names']:
                    raise ValueError('Missing measured joint/body for '+role)
            self.pending_mechanisms=clean
        except (ValueError,KeyError,TypeError,IndexError,OverflowError) as exc:
            self._error(exc)

    def label(self,name):
        obj=self.objects[name]
        return obj.get('semantic_identity',obj.get('identity',name))

    def bounds(self,name,state=None):
        current=self.state if state is None else state
        obj=self.objects[name];value=current[name]
        center=value['pos']+value['mat']@np.asarray(obj.get('local_bounds_center',[0,0,0]),float)
        half=np.abs(value['mat'])@np.asarray(obj['size'],float)
        if obj.get('kind')=='sphere':half=np.full(3,float(obj['size'][0]))
        return center,half

    def contact(self,a,b):
        return frozenset((a,b)) in self.contacts

    def _touch(self,role):
        return any(self.contact(self.roles[role]['contact_body'],finger) for finger in self.interactors)

    def _released(self):
        # The task targets are the balls or moving joint roles. A hand may
        # steady a fixed holder; that is not a grasp of the released cargo.
        return not any(any(self.state[n]['grasp']) for n in self.balls) and not any(self._touch(r) for r in self.roles)

    def _joint(self,role,mechanisms=None):
        values=self.mechanisms if mechanisms is None else mechanisms
        entry=self.roles[role];value=values[entry['mechanism']];i=value['joint_names'].index(entry['joint'])
        return float((value['joint_pos'][i]-entry['closed'])*entry['direction'])

    def _body(self,mechanism,body):
        return self.mechanisms[mechanism]['body_pos_task'][body],self.mechanisms[mechanism]['body_mat_task'][body]

    def _drawer_members(self):
        cavity=self.semantic['drawer_cavity'];bp,br=self._body(cavity['mechanism'],cavity['body'])
        low=np.asarray(cavity['lower']);high=np.asarray(cavity['upper']);inside=[]
        floor_axis=cavity.get('floor_axis',2);lower_floor=cavity.get('floor_side','lower')=='lower'
        up=br[:,floor_axis]*(1 if lower_floor else -1)
        if up[2]<.95:return []
        for name in self.balls:
            center,half=self.bounds(name);local=br.T@(center-bp)
            # Balls are rotationally symmetric; use the reviewed collision radius.
            radius=float(max(half))
            floor_gap=(local[floor_axis]-radius-low[floor_axis] if lower_floor else high[floor_axis]-local[floor_axis]-radius)
            if (not any(self.state[name]['grasp']) and np.all(local-radius>=low-.003)
                    and np.all(local+radius<=high+.003) and abs(floor_gap)<=.012
                    and self.contact(name,cavity['contact_body'])):inside.append(name)
        return inside

    def _in_target(self,name):
        center,half=self.bounds(name);z=self.target
        return (not any(self.state[name]['grasp']) and self.contact(name,z.get('support','table'))
                and np.all(np.abs(center[:2]-np.asarray(z['xy']))<=np.asarray(z['half_size'])+.005)
                and abs(center[2]-half[2]-z.get('surface_z',.8))<=.012)

    def _record(self,event,role):
        item=dict(event=event,role=role,step=self.steps,joint_displacement=self._joint(role))
        self.events.append(item);self.event_history['joint_events'].append(deepcopy(item))

    def _history(self):
        for role,entry in self.roles.items():
            displacement=self._joint(role);touched=self._touch(role)
            if displacement>=entry['open_threshold']:self.opened_measured.add(role)
            if self.previous_mechanisms is not None:
                delta=displacement-self._joint(role,self.previous_mechanisms)
                active_touch=touched or self.previous_touched[role]
                if delta>1e-5 and active_touch:self.open_contact[role]=True
                if delta<-1e-5 and active_touch and (role in self.opened_seen or self.execution_v3_drawer_input is not None):self.close_contact[role]=True
                # The final solver step can cross the closed boundary by less
                # than 10um after a real millimetre contact push. Require the
                # established contact-driven closing motion and contact at the
                # crossing, rather than a frame-rate-dependent final step size.
                if (self.execution_v3_drawer_input is not None and delta<-1e-9
                        and self.close_contact[role] and active_touch
                        and abs(displacement)<=entry['closed_tolerance']
                        and self._joint(role,self.previous_mechanisms)>entry['closed_tolerance']):
                    self.closed_initial_drawers.add(role);self._record('initial_half_open_drawer_closed_with_contact',role)
                if self.task=='E26':
                    if displacement>=entry['open_threshold'] and not self.bell_down[role]:
                        if not self.open_contact[role]:
                            self.initial_valid=False
                            self._record('unactuated_press',role)
                        else:
                            self.bell_down[role]=True
                            event=dict(side=role,event='press',step=self.steps,contact=True)
                            self.event_history['bell_events'].append(event);self.events.append(deepcopy(event))
                    if self.bell_down[role] and abs(displacement)<=entry['closed_tolerance'] and not touched:
                        self.bell_down[role]=False;self.open_contact[role]=False
                        event=dict(side=role,event='release',step=self.steps)
                        self.event_history['bell_events'].append(event);self.events.append(deepcopy(event))
                else:
                    if (displacement>=entry['open_threshold'] and self.open_contact[role] and role not in self.opened_seen
                            and (self.execution_v3_drawer_input is None or active_touch)):
                        self.opened_seen.add(role);self._record('joint_opened_with_contact',role)
                    if (role in self.opened_seen and self.close_contact[role] and abs(displacement)<=entry['closed_tolerance']
                            and role not in self.closed_after_open):
                        self.closed_after_open.add(role);self._record('joint_closed_after_open',role)
            self.previous_touched[role]=touched

    def _mechanisms_within_envelope(self,current,anchor):
        """Bounded actual pose/joint movement, independent of tick frequency.

        Solver jitter can have a large instantaneous velocity at 250 Hz while
        remaining inside a sub-millimetre envelope. Compare every sample to a
        fixed anchor, not its predecessor, so cumulative drift still resets.
        """
        from .realworld_stability import for_evaluator
        settling=for_evaluator(self)
        if anchor is None:return False
        for mid,value in current.items():
            old=anchor[mid]
            if value['joint_names']!=old['joint_names'] or value['body_names']!=old['body_names']:return False
            if np.any(np.abs(value['joint_pos']-old['joint_pos'])>.0005):return False
            for body in value['body_names']:
                if np.linalg.norm(value['body_pos_task'][body]-old['body_pos_task'][body])>settling.translation_m:return False
                if np.linalg.norm(value['body_mat_task'][body]-old['body_mat_task'][body])>settling.rotation_matrix:return False
        return True

    def _derive(self,stable):
        released=self._released()
        obs=dict(released=released,stable=stable,opened_with_contact=sorted(self.opened_seen),
                 opened_measured=sorted(self.opened_measured),closed_after_open=sorted(self.closed_after_open),
                 pending_bell_presses={k:bool(v) for k,v in self.bell_down.items()})
        extra=dict(native_history_complete=self.history_valid,source_initial_state=self.initial_valid)
        if self.task=='E06':
            holder=self.semantic['holder'];assignments={};seated=[]
            for name in self.balls:
                center,half=self.bounds(name)
                choices=[cell for cell,data in self.semantic['cells'].items()
                         if np.linalg.norm(center[:2]-np.asarray(data['center'])[:2])<=data['radius']
                         and abs(center[2]-half[2]-data['center'][2])<=.012]
                if len(choices)==1 and self.contact(holder,name) and not any(self.state[name]['grasp']):
                    assignments[self.label(name)]=choices[0];seated.append(self.label(name))
            independent=all(np.linalg.norm(self.bounds(a)[0]-self.bounds(b)[0])>=max(self.bounds(a)[1])+max(self.bounds(b)[1])-.003
                            for i,a in enumerate(self.balls) for b in self.balls[i+1:])
            obs.update(ball_to_cell=assignments,seated=seated)
            extra.update(holder_frame_fixed=self.holder_fixed,independent_ball_bodies=bool(independent))
        elif self.task=='E18':
            delivered=[n for n in self.balls if self._in_target(n)]
            for n in delivered:
                if n not in self.progress_in_target:self.progress_delivery_steps[n]=self.steps
            self.progress_in_target=set(delivered)
            if (self.previous_mechanisms is not None and abs(self._joint('drawer'))<=self.roles['drawer']['closed_tolerance']
                    and abs(self._joint('drawer',self.previous_mechanisms))>self.roles['drawer']['closed_tolerance']
                    and self.close_contact.get('drawer')):
                self.progress_close_steps['drawer']=self.steps
            obs.update(drawer_opened_for_access='drawer' in self.opened_seen,
                       drawer_closed_after_delivery=bool(delivered and self.progress_close_steps.get('drawer',-1)>max(self.progress_delivery_steps[n] for n in delivered)),
                       delivered=[self.label(n) for n in delivered],
                       in_drawer=[self.label(n) for n in self._drawer_members()],
                       drawer_closed=abs(self._joint('drawer'))<=self.roles['drawer']['closed_tolerance'])
            extra['drawer_opened_and_reclosed_with_contact']='drawer' in self.closed_after_open
        elif self.task=='E26':
            obs['bell_events']=deepcopy(self.event_history['bell_events'])
            extra['all_plungers_released']=not any(self.bell_down.values()) and all(abs(self._joint(r))<=e['closed_tolerance'] for r,e in self.roles.items())
        else:
            displacement={r:self._joint(r) for r in self.roles}
            obs.update(opened={r:d>=self.roles[r]['open_threshold'] for r,d in displacement.items()},joint_displacements_m=displacement)
            selected=({'upper'},{'lower'},{'upper','lower'})['ABC'.index(self.variant)]
            extra['selected_drawers_have_contact_driven_open_history']=selected<=self.opened_seen
            extra['unselected_drawers_never_opened']=not (self.opened_measured-selected)
            if self.execution_v3_drawer_input is not None:
                obs.update(drawer_initial_revision=self.spec['execution_design']['revision'],
                           drawer_initial_displacements=deepcopy(self.execution_v3_drawer_input),
                           drawer_initial_state_valid=bool(self.initial_valid),
                           closed_with_contact=sorted(self.closed_initial_drawers))
                extra['unselected_initial_half_open_drawers_closed_with_contact']=set(self.roles)-selected<=self.closed_initial_drawers
        return obs,extra

    def update(self,state,contacts,dt):
        try:
            if not _number(dt) or dt<=0:raise ValueError('Invalid native physics interval')
            if not isinstance(state,Mapping) or set(state)!=set(self.objects):raise ValueError('Incomplete native rigid snapshot')
            if not isinstance(contacts,(set,frozenset)) or any(not isinstance(c,frozenset) or len(c)!=2 or not all(isinstance(n,str) for n in c) for c in contacts):raise ValueError('Invalid native contact pairs')
            if self.roles:
                if self.pending_mechanisms is None:raise ValueError('Fresh articulation snapshot required every physics step')
                self.mechanisms=self.pending_mechanisms
            self.pending_mechanisms=None
            clean={}
            for name,value in state.items():
                grasp=value['grasp']
                if len(grasp)!=2 or any(not isinstance(g,(bool,np.bool_)) for g in grasp):raise ValueError('Invalid native grasp state')
                clean[name]=dict(pos=_finite(value['pos'],(3,)),mat=_rotation(value['mat']),grasp=tuple(grasp))
            self.state,self.contacts=clean,set(contacts)
            self.steps+=1;self.elapsed+=dt
            if self.initial is None:
                self.initial=deepcopy(clean);self.initial_mechanisms=deepcopy(self.mechanisms)
                self.initial_valid=all(abs(self._joint(r))<=e['closed_tolerance'] for r,e in self.roles.items())
                if self.execution_v3_drawer_input is not None:
                    from .execution_design_drawers import matches_initial
                    self.initial_valid=matches_initial({r:self._joint(r)for r in self.roles},self.execution_v3_drawer_input,self.roles)
                if self.task=='E18':self.initial_valid=self.initial_valid and set(self._drawer_members())==set(self.balls)
            elif any(value['joint_names']!=self.initial_mechanisms[mid]['joint_names']
                     or value['body_names']!=self.initial_mechanisms[mid]['body_names'] for mid,value in self.mechanisms.items()):
                raise ValueError('Articulation identities changed during episode')
            for name,value in clean.items():
                if np.linalg.norm(value['pos']-self.initial[name]['pos'])>.015:self.moved.add(name)
            if self.task=='E06':
                holder=self.semantic['holder'];a=clean[holder];b=self.initial[holder]
                self.holder_fixed=self.holder_fixed and np.linalg.norm(a['pos']-b['pos'])<=.002 and np.linalg.norm(a['mat']-b['mat'])<=.02
            self._history()
            from .realworld_stability import for_evaluator
            settling=for_evaluator(self)
            anchored=self.anchor is not None and all(np.linalg.norm(v['pos']-self.anchor[n]['pos'])<=settling.translation_m
                     and np.linalg.norm(v['mat']-self.anchor[n]['mat'])<=settling.rotation_matrix for n,v in clean.items())
            anchored=anchored and self._mechanisms_within_envelope(self.mechanisms,self.anchor_mechanisms)
            released=self._released()
            if released and self.history_valid:
                if not anchored:
                    self.anchor=deepcopy(clean);self.anchor_mechanisms=deepcopy(self.mechanisms);self.hold_seconds=0.
                else:self.hold_seconds+=float(dt)
            else:
                self.hold_seconds=0.;self.anchor=None;self.anchor_mechanisms=None
            progress_evidence.update_physical(self, dt)
            for role,entry in self.roles.items():
                p,r=self._body(entry['mechanism'],entry['body'])
                progress_evidence.measured_group(self,role,{entry['body']:dict(pos=p,mat=r)},not self._touch(role),True,dt)
            self.observation,extra=self._derive(self.hold_seconds>=settling.seconds)
            self.observation=progress_evidence.finish_observation(self, self.observation)
            if self.execution_v2_bells:
                from .execution_design_inputs import e26_checks
                checks=e26_checks(self.spec,self.observation)
                self.last=dict(task=self.task,variant=self.variant,checks=checks,success=all(checks.values()))
            else:
                self.last=check_task(self.task,self.variant,self.observation)
            self.last['checks'].update(extra);self.last['success']=all(self.last['checks'].values())
            self.current_conditions=[dict(index=i,type=k,passed=bool(v)) for i,(k,v) in enumerate(self.last['checks'].items())]
            self.previous=deepcopy(clean);self.previous_mechanisms=deepcopy(self.mechanisms)
            self.event_history['moved_objects']=[self.label(n) for n in sorted(self.moved)]
        except (ValueError,KeyError,TypeError,IndexError,OverflowError) as exc:
            self.pending_mechanisms=None;self._error(exc)

    def result(self):
        result=deepcopy(dict(success=bool(self.last['success'] and self.history_valid),hold_seconds=self.hold_seconds,
            conditions=self.current_conditions,failed_checks=[c['type'] for c in self.current_conditions if not c['passed']],
            progress_evidence=progress_evidence.envelope(self),
            observation=self.observation,events=self.events,event_history=self.event_history,errors=self.errors,
            history_valid=self.history_valid,backend='isaaclab_physx',protocol='realworld50-native-mechanism-v1',provenance=self.provenance))
        if not self.execution_v2_bells:
            return progress_evidence.attach_score(result)
        from .execution_design_inputs import score_e26, e26_targets
        evidence=result['progress_evidence']
        evidence['execution_design']=deepcopy(self.spec['execution_design'])
        evidence['digit_cards']=deepcopy(self.semantic['digit_cards'])
        encoded=json.dumps(evidence,sort_keys=True,separators=(',',':'),ensure_ascii=False,allow_nan=False)
        available=self.history_valid and bool(self.observation) and evidence['source']=='trusted_native_per_physics_tick'
        score=score_e26(self.spec,self.observation) if available else None
        value=score['task_score_100'] if score else None
        if value is not None and not result['success']:value=min(value,90.)
        result['progress_result']=dict(protocol='realworld50-execution-v2-bell-progress',task=self.task,variant=self.variant,
            task_score_100=value,progress_available=available,units=[],
            missing_evidence=[] if available else ['history_invalid_or_untrusted'],
            failure_ceiling_100=90.,score_is_raw_before_native_gate=True,native_physics_verified=False,
            required_change_count=sum(e26_targets(self.spec).values()),
            evidence_sha256=hashlib.sha256(encoded.encode()).hexdigest())
        return result


__all__=['MechanismTaskEvaluator','SUPPORTED']
