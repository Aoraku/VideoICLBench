"""Private E18/E26/E30 demonstrations through native robot actuation.

Ordinary mode uses bounded public actions. Smooth recording uses the recorder's
continuous Cartesian targets with actual contact guards at every physical tick.
Both paths use author.tip, actual rigid/contact snapshots and
snapshot_mechanisms. No object/joint pose writes, drives, solver
flags, evaluator result or success feedback are read. This is a privileged
recording policy, never a public prompt or an actor-facing observation.

Required private recipe fields, in addition to the evaluator's joint_roles:
  semantic.handle_points / press_points: {role:{mechanism,body,local:[3],
      hand:'left'|'right' (optional), approach_local:[3] (optional),
      wrist_yaw_deg:0,wrist_pitch_deg:0,wrist_roll_deg:0 (optional)}}
  semantic.joint_motion: {role:{mechanism,body,axis_local:[3],
      open_distance:m,max_travel:m}}
axis_local means the direction of INCREASING NORMALIZED opening/press travel,
not necessarily the URDF positive q axis; body_mat_task transforms it to task
coordinates. No direction or handle position is guessed from an asset kind.
Approach_local points outwards from the contact point; default is +opening axis
for handles and -press axis for buttons. Points/axes must be source-reviewed.

Optional semantic.expert_clearance_z (default 1.15 m), expert_hand (default chosen
from measured point y), ball_grasp_offsets:{actor_id:[local xyz]}. Standard target
zone geometry and ball identity are used for E18. The grip is verified through
actual two-finger contacts, and cargo grasp is checked throughout transport.
Failures are bounded and explicit; a completed action sequence is not a physics
success claim. The caller separately records/evaluates the resulting episode.
"""
from collections.abc import Mapping
import math
import numpy as np


class MechanismExecutionError(RuntimeError):
    pass


def _vec(value):
    try:array=np.asarray(value,float)
    except (TypeError,ValueError) as exc:raise MechanismExecutionError('Invalid private geometry vector') from exc
    if array.shape!=(3,) or not np.isfinite(array).all():raise MechanismExecutionError('Nonfinite private/native geometry')
    return array.copy()


def _unit(value):
    array=_vec(value);norm=np.linalg.norm(array)
    if norm<1e-8:raise MechanismExecutionError('Zero mechanism motion axis')
    return array/norm


