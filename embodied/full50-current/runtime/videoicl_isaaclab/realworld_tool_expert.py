"""Private source-geometry tool demonstrations through real robot actuation.

solve_tool(author) uses Controller snapshots and actual contacts, never evaluator
results, joint drives, object-state writes or desired-state success assertions.
The optional smooth recording mode interpolates simultaneous Cartesian targets
through the recorder; ordinary recording retains bounded public actions. Both
paths check real holding contacts throughout each physical trajectory.
All manipulation points must be reviewed source coordinates. Missing geometry,
lost physical grip, stalled contact/joint motion and action budget exhaustion
raise ToolExecutionError. Finishing a policy is not a physics-success receipt.

Extra recipe geometry, private to the recorder:
* tools.main: actor, grasp_local, jaw_axis_local, working_local; spatula also
  support_normal_local/plane_offset and withdraw_local. Optional hand=right.
* cargo_grasps: {actor:{local,jaw_axis_local}}; card_grasp same structure.
* keys + key_points:{"1":{local,normal_local},...}; actual key actor frames.
* launcher: release_direction_task, guide_intercept_task, trigger:{actor,local,
  press_direction_task,max_travel}; trigger must be a real physical gate.
* containers.cup: grasp_local,jaw_axis_local; tool_expert.pour_rotation_token
  is PITCH_UP/PITCH_DOWN/ROLL_LEFT/ROLL_RIGHT, matched to the real cup/receiver.
* clips.<id>.expert: handle_grasp/body_grasp each {body,contact_body,local,
  jaw_axis_local}, open_gap_m, insert_direction_task, return_point_task.
* crease.expert: fold_grasp:{body,contact_body,local,jaw_axis_local},
  base_press:{body,contact_body,local}, hinge_point_local, axis_local,direction.

Holding body_local references are transformed from actual articulation snapshots.
The source task+X is far, +Y operator-left, +Z up. Source axes are not inferred
from the asset's kind or a joint's label. Public rotations retain actual feedback.
"""
import math
import json
import numpy as np
from .realworld_mechanism_evidence import _finite, _rotation

SUPPORTED=('E28','E29','E40','E42','E43','E44','E45','E46','E50')


class ToolExecutionError(RuntimeError):pass


def _unit(value):
    v=_finite(value,(3,));n=float(np.linalg.norm(v))
    if n<1e-9:raise ToolExecutionError('Zero reviewed motion direction')
    return v/n


def _axis_rotation(axis,angle):
    x,y,z=_unit(axis);k=np.array([[0,-z,y],[z,0,-x],[-y,x,0]])
    return np.eye(3)+math.sin(angle)*k+(1-math.cos(angle))*(k@k)


def _push_rotation(support_normal_local,edge_outward_local,direction_task):
    """Rigidly align a measured blade frame, independent of source yaw/axes.

    A slightly sloped blade can have a nonorthogonal front-face normal. Its
    tangent projection defines forward; a rotation preserves that original
    angle rather than pretending both raw source directions are orthogonal.
    """
    normal=_unit(support_normal_local);outward=_unit(edge_outward_local)
    forward=_unit(outward-normal*float(outward@normal))
    source=np.column_stack((forward,_unit(np.cross(normal,forward)),normal))
    direction=_finite(direction_task,(3,)).copy();direction[2]=0.;direction=_unit(direction)
    up=np.array([0.,0.,1.]);world=np.column_stack((direction,np.cross(up,direction),up))
    return _rotation(world@source.T)


