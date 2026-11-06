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
    def __init__(self,author,*,allow_existing_e18_drawer=False):
        self.a=author;self.c=author.c;self.spec=author.scene.spec;self.semantic=self.spec['semantic']
        self.task,self.variant=self.spec['id'],self.spec['variant']
        if allow_existing_e18_drawer:
            resume=self.spec.get('engineering_checkpoint_resume',{})
            if (self.task!='E18' or resume.get('diagnostic_only')is not True
                    or resume.get('entry')not in ('e18_continue_held_short_pull','e18_hold166_then_three_short_pulls','e18_follow166_then_two_short_pulls','e18_zfollow2_then_two_2mm_pulls','e18_zfollow4_before_two_2mm_pulls','e18_regrasp2_deeper_then_two_pulls','e18_finish_closing3_then_two_pulls','e18_continue_original_open4','e18_grasp_lift_ball_from616','e18_grasp_lift_ball_from_open483','e18_roll_selected_ball_from160','e18_roll_selected_ball_from_closed3','e18_roll_selected_ball_from_tilted40','e18_closed_cap_from3')
                    or not getattr(author,'control_report',{}).get('engineering_reference_only')):
                raise MechanismExecutionError('Existing drawer travel requires explicit E18 held short-pull checkpoint')
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
        from .execution_design_drawers import initial_displacements,matches_initial
        drawer_input=initial_displacements(self.spec)
        if drawer_input is not None and not matches_initial({r:self.displacement(r,snapshot)for r in required},drawer_input,self.roles):
            raise MechanismExecutionError('Measured E30 input differs from declared half-open scene')
        for role in required:
            self.point(role,snapshot);self.axis(role,snapshot)
            if (drawer_input is None and not allow_existing_e18_drawer
                    and abs(self.displacement(role,snapshot))>self.roles[role]['closed_tolerance']):
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
                base=_vec(world_to_task(_vec(robots[side]['position'])+_vec(getattr(scene,'origin',(0.,0.,0.)))))
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
        import os
        if self.task=='E30' and side in ('left','right') and os.environ.get('VIC_ENGINEERING_DRAWER_IK_PROBE')=='1':
            from .execution_design_drawer_ik_probe import record_action_dynamics
            record_action_dynamics(self.a,self.c,side,token)

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

    def drawer_jaw_axis(self,role):
        entry=self.points[role]
        if 'pinch_axis_local' in entry:
            _,rotation=self.frame(entry,self.mechanisms())
            return _unit(rotation@_unit(entry['pinch_axis_local']))
        return _unit(np.cross(np.array([0.,0.,1.]),self.axis(role)))

    def engineering_drawer_grasp_axes(self,role):
        outward=self.axis(role);jaw=self.drawer_jaw_axis(role)
        if self.engineering_drawer_panel_push(role):
            # Empty closed fingers push the front panel; they need not pinch
            # the handle. Keeping the jaw horizontal avoids the other drawer.
            return outward,_unit(np.cross(outward,jaw))
        import os
        from .execution_design_drawers import initial_displacements
        if role=='lower' and os.environ.get('VIC_ENGINEERING_DRAWER_IK_PROBE')=='1' and initial_displacements(self.spec) is not None and not any(m.get('instance_support_lift_m',0.)>=.04 for m in self.spec.get('mechanisms',[])):
            # Native v13 measured q + source collision meshes show a vertical
            # Panda palm hits the table before reaching this lower handle.
            # Oblique pinch retains 8.4mm opening margin; source-convex checks
            # give 13.3mm table and 14.3mm cabinet palm clearance. Public motion
            # and actual bilateral contacts still determine physical success.
            from .realworld_tool_expert import _axis_rotation
            inward=-outward;pitch_axis=_unit(np.cross([0.,0.,1.],inward))
            turn=_axis_rotation(pitch_axis,math.radians(15.))@_axis_rotation(inward,math.radians(45.))
            return turn@outward,turn@jaw
        return outward,jaw

    def engineering_drawer_capture_target(self,role):
        p=self.point(role)
        if self.engineering_drawer_panel_push(role):
            # Actual source board_0 center is 32.7mm below the handle. A 4mm
            # stand-off leaves ~2mm before the closed fingertips meet its face.
            return p+np.array([0.,0.,-.033])+self.axis(role)*.004
        import os
        from .execution_design_drawers import initial_displacements
        if role=='lower' and os.environ.get('VIC_ENGINEERING_DRAWER_IK_PROBE')=='1' and initial_displacements(self.spec) is not None and not any(m.get('instance_support_lift_m',0.)>=.04 for m in self.spec.get('mechanisms',[])):
            # Source convex finger sweeps at native v15 poses: 7mm outside
            # the bar center lets both fingers contact the real bar during
            # closure without requiring open fingers to enter the front panel.
            # Keep the actual handle point unchanged for all native checks.
            return p+self.axis(role)*.007
        return p

    def engineering_drawer_panel_push(self,role):
        import os
        return (os.environ.get('VIC_ENGINEERING_DRAWER_PANEL_PUSH')=='1'
                and getattr(self,'task',None)=='E30' and getattr(self,'drawer_closing_role',None)==role
                and any(m.get('instance_support_lift_m',0.)>=.04 for m in self.spec.get('mechanisms',[])))

    def orient_drawer_measured(self,role,side,inverse=False):
        from .author_orientation import _rotation,_axis_angle
        from .realworld_tool_expert import _axis_rotation
        actual=lambda:_rotation(self.a.tcp_rotation_task(side),'actual E30 TCP')
        if not hasattr(self,'drawer_neutral_rotations'):self.drawer_neutral_rotations={}
        if side not in self.drawer_neutral_rotations:self.drawer_neutral_rotations[side]=actual().copy()
        target=self.drawer_neutral_rotations[side].copy()
        if not inverse:
            for field,axis in [('wrist_yaw_deg',[0,0,1]),('wrist_pitch_deg',[0,1,0]),('wrist_roll_deg',[1,0,0])]:
                target=_axis_rotation(axis,math.radians(float(self.points[role].get(field,0.))))@target
            if side=='right' and any(abs(float(self.points[role].get(f,0.)))>1e-9 for f in ('wrist_yaw_deg','wrist_pitch_deg','wrist_roll_deg')):
                # Empty Panda pinch is symmetric under a half-turn about its
                # longitudinal TCP axis: preserve approach direction, swap jaws.
                # v7 hit joint7 on the original assignment before any contact.
                target=target@_axis_rotation([0,0,1],math.pi)
        import os
        if not inverse and os.environ.get('VIC_ENGINEERING_DRAWER_IK_PROBE')=='1':
            from .execution_design_drawer_ik_probe import inspect,physical_grasp_targets
            candidates=physical_grasp_targets(self.a,self.c,side,*self.engineering_drawer_grasp_axes(role))
            if (role,side) in getattr(self,'drawer_selected_rotations',{}):
                candidates=[self.drawer_selected_rotations[(role,side)]]
            predictions=inspect(self.a,self.c,side,candidates)
            feasible=[row for row in predictions if row['kinematically_reachable']]
            if not feasible:
                raise MechanismExecutionError('Measured native IK predicts neither symmetric wrist assignment reachable at staging pose')
            selected=min(feasible,key=lambda row:(row['minimum_joint_margin_rad']<.05,row['joint_distance_rad']))
            target=candidates[selected['index']]
        labels=(('ROLL_LEFT','ROLL_RIGHT'),('PITCH_UP','PITCH_DOWN'),('ROTATE_CCW','ROTATE_CW'))
        limits=self.a.scene.embodiment.config.get('control',{}).get('rotation_deg',[.5,10.])
        lo=max(.5,float(limits[0]));hi=min(10.,float(limits[1]));history=[]
        for _ in range(360):
            current=actual();axis,angle=_axis_angle(target@current.T)
            if angle<math.radians(1.5):return
            if self.c.steps-self.start_steps>=self.max_actions:raise MechanismExecutionError('Mechanism expert action budget exhausted')
            component=int(np.argmax(np.abs(axis)));token=labels[component][int(axis[component]<0)]
            degrees=min(hi,max(lo,abs(math.degrees(angle*axis[component]))))
            self.a.act(token if side=='left'else'STILL',token if side=='right'else'STILL',rotation_deg=degrees)
            history.append(actual())
            if len(history)>=12 and max(_axis_angle(r@history[-1].T)[1]for r in history[-12:])<.002:
                raise MechanismExecutionError('Measured E30 wrist rotation stalled before handle approach')
        raise MechanismExecutionError('Measured E30 wrist orientation did not converge')

    def orient(self,role,side,inverse=False):
        from .execution_design_drawers import initial_displacements
        if initial_displacements(self.spec) is not None:
            return self.orient_drawer_measured(role,side,inverse=inverse)
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

    def front_corridor(self):
        # New half-open E30 inputs use the source handle's horizontal front
        # normal. This geometry route is independent of video interpolation.
        from .execution_design import REVISION_V3
        design=self.spec.get('execution_design',{})
        new_drawer=(self.task=='E30' and design.get('revision')==REVISION_V3
                    and design.get('condition') in ('I','E'))
        return new_drawer or (self.spec.get('author_smooth_recording',False)
                and self.semantic.get('expert_approach_mode')=='horizontal_front_corridor')

    def approach(self,role,side,button=False):
        p=self.point(role);axis=self.axis(role)
        if not button and self.task=='E30':p=self.engineering_drawer_capture_target(role)
        config=self.a.scene.embodiment.config.get('author_recording',{})
        grip_tolerance=float(config.get('mechanism_grasp_tolerance_m',.002))
        if not .0005<=grip_tolerance<=.005:raise MechanismExecutionError('Invalid handle approach tolerance')
        entry=self.points[role]
        if 'approach_local' in entry:
            _,r=self.frame(entry,self.mechanisms());outward=_unit(r@_unit(entry['approach_local']))
        else:outward=-axis if button else axis
        stand=p+outward*(.020 if button else .045)
        if not button and self.front_corridor():
            if abs(outward[2])>.1:
                raise MechanismExecutionError('Horizontal front corridor requires a measured horizontal handle normal')
            current=self.tip(side)
            import os
            if os.environ.get('VIC_ENGINEERING_DRAWER_IK_PROBE')=='1':
                # Descending at the farther rotation staging depth can fold the
                # arm into a local singularity. Advance in the clear front lane
                # first, then descend 11cm outside the actual handle plane.
                front=p+outward*.11
                elevated=front.copy();elevated[2]=max(float(current[2]),float(p[2]))
                from .execution_design_drawer_ik_probe import inspect
                rotation=self.a.tcp_rotation_task(side)
                predicted=inspect(self.a,self.c,side,[dict(position=goal,rotation=rotation)for goal in(elevated,front,stand,p)])
                if not all(row['kinematically_reachable']for row in predicted):
                    raise MechanismExecutionError('Measured IK rejects approach waypoint; no speculative descent issued')
                self.move(side,elevated)
                self.move(side,front)
                self.move(side,stand)
                self.move(side,self.engineering_drawer_capture_target(role),tolerance=grip_tolerance)
                return
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
            self.move(side,self.engineering_drawer_capture_target(role),tolerance=grip_tolerance)
            return
        from .execution_design_bell_repeat import enabled as short_bell_repeat
        if button and (self.spec.get('author_smooth_recording',False) or short_bell_repeat(self)):
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
        if not button and self.front_corridor():
            self.move(side,self.tip(side)+outward*.11)
            return
        self.move(side,self.tip(side)+outward*(.012 if button else .035))
        from .execution_design_bell_repeat import enabled as short_bell_repeat
        if button and (self.spec.get('author_smooth_recording',False) or short_bell_repeat(self)):return
        self.move(side,[*self.tip(side)[:2],max(self.clearance,self.tip(side)[2]+.03)])

    def stage_drawer_orientation(self,role,side):
        # Rotate outside and above the measured handle. The lateral home TCP
        # exhausted joint6 in v4; handle-height staging exhausted joint2 in v6.
        from .author_orientation import _rotation
        if not hasattr(self,'drawer_neutral_rotations'):self.drawer_neutral_rotations={}
        if side not in self.drawer_neutral_rotations:
            self.drawer_neutral_rotations[side]=_rotation(self.a.tcp_rotation_task(side),'actual E30 TCP').copy()
        p=self.engineering_drawer_capture_target(role);outward=self.axis(role)
        if abs(float(outward[2]))>.1:
            raise MechanismExecutionError('E30 orientation staging requires horizontal drawer normal')
        current=self.tip(side)
        depth=max(.17,float((current-p)@outward))
        front=p+outward*depth
        front[2]=max(float(p[2])+.10,float(current[2]))
        import os
        if os.environ.get('VIC_ENGINEERING_DRAWER_IK_PROBE')=='1':
            from .execution_design_drawer_ik_probe import inspect,physical_grasp_targets
            rotations=physical_grasp_targets(self.a,self.c,side,*self.engineering_drawer_grasp_axes(role))
            options=[]
            for distance in (.12,.18,.24):
                for height in (.04,.12,.20):
                    position=p+outward*distance;position[2]=p[2]+height
                    for rotation in rotations:
                        options.append(dict(position=position,rotation=rotation))
            predictions=inspect(self.a,self.c,side,options)
            final_predictions=inspect(self.a,self.c,side,[dict(position=p,rotation=rotation)for rotation in rotations])
            final_reachable={row['index'] for row in final_predictions if row['kinematically_reachable']}
            feasible=[row for row in predictions if row['kinematically_reachable'] and row['index']%2 in final_reachable]
            if not feasible:raise MechanismExecutionError('Measured native IK found no reachable front rotation staging pose')
            selected=min(feasible,key=lambda row:(row['minimum_joint_margin_rad']<.08,row['joint_distance_rad']))
            front=options[selected['index']]['position']
            if not hasattr(self,'drawer_selected_rotations'):self.drawer_selected_rotations={}
            self.drawer_selected_rotations[(role,side)]=options[selected['index']]['rotation']
        lane=current+outward*float((front-current)@outward)
        lane[2]=front[2]
        self.move(side,lane)
        self.move(side,front)

    def choose_drawer_hand(self,role):
        import os
        if os.environ.get('VIC_ENGINEERING_DRAWER_IK_PROBE')!='1':return self.hand(role)
        from .execution_design_drawers import initial_displacements
        if initial_displacements(self.spec) is None:return self.hand(role)
        from .execution_design_drawer_ik_probe import inspect,physical_grasp_targets
        feasible=[]
        for side in ('left','right'):
            rotations=physical_grasp_targets(self.a,self.c,side,*self.engineering_drawer_grasp_axes(role))
            rows=inspect(self.a,self.c,side,[dict(position=self.engineering_drawer_capture_target(role),rotation=r)for r in rotations])
            feasible.extend(dict(side=side,**row)for row in rows if row['kinematically_reachable'])
        if not feasible:raise MechanismExecutionError('Neither actual arm has a feasible handle grasp pose')
        return min(feasible,key=lambda row:(-row['minimum_joint_margin_rad'],row['joint_distance_rad']))['side']

    def acquire(self,role,*,closing_push=False):
        side=self.choose_drawer_hand(role);self.stage('mechanism-approach-'+role)
        self.act(side,'RELEASE')
        config=self.a.scene.embodiment.config.get('author_recording',{})
        if config.get('acquire_align_above_source',False):
            p=self.point(role);height=max(self.clearance,float(p[2])+.15,float(self.tip(side)[2]))
            self.move(side,[*self.tip(side)[:2],height])
            self.move(side,[*p[:2],height])
        from .execution_design_drawers import initial_displacements
        if initial_displacements(self.spec) is not None:
            self.stage_drawer_orientation(role,side)
        self.orient(role,side)
        if initial_displacements(self.spec) is not None:
            # Public rotations begin from achieved poses. Nine nominal 10deg
            # requests need not produce 90deg; measure the real jaw axis before
            # approaching the cabinet instead of accumulating that error.
            normal=self.axis(role)
            if abs(float(normal[2]))>.1:
                raise MechanismExecutionError('E30 front grasp requires horizontal measured drawer normal')
            _,jaw=self.engineering_drawer_grasp_axes(role)
            self.a.align_gripper_axis(side,jaw)
        if closing_push and self.engineering_drawer_panel_push(role):self.act(side,'GRASP')
        self.approach(role,side)
        if closing_push:
            # Closing a drawer is a contact push, not a tensile grasp. Native
            # joint/contact history still decides whether it really closed.
            self.act(side,'GRASP')
            return side
        refresh_handle=initial_displacements(self.spec) is not None
        for attempt in range(6 if refresh_handle else 3):
            self.act(side,'GRASP')
            if self.touching(role,side,both=True):return side
            if refresh_handle and attempt<5:
                # Finger closure can move a freely sliding drawer a few mm.
                # Releasing and following the measured handle prevents all
                # retries from squeezing empty space at its former position.
                self.act(side,'RELEASE')
                self.move(side,self.engineering_drawer_capture_target(role),tolerance=.001)
        raise MechanismExecutionError('No physical two-finger handle grip: '+role)

    def drawer_public_step_m(self,role,close):
        return None

    def prepare_drawer_public_pull(self,role,side):
        return None

    def record_drawer_public_pull(self,role,side):
        return None

    def drawer(self,role,close=False):
        from .execution_design_drawers import initial_displacements
        before_acquire=self.displacement(role) if initial_displacements(self.spec) is not None else None
        closing_push=close and before_acquire is not None
        raised_e30=self.task=='E30' and any(m.get('instance_support_lift_m',0.)>=.04 for m in self.spec.get('mechanisms',[]))
        self.drawer_closing_role=role if closing_push else None
        side=self.acquire(role,closing_push=True) if closing_push else self.acquire(role)
        target=0. if close else self.motion[role]['open_distance']
        tolerance=self.roles[role]['closed_tolerance'] if close else min(.001,self.motion[role]['open_distance']-self.roles[role]['open_threshold'])
        initial=self.displacement(role) if before_acquire is None else before_acquire;history=[]
        self.stage(('mechanism-close-' if close else 'mechanism-open-')+role)
        bilateral=self.a.scene.embodiment.config.get('author_recording',{}).get('mechanism_bilateral_transport_required',True)
        public_step=self.drawer_public_step_m(role,close)
        if public_step is not None and not .0005<=public_step<=.006:
            raise MechanismExecutionError('Invalid bounded public drawer step')
        def guard():
            self.displacement(role)
            if not self.touching(role,side,both=bilateral):raise MechanismExecutionError('Handle grip lost during joint motion: '+role)
        for _ in range(80):
            q=self.displacement(role)
            if abs(target-q)<=tolerance:break
            if public_step is not None:
                self.prepare_drawer_public_pull(role,side)
                q=self.displacement(role)
                if abs(target-q)<=tolerance:break
            if not closing_push:guard()
            direction=self.axis(role)*(1 if target>q else -1)
            amount=min(public_step if public_step is not None else (.002 if closing_push or raised_e30 else .006),max(.0005,abs(target-q)))
            if closing_push or raised_e30 or public_step is not None:
                # At contact, chasing a 0.3mm Cartesian waypoint alternates
                # force-induced vertical drift corrections and can cancel the
                # useful axial movement. Send one bounded public axial action,
                # then judge progress from the actual drawer joint. Opening
                # retains its physical bilateral grip guard on every step.
                component=int(np.argmax(np.abs(direction)))
                if abs(direction[component])<.95:raise MechanismExecutionError('Drawer push axis is not aligned with public translation axes')
                token=(('FWD','BACK'),('LEFT','RIGHT'),('UP','DOWN'))[component][int(direction[component]<0)]
                self.act(side,token,mm=amount*1000.)
                if public_step is not None:
                    feedback=self.c.action_feedback().get('control_feedback',{}).get(side,{})
                    if (feedback.get('status')=='blocked' or feedback.get('joint_limit_names')
                            or feedback.get('consecutive_ik_refusals',0)>0):
                        raise MechanismExecutionError('E18 public drawer pull controller rejected the action')
                    self.record_drawer_public_pull(role,side)
                    guard()
            else:
                self.move(side,self.tip(side)+direction*amount,tolerance=.0003,guard=guard,
                          done=lambda:abs(target-self.displacement(role))<=tolerance)
            history.append(self.displacement(role))
            if len(history)>=8 and max(history[-8:])-min(history[-8:])<.0002:
                raise MechanismExecutionError('Drawer joint stalled despite handle contact: '+role)
        else:raise MechanismExecutionError('Drawer did not reach measured target: '+role)
        final=self.displacement(role)
        if abs(final-initial)<.001:raise MechanismExecutionError('No measured drawer travel: '+role)
        self.act(side,'RELEASE');self.retreat(role,side)
        # Source E30 requires released, stable drawer states, not a neutral
        # wrist. Retain the collision-checked horizontal pose outside the
        # cabinet; the next acquisition still measures/validates its pose.
        if not raised_e30:self.orient(role,side,inverse=True)
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
        from .execution_design_bell_repeat import enabled as short_bell_repeat
        if self.spec.get('author_smooth_recording',False) or short_bell_repeat(self):self.button_releases[side]=role
        self.operations.append(dict(operation='press_release',role=role,cycle=index,pressed=measured_press,released=self.displacement(role)))

    def press_steps(self,role,side,start):
        had_contact=False
        def pressed():
            nonlocal had_contact
            had_contact=had_contact or self.touching(role,side)
            if self.displacement(role)<self.roles[role]['open_threshold']:return False
            if not had_contact:raise MechanismExecutionError('Bell moved without observed plunger contact')
            return True
        for _ in range(64):
            if pressed():break
            touch=self.touching(role,side)
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
                # Contact during transverse correction can already depress
                # the real plunger. Stop on that physical event instead of
                # chasing a millimetre TCP residual for another 120 actions.
                def aligned_or_pressed():
                    if pressed():return True
                    residual=self.point(role)-self.tip(side)
                    transverse=residual-axis*float(residual@axis)
                    return bool(np.linalg.norm(transverse)<=.003)
                self.move(side,self.tip(side)+lateral,tolerance=.0015,done=aligned_or_pressed)
                if pressed():break
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
            if self.spec.get('execution_design',{}).get('revision') in ('embodied50-execution-v2-20261102','embodied50-execution-v3-20261102'):
                from .execution_design_inputs import e26_targets
                expected=e26_targets(self.spec);counts=(expected['left'],expected['right'])
            else:
                counts=((9,1),(1,9),(10,0))['ABC'.index(self.variant)]
            for role,count in zip(('left','right'),counts):
                for index in range(1,count+1):self.press(role,index)
            if self.spec.get('author_smooth_recording',False):
                self.park_bell_hands()
        elif self.task=='E30':
            selected=(('upper',),('lower',),('upper','lower'))['ABC'.index(self.variant)]
            from .execution_design_drawers import initial_displacements
            if initial_displacements(self.spec) is not None:
                for role in ('lower','upper'):
                    if role not in selected:self.drawer(role,close=True)
                # An opened upper drawer overhangs the lower capture corridor.
                # Source C requires both open without prescribing their order;
                # handle the lower drawer before extending that upper panel.
                if self.variant=='C':selected=('lower','upper')
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
