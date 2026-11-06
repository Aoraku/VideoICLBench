"""E18-only v3 engineering wrist tracking, using public relative actions.

Nominal nine 10-degree commands are not an achieved 90-degree rotation. The
native E18 reference recorded roughly 0.142rad residual after each command.
This fixes that reference assumption; physical handle feasibility stays pending.
"""
import math,json
import numpy as np
from .execution_design import REVISION_V3
from .realworld_mechanism_expert import _Author,MechanismExecutionError


def handle_orientation_target(author, side, outward, bar_axis, jaw_sign=1.):
    """Orient real fingertips vertically around the source bar, palm outside.

    Uses actual finger body origins, not target/nominal Panda poses. A normal
    pinch would require a finger in the measured 5.68 mm wall gap.
    """
    from .author_orientation import _rotation
    from .realworld_mechanism_expert import _unit
    normal=_unit(outward);bar=_unit(bar_axis)
    jaw=_unit(np.cross(normal,bar))
    if jaw[2]<0:jaw=-jaw
    if jaw_sign not in (-1.,1.):raise MechanismExecutionError('Equivalent jaw sign must be +/-1')
    jaw=jaw*jaw_sign
    geometry=author.finger_geometry(side)
    if geometry.get('source')!='actual_collision_mesh_current_body_pose':
        raise MechanismExecutionError('Actual finger collision body poses required')
    origins=[np.asarray(row['body_origin_task_m'],float)for row in geometry['fingers']]
    if len(origins)!=2:raise MechanismExecutionError('Two actual finger bodies required')
    current_jaw=_unit(origins[0]-origins[1])
    palm=np.mean(origins,axis=0)-np.asarray(author.tip(side),float)
    palm=_unit(palm-current_jaw*float(palm@current_jaw))
    actual_frame=np.column_stack((current_jaw,np.cross(palm,current_jaw),palm))
    desired_frame=np.column_stack((jaw,np.cross(normal,jaw),normal))
    return _rotation(desired_frame@actual_frame.T@_rotation(author.tcp_rotation_task(side),'actual E18 TCP'),'E18 source handle target')