class ToolAuthor:
    def __init__(self,author):
        self.a=author;self.c=author.c;self.spec=author.scene.spec;self.s=self.spec['semantic'];self.task=self.spec['id'];self.variant=self.spec['variant']
        if self.task not in SUPPORTED:raise NotImplementedError(self.task+': tool expert unavailable')
        if self.variant not in 'ABC' or len(self.variant)!=1:raise ToolExecutionError('Unknown source variant')
        self.index='ABC'.index(self.variant);self.start=self.c.steps;self.limit=self.spec.get('expert_action_budget',1000)
        config=author.scene.embodiment.config['control'];self.min_mm=float(config['step_mm'][0]);self.max_mm=min(12.,float(config['step_mm'][1]));self.min_deg=float(config['rotation_deg'][0]);self.max_deg=min(10.,float(config['rotation_deg'][1]))
        if self.min_mm>self.max_mm:raise ToolExecutionError('No suitable public precision motion range')
        self.clearance=float(self.s.get('expert_clearance_z',1.12));self.operations=[]

    def snapshot(self):
        state,contacts=self.c.snapshot()
        for v in state.values():_finite(v['pos'],(3,));_rotation(v['mat'])
        return state,contacts
    def mechanisms(self):return self.c.snapshot_mechanisms()
    def stage(self,name):self.a.stage=name;self.operations.append(dict(stage=name,action_step=self.c.steps))
    def act(self,side=None,token='STILL',mm=1.,degrees=5.,follower=None):
        if self.c.steps-self.start>=self.limit:raise ToolExecutionError('Tool expert action budget exhausted')
        active={side,follower}-{None}
        self.a.act(token if 'left' in active else 'STILL',token if 'right' in active else 'STILL',mm=max(self.min_mm,min(self.max_mm,float(mm))),rotation_deg=max(self.min_deg,min(self.max_deg,float(degrees))))
    def wait(self,n=2):
        for _ in range(n):self.act()
    def tip(self,side):return _finite(self.a.tip(side),(3,))
    def frame(self,ref):
        if 'actor' in ref:
            v=self.snapshot()[0][ref['actor']];return _finite(v['pos'],(3,)),_rotation(v['mat'])
        v=self.mechanisms()[ref['mechanism']];n=ref['body']
        return _finite(v['body_pos_task'][n],(3,)),_rotation(v['body_mat_task'][n])
    def point(self,ref):
        p,r=self.frame(ref);return p+r@_finite(ref['local'],(3,))
    def contact(self,a,b):return frozenset((a,b)) in self.snapshot()[1]
    def held(self,ref,side):
        state,contacts=self.snapshot();name=ref.get('actor',ref.get('contact_body'))
        if 'grasp_contacts' in ref:
            bodies=ref['grasp_contacts']
            if not isinstance(bodies,(list,tuple)) or len(bodies)!=2 or len(set(bodies))!=2 or not all(isinstance(n,str) for n in bodies):
                raise ToolExecutionError('Two distinct actual handle bodies required')
            # A spring clip is squeezed with one finger on each handle. Both
            # fingers touching only the same jaw cannot establish this grip.
            return any(all(frozenset((body,f'{side}_finger{i}')) in contacts for i,body in enumerate(order,1))
                       for order in (bodies,bodies[::-1]))
        if name in state:return bool(state[name]['grasp'][0 if side=='left' else 1])
        return all(frozenset((name,f'{side}_finger{i}')) in contacts for i in (1,2))
    def require_held(self,ref,side):
        if not self.held(ref,side):raise ToolExecutionError('Actual grip lost on '+str(ref.get('actor',ref.get('contact_body'))))
    def move(self,side,target,guard=None,follower=None,tolerance=.002):
        target=_finite(target,(3,));history=[]
        if self.spec.get('author_smooth_recording',False):
            if self.c.steps-self.start>=self.limit:raise ToolExecutionError('Tool expert action budget exhausted')
            if side not in ('left','right') or follower not in (None,'left','right'):
                raise ToolExecutionError('Unknown physical robot hand')
            goals={side:target}
            # The two real TCPs follow one synchronized displacement. This is
            # needed when one hand maintains a clip opening while the other
            # transports its body; independent moves would strain the grip.
            if follower is not None and follower!=side:
                goals[follower]=self.tip(follower)+(target-self.tip(side))
            return self.a.move_smooth(goals,tolerance=tolerance,guard=guard,
                max_speed=.075 if guard else .18,max_acceleration=.35 if guard else .6)
        for _ in range(180):
            if guard:guard()
            error=target-self.tip(side)
            if np.max(np.abs(error))<=tolerance:return
            axis=int(np.argmax(np.abs(error)));token=(('FWD','BACK'),('LEFT','RIGHT'),('UP','DOWN'))[axis][int(error[axis]<0)]
            self.act(side,token,mm=abs(error[axis])*1000,follower=follower)
            history.append(self.tip(side))
            if len(history)>12 and max(np.linalg.norm(x-history[-1]) for x in history[-12:])<.0003:raise ToolExecutionError('Cartesian motion stalled: '+self.a.stage)
        raise ToolExecutionError('Unreachable actual tool waypoint: '+self.a.stage)
    def move_point(self,side,ref,target,guard=None,follower=None,tolerance=.002):
        target=_finite(target,(3,))
        if (self.task in ('E09','E28','E37','E42','E43','E45','E46')
                and self.spec.get('execution_design',{}).get('revision')=='embodied50-execution-v3-20261102'
                and getattr(self.a,'control_report',{}).get('engineering_reference_only')
                and not self.spec.get('author_smooth_recording',False)):
            from .execution_design_tool_tracking import move_material
            return move_material(self,side,ref,target,guard,follower,tolerance)
        if self.spec.get('author_smooth_recording',False):
            # Translate the measured working point along one continuous path.
            # The TCP-to-point offset is measured again after each real servo
            # trajectory: settling or small in-grip slip must not accumulate
            # into an assumed rigid attachment. The recorder invokes guard at
            # every physical tick, including during a synchronized follower move.
            for _ in range(5):
                if guard:guard()
                error=target-self.point(ref)
                if np.max(np.abs(error))<=tolerance:return
                if self.a.scene.embodiment.config.get('author_recording',{}).get('actual_material_point_stopping',False) and follower is None:
                    self.a.move_smooth({side:self.tip(side)+error},guard=guard,
                        done=lambda:bool(np.max(np.abs(target-self.point(ref)))<=tolerance),
                        tolerance=min(tolerance,.002))
                else:
                    self.move(side,self.tip(side)+error,guard,follower,
                              tolerance=min(tolerance,.002))
            if guard:guard()
            if np.max(np.abs(target-self.point(ref)))<=tolerance:return
            raise ToolExecutionError('Measured working point failed to converge')
        for _ in range(100):
            if guard:guard()
            error=target-self.point(ref)
            if np.max(np.abs(error))<=tolerance:return
            # Small increments correct source/tool slippage from new actual pose.
            self.move(side,self.tip(side)+np.clip(error,-.012,.012),guard,follower,tolerance=.0008)
        raise ToolExecutionError('Measured working point failed to converge')
    def acquire(self,ref,side):
        if (self.task=='E45' and getattr(self.a,'control_report',{}).get('engineering_reference_only')
                and ref.get('engineering_exterior_body_grip')is True):
            from .execution_design_pour_acquire import acquire
            return acquire(self,ref,side)
        self.stage('acquire-'+ref.get('actor',ref.get('contact_body','tool')))
        from .author_clearance import prepare_single_hand
        prepare_single_hand(self.a,side,self.clearance)
        ramped_e40=(self.task=='E40'and self.a.control_report.get('engineering_reference_only')
                    and getattr(self.c,'_public_gripper_limits',None)is not None)
        if ramped_e40:
            from .execution_design_clip_handover import open_clip_hand
            open_clip_hand(self,side)
        else:self.act(side,'RELEASE')
        recording=self.a.scene.embodiment.config.get('author_recording',{})
        if recording.get('acquire_align_above_source',False):
            # The outer stow is reachable in its initial orientation. Move
            # over the actual grasp site before asking the wrist to turn.
            point=self.point(ref)
            height=max(self.clearance,float(point[2])+.10,float(self.tip(side)[2]))
            self.move(side,[*self.tip(side)[:2],height])
            self.move(side,[*point[:2],height])
        if self.spec.get('author_smooth_recording',False) and recording.get('reset_empty_wrist_before_acquire',False):
            self.move(side,[*self.tip(side)[:2],max(self.clearance,self.tip(side)[2])])
            self.a.neutralize_empty_wrist(side)
        pre_yaw=float(ref.get('pre_grasp_task_yaw_rad',0.))
        if pre_yaw:
            self.move(side,[*self.tip(side)[:2],max(self.clearance,self.tip(side)[2])])
            self.a.rotate_tcp_smooth(side,_axis_rotation([0,0,1],pre_yaw))
        _,r=self.frame(ref);axis=r@_unit(ref['jaw_axis_local'])
        self.a.align_gripper_axis(side,axis)
        if (self.task=='E08' and self.spec.get('execution_design',{}).get('revision')=='embodied50-execution-v3-20261102'
                and getattr(self.a,'control_report',{}).get('engineering_reference_only')):
            from .execution_design_tabletop_grasp import prepare_e08_empty_palm
            prepare_e08_empty_palm(self,side,axis)
        # A calibrated stow can be above the manipulation plane and outside
        # the low workspace. Keep that achieved height until over the object.
        point=self.point(ref);height=max(self.clearance,point[2]+.07,float(self.tip(side)[2]))
        if recording.get('palm_down_grasp',False) or recording.get('grasp_table_clearance',False):
            point=point.copy()
            point[2]=max(point[2],self.a.floor_clear_tcp(side))
        if self.task=='E29'and getattr(self.a,'control_report',{}).get('engineering_reference_only'):
            from .execution_design_mallet_grasp import table_clear_mallet_grasp
            point=table_clear_mallet_grasp(self,ref,side,point)
        if (self.task=='E08' and self.spec.get('execution_design',{}).get('revision')=='embodied50-execution-v3-20261102'
                and getattr(self.a,'control_report',{}).get('engineering_reference_only')):
            from .execution_design_e08_approach import approach
            approach(self,side,ref)
        else:
            self.move(side,[*self.tip(side)[:2],height]);self.move(side,[*point[:2],height])
            if recording.get('pre_grasp_opening_m') is not None:self.a.prepare_generated_gripper(side)
            self.move(side,point)
        if (self.task=='E08' and self.spec.get('execution_design',{}).get('revision')=='embodied50-execution-v3-20261102'
                and getattr(self.a,'control_report',{}).get('engineering_reference_only')):
            from .execution_design_tabletop_grasp import require_e08_table_clearance
            require_e08_table_clearance(self.a,side)
        stable=0
        for i in range(13 if ramped_e40 else 5):
            self.act(side,'STILL'if ramped_e40 and i else'GRASP')
            stable=stable+1 if self.held(ref,side) else 0
            if stable>=(1 if ramped_e40 else 3):return
        raise ToolExecutionError('No settled two-finger grip at reviewed grasp point')
    def release(self,ref,side):
        if (self.task=='E40'and self.a.control_report.get('engineering_reference_only')
                and getattr(self.c,'_public_gripper_limits',None)is not None):
            from .execution_design_clip_handover import open_clip_hand
            open_clip_hand(self,side)
            if self.held(ref,side):raise ToolExecutionError('Physical grip did not release')
            return
        self.act(side,'RELEASE');self.wait()
        if self.held(ref,side):raise ToolExecutionError('Physical grip did not release')
    def tool(self):
        t=self.s['tools']['main'];ref=dict(actor=t['actor'],local=t['grasp_local'],jaw_axis_local=t['jaw_axis_local'])
        side=t.get('hand','right');self.acquire(ref,side)
        return t,ref,side
    def rotate_actor(self,actor,side,target):
        recording=self.a.scene.embodiment.config.get('author_recording',{})
        if self.spec.get('author_smooth_recording',False) and recording.get('continuous_orientation',False):
            return self.a.rotate_held_smooth(actor,side,_rotation(target),guard=lambda:self.require_held({'actor':actor},side))
        # Matrix feedback through public 3-axis wrist increments. No Euler
        # singularity or assumption about the initial object orientation.
        for _ in range(120):
            current=self.snapshot()[0][actor]['mat'];delta=_rotation(target)@current.T;angle=float(np.arccos(np.clip((np.trace(delta)-1)/2,-1,1)))
            if angle<math.radians(4):return
            self.require_held({'actor':actor},side)
            if math.pi-angle<.01:
                values,vectors=np.linalg.eigh((delta+np.eye(3))/2);axis=vectors[:,np.argmax(values)]
            else:axis=np.array([delta[2,1]-delta[1,2],delta[0,2]-delta[2,0],delta[1,0]-delta[0,1]])/(2*math.sin(angle))
            i=int(np.argmax(abs(axis)));token=(('ROLL_LEFT','ROLL_RIGHT'),('PITCH_UP','PITCH_DOWN'),('ROTATE_CCW','ROTATE_CW'))[i][int(axis[i]<0)]
            self.act(side,token,degrees=abs(math.degrees(angle*axis[i])))
        raise ToolExecutionError('Actual held-tool rotation failed to converge')
    def park(self,ref,side,point=None):
        point=np.asarray(point if point is not None else self.s['tool_expert']['park_point_task'],float)
        self.move(side,[*self.tip(side)[:2],self.clearance],lambda:self.require_held(ref,side));self.move_point(side,ref,[*point[:2],self.clearance],lambda:self.require_held(ref,side))
        if self.a.scene.embodiment.config.get('author_recording',{}).get('park_release_on_actual_table_support',False):
            self.a.move_smooth({side:self.tip(side)+point-self.point(ref)},
                guard=lambda:self.require_held(ref,side),
                done=lambda:self.contact(ref['actor'],'table'),tolerance=.002)
        else:self.move_point(side,ref,point,lambda:self.require_held(ref,side))
        self.release(ref,side);self.move(side,self.tip(side)+[0,0,.06])

    def destination(self,name,slot=0):
        if self.task=='E28':
            c=self.s['containers']['plate'];v=self.snapshot()[0][c['object']];axis=c.get('floor_axis',2)
            local=(np.asarray(c['lower'])+np.asarray(c['upper']))/2;local[axis]=c['lower'][axis] if c.get('floor_side','lower')=='lower' else c['upper'][axis]
            local[1]+=.025*slot;return v['pos']+v['mat']@local
        zone=next(z for z in self.spec['zones'] if z['id']==('circle','triangle','square')[self.index])
        if zone.get('anchor_object'):
            value=self.snapshot()[0][zone['anchor_object']]
            xy=(value['pos']+value['mat']@np.asarray(zone['anchor_local_center'],float))[:2]
            return np.array([*xy,zone.get('surface_z',.8)])
        return np.array([*zone['xy'],zone.get('surface_z',.8)])

    def spatula(self):
        if (self.task=='E46'
                and self.spec.get('execution_design',{}).get('revision')=='embodied50-execution-v3-20261102'
                and getattr(self.a,'control_report',{}).get('engineering_reference_only')):
            from .execution_design_e46_reference import solve
            return solve(self)
        if (self.task=='E28'
                and self.spec.get('execution_design',{}).get('revision')=='embodied50-execution-v3-20261102'
                and getattr(self.a,'control_report',{}).get('engineering_reference_only')):
            from .execution_design_e28_reference import solve
            return solve(self)
        return self._handload_spatula_transport()

    def _handload_spatula_transport(self):
        # Legacy physical author, retained explicitly for the E28 v3
        # counterexample. It must never stand in for a v3 positive scoop.
        t,grip,side=self.tool();other='left' if side=='right' else 'right';work=dict(actor=t['actor'],local=t['working_local']);cargo=self.s['groups']['cargo']
        identities={o.get('semantic_identity',o.get('identity',o['id'])):o['id'] for o in self.spec['objects']}
        names=([identities['yellow_rectangle']],[identities['white_yellow_round']],[identities['yellow_rectangle'],identities['white_yellow_round']])[self.index] if self.task=='E28' else cargo
        for i,name in enumerate(names):
            self.stage('load-spatula-'+name);entry=self.s['cargo_grasps'][name];objref=dict(actor=name,**entry);self.acquire(objref,other)
            # Native source plane and current tool frame, not a hardcoded +Z top.
            _,tr=self.frame(work);normal=tr@_unit(t['support_normal_local']);obj=next(o for o in self.spec['objects'] if o['id']==name);radius=float(np.abs(self.snapshot()[0][name]['mat'].T@normal)@np.asarray(obj['size']))
            self.move_point(other,objref,self.point(work)+normal*(radius+.025),lambda:self.require_held(objref,other))
            self.move_point(other,objref,self.point(work)+normal*(radius+.001),lambda:self.require_held(objref,other));self.release(objref,other);self.move(other,self.tip(other)+[0,0,.07]);self.wait()
            if not self.contact(name,t['actor']):raise ToolExecutionError('Cargo did not settle on actual blade')
            def loaded():
                self.require_held(grip,side)
                if not self.contact(name,t['actor']):raise ToolExecutionError('Blade lost cargo during transport')
            self.stage('transport-spatula-'+name);dest=self.destination(name,i)
            self.move_point(side,work,[*self.point(work)[:2],max(dest[2]+.08,.92)],loaded)
            self.move_point(side,work,[*dest[:2],max(dest[2]+.08,.92)],loaded)
            self.move_point(side,work,dest+[0,0,.003],loaded)
            direction=self.frame(work)[1]@_unit(t['withdraw_local'])
            self.move_point(side,work,self.point(work)+direction*.10,lambda:self.require_held(grip,side));self.wait(3)
        self.move(side,self.tip(side)+[0,0,.05],lambda:self.require_held(grip,side))

    def mallet(self):
        t,grip,side=self.tool();head=dict(actor=t['actor'],local=t['working_local']);keys=(list(range(1,9)),list(range(8,0,-1)),list(range(1,9))+list(range(8,0,-1)))[self.index]
        recording=self.a.scene.embodiment.config.get('author_recording',{})
        single_stroke=recording.get('mallet_single_contact_stroke',False)
        clearance=.012 if single_stroke else .035
        isolated_public=(self.spec.get('execution_design',{}).get('revision')=='embodied50-execution-v3-20261102'
                         and getattr(self.a,'control_report',{}).get('engineering_reference_only'))
        if isolated_public:
            from .execution_design_mallet_route import level_held_mallet,collision_centered_head
            head=collision_centered_head(self,head)
            level_held_mallet(self,t['actor'],grip,side)
        elif recording.get('level_mallet_before_strikes',False):
            self.stage('level-mallet-before-strikes')
            self.move(side,[*self.tip(side)[:2],self.clearance],lambda:self.require_held(grip,side))
            # The published source mallet rests with an inclined handle. A
            # level shaft keeps its actual collision geometry above the keys
            # while the lower head face taps the requested key.
            self.rotate_actor(t['actor'],side,np.eye(3))
        for key in keys:
            self.stage('strike-key-'+str(key));name=self.s['keys'][str(key)];entry=self.s['key_points'][str(key)]
            frame=self.s.get('key_frames',{}).get(str(key))
            ref=dict(**frame,local=entry['local']) if frame else dict(actor=name,local=entry['local'])
            normal=self.frame(ref)[1]@_unit(entry['normal_local']);target=self.point(ref)
            if (self.spec.get('execution_design',{}).get('revision')=='embodied50-execution-v3-20261102'
                    and getattr(self.a,'control_report',{}).get('engineering_reference_only')):
                from .execution_design_mallet_route import approach_key
                approach_key(self,head,grip,side,target+normal*clearance)
                from .execution_design_mallet_route import strike_key
                strike_key(self,t,grip,head,side,name,target,normal)
                continue
            else:self.move_point(side,head,target+normal*clearance,lambda:self.require_held(grip,side))
            if single_stroke:
                touched={}
                def first_key_contact():
                    # A short physical impact may end during the actuator's
                    # settling hold. Remember that measured event so the
                    # recorder does not repeat the downward stroke after it
                    # has already hit and separated from the real key.
                    for other in self.s['keys'].values():
                        if other not in touched and self.contact(t['actor'],other):
                            touched[other]=getattr(self.c,'physics_ticks',None)
                    return bool(touched)
                self.a.move_smooth({side:self.tip(side)-normal*(clearance+.006)},tolerance=.0004,
                    guard=lambda:self.require_held(grip,side),
                    done=first_key_contact,
                    max_speed=.04,max_acceleration=.25)
                first_key_contact()
                self.operations.append(dict(stage=self.a.stage,measured_key_contacts=touched,
                    action_step=self.c.steps))
                unexpected=[other for other in touched if other!=name]
                if unexpected:raise ToolExecutionError('Mallet contacted unexpected key: '+str(unexpected))
                if name not in touched:
                    raise ToolExecutionError('Continuous mallet stroke missed actual key')
                self.move_point(side,head,target+normal*clearance,lambda:self.require_held(grip,side));self.wait()
                if self.contact(t['actor'],name):raise ToolExecutionError('Mallet key contact did not separate')
                continue
            for _ in range(50):
                if self.contact(t['actor'],name):break
                unexpected=[other for other in self.s['keys'].values()
                            if other!=name and self.contact(t['actor'],other)]
                if unexpected:raise ToolExecutionError('Mallet contacted unexpected key: '+str(unexpected))
                if self.spec.get('author_smooth_recording',False):
                    # A real key stops the mallet before an unconstrained TCP
                    # waypoint. End on measured contact rather than pushing
                    # farther into the source key to reduce position error.
                    self.a.move_smooth({side:self.tip(side)-normal*.001},tolerance=.0004,
                        guard=lambda:self.require_held(grip,side),
                        done=lambda:any(self.contact(t['actor'],other) for other in self.s['keys'].values()),
                        max_speed=.02,max_acceleration=.10)
                else:
                    self.move_point(side,head,self.point(head)-normal*.001,lambda:self.require_held(grip,side),tolerance=.0004)
            else:raise ToolExecutionError('Mallet did not contact actual key')
            self.move_point(side,head,target+normal*.035,lambda:self.require_held(grip,side));self.wait()
            if self.contact(t['actor'],name):raise ToolExecutionError('Mallet key contact did not separate')
        self.wait(3)

    def push(self):
        import json
        isolated_push=(self.task=='E42' and self.spec.get('execution_design',{}).get('revision')=='embodied50-execution-v3-20261102'
                       and getattr(self.a,'control_report',{}).get('engineering_reference_only'))
        if isolated_push:
            from .execution_design_tool_tracking import handle_level_push_rotation
            from .execution_design_e42_paper_goal import reached as reached_paper
            from .execution_design_e42_contact import native_edge_progress,edge_progress_advanced,remember_native_contact,current_or_recent_edge_contact
            self.max_mm=min(25.,float(self.a.scene.embodiment.config['control']['step_mm'][1]))
        from pathlib import Path
        t,grip,side=self.tool();actor=t['actor']
        edge=dict(actor=actor,local=np.asarray(t['edge_segment']).mean(axis=0).tolist())
        normal=_unit(t.get('support_normal_local',self.s.get('blade_support_normal_local')))
        outward=_unit(t.get('edge_outward_normal_local',self.s.get('edge_outward_normal_local')))
        tangent=_unit(outward-normal*float(outward@normal));guard=lambda:self.require_held(grip,side)
        tool_obj=next(o for o in self.spec['objects'] if o['id']==actor)
        if isolated_push:
            from .execution_design_e42_edge import central_reference
            edge['local']=central_reference(tool_obj).tolist()
        edge_contact_height=0.
        half=_finite(tool_obj['size'],(3,));grasp=_finite(grip['local'],(3,))
        corners=np.array([[a*half[0],b*half[1],c*half[2]] for a in (-1,1) for b in (-1,1) for c in (-1,1)])
        sweep_radius=float(np.linalg.norm(corners-grasp,axis=1).max())

        def feedback(name,phase,**extra):
            state,contacts=self.snapshot();tv=state[actor]
            row=dict(phase=phase,ball=name,action_step=self.c.steps,
                     physics_tick=getattr(self.c,'physics_ticks',None),
                     held=bool(tv['grasp'][0 if side=='left' else 1]),
                     edge_contact=frozenset((name,actor)) in contacts,
                     table_contact=frozenset((name,'table')) in contacts,
                     ball_pos=state[name]['pos'].tolist(),tool_pos=tv['pos'].tolist(),
                     tool_rotation=tv['mat'].tolist(),edge_point=(tv['pos']+tv['mat']@np.asarray(edge['local'])).tolist(),**extra)
            self.operations.append(row)
            directory=getattr(self.a,'out',None)
            if directory is not None:
                with (Path(directory)/'tool-push.private.jsonl').open('a') as stream:
                    stream.write(json.dumps(row)+'\n')
            return state,contacts

        def align(name,direction):
            nonlocal edge_contact_height
            self.stage('orient-edge-push-'+name);guard()
            if isolated_push:
                from .execution_design_push_rotation_path import align as align_path
                target=handle_level_push_rotation(outward,direction)
                selected=align_path(self,t,grip,side,target,name,direction)
                edge['local']=selected['edge_local']
                edge_contact_height=selected.get('edge_contact_height_offset_m',0.)
                feedback(name,'oriented',target_rotation=selected['target_actor_rotation'])
                return
            p=self.snapshot()[0][name]['pos']
            # Bound the entire source tool's rotation envelope about the real
            # grasp, not just the TCP or a guessed short blade.
            safe=max(self.clearance,float(p[2])+sweep_radius+.06)
            self.move(side,[*self.tip(side)[:2],safe],guard)
            target=handle_level_push_rotation(outward,direction) if isolated_push else _push_rotation(normal,outward,direction)
            hooks=getattr(self.c,'tick_hooks',None)
            def rotation_guard(*_):guard()
            if hooks is not None:hooks.append(rotation_guard)
            try:self.rotate_actor(actor,side,target)
            finally:
                if hooks is not None:hooks.remove(rotation_guard)
            guard();feedback(name,'oriented',target_rotation=target.tolist())

        def approach(name,target,radius,realign=False):
            p=self.snapshot()[0][name]['pos'];direction=_unit([*(target-p)[:2],0])
            if realign:align(name,direction)
            self.stage('reapproach-edge-push-'+name)
            # Lift before translating around the ball; never sweep the broad
            # blade through the ball to recover a lost working edge.
            high=(max(float(self.point(edge)[2]),float(p[2])+.055)if isolated_push
                  else float(self.point(edge)[2])+.055)
            self.move_point(side,edge,[*self.point(edge)[:2],high],guard)
            p=self.snapshot()[0][name]['pos'];direction=_unit([*(target-p)[:2],0])
            start=p-direction*(radius+.006)
            if isolated_push:start[2]+=edge_contact_height
            above=max(high,float(start[2])+.055)if isolated_push else float(start[2])+.055
            self.move_point(side,edge,[*start[:2],above],guard)
            self.move_point(side,edge,start,guard,tolerance=.001)
            if isolated_push:
                from .execution_design_e42_contact import seek_edge_contact
                seek_edge_contact(self,side,edge,name,target,guard)
                feedback(name,'seek-edge-contact-measured')
                return
            # Close only the measured small initial gap. If contact never
            # appears, fail rather than moving through an assumed payload.
            for _ in range(9):
                _,contacts=feedback(name,'seek-edge-contact',desired_edge=start.tolist())
                if frozenset((name,actor)) in contacts:return
                self.move_point(side,edge,self.point(edge)+direction*.002,guard,tolerance=.0007)
            raise ToolExecutionError('No actual blade-edge contact after measured reapproach')

        for name in self.s['groups']['balls']:
            target=self.destination(name);obj=next(o for o in self.spec['objects'] if o['id']==name);radius=float(max(obj['size']))
            p=self.snapshot()[0][name]['pos'];target[2]=p[2]
            if (reached_paper(self,name)if isolated_push else np.linalg.norm(target[:2]-p[:2])<.012):continue
            approach(name,target,radius,realign=True)
            progress=[];recoveries=0
            recovery_anchor=float(np.linalg.norm(target[:2]-self.snapshot()[0][name]['pos'][:2]));stalled_recoveries=0
            for _ in range(150):
                guard();state,contacts=feedback(name,'push-feedback');p=state[name]['pos']
                distance=float(np.linalg.norm(target[:2]-p[:2]));progress.append(distance)
                if (reached_paper(self,name)if isolated_push else distance<.012):break
                if frozenset((name,'table')) not in contacts:raise ToolExecutionError('Push ball left actual table support')
                direction=_unit([*(target-p)[:2],0]);tv=state[actor]
                actual_edge=tv['pos']+tv['mat']@np.asarray(edge['local']);offset=p-actual_edge
                lateral=float(np.linalg.norm(offset[:2]-direction[:2]*float(offset[:2]@direction[:2])))
                front=tv['mat']@tangent;front[2]=0.;front=_unit(front)
                expected_normal=(handle_level_push_rotation(outward,direction)@normal if isolated_push else np.array([0.,0.,1.]))
                rotated=float(front@direction)<math.cos(math.radians(12)) or float((tv['mat']@normal)@expected_normal)<math.cos(math.radians(8))
                stalled=len(progress)>12 and progress[-1]>=progress[-12]-.001
                contact_ok=(current_or_recent_edge_contact(self,edge,name)if isolated_push else frozenset((name,actor))in contacts)
                if not contact_ok or lateral>max(.004,radius*.6) or rotated or stalled:
                    recoveries+=1
                    if isolated_push:
                        if distance<recovery_anchor-.005:
                            recovery_anchor=distance;stalled_recoveries=0
                        else:stalled_recoveries+=1
                        if recoveries>48 or stalled_recoveries>12:
                            raise ToolExecutionError('Actual edge push exhausted bounded recoveries without sufficient ball progress')
                    elif recoveries>12:raise ToolExecutionError('Actual edge push exhausted measured contact recoveries')
                    feedback(name,'contact-recovery',lateral_error_m=lateral,recovery=recoveries)
                    approach(name,target,radius,realign=rotated);progress=[];continue
                self.stage('edge-push-'+name);delta=direction*min(.025 if isolated_push else .01,distance)
                contact_before=native_edge_progress(self,name)if isolated_push else None
                if self.spec.get('author_smooth_recording',False):
                    # Stop the real trajectory as soon as its measured edge
                    # contact breaks; the next pass reapproaches current p.
                    def lost_contact():
                        if not isolated_push:return not self.contact(name,actor)
                        return not self.contact(name,actor)and edge_progress_advanced(contact_before,native_edge_progress(self,name))
                    self.a.move_smooth({side:self.tip(side)+delta},tolerance=.001,
                        guard=guard,done=lost_contact,max_speed=.06,max_acceleration=.35)
                else:self.move_point(side,edge,self.point(edge)+delta,guard,tolerance=.001)
                if isolated_push:remember_native_contact(self,edge,name,contact_before)
                feedback(name,'push-step-finished')
            else:raise ToolExecutionError('Ball did not reach target by bounded actual edge push')
            self.move_point(side,edge,self.point(edge)+[0,0,.055],guard)
        self.wait(3)

    def pour(self):
        from .execution_design_pour_clearance import pour_token
        cup=self.s['containers']['cup'];name=cup['object'];ref=dict(actor=name,local=cup['grasp_local'],jaw_axis_local=cup['jaw_axis_local']);side=self.s.get('tool_expert',{}).get('hand','right')
        if (self.task=='E45' and self.spec.get('execution_design',{}).get('revision')=='embodied50-execution-v3-20261102'
                and getattr(self.a,'control_report',{}).get('engineering_reference_only')):
            from .execution_design_pour_clearance import body_grip_reference
            ref=getattr(self,'_engineering_pour_grip_reference',None)or body_grip_reference(self,ref)
        rest_point=self.point(ref).copy();rest_rotation=self.snapshot()[0][name]['mat'].copy();self.acquire(ref,side)
        if getattr(self,'_engineering_pour_return_point_task',None)is not None:
            rest_point=_finite(self._engineering_pour_return_point_task,(3,)).copy()
            rest_rotation=_rotation(self._engineering_pour_return_rotation_task)
        if (self.task=='E45' and self.spec.get('execution_design',{}).get('revision')=='embodied50-execution-v3-20261102'
                and getattr(self.a,'control_report',{}).get('engineering_reference_only')):
            from .execution_design_pour_handoff import handoff_if_needed
            side,rest_point=handoff_if_needed(self,ref,side,rest_point)
            if ref.get('engineering_exterior_body_grip')is True:
                from .execution_design_pour_clearance import exterior_grip_readback
                exterior_grip_readback(self,side,ref)
        self.move(side,[*self.tip(side)[:2],self.clearance],lambda:self.require_held(ref,side))
        target=self.destination(name);rim=(np.asarray(cup['lower'])+np.asarray(cup['upper']))/2;axis=cup.get('rim_axis',2);rim[axis]=cup['upper'][axis] if cup.get('rim_side','upper')=='upper' else cup['lower'][axis]
        pour_height=float(self.a.scene.embodiment.config.get('author_recording',{}).get('pour_rim_height_above_target_m',.13))
        recording=self.a.scene.embodiment.config.get('author_recording',{})
        if recording.get('pour_outflow_rim_local') is not None:
            rim=_finite(recording['pour_outflow_rim_local'],(3,))
        rimref=dict(actor=name,local=rim.tolist())
        isolated_clear_pour=(self.task=='E45' and self.spec.get('execution_design',{}).get('revision')=='embodied50-execution-v3-20261102'
            and getattr(self.a,'control_report',{}).get('engineering_reference_only'))
        fixed_clear_target=None;receiver_anchor=None;initial_outlet_offset=None
        def current_outlet_offset():
            from .execution_design_pour_clearance import outlet_offset
            mouth=max(next(o for o in self.spec['objects']if o['id']==name)['size'][:2])
            radius=max(max(next(o for o in self.spec['objects']if o['id']==ball)['size'])for ball in self.s['groups']['balls'])
            return outlet_offset(self.snapshot()[0][name]['mat'],pour_token(self),mouth,radius)
        def actual_rim_target():
            if fixed_clear_target is not None:
                # Follow a modest real tray displacement. A few millimetres of
                # motion are acceptable; only leaving the screened workspace
                # terminates this engineering route.
                displacement=self.destination(name)-receiver_anchor['destination']
                if np.linalg.norm(displacement)>.10:
                    raise ToolExecutionError('Receiver moved outside the swept-clear cup workspace')
                point=fixed_clear_target+displacement
                point[:2]-=current_outlet_offset()-initial_outlet_offset
                return point
            point=self.destination(name)
            if isolated_clear_pour:
                point[:2]-=current_outlet_offset()
                point[:2]+=getattr(self,'_engineering_pour_aim_offset_xy',np.zeros(2))
            if recording.get('pour_adaptive_rim_height_m') is None:
                return np.array([*point[:2],point[2]+pour_height])
            state,_=self.snapshot();receiver=self.s['container']
            half=np.asarray(next(o for o in self.spec['objects'] if o['id']==receiver)['size'],float)
            receiver_top=state[receiver]['pos'][2]+(np.abs(state[receiver]['mat'])@half)[2]
            cup_half=np.asarray(next(o for o in self.spec['objects'] if o['id']==name)['size'],float)
            rotation=state[name]['mat']
            gap=float(recording.get('pour_receiver_clearance_m',.01))
            height=max(point[2]+float(recording['pour_adaptive_rim_height_m']),
                       receiver_top+gap+(np.abs(rotation)@cup_half)[2]+(rotation@rim)[2])
            return np.array([*point[:2],height])
        material_tolerance=float(recording.get('pour_material_tolerance_m',.002))
        if isolated_clear_pour:
            from .execution_design_pour_clearance import actual_clear_target
            receiver=self.snapshot()[0][self.s['container']]
            receiver_anchor={key:receiver[key].copy()for key in('pos','mat')}
            receiver_anchor['destination']=self.destination(name).copy()
            initial_outlet_offset=current_outlet_offset()
            fixed_clear_target=actual_clear_target(self,side,rimref,actual_rim_target(),pour_token(self),
                rest_point+self.tip(side)-self.point(ref),rest_rotation)
        def move_rim():
            if isolated_clear_pour:
                from .execution_design_pour_clearance import move_clear_rim
                return move_clear_rim(self,side,rimref,actual_rim_target(),lambda:self.require_held(ref,side))
            return self.move_point(side,rimref,actual_rim_target(),lambda:self.require_held(ref,side),tolerance=material_tolerance)
        move_rim()
        token=pour_token(self)
        if token not in ('PITCH_UP','PITCH_DOWN','ROLL_LEFT','ROLL_RIGHT'):raise ToolExecutionError('Reviewed cup tilt action required')
        self.stage('tilt-cup-with-actual-feedback')
        for _ in range(40 if isolated_clear_pour else 30):
            self.require_held(ref,side)
            recording=self.a.scene.embodiment.config.get('author_recording',{})
            if self.spec.get('author_smooth_recording',False) and recording.get('continuous_orientation',False):
                rotation_axis=(1,0,0) if token.startswith('ROLL_') else (0,1,0)
                sign=1 if token in ('ROLL_LEFT','PITCH_UP') else -1
                delta=_axis_rotation(rotation_axis,math.radians(5)*sign)
                measured_target=delta@self.snapshot()[0][name]['mat']
                def actual_angle_reached():
                    current=self.snapshot()[0][name]['mat']
                    error=float(np.arccos(np.clip((np.trace(measured_target@current.T)-1)/2,-1,1)))
                    return error<math.radians(float(recording.get('pour_step_angle_tolerance_deg',.5)))
                self.a.rotate_tcp_smooth(side,delta,guard=lambda:self.require_held(ref,side),
                    done=actual_angle_reached if recording.get('pour_measure_rotation_progress',False) else None,
                    verify_done=(lambda:float(np.arccos(np.clip((np.trace(measured_target@self.snapshot()[0][name]['mat'].T)-1)/2,-1,1)))<math.radians(3)) if recording.get('pour_completion_hysteresis',False) else None)
            else:self.act(side,token,degrees=5.)
            if isolated_clear_pour or recording.get('pour_stop_when_physically_empty',False):
                values,_=self.snapshot();body=values[name];empty=True
                for ball in self.s['groups']['balls']:
                    local=body['mat'].T@(values[ball]['pos']-body['pos'])
                    radius=max(next(o for o in self.spec['objects'] if o['id']==ball)['size'])
                    outside=bool(np.any(local<np.asarray(cup['lower'])-radius) or np.any(local>np.asarray(cup['upper'])+radius))
                    empty=empty and outside and not self.contact(name,ball)
                if empty:break
            move_rim()
            mat=self.snapshot()[0][name]['mat'];normal=mat[:,axis]*(1 if cup.get('rim_side','upper')=='upper' else -1)
            if recording.get('pour_pose_feedback',False):
                import json
                state,contacts=self.snapshot()
                with (self.a.out/'pour-feedback.private.jsonl').open('a') as stream:
                    stream.write(json.dumps(dict(normal=normal.tolist(),rim_task=self.point(rimref).tolist(),
                        cup_position=state[name]['pos'].tolist(),cup_rotation=mat.tolist(),
                        balls={n:state[n]['pos'].tolist() for n in self.s['groups']['balls']},
                        contacts=[sorted(pair) for pair in contacts]))+'\n')
            if normal[2]<(-.85 if isolated_clear_pour else-.4):break
        else:raise ToolExecutionError('Actual cup failed to tilt past pouring angle')
        self.wait(10)
        if isolated_clear_pour:
            values,_=self.snapshot();body=values[name]
            retained=[]
            for ball in self.s['groups']['balls']:
                local=body['mat'].T@(values[ball]['pos']-body['pos'])
                radius=max(next(o for o in self.spec['objects']if o['id']==ball)['size'])
                outside=bool(np.any(local<np.asarray(cup['lower'])-radius)or np.any(local>np.asarray(cup['upper'])+radius))
                if not outside or self.contact(name,ball):retained.append(ball)
            if retained:raise ToolExecutionError('Actual bounded cup tilt retained contents: '+str(retained))
        if recording.get('pour_return_upright_only',False):
            self.stage('lift-empty-cup-before-upright-return')
            self.move(side,[*self.tip(side)[:2],max(self.clearance,self.tip(side)[2]+.10)],lambda:self.require_held(ref,side))
            current=self.snapshot()[0][name]['mat'];normal=current[:,axis]*(1 if cup.get('rim_side','upper')=='upper' else -1)
            turn=np.cross(normal,[0,0,1]);angle=float(np.arccos(np.clip(normal[2],-1,1)))
            if angle>math.radians(5):
                if np.linalg.norm(turn)<1e-8:turn=np.array([1.,0.,0.])
                def actually_upright():
                    rotation=self.snapshot()[0][name]['mat']
                    return float(rotation[2,axis])*(1 if cup.get('rim_side','upper')=='upper' else -1)>math.cos(math.radians(float(recording.get('pour_return_upright_tolerance_deg',5))))
                def upright_after_settling():
                    rotation=self.snapshot()[0][name]['mat']
                    return float(rotation[2,axis])*(1 if cup.get('rim_side','upper')=='upper' else -1)>math.cos(math.radians(10))
                self.a.rotate_tcp_smooth(side,_axis_rotation(turn,angle),
                    guard=lambda:self.require_held(ref,side),done=actually_upright,
                    verify_done=upright_after_settling if recording.get('pour_completion_hysteresis',False) else None)
        else:self.rotate_actor(name,side,rest_rotation)
        self.stage('return-empty-cup-to-table');self.park(ref,side,rest_point+[0,0,.001]);self.wait(4)
        if not self.contact(name,'table'):raise ToolExecutionError('Returned cup lacks actual table support')
        if recording.get('pour_wait_for_physical_settle',False):
            for _ in range(int(recording.get('pour_settle_max_actions',40))):
                if self.c.evaluator.result().get('success'):break
                self.wait(1)
                import json
                state,_=self.snapshot();anchor=getattr(self.c.evaluator,'target_anchor',None)
                tracked=[*self.s['groups']['balls'],name]
                changes={n:dict(position_task=state[n]['pos'].tolist(),
                    translation_from_anchor_m=float(np.linalg.norm(state[n]['pos']-anchor[n]['pos'])),
                    rotation_from_anchor_fro=float(np.linalg.norm(state[n]['mat']-anchor[n]['mat'])))
                    for n in tracked}if anchor else {}
                with(self.a.out/'pour-physical-settling.private.jsonl').open('a')as stream:
                    stream.write(json.dumps(dict(tick=self.c.physics_ticks,
                        hold_seconds=getattr(self.c.evaluator,'target_hold',None),changes=changes))+'\n')

    def guide(self):
        t,grip,side=self.tool()
        isolated_guide=(self.task=='E43' and self.spec.get('execution_design',{}).get('revision')=='embodied50-execution-v3-20261102'
                        and getattr(self.a,'control_report',{}).get('engineering_reference_only'))
        if isolated_guide:
            self.stage('lift-guide-before-launcher-transit')
            self.move(side,[*self.tip(side)[:2],self.clearance],lambda:self.require_held(grip,side))
        if self.a.scene.embodiment.config.get('author_recording',{}).get('lift_tool_before_orientation',False):
            self.stage('lift-guide-clear-of-table')
            self.move(side,[*self.tip(side)[:2],max(self.clearance,self.tip(side)[2]+.10)],lambda:self.require_held(grip,side),tolerance=.006)
        launch=self.s['launcher'];point=_finite(launch['guide_intercept_task'],(3,));incoming=_unit(launch['release_direction_task']);target=self.destination('ball')
        guide_plan=None
        if (self.task=='E43' and self.spec.get('execution_design',{}).get('revision')=='embodied50-execution-v3-20261102'
                and getattr(self.a,'control_report',{}).get('engineering_reference_only')):
            from .execution_design_e43_guide_plan import plan,response_plan
            values,_=self.snapshot();launcher=values[launch['actor']]
            objects={o['id']:o for o in self.spec['objects']}
            fixture=objects[launch['actor']];guide=objects[t['actor']]
            response=getattr(self,'_engineering_guide_response',None)
            planner=response_plan if response is not None else plan
            options=({'ball_radius':max(objects['ball']['size']),'response':response}if response is not None else{})
            guide_plan=planner(point,incoming,target,values['ball']['pos'],
                launcher['pos']+launcher['mat']@np.asarray(fixture.get('local_bounds_center',[0,0,0])),
                launcher['mat'],fixture['size'],values[t['actor']]['mat'],guide['size'],t['guide_normal_local'],
                center_relative_work=np.asarray(guide.get('local_bounds_center',[0,0,0]))-np.asarray(t['working_local']),**options)
            point=np.asarray(guide_plan['point'])
            (self.a.out/'actual-passive-guide-plan.private.json').write_text(json.dumps(guide_plan))
        hand_clear_reference=None
        if isolated_guide and getattr(self,'_engineering_guide_response',None)is not None:
            from .execution_design_e43_hand_clearance import select
            hand_clear_reference=select(self,t,grip,side,guide_plan,point)
            t=dict(t,working_local=hand_clear_reference['working_local'])
            point=np.asarray(hand_clear_reference['working_point_task'])
        recording=self.a.scene.embodiment.config.get('author_recording',{})
        if recording.get('guide_closest_plane_normal',False):
            # A plane has two equivalent normals. Choose the nearby physical
            # wrist pose; first compute the reflection in the table plane.
            incoming[2]=0;incoming=_unit(incoming);direction=target-point;direction[2]=0
            outgoing=_unit(direction)
            if np.linalg.norm(incoming-outgoing)<1e-6:
                direction[1]+=.01;outgoing=_unit(direction)
        else:outgoing=_unit(target-point)
        normal=(np.asarray(guide_plan['normal'])if guide_plan is not None else
            np.array([-outgoing[1],outgoing[0],0.]) if recording.get('guide_contact_tangent',False) else _unit(incoming-outgoing))
        normal[2]=0;normal=_unit(normal);local=_unit(t['guide_normal_local']);current=self.snapshot()[0][t['actor']]['mat'];world=current@local
        if recording.get('guide_closest_plane_normal',False) and normal@world<0:normal=-normal
        yaw=math.atan2(normal[1],normal[0])-math.atan2(world[1],world[0])
        guide_rotation=(hand_clear_reference['target_actor_rotation']if hand_clear_reference is not None
            else _axis_rotation([0,0,1],yaw)@current)
        orientations=(hand_clear_reference.get('actor_orientation_waypoints',[guide_rotation])
                      if hand_clear_reference is not None else[guide_rotation])
        for orientation in orientations:self.rotate_actor(t['actor'],side,orientation)
        if isolated_guide:
            self.stage('guide-above-external-intercept')
            self.move_point(side,dict(actor=t['actor'],local=t['working_local']),
                [*point[:2],self.clearance],lambda:self.require_held(grip,side))
        self.stage('actual-guide-material-at-intercept')
        self.move_point(side,dict(actor=t['actor'],local=t['working_local']),point,lambda:self.require_held(grip,side),tolerance=float(recording.get('guide_material_tolerance_m',.002)))
        trigger=launch['trigger'];other='left' if side=='right' else 'right';ref=dict(actor=trigger['actor'],local=trigger['local']);direction=_unit(trigger['press_direction_task']);start=self.point(ref)
        self.stage('physical-launcher-trigger')
        if isolated_guide:
            from .execution_design_e43_trigger import open_upper_gate
            return open_upper_gate(self,grip,side)
        if recording.get('guide_initial_held_gate',False):
            gate_ref=dict(actor=trigger['actor'],local=[0,0,.020])
            self.require_held(gate_ref,other)
            def hold_gate_and_guide():
                self.require_held(grip,side);self.require_held(gate_ref,other)
                if self.contact('ball',f'{other}_finger1')or self.contact('ball',f'{other}_finger2'):
                    raise ToolExecutionError('Gate hand touched source ball directly')
            self.move(other,self.tip(other)+direction*float(trigger['max_travel']),hold_gate_and_guide,tolerance=.003)
            self.act(other,'RELEASE');self.move(other,self.tip(other)+[0,0,.08],lambda:self.require_held(grip,side))
            self.wait(20)
            return
        if recording.get('guide_closed_empty_trigger',False):
            self.move(other,[*self.tip(other)[:2],max(self.clearance,self.tip(other)[2])])
            self.move(other,[*start[:2],max(self.clearance,start[2]+.12)])
            self.a.align_gripper_axis(other,[1.,0.,0.]);self.act(other,'GRASP')
        if recording.get('guide_trigger_tcp_height_offset_m') is not None:
            start=start.copy();start[2]+=float(recording['guide_trigger_tcp_height_offset_m'])
        held=lambda:self.require_held(grip,side)
        self.move(other,start-direction*.02,held)
        if recording.get('guide_stop_on_physical_release',False):
            gate_start=self.snapshot()[0][trigger['actor']]['pos'].copy()
            def released():
                values,_=self.snapshot()
                return (float((values[trigger['actor']]['pos']-gate_start)@direction)>.025
                        and not self.contact('ball',launch['actor']))
            self.a.move_smooth({other:start+direction*float(trigger['max_travel'])},
                guard=held,done=released,tolerance=.004)
        else:self.move(other,start+direction*float(trigger['max_travel']),held)
        self.wait(10)
        self.move(other,self.tip(other)-direction*.03);self.wait(3)

    def clip_gap(self,clip):
        points=[]
        for name in ('left','right'):
            e=clip[name];points.append(self.point(dict(mechanism=clip['mechanism'],body=e['body'],local=e['point_local'])))
        return float(np.linalg.norm(points[1]-points[0])),(points[1]+points[0])/2
    def clip_ref(self,clip,key):return dict(mechanism=clip['mechanism'],**clip['expert'][key])
    def squeeze(self,clip,ref,side):
        if (self.task=='E40'
                and self.spec.get('execution_design',{}).get('revision')=='embodied50-execution-v3-20261102'
                and getattr(self.a,'control_report',{}).get('engineering_reference_only')):
            from .execution_design_clip_grasp import squeeze_supported
            return squeeze_supported(self,clip,ref,side)
        self.acquire(ref,side)
        for _ in range(6):
            if self.clip_gap(clip)[0]>=clip['expert']['open_gap_m']:return
            self.act(side,'GRASP')
        raise ToolExecutionError('Actual spring jaws did not open under handle squeeze')
    def clip_move(self,clip,ref,side,point,follower=None,guard=None):
        progress=[]
        for _ in range(100):
            if guard:guard()
            self.require_held(ref,side);_,current=self.clip_gap(clip);error=np.asarray(point)-current
            if np.max(np.abs(error))<.002:return
            if getattr(self,'_e40_table_supported_reference',False):
                progress.append(float(np.linalg.norm(error)))
                if len(progress)>=8 and min(progress[-4:])>=min(progress[-8:-4])-.0002:
                    raise ToolExecutionError('Actual clip insertion made no net physical progress')
            def held():
                self.require_held(ref,side)
                if guard:guard()
            if getattr(self,'_e40_table_supported_reference',False) and follower is None:
                # Use the measured jaw midpoint after each public move. A
                # flexible clip need not finish an extra submillimetre TCP
                # waypoint before the material point can be corrected again.
                axis=int(np.argmax(abs(error)))
                token=(('FWD','BACK'),('LEFT','RIGHT'),('UP','DOWN'))[axis][int(error[axis]<0)]
                self.act(side,token,mm=min(8.,abs(error[axis])*1000.))
            else:
                self.move(side,self.tip(side)+np.clip(error,-.008,.008),held,follower,tolerance=.0008)
        raise ToolExecutionError('Actual jaw midpoint failed to reach edge')
    def clip_contact(self,clip,actor):return all(self.contact(clip[n]['contact_body'],actor) for n in ('left','right'))

    def clip_edges(self,start_index=0):
        selected=(['circle','cross'],['square','triangle'],['circle','triangle','cross'])[self.index];clips=list(self.s['clips'].values())
        if start_index and not (start_index in (1,2,3) and self.task=='E40' and hasattr(self.a,'_engineering_resume_checkpoint') and start_index<=len(selected)):
            raise ToolExecutionError('Partial clip continuation requires explicit E40 engineering checkpoint')
        if len(clips)<len(selected):raise ToolExecutionError('Distinct physical clips required')
        for clip,marker in list(zip(clips,selected))[start_index:]:
            self.stage('clip-marker-'+marker);ref=self.clip_ref(clip,'handle_grasp');side='right'
            if (self.spec.get('execution_design',{}).get('revision')=='embodied50-execution-v3-20261102'
                    and getattr(self.a,'control_report',{}).get('engineering_reference_only')):
                body_point=self.point(self.clip_ref(clip,'body_grasp'))
                support=min(('left','right'),key=lambda hand:float(np.linalg.norm(self.tip(hand)-body_point)))
                side='right' if support=='left' else 'left'
            side=self.squeeze(clip,ref,side) or side;z=next(z for z in self.spec['zones'] if z['id']==marker);point=np.array(z['edge_point']);axis=_unit(clip['expert']['insert_direction_task'])
            if getattr(self,'_e40_table_supported_reference',False) and self.task=='E40':
                from .execution_design_clip_edge_alignment import insertion_point
                point=insertion_point(self,clip,point)
            self.clip_move(clip,ref,side,point-axis*.03);self.clip_move(clip,ref,side,point);self.release(ref,side);self.wait(3)
            if not self.clip_contact(clip,z['support']):raise ToolExecutionError('Both real jaws did not clamp paper edge')
            self.move(side,self.tip(side)-axis*.03+[0,0,.04])
        if getattr(self,'_e40_table_supported_reference',False):
            from .execution_design_clip_edge_alignment import require_prior_physical_clamps
            require_prior_physical_clamps(self,len(selected))

    def clip_card(self):
        name,=self.s['groups']['cards'];clip,=self.s['clips'].values();card=dict(actor=name,**self.s['card_grasp'])
        if (self.spec.get('execution_design',{}).get('revision')=='embodied50-execution-v3-20261102'
                and self.a.control_report.get('engineering_reference_only')):
            import os
            if os.environ.get('VIC_ENGINEERING_PRACTICAL_CARD_THICKNESS')=='1':
                from .execution_design_practical_card_grasp import acquire
                acquire(self,card,'left')
            else:
                from .execution_design_card_edge import acquire_card
                acquire_card(self,card,'left')
        else:self.acquire(card,'left')
        return self.clip_card_after_grasp(name,clip,card)

    def clip_card_after_grasp(self,name,clip,card):
        if (self.task=='E50' and self.spec.get('semantic',{}).get('engineering_card_approximation')
                and getattr(self.a,'control_report',{}).get('engineering_reference_only')):
            from .execution_design_e50_card_finish import flip_then_clip
            return flip_then_clip(self,name,clip,card)
        self.require_held(card,'left')
        initial=self.snapshot()[0][name]['mat'];self.move('left',self.tip('left')+[0,0,.10],lambda:self.require_held(card,'left'));self.rotate_actor(name,'left',_axis_rotation([1,0,0],math.pi)@initial)
        self.move_point('left',card,self.s['tool_expert']['card_flip_place_task'],lambda:self.require_held(card,'left'))
        return self.clip_card_after_flip(name,clip,card)

    def clip_card_after_flip(self,name,clip,card):
        """Continue from an actually held, already flipped card, without reflipping."""
        self.require_held(card,'left')
        # Keep the allowed assisting hand on the thin card while the opposite
        # hand squeezes the real two-handle mechanism. This leaves clearance
        # under the card for the lower jaw and prevents a tabletop scrape from
        # being mistaken for insertion. Clamp the measured edge, not its center.
        body=self.clip_ref(clip,'body_grasp');handle=self.clip_ref(clip,'handle_grasp');self.squeeze(clip,handle,'right')
        local=_finite(self.s['tool_expert']['card_clip_point_local'],(3,));value=self.snapshot()[0][name];point=value['pos']+value['mat']@local
        axis=_unit(clip['expert']['insert_direction_task']);assisting=lambda:self.require_held(card,'left')
        self.clip_move(clip,handle,'right',point-axis*.025,guard=assisting);self.clip_move(clip,handle,'right',point,guard=assisting)
        self.release(handle,'right');self.wait(3)
        if not self.clip_contact(clip,name):raise ToolExecutionError('Card not physically clamped')
        self.move('right',self.tip('right')-axis*.025);self.acquire(body,'right')
        if not self.clip_contact(clip,name):raise ToolExecutionError('Card clamp lost while acquiring clip body')
        self.release(card,'left');self.move('left',self.tip('left')+[0,0,.08]);self.wait()
        def carrying():
            self.require_held(body,'right')
            if not self.clip_contact(clip,name):raise ToolExecutionError('Card lost actual two-jaw clamp')
        zone=next(z for z in self.spec['zones'] if z['id']==('green','blue','red')[self.index]);target=np.array([*zone['xy'],zone.get('surface_z',.8)+.003]);self.move('right',self.tip('right')+[0,0,.08],carrying);self.clip_move(clip,body,'right',target+[0,0,.08],guard=carrying);self.clip_move(clip,body,'right',target,guard=carrying)
        self.squeeze(clip,handle,'left');self.clip_move(clip,body,'right',target+[0,0,.03],follower='left');self.release(handle,'left');self.move('left',self.tip('left')+[0,0,.08]);self.park(body,'right',clip['expert']['return_point_task'])

    def fold(self):
        if (self.spec.get('execution_design',{}).get('revision')=='embodied50-execution-v3-20261102'
                and getattr(self.a,'control_report',{}).get('engineering_reference_only')):
            from .execution_design_fold_public import fold_public
            return fold_public(self)
        if self.a.scene.embodiment.config.get('author_recording',{}).get('e44_source_edge_fold',False):
            from .author_e44_edge_private import fold_source_edge
            return fold_source_edge(self)
        c=self.s['crease'];g=c['expert'];fold=dict(mechanism=c['mechanism'],**g['fold_grasp']);base=dict(mechanism=c['mechanism'],**g['base_press']);self.acquire(fold,'right');press=self.point(base)
        self.move('left',press+[0,0,.035]);self.move('left',press)
        if not any(self.contact(base['contact_body'],f'left_finger{i}') for i in (1,2)):raise ToolExecutionError('Base panel lacks physical holding contact')
        bp,br=self.frame(base);hinge=bp+br@_finite(g['hinge_point_local'],(3,));axis=br@_unit(g['axis_local']);vector=self.point(fold)-hinge;target=(90.,120.,45.)[self.index];direction=float(g['direction'])
        if direction not in (-1,1):raise ToolExecutionError('Reviewed crease direction required')
        self.stage('contact-driven-plastic-fold')
        for angle in np.arange(5.,180-target+5.,5.):
            point=hinge+_axis_rotation(axis,math.radians(min(angle,180-target))*direction)@vector
            self.move_point('right',fold,point,lambda:self.require_held(fold,'right'))
        self.release(fold,'right');self.move('right',self.tip('right')+[0,0,.07]);self.move('left',self.tip('left')+[0,0,.07]);self.wait(5)


def solve_tool(author):
    policy=ToolAuthor(author)
    import os
    if os.environ.get('VIC_ENGINEERING_E43_CONTACT_RESPONSE')=='1':
        from .execution_design_e43_guide_plan import configure_measured_reference
        configure_measured_reference(policy)
    if policy.task=='E43' and os.environ.get('VIC_ENGINEERING_E43_RAIL_AUDIT')=='1':
        from .engineering_e43_rail_audit import solve
        return solve(policy)
    try:
        method={'E28':'spatula','E29':'mallet','E40':'clip_edges','E42':'push','E43':'guide','E44':'fold','E45':'pour','E46':'spatula','E50':'clip_card'}[policy.task]
        getattr(policy,method)();policy.wait(4)
    except (KeyError,ValueError,TypeError,IndexError) as exc:
        raise ToolExecutionError('Missing/invalid reviewed source tool geometry: '+str(exc)) from exc
    return dict(task=policy.task,variant=policy.variant,actions=policy.c.steps-policy.start,operations=policy.operations,execution_finished=True,physics_success_not_asserted=True)


__all__=['ToolAuthor','ToolExecutionError','solve_tool','SUPPORTED']