class _Author:
    def __init__(self,author):
        self.a=author;self.c=author.c;self.spec=author.scene.spec;self.semantic=self.spec['semantic']
        self.task,self.variant=self.spec['id'],self.spec['variant']
        if self.task not in ('E18','E26','E30'):raise NotImplementedError(self.task+': no mechanism recording policy')
        if self.variant not in ('A','B','C'):raise MechanismExecutionError('Unknown source variant')
        self.roles=self.semantic['joint_roles'];self.operations=[]
        self.button_releases={}
        required={'E18':{'drawer'},'E26':{'left','right'},'E30':{'upper','lower'}}[self.task]
        if set(self.roles)!=required:raise MechanismExecutionError('Incomplete joint-role mapping')
        self.motion=self.semantic.get('joint_motion',{})
        self.points=self.semantic.get('press_points' if self.task=='E26' else 'handle_points',{})
        self.clearance=float(self.semantic.get('expert_clearance_z',1.15))
        if not math.isfinite(self.clearance):raise MechanismExecutionError('Invalid transit clearance')
        self.max_actions=int(self.spec.get('expert_action_budget',600));self.start_steps=self.c.steps
        self.min_mm=.5;self.max_mm=20.
        config=getattr(getattr(author.scene,'embodiment',None),'config',{})
        bounds=config.get('control',{}).get('step_mm')
        if bounds is not None:self.min_mm=max(.5,float(bounds[0]));self.max_mm=min(20.,float(bounds[1]))
        if self.min_mm>self.max_mm:raise MechanismExecutionError('No compatible public Cartesian step range')
        self.bell_park_points=(self.bell_parking_geometry() if self.task=='E26'
                               and self.spec.get('author_smooth_recording',False) else None)
        for role in required:
            r=self.roles[role];m=self.motion.get(role);p=self.points.get(role)
            if not isinstance(m,Mapping) or not isinstance(p,Mapping):raise MechanismExecutionError('Reviewed motion and contact point required for '+role)
            for entry in (m,p):
                if entry.get('mechanism')!=r['mechanism'] or not isinstance(entry.get('body'),str):
                    raise MechanismExecutionError('Geometry must identify an actual articulation body for '+role)
            _vec(p['local']);_unit(m['axis_local'])
            if 'approach_local' in p:_unit(p['approach_local'])
            if p.get('hand','left') not in ('left','right'):raise MechanismExecutionError('Unknown hand')
            if r['direction'] not in (-1,1):raise MechanismExecutionError('Invalid normalized joint direction')
            values=[r['closed'],r['closed_tolerance'],r['open_threshold'],m['open_distance'],m['max_travel']]
            if not all(isinstance(v,(int,float)) and not isinstance(v,bool) and math.isfinite(v) for v in values):
                raise MechanismExecutionError('Finite joint calibration required')
            if not 0<=r['closed_tolerance']<r['open_threshold']<=m['open_distance']<=m['max_travel']:
                raise MechanismExecutionError('Inconsistent calibrated joint thresholds/travel')
            for angle in ('wrist_yaw_deg','wrist_pitch_deg','wrist_roll_deg'):
                value=p.get(angle,0.)
                if not isinstance(value,(int,float)) or isinstance(value,bool) or not math.isfinite(value) or abs(value)>180:
                    raise MechanismExecutionError('Invalid private wrist rotation: '+angle)
        # Validate all required names and frames before making any action.
        snapshot=self.mechanisms()
        for role in required:
            self.point(role,snapshot);self.axis(role,snapshot)
            if abs(self.displacement(role,snapshot))>self.roles[role]['closed_tolerance']:
                raise MechanismExecutionError('Episode must begin with closed/unpressed '+role)

    def mechanisms(self):
        snapshot=self.c.snapshot_mechanisms()
        if not isinstance(snapshot,Mapping):raise MechanismExecutionError('No actual articulation snapshot')
        return snapshot

    def bell_parking_geometry(self):
        """Reviewed robot base geometry is required; no guessed zero origin."""
        try:
            scene=self.a.scene;world_to_task=scene.world_to_task
            if not callable(world_to_task):raise TypeError('world_to_task must be callable')
            robots=scene.embodiment.config['robots'];points={}
            for side in ('left','right'):
                base=_vec(world_to_task(_vec(robots[side]['position'])))
                points[side]=np.array([base[0]+.15,base[1]+(.22 if side=='left' else -.22),1.25])
            return points
        except (AttributeError,KeyError,TypeError,ValueError,MechanismExecutionError) as exc:
            raise MechanismExecutionError('Reviewed robot base positions and world_to_task transform required for E26 final parking') from exc

    def park_bell_hands(self):
        """Lift both real hands, then park outside the source bell/card view."""
        if self.bell_park_points is None:raise MechanismExecutionError('E26 parking geometry was not validated')
        def released():
            if self.c.steps-self.start_steps>=self.max_actions:
                raise MechanismExecutionError('Mechanism expert action budget exhausted')
            for role in self.roles:
                if (abs(self.displacement(role))>self.roles[role]['closed_tolerance']
                        or not self.no_touch(role)):
                    raise MechanismExecutionError('Final parking must not touch or press a bell: '+role)
        released()
        # Include C's unused hand: an idle wrist can still hide the second bell.
        lifted={side:np.array([*self.tip(side)[:2],max(1.25,self.tip(side)[2])])
                for side in ('left','right')}
        self.stage('mechanism-bells-final-retreat')
        self.a.move_smooth(lifted,tolerance=.006,guard=released,max_speed=.18,max_acceleration=.6)
        targets={side:np.array([*point[:2],lifted[side][2]]) for side,point in self.bell_park_points.items()}
        self.stage('mechanism-bells-final-park')
        self.a.move_smooth(targets,tolerance=.006,guard=released,max_speed=.18,max_acceleration=.6)

    def frame(self,entry,snapshot):
        try:
            value=snapshot[entry['mechanism']];body=entry['body']
            if body not in value['body_names']:raise KeyError(body)
            p=_vec(value['body_pos_task'][body]);r=np.asarray(value['body_mat_task'][body],float)
            if r.shape!=(3,3) or not np.isfinite(r).all() or not np.allclose(r.T@r,np.eye(3),atol=1e-4) or not np.isclose(np.linalg.det(r),1.,atol=1e-4):raise ValueError('bad rotation')
            return p,r
        except (KeyError,TypeError,ValueError) as exc:raise MechanismExecutionError('Missing/invalid actual articulation frame') from exc

    def point(self,role,snapshot=None):
        entry=self.points[role];p,r=self.frame(entry,snapshot or self.mechanisms())
        return p+r@_vec(entry['local'])

    def axis(self,role,snapshot=None):
        entry=self.motion[role];_,r=self.frame(entry,snapshot or self.mechanisms())
        return _unit(r@_unit(entry['axis_local']))

    def displacement(self,role,snapshot=None):
        entry=self.roles[role];snapshot=snapshot or self.mechanisms()
        try:
            value=snapshot[entry['mechanism']];names=value['joint_names'];values=value['joint_pos']
            if len(names)!=len(values) or names.count(entry['joint'])!=1:raise ValueError('joint identity')
            q=float(values[names.index(entry['joint'])]);travel=(q-entry['closed'])*entry['direction']
        except (KeyError,ValueError,IndexError,TypeError) as exc:raise MechanismExecutionError('Missing actual joint value for '+role) from exc
        if not math.isfinite(travel) or travel<-.003 or travel>self.motion[role]['max_travel']+.003:
            raise MechanismExecutionError('Joint outside calibrated travel: '+role)
        return travel

    def tip(self,side):return _vec(self.a.tip(side))

    def act(self,side=None,token='STILL',mm=1.):
        if self.c.steps-self.start_steps>=self.max_actions:raise MechanismExecutionError('Mechanism expert action budget exhausted')
        self.a.act(token if side=='left' else 'STILL',token if side=='right' else 'STILL',mm=max(self.min_mm,min(self.max_mm,float(mm))))

    def stage(self,name):
        self.a.stage=name
        note=getattr(self.a,'note',None)
        if callable(note):note(name)

    def move(self,side,target,tolerance=.0015,guard=None,done=None):
        target=_vec(target);history=[]
        if self.spec.get('author_smooth_recording',False):
            if self.c.steps-self.start_steps>=self.max_actions:raise MechanismExecutionError('Mechanism expert action budget exhausted')
            return self.a.move_smooth({side:target},tolerance=tolerance,guard=guard,done=done)
        for _ in range(120):
            if guard:guard()
            if done and done():return
            error=target-self.tip(side)
            if np.max(np.abs(error))<=tolerance:return
            axis=int(np.argmax(np.abs(error)))
            token=(('FWD','BACK'),('LEFT','RIGHT'),('UP','DOWN'))[axis][int(error[axis]<0)]
            # Public actions use the rig's normal transit step, with a smaller
            # loaded step while contact/grasp feedback is guarded.
            mm=min(8. if guard else self.max_mm,max(self.min_mm,abs(error[axis])*1000))
            self.act(side,token,mm)
            if guard:guard()
            history.append(self.tip(side))
            if len(history)>=10 and max(np.linalg.norm(p-history[-1]) for p in history[-10:])<.0002:
                raise MechanismExecutionError('Cartesian motion stalled at '+self.a.stage)
        raise MechanismExecutionError('Cartesian waypoint unreachable at '+self.a.stage)

    def contacts(self):
        _,contacts=self.c.snapshot()
        if not isinstance(contacts,(set,frozenset)):raise MechanismExecutionError('Actual contact set required')
        return contacts

    def touching(self,role,side,both=False):
        contacts=self.contacts();body=self.roles[role]['contact_body']
        values=[frozenset((body,f'{side}_finger{i}')) in contacts for i in (1,2)]
        return all(values) if both else any(values)

    def no_touch(self,role):
        return not any(self.touching(role,s) for s in ('left','right'))

    def hand(self,role):
        return self.points[role].get('hand',self.semantic.get('expert_hand','left' if self.point(role)[1]>=0 else 'right'))

    def yaw(self,side,degrees):
        # Public relative rotations only; source recipe defines a reviewed
        # offset from the rig's initial wrist orientation, not a pose write.
        if abs(degrees)<1e-9:return
        quantum=10.
        if abs(degrees/quantum-round(degrees/quantum))>1e-6:
            raise MechanismExecutionError('wrist_yaw_deg must use public 10-degree increments')
        for _ in range(round(abs(degrees)/quantum)):
            self.act(side,'ROTATE_CCW' if degrees>0 else 'ROTATE_CW')

    def orient(self,role,side,inverse=False):
        # Task-frame rotations compose in order. Releasing a handle restores
        # the inverse order, so the next source-reviewed grasp starts from the
        # same orientation even when both drawers use one physical hand.
        commands=[('wrist_yaw_deg','ROTATE_CCW','ROTATE_CW'),
                  ('wrist_pitch_deg','PITCH_UP','PITCH_DOWN'),
                  ('wrist_roll_deg','ROLL_LEFT','ROLL_RIGHT')]
        for field,positive,negative in (reversed(commands) if inverse else commands):
            degrees=float(self.points[role].get(field,0.))*(-1 if inverse else 1)
            if abs(degrees/10.-round(degrees/10.))>1e-6:
                raise MechanismExecutionError(field+' must use public 10-degree increments')
            for _ in range(round(abs(degrees)/10.)):
                self.act(side,positive if degrees>0 else negative)

    def approach(self,role,side,button=False):
        p=self.point(role);axis=self.axis(role)
        config=self.a.scene.embodiment.config.get('author_recording',{})
        grip_tolerance=float(config.get('mechanism_grasp_tolerance_m',.002))
        if not .0005<=grip_tolerance<=.005:raise MechanismExecutionError('Invalid handle approach tolerance')
        entry=self.points[role]
        if 'approach_local' in entry:
            _,r=self.frame(entry,self.mechanisms());outward=_unit(r@_unit(entry['approach_local']))
        else:outward=-axis if button else axis
        stand=p+outward*(.020 if button else .045)
        if (not button and self.spec.get('author_smooth_recording',False)
                and self.semantic.get('expert_approach_mode')=='horizontal_front_corridor'):
            if abs(outward[2])>.1:
                raise MechanismExecutionError('Horizontal front corridor requires a measured horizontal handle normal')
            current=self.tip(side)
            depth=max(.11,float((current-p)@outward))
            front=p+outward*depth
            # A sideways Panda wrist has a different vertical workspace.
            # Stay outside the source cabinet's front plane and approach
            # laterally at the measured handle height instead of requiring
            # an unreachable high pose after rotating the wrist.
            lane=current+outward*float((front-current)@outward)
            lane[2]=p[2]
            self.move(side,lane)
            self.move(side,front)
            self.move(side,stand)
            self.move(side,self.point(role),tolerance=grip_tolerance)
            return
        if button and self.spec.get('author_smooth_recording',False):
            current=self.tip(side);offset=current-p
            lateral=offset-outward*float(offset@outward)
            # Repeat a released press from just above the same plunger. A
            # different bell, lateral drift or a hand on the pressed side
            # still uses the complete high-clearance route below.
            if (self.button_releases.get(side)==role
                    and np.linalg.norm(lateral)<=.003
                    and np.linalg.norm(current-stand)<=.05
                    and float(offset@outward)>=0.
                    and abs(self.displacement(role))<=self.roles[role]['closed_tolerance']
                    and self.no_touch(role)):
                self.move(side,stand)
                return
        z=max(self.clearance,p[2]+.10,self.tip(side)[2])
        self.move(side,[*self.tip(side)[:2],z])
        self.move(side,[*stand[:2],z])
        self.move(side,stand)
        if not button:self.move(side,self.point(role),tolerance=grip_tolerance)

    def retreat(self,role,side,button=False):
        outward=-self.axis(role) if button else self.axis(role)
        if (not button and self.spec.get('author_smooth_recording',False)
                and self.semantic.get('expert_approach_mode')=='horizontal_front_corridor'):
            self.move(side,self.tip(side)+outward*.11)
            return
        self.move(side,self.tip(side)+outward*(.012 if button else .035))
        if button and self.spec.get('author_smooth_recording',False):return
        self.move(side,[*self.tip(side)[:2],max(self.clearance,self.tip(side)[2]+.03)])

    def acquire(self,role):
        side=self.hand(role);self.stage('mechanism-approach-'+role)
        self.act(side,'RELEASE')
        config=self.a.scene.embodiment.config.get('author_recording',{})
        if config.get('acquire_align_above_source',False):
            p=self.point(role);height=max(self.clearance,float(p[2])+.15,float(self.tip(side)[2]))
            self.move(side,[*self.tip(side)[:2],height])
            self.move(side,[*p[:2],height])
        self.orient(role,side);self.approach(role,side)
        for _ in range(3):
            self.act(side,'GRASP')
            if self.touching(role,side,both=True):return side
        raise MechanismExecutionError('No physical two-finger handle grip: '+role)

    def drawer(self,role,close=False):
        side=self.acquire(role);target=0. if close else self.motion[role]['open_distance']
        tolerance=self.roles[role]['closed_tolerance'] if close else min(.001,self.motion[role]['open_distance']-self.roles[role]['open_threshold'])
        initial=self.displacement(role);history=[]
        self.stage(('mechanism-close-' if close else 'mechanism-open-')+role)
        bilateral=self.a.scene.embodiment.config.get('author_recording',{}).get('mechanism_bilateral_transport_required',True)
        def guard():
            self.displacement(role)
            if not self.touching(role,side,both=bilateral):raise MechanismExecutionError('Handle grip lost during joint motion: '+role)
        for _ in range(80):
            q=self.displacement(role)
            if abs(target-q)<=tolerance:break
            guard();direction=self.axis(role)*(1 if target>q else -1)
            amount=min(.006,max(.0005,abs(target-q)))
            self.move(side,self.tip(side)+direction*amount,tolerance=.0003,guard=guard,
                      done=lambda:abs(target-self.displacement(role))<=tolerance)
            history.append(self.displacement(role))
            if len(history)>=8 and max(history[-8:])-min(history[-8:])<.0002:
                raise MechanismExecutionError('Drawer joint stalled despite handle contact: '+role)
        else:raise MechanismExecutionError('Drawer did not reach measured target: '+role)
        final=self.displacement(role)
        if abs(final-initial)<.001:raise MechanismExecutionError('No measured drawer travel: '+role)
        self.act(side,'RELEASE');self.retreat(role,side)
        self.orient(role,side,inverse=True)
        for _ in range(2):self.act()
        final=self.displacement(role)
        if close and abs(final)>self.roles[role]['closed_tolerance']:raise MechanismExecutionError('Drawer reopened after release')
        if not close and final<self.roles[role]['open_threshold']:raise MechanismExecutionError('Drawer did not stay open after release')
        self.operations.append(dict(operation='close' if close else 'open',role=role,start=initial,end=final))

    def press(self,role,index):
        side=self.hand(role);self.stage(f'mechanism-press-{role}-{index}')
        self.act(side,'GRASP');self.approach(role,side,button=True)
        if abs(self.displacement(role))>self.roles[role]['closed_tolerance'] or not self.no_touch(role):
            raise MechanismExecutionError('Bell was not released before next cycle: '+role)
        start=self.tip(side);had_contact=False
        if self.spec.get('author_smooth_recording',False):
            axis=self.axis(role);travel=.020+self.motion[role]['max_travel']+.010
            def guard():
                nonlocal had_contact
                had_contact=had_contact or self.touching(role,side)
                if np.linalg.norm(self.tip(side)-start)>travel+.001:
                    raise MechanismExecutionError('Bell contact/travel missing at reviewed press point')
                if self.displacement(role)>=self.roles[role]['open_threshold'] and not had_contact:
                    raise MechanismExecutionError('Bell moved without observed plunger contact')
            done=lambda:self.displacement(role)>=self.roles[role]['open_threshold']
            self.a.move_smooth({side:start+axis*travel},tolerance=.0005,
                guard=guard,done=done,max_speed=.02,max_acceleration=.2)
            if not done() or not had_contact:
                raise MechanismExecutionError('Bell failed to reach physical press threshold with contact')
        else:
            self.press_steps(role,side,start)
        measured_press=self.displacement(role)
        self.retreat(role,side,button=True)
        for _ in range(20):
            if abs(self.displacement(role))<=self.roles[role]['closed_tolerance'] and self.no_touch(role):break
            self.act()
        else:raise MechanismExecutionError('Bell spring failed to return or finger still touching')
        if self.spec.get('author_smooth_recording',False):self.button_releases[side]=role
        self.operations.append(dict(operation='press_release',role=role,cycle=index,pressed=measured_press,released=self.displacement(role)))

    def press_steps(self,role,side,start):
        had_contact=False
        for _ in range(64):
            q=self.displacement(role);touch=self.touching(role,side)
            had_contact=had_contact or touch
            if q>=self.roles[role]['open_threshold']:
                if not had_contact:raise MechanismExecutionError('Bell moved without observed plunger contact')
                break
            if np.linalg.norm(self.tip(side)-start)>.020+self.motion[role]['max_travel']+.010:
                raise MechanismExecutionError('Bell contact/travel missing at reviewed press point')
            step=.0005 if touch else .002
            # A physical contact step is driven along the reviewed button
            # normal. Requiring the *whole TCP* to converge within .2 mm for
            # every .5 mm press caused submillimetre IK cross-axis residuals
            # to consume the entire attempt before the finger reached the
            # button. Joint travel and observed plunger contact remain the
            # completion evidence. Correct only material transverse drift.
            axis=self.axis(role);error=self.point(role)-self.tip(side)
            lateral=error-axis*float(error@axis)
            if np.linalg.norm(lateral)>.003:
                self.move(side,self.tip(side)+lateral,tolerance=.0015)
            component=int(np.argmax(np.abs(axis)))
            token=(('FWD','BACK'),('LEFT','RIGHT'),('UP','DOWN'))[component][int(axis[component]<0)]
            self.act(side,token,mm=step*1000/abs(float(axis[component])))
        else:raise MechanismExecutionError('Bell failed to reach physical press threshold')

    def ball(self):
        color=('red','green','blue')['ABC'.index(self.variant)]
        objects={o['id']:o for o in self.spec['objects']}
        selected=[n for n in self.semantic['groups']['balls'] if objects[n].get('semantic_identity',objects[n].get('identity',n))==color]
        if len(selected)!=1:raise MechanismExecutionError('Unique source-color ball identity required')
        name=selected[0];obj=objects[name];state,_=self.c.snapshot();p=_vec(state[name]['pos'])
        side=self.semantic.get('expert_hand','left' if p[1]>=0 else 'right')
        zone=next((z for z in self.spec['zones'] if z['id']=='target'),None)
        if zone is None:raise MechanismExecutionError('Target paper region missing')
        local=self.semantic.get('ball_grasp_offsets',{}).get(name,[0,0,0]);grasp=p+np.asarray(state[name]['mat'])@_vec(local)
        self.stage('mechanism-retrieve-'+name);self.act(side,'RELEASE')
        z=max(self.clearance,grasp[2]+.10,self.tip(side)[2])
        self.move(side,[*self.tip(side)[:2],z]);self.move(side,[*grasp[:2],z]);self.move(side,grasp)
        index=0 if side=='left' else 1
        def guard():
            s,_=self.c.snapshot()
            if not s[name]['grasp'][index]:raise MechanismExecutionError('Ball grasp lost during transport')
        for _ in range(3):
            self.act(side,'GRASP');s,_=self.c.snapshot()
            if s[name]['grasp'][index]:break
        else:raise MechanismExecutionError('Selected ball not physically grasped')
        self.move(side,[*self.tip(side)[:2],z],guard=guard)
        self.move(side,[*zone['xy'],z],guard=guard)
        radius=float(max(obj['size']));target=np.array([*zone['xy'],zone.get('surface_z',.8)+radius+.003])
        # Preserve the measured ball-to-TCP offset, rather than assuming the
        # ball origin coincides exactly with the grasp centre.
        s,_=self.c.snapshot();offset=_vec(s[name]['pos'])-self.tip(side)
        self.move(side,target-offset,guard=guard)
        self.act(side,'RELEASE');self.move(side,[*self.tip(side)[:2],z])
        for _ in range(3):self.act()
        s,contacts=self.c.snapshot();actual=_vec(s[name]['pos'])
        if (any(s[name]['grasp']) or frozenset((name,zone.get('support','table'))) not in contacts
                or np.any(np.abs(actual[:2]-zone['xy'])>np.asarray(zone['half_size'])+.005)):
            raise MechanismExecutionError('Selected ball did not physically settle on target paper')
        self.operations.append(dict(operation='deliver_ball',object=name,position=actual.tolist()))

    def solve(self):
        if self.task=='E26':
            counts=((9,1),(1,9),(10,0))['ABC'.index(self.variant)]
            for role,count in zip(('left','right'),counts):
                for index in range(1,count+1):self.press(role,index)
            if self.spec.get('author_smooth_recording',False):
                self.park_bell_hands()
        elif self.task=='E30':
            selected=(('upper',),('lower',),('upper','lower'))['ABC'.index(self.variant)]
            for role in selected:self.drawer(role)
        else:
            self.drawer('drawer');self.ball();self.drawer('drawer',close=True)
        # Real elapsed physics via STILL, no wall-clock sleep or state writes.
        for _ in range(3):self.act()
        self.stage('mechanism-actions-complete')
        return dict(task=self.task,variant=self.variant,operations=self.operations,
                    execution='continuous_robot_targets_completed' if self.spec.get('author_smooth_recording',False) else 'public_actions_completed',
                    physics_success_evaluated=False)


def solve_mechanism(author):
    """Record a private native mechanism demonstration; raise on missing evidence."""
    return _Author(author).solve()


__all__=['solve_mechanism','MechanismExecutionError']