def choose_handle_orientation(author,controller,side,point,outward,bar_axis,ik_probe=None,clearance_probe=None):
    """Screen equivalent/oblique real-hand grasps, then actual endpoint IK."""
    if ik_probe is None:
        if getattr(author.scene,'spec',{}).get('e18_support_layout'):
            from .execution_design_e15_path import inspect_path
            ik_probe=inspect_path
        else:
            from .execution_design_drawer_ik_probe import inspect
            ik_probe=inspect
    if clearance_probe is None:
        from .execution_design_e18_pinch import closed_hand_geometry,bar_pinch_candidate,finite_bar_pinch_candidate
        geometry=closed_hand_geometry(author,side)
        probe=finite_bar_pinch_candidate if author.scene.spec.get('e18_support_layout')else bar_pinch_candidate
        clearance_probe=lambda rotation:probe(geometry,rotation,point,outward,bar_axis)
    from .realworld_tool_expert import _axis_rotation
    point=np.asarray(point,float);normal=np.asarray(outward,float);normal=normal/np.linalg.norm(normal)
    pitch=np.cross([0.,0.,1.],-normal);pitch/=np.linalg.norm(pitch)
    candidates=[]
    options=((0.,0.),(0.,5.),(0.,-5.)) if getattr(author.scene,'spec',{}).get('e18_support_layout')else ((0.,0.),(45.,15.),(-45.,15.),(30.,25.),(-30.,25.),(50.,5.),(55.,0.),(55.,5.),(60.,0.),(60.,5.),(60.,10.))
    for roll,tilt in options:
      for sign in (1.,-1.):
        base=handle_orientation_target(author,side,normal,bar_axis,jaw_sign=sign)
        rotation=_axis_rotation(pitch,math.radians(tilt))@_axis_rotation(-normal,math.radians(roll))@base
        clearance=clearance_probe(rotation)
        target=np.asarray(clearance['target_position'],float)
        front=target+normal*.11;staging=front.copy();staging[2]=max(point[2]+.08,clearance['rotation_safe_z_m'])
        raised=np.asarray(author.tip(side),float).copy();raised[2]=max(raised[2],staging[2])
        neutral=np.asarray(author.tcp_rotation_task(side),float)
        positions=[dict(position=raised,rotation=neutral),dict(position=staging,rotation=neutral),dict(position=staging,rotation=rotation),dict(position=front,rotation=rotation),dict(position=target,rotation=rotation)]
        measured=ik_probe(author,controller,side,positions)if clearance['feasible']else[]
        valid=(len(measured)==len(positions)and all(x.get('kinematically_reachable')for x in measured))
        margin=min((x.get('minimum_joint_margin_rad',-1.)for x in measured),default=-1.)
        distance=sum(x.get('joint_distance_rad',float('inf'))for x in measured)
        candidates.append(dict(jaw_sign=sign,roll_deg=roll,tilt_deg=tilt,target_rotation=rotation.tolist(),orientation_staging=staging.tolist(),orientation_raise=raised.tolist(),geometry=clearance,ik=measured,feasible=bool(valid and margin>.01),minimum_joint_margin_rad=margin,total_joint_distance_rad=distance))
    valid=[x for x in candidates if x['feasible']]
    # Once endpoint clearance is adequate, do not select a longer wrist branch
    # just to gain a few extra milliradians of margin. Measured E18 replay found
    # the +jaw/-30deg branch winds joint7 toward its lower limit, while the
    # equivalent -jaw/+30deg branch follows a nearby continuous rotation path.
    # This ranking does not waive endpoint or per-action native checks.
    selected=max(valid,key=lambda x:(min(.25,x['minimum_joint_margin_rad']),-x['total_joint_distance_rad']))if valid else None
    if getattr(author,'out',None)is not None:
        with (author.out/'e18-equivalent-grip-candidates.private.jsonl').open('a')as stream:
            stream.write(json.dumps(dict(candidates=candidates,selected_jaw_sign=selected['jaw_sign']if selected else None,selected_roll_deg=selected['roll_deg']if selected else None,selected_tilt_deg=selected['tilt_deg']if selected else None,collision_verified=False,actuation_performed=False))+'\n')
    if selected is None:raise MechanismExecutionError('Neither equivalent nor oblique E18 pinch has measured hand clearance and endpoint joint margins')
    if not hasattr(author,'_e18_orientation_staging'):author._e18_orientation_staging={}
    author._e18_orientation_staging[side]=(selected['orientation_raise'],selected['orientation_staging'])
    return np.asarray(selected['target_rotation'],float)


def handle_tcp_target(author,side,point,outward):
    """Actual closed-finger reach, never the opened AABB's empty corner."""
    from .execution_design_e18_pinch import closed_hand_geometry,bar_pinch_candidate,finite_bar_pinch_candidate
    normal=np.asarray(outward,float);normal/=np.linalg.norm(normal)
    bar=np.cross([0.,0.,1.],normal);bar/=np.linalg.norm(bar)
    probe=finite_bar_pinch_candidate if author.scene.spec.get('e18_support_layout')else bar_pinch_candidate
    result=probe(closed_hand_geometry(author,side),author.tcp_rotation_task(side),point,normal,bar)
    if not result['feasible']:
        raise MechanismExecutionError('Actual E18 bilateral closing geometry or panel/table clearance failed')
    if getattr(author,'out',None)is not None:
        with (author.out/'e18-actual-pinch-geometry.private.jsonl').open('a')as stream:
            stream.write(json.dumps(result)+'\n')
    return np.asarray(result['target_position'],float)


def choose_rotation_increment(author,controller,side,target,lo,hi,ik_probe=None):
    """Check nearby public rotations from the actual current wrist state.

    A distant endpoint solution does not establish a continuous wrist path.
    No candidate joints are commanded; native public actions remain the only
    actuator, and their actual responses are checked by the caller.
    """
    from .author_orientation import _rotation,_axis_angle
    from .realworld_tool_expert import _axis_rotation
    if ik_probe is None:
        from .execution_design_drawer_ik_probe import inspect
        ik_probe=inspect
    current=_rotation(author.tcp_rotation_task(side),'actual E18 TCP')
    axis,error=_axis_angle(target@current.T)
    labels=(('ROLL_LEFT','ROLL_RIGHT'),('PITCH_UP','PITCH_DOWN'),('ROTATE_CCW','ROTATE_CW'))
    choices=[]
    for component in range(3):
        degrees=min(5.,hi,max(lo,abs(math.degrees(error*axis[component]))))
        if degrees<lo:continue
        for sign in (1.,-1.):
            rotation=_axis_rotation(np.eye(3)[component],sign*math.radians(degrees))@current
            predicted=_axis_angle(target@rotation.T)[1]
            if predicted<error-math.radians(.01):
                choices.append(dict(token=labels[component][int(sign<0)],degrees=degrees,
                    predicted_error_rad=predicted,rotation=rotation.tolist(),position=list(author.tip(side))))
    rows=ik_probe(author,controller,side,[dict(position=x['position'],rotation=x['rotation'])for x in choices]) if choices else []
    if len(rows)!=len(choices):raise MechanismExecutionError('Incomplete E18 incremental IK evidence')
    accepted=[]
    for index,row in enumerate(rows):
        values=np.asarray([row.get('position_error_m',float('inf')),row.get('orientation_error_rad',float('inf')),
            row.get('minimum_joint_margin_rad',-1.),row.get('joint_distance_rad',float('inf'))],float)
        if (row.get('kinematically_reachable') and np.isfinite(values).all() and values[0]<.001
                and values[1]<math.radians(1.5) and values[2]>.05 and values[3]<.35):accepted.append(index)
    chosen=min(accepted,key=lambda i:(choices[i]['predicted_error_rad'],rows[i]['joint_distance_rad'])) if accepted else None
    if getattr(author,'out',None)is not None:
        evidence=dict(step=controller.steps,side=side,actual_error_rad=error,
            candidates=[dict(**choice,ik=row)for choice,row in zip(choices,rows)],chosen_index=chosen,
            collision_verified=False,actuation_performed=False)
        with (author.out/'e18-rotation-increments.private.jsonl').open('a')as stream:stream.write(json.dumps(evidence)+'\n')
    if chosen is None:
        # Near a kinematic singularity five degrees can require a large joint
        # change even while the endpoint has ample limit clearance. Subdivide
        # the public rotation, retaining the same strict IK and margin tests.
        reduced=max(lo,min(5.,hi)/2.)
        if reduced<min(5.,hi)-1e-9:
            return choose_rotation_increment(author,controller,side,target,lo,reduced,ik_probe)
        raise MechanismExecutionError('No improving near-neighbor E18 public rotation with joint margin')
    return choices[chosen]['token'],choices[chosen]['degrees']


def orientation_waypoints(current,target,max_degrees=12.):
    """Short geodesic targets; public axis actions still perform every motion."""
    from .author_orientation import _rotation,_axis_angle
    from .realworld_tool_expert import _axis_rotation
    current=_rotation(current,'actual E18 start');target=_rotation(target,'E18 final target')
    if not math.isfinite(max_degrees) or not 0<max_degrees<=12.:
        raise ValueError('E18 orientation waypoints must be at most12degrees')
    axis,angle=_axis_angle(target@current.T)
    if angle<1e-9:return [target]
    count=max(1,math.ceil(math.degrees(angle)/max_degrees))
    return [_axis_rotation(axis,angle*i/count)@current for i in range(1,count+1)]


class E18MeasuredAuthor(_Author):
    def _public_pull_observation(self,role,side,phase):
        snapshot=self.mechanisms();point=self.point(role,snapshot);axis=self.axis(role,snapshot)
        _,frame=self.frame(self.points[role],snapshot);tip=self.tip(side);offset=tip-point
        robot=self.a.scene.robots[side];ids,names=robot.find_joints('panda_finger_joint[1-2]')
        if list(names)!=['panda_finger_joint1','panda_finger_joint2']:
            raise MechanismExecutionError('Actual E18 finger identity required for loaded pull')
        def array(value):
            if hasattr(value,'detach'):value=value.detach()
            if hasattr(value,'cpu'):value=value.cpu()
            return np.asarray(value,float)[0,ids]
        opening=array(robot.data.joint_pos);speed=array(robot.data.joint_vel)
        if not np.isfinite(np.r_[opening,speed,offset]).all():
            raise MechanismExecutionError('Invalid E18 actual loaded-pull measurement')
        entry=self.roles[role];mechanism=snapshot[entry['mechanism']]
        index=mechanism['joint_names'].index(entry['joint'])
        feedback=self.c.action_feedback().get('control_feedback',{}).get(side,{})
        requested=feedback.get('requested_delta_m');achieved=feedback.get('actual_delta_m')
        target_error=None
        if requested is not None and achieved is not None:
            requested=np.asarray(requested,float);achieved=np.asarray(achieved,float)
            if requested.shape==(3,)and achieved.shape==(3,)and np.isfinite(np.r_[requested,achieved]).all():
                target_error=(requested-achieved).tolist()
        forces=[]
        for i in (1,2):
            value=self.c.contact_forces.get(frozenset((entry['contact_body'],f'{side}_finger{i}')))
            forces.append(float(value)if isinstance(value,(int,float))and math.isfinite(value)else None)
        row=dict(phase_index=phase,action_step=self.c.steps,actual_tcp_task_m=tip.tolist(),
            actual_handle_task_m=point.tolist(),actual_handle_axis_task=axis.tolist(),
            tcp_minus_handle_task_m=offset.tolist(),tcp_minus_handle_local_m=(frame.T@offset).tolist(),
            tcp_axial_offset_m=float(offset@axis),tcp_lateral_offset_m=float(np.linalg.norm(offset-axis*float(offset@axis))),
            drawer_displacement_m=self.displacement(role,snapshot),drawer_velocity_m_s=float(mechanism['joint_vel'][index])*entry['direction'],
            finger_q_m=opening.tolist(),finger_qd_m_s=speed.tolist(),
            bilateral_contact=bool(self.touching(role,side,both=True)),contact_forces_n=forces,
            retained_tcp_goal_error_task_m=target_error)
        if getattr(self.a,'out',None)is not None:
            with (self.a.out/'e18-public-pull-following.private.jsonl').open('a')as stream:
                stream.write(json.dumps(row,allow_nan=False)+'\n')
        self.operations.append(dict(operation='actual_public_drawer_pull_readback',**row))
        return row

    def prepare_drawer_public_pull(self,role,side):
        if getattr(self,'_engineering_two_mm_real_reseat',False):
            from .execution_design_e18_opening import prepare
            return prepare(self,role,side)
        before=self._public_pull_observation(role,side,0)
        if not before['bilateral_contact']:
            raise MechanismExecutionError('E18 actual handle contact absent before public GRASP hold')
        if not hasattr(self,'_e18_pull_reference'):self._e18_pull_reference={}
        key=(role,side)
        if key not in self._e18_pull_reference:
            self._e18_pull_reference[key]=dict(axial_m=before['tcp_axial_offset_m'],
                lateral_m=before['tcp_lateral_offset_m'],source_action=before['action_step'],
                engineering_calibration=True)
        reference=self._e18_pull_reference[key];excess=before['tcp_axial_offset_m']-reference['axial_m'];follow=None
        if excess>.0005:
            # Follow the actual material handle inward once. This real public
            # increment supersedes the unfinished outward goal; it is not a
            # private TCP/joint retarget or a fabricated quiet hold.
            direction=-self.axis(role);component=int(np.argmax(np.abs(direction)))
            if abs(float(direction[component]))<.95:
                raise MechanismExecutionError('E18 inward handle follow is not a public translation axis')
            token=(('FWD','BACK'),('LEFT','RIGHT'),('UP','DOWN'))[component][int(direction[component]<0)]
            amount=min(1.,excess*1000.);self.act(side,token,mm=amount)
            follow=self._public_pull_observation(role,side,3)
            self._require_public_pull_grip(follow,side)
            advance=float((np.asarray(follow['actual_tcp_task_m'])-before['actual_tcp_task_m'])@direction)
            if advance<.0001:
                raise MechanismExecutionError('E18 public inward handle follow failed to advance')
            follow=dict(follow,requested_inward_mm=amount)
        # Exactly one public GRASP keeps the existing Cartesian goal and real
        # finger drive. Its resulting motion/target residual is measured; no
        # quiet-state label, joint override, or TCP retarget is manufactured.
        self.act(side,'GRASP')
        after=self._public_pull_observation(role,side,1)
        self._require_public_pull_grip(after,side)
        return dict(before=before,reference=reference,inward_follow=follow,after=after)

    def _require_public_pull_grip(self,after,side):
        feedback=self.c.action_feedback().get('control_feedback',{}).get(side,{})
        if (feedback.get('status')=='blocked' or feedback.get('joint_limit_names')
                or feedback.get('consecutive_ik_refusals',0)>0):
            raise MechanismExecutionError('E18 public bounded handle preparation controller rejected the action')
        if (not after['bilateral_contact']or min(after['finger_q_m'])<.0003
                or any(value is None or value<=.001 for value in after['contact_forces_n'])):
            raise MechanismExecutionError('E18 actual bilateral nonempty handle grip lost during bounded follow/GRASP preparation')

    def record_drawer_public_pull(self,role,side):
        return self._public_pull_observation(role,side,2)

    def follow_drawer_pad_z_once(self,role,side):
        """One actual<=1mm vertical pad-follow, preserving native hand clearance."""
        before=self._public_pull_observation(role,side,0);self._require_public_pull_grip(before,side)
        reference_z=.0003393166818053215  # Actual source162 TCP-minus-handle Z.
        error=reference_z-float(before['tcp_minus_handle_task_m'][2])
        if abs(error)<=.00025:return dict(performed=False,before=before,after=before,reference_z_m=reference_z)
        if self.min_mm>1.:raise MechanismExecutionError('E18 precision vertical follow exceeds public one-mm bound')
        amount=min(1.,max(self.min_mm,abs(error)*1000.));token='UP'if error>0 else'DOWN'
        from .execution_design_e18_geometry import actual_hand_clouds
        def hand_floor():
            geometry=actual_hand_clouds(self.a,side)
            if geometry.get('source')!='actual_native_collision_mesh_current_body_pose'or len(geometry['clouds_tcp'])!=3:
                raise MechanismExecutionError('Actual E18 two-finger and palm geometry required for vertical follow')
            rotation=np.asarray(self.a.tcp_rotation_task(side));tip=self.tip(side)
            return min(float(np.min((np.asarray(cloud)@rotation.T+tip)[:,2])-geometry['table_top'])for cloud in geometry['clouds_tcp'])
        floor=hand_floor();predicted=floor+(amount/1000 if token=='UP'else-amount/1000)
        if predicted<=.002:raise MechanismExecutionError('E18 vertical pad follow violates original hand/table clearance')
        self.act(side,token,mm=amount)
        after=self._public_pull_observation(role,side,4);self._require_public_pull_grip(after,side)
        actual_floor=hand_floor()
        if actual_floor<=.002:raise MechanismExecutionError('E18 actual vertical follow lost original hand/table clearance')
        advance=(after['actual_tcp_task_m'][2]-before['actual_tcp_task_m'][2])*(1 if token=='UP'else-1)
        if advance<.0001:raise MechanismExecutionError('E18 public vertical pad follow failed to advance')
        return dict(performed=True,public_token=token,requested_mm=amount,reference_z_m=reference_z,
            before=before,after=after,hand_floor_before_m=floor,hand_floor_after_m=actual_floor)

    def drawer_public_step_m(self,role,close):
        from .execution_design_e18_support import VERSION,LIFT_M,SOURCE_SHA
        layout=self.spec.get('e18_support_layout',{})
        if (self.task=='E18' and role=='drawer' and not close
                and self.spec.get('execution_design',{}).get('revision')==REVISION_V3
                and getattr(self.a,'control_report',{}).get('engineering_reference_only')
                and layout.get('version')==VERSION and layout.get('source_cabinet_sha256')==SOURCE_SHA
                and isinstance(layout.get('lift_m'),(int,float))
                and math.isclose(layout['lift_m'],LIFT_M,rel_tol=0,abs_tol=1e-12)):
            # The real supported-source short segment retained its bilateral
            # grip after one public3mm pull. The full6mm waypoint-tracking
            # route subsequently lost the measured handle grip.
            return .002 if getattr(self,'_engineering_two_mm_real_reseat',False)else .003
        return super().drawer_public_step_m(role,close)

    def approach(self,role,side,button=False):
        if button:raise MechanismExecutionError('E18 has no button approach')
        # Stay outside the drawer while descending, then approach horizontally.
        # 0.11m exceeds actual open-hand half width; the source handle point is
        # always refreshed from the real articulation frame before contact.
        normal=self.axis(role);point=handle_tcp_target(self.a,side,self.point(role),normal)
        if abs(float(normal[2]))>.1:raise MechanismExecutionError('E18 source handle normal is not horizontal')
        front=point+normal*.11
        current=self.tip(side);elevated=front.copy();elevated[2]=max(current[2],point[2])
        self.stage('mechanism-front-lane-'+role)
        self.move(side,elevated,tolerance=.006);self.move(side,front,tolerance=.006)
        self.stage('mechanism-contact-'+role)
        self.move(side,point+normal*.025)
        self.move(side,handle_tcp_target(self.a,side,self.point(role),normal),tolerance=.0005)

    def acquire(self,role,*,closing_push=False):
        quick=bool(getattr(self,'_engineering_single_handle_observation',False))
        if quick and (self.spec.get('execution_design',{}).get('revision')!=REVISION_V3
                or not getattr(self.a,'control_report',{}).get('engineering_reference_only')):
            raise ValueError('Single-observation handle acquisition is private v3 engineering only')
        side=super().acquire(role,closing_push=closing_push)
        if closing_push:return side
        # A transient first touch while fingers still close is not a settled
        # tensile grip. Keep the public GRASP target and observe actual joints
        # and bilateral contacts before permitting the first pull.
        self.stage('mechanism-settle-handle-'+role)
        robot=self.a.scene.robots[side]
        ids,names=robot.find_joints('panda_finger_joint[1-2]')
        if list(names)!=['panda_finger_joint1','panda_finger_joint2']:
            raise MechanismExecutionError('Actual E18 finger joint identity required')
        consecutive=0
        for _ in range(1 if quick else 8):
            if not quick:self.act(side,'GRASP')
            def array(value):
                if hasattr(value,'detach'):value=value.detach()
                if hasattr(value,'cpu'):value=value.cpu()
                return np.asarray(value,float)[0,ids]
            opening=array(robot.data.joint_pos);speed=array(robot.data.joint_vel)
            bilateral=self.touching(role,side,both=True)
            row=dict(operation='settle_handle',role=role,side=side,opening_m=opening.tolist(),
                     velocity_m_s=speed.tolist(),bilateral_contact=bilateral)
            self.operations.append(row)
            if not np.isfinite(opening).all() or not np.isfinite(speed).all():
                raise MechanismExecutionError('Invalid actual E18 finger measurement')
            minimum=.0003 if getattr(self.a.scene,'spec',{}).get('e18_support_layout')else .002
            if not bilateral or np.any(opening<minimum):
                raise MechanismExecutionError('E18 handle grip lost while settling before pull')
            if quick:
                row['engineering_grip_gate']='single_bilateral_nonempty_observation'
                return side
            consecutive=consecutive+1 if np.max(np.abs(speed))<.002 else 0
            if consecutive>=3:return side
        raise MechanismExecutionError('E18 handle grip did not settle before pull')

    def orient(self,role,side,inverse=False):
        from .author_orientation import _rotation,_axis_angle
        from .realworld_tool_expert import _axis_rotation
        if self.task!='E18' or self.spec.get('execution_design',{}).get('revision')!=REVISION_V3:
            raise ValueError('E18 measured reference requires explicit v3 engineering scope')
        actual=lambda:_rotation(self.a.tcp_rotation_task(side),'actual E18 TCP')
        if not hasattr(self,'_e18_neutral_rotations'):self._e18_neutral_rotations={}
        if side not in self._e18_neutral_rotations:
            if inverse:raise MechanismExecutionError('Cannot restore unknown E18 wrist baseline')
            self._e18_neutral_rotations[side]=actual().copy()
        target=self._e18_neutral_rotations[side].copy()
        if not inverse:
            _,frame=self.frame(self.points[role],self.mechanisms())
            # Local X is the measured 97.94mm bar; local Z is its outward face.
            # The upper/lower pinch axis is perpendicular to both, not normal
            # to the panel as in the legacy yaw-only recording recipe.
            target=choose_handle_orientation(self.a,self.c,side,self.point(role),frame@np.array([0.,0.,1.]),frame@np.array([1.,0.,0.]),ik_probe=getattr(self,'_e18_ik_probe',None),clearance_probe=getattr(self,'_e18_clearance_probe',None))
            self.stage('mechanism-safe-empty-wrist-staging-'+role)
            raised,staging=self.a._e18_orientation_staging[side]
            self.move(side,raised,tolerance=.006);self.move(side,staging,tolerance=.006)
        bounds=self.a.scene.embodiment.config['control']['rotation_deg'];lo=max(.5,float(bounds[0]));hi=min(10.,float(bounds[1]))
        if not 0<lo<=hi:raise MechanismExecutionError('Invalid public E18 rotation limits')
        labels=(('ROLL_LEFT','ROLL_RIGHT'),('PITCH_UP','PITCH_DOWN'),('ROTATE_CCW','ROTATE_CW'))
        # Global greedy XYZ rotation can wind the wrist onto a different
        # redundant branch. Follow short orientation waypoints instead. Also
        # keep the actual staging centre: relative actions otherwise reset
        # their hold point to each small tracking error and accumulate drift.
        waypoints=orientation_waypoints(actual(),target);waypoint_index=0
        rotation_center=np.asarray(self.a.tip(side),float).copy()
        history=[];previous=self.a.stage;self.stage('mechanism-measured-orient-'+role)
        try:
            for _ in range(360):
                if self.c.steps-self.start_steps>=self.max_actions:raise MechanismExecutionError('Mechanism expert action budget exhausted')
                if np.max(np.abs(np.asarray(self.a.tip(side))-rotation_center))>.006:
                    self.move(side,rotation_center,tolerance=.004)
                    if np.max(np.abs(np.asarray(self.a.tip(side))-rotation_center))>.006:
                        raise MechanismExecutionError('Actual E18 rotation centre not recovered')
                current=actual();axis,angle=_axis_angle(target@current.T)
                if angle<math.radians(1.5):
                    self.operations.append(dict(operation='measured_wrist_restore'if inverse else'measured_wrist_orientation',role=role,side=side,actual_rotation=current.tolist(),target_rotation=target.tolist(),residual_rad=float(angle),native_handle_success_not_asserted=True))
                    return
                while (waypoint_index<len(waypoints)-1 and
                       _axis_angle(waypoints[waypoint_index]@current.T)[1]<math.radians(1.5)):
                    waypoint_index+=1
                token,degrees=choose_rotation_increment(self.a,self.c,side,waypoints[waypoint_index],lo,hi,
                    ik_probe=getattr(self,'_e18_increment_ik_probe',None))
                self.a.act(token if side=='left'else'STILL',token if side=='right'else'STILL',rotation_deg=degrees)
                history.append(actual())
                if len(history)>=12 and max(_axis_angle(r@history[-1].T)[1]for r in history[-12:])<.002:
                    raise MechanismExecutionError('Measured E18 wrist rotation stalled')
            raise MechanismExecutionError('Measured E18 wrist orientation did not converge')
        finally:self.a.stage=previous


def solve_e18_reference(author):
    if not getattr(author,'_execution_design_reference_authorized',False):
        raise ValueError('Explicit engineering reference authorization required')
    worker=E18MeasuredAuthor(author)
    from .execution_design_e18_support import VERSION,SOURCE_SHA,LIFT_M
    layout=author.scene.spec.get('e18_support_layout',{})
    if (layout.get('version')==VERSION and layout.get('source_cabinet_sha256')==SOURCE_SHA
            and layout.get('lift_m')==LIFT_M):
        # The native held4 continuation reached the unchanged95mm target via
        # actual public2mm pulls, measured Z follow and real pad-depth regrasp.
        worker._engineering_two_mm_real_reseat=True
    import os
    if os.environ.get('VIC_ENGINEERING_E18_SINGLE_CONTACT')=='1':
        worker._engineering_single_handle_observation=True
    return worker.solve()
