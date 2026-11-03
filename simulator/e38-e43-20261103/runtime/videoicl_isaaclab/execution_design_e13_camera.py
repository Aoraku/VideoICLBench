"""Measured camera-end regrasp after supported E13 placement; public actions only."""
import math
import numpy as np
from .realworld_tool_expert import ToolExecutionError,_axis_rotation
from .execution_design_branch_geometry import collision_parts_task,swept_pose_clearance,install_public_guard

BRANCHES=frozenset(('camera_end_acquire','camera_end_reacquire','camera_end_finish_lift','camera_end_resume_entry','camera_end_finish_entry','camera_end_inset_regrasp'))


def camera_entry(position,rotation,local_x=.085):
    """Camera end above the COM, with the real lower finger clear of Table."""
    position=np.asarray(position,float);r=np.asarray(rotation,float)
    if position.shape!=(3,)or r.shape!=(3,3)or not np.isfinite(np.r_[position,r.ravel()]).all()or not np.allclose(r.T@r,np.eye(3),atol=1e-4)or np.linalg.det(r)<.999:
        raise ValueError('Finite actual phone pose required')
    camera=r[:,0];normal=r[:,2];up=np.array([0.,0.,1.])-normal*normal[2]
    if np.linalg.norm(up)<.5 or abs(camera[2])>.15 or camera[1]>-.7 or normal[0]>-.7:
        raise ToolExecutionError('Reviewed supported landscape camera-right fixture required')
    up/=np.linalg.norm(up);z=-math.cos(math.radians(30))*camera-math.sin(math.radians(30))*up
    z-=normal*float(z@normal);z/=np.linalg.norm(z);y=-normal;x=np.cross(y,z)
    if not np.isfinite(local_x)or not .065<=local_x<=.085:raise ValueError('Reviewed camera-end working-point range required')
    point=position+r@np.array([local_x,.012,0.])+[0.,0.,.016]
    return point,np.column_stack((x,y,z))


def actual_closing_bodies(policy,side):
    from .execution_design_e33_grasp import actual_mesh
    a=policy.a;profile=a.scene.embodiment;robot=a.scene.robots[side]
    if profile.name!='franka'or profile.finger_joints!=['panda_finger_joint1','panda_finger_joint2']:
        raise ToolExecutionError('Reviewed actual Panda finger transmission required')
    ids,_=robot.find_joints(profile.finger_joints,preserve_order=True)
    measured=robot.data.joint_pos[0,ids].detach().cpu().numpy();closed=np.asarray(profile.gripper_values(0.),float)
    rotation=np.asarray(a.tcp_rotation_task(side),float);result={'panda_hand':actual_mesh(a,side,'panda_hand')}
    for i,name in enumerate(profile.fingers):
        points=actual_mesh(a,side,name);delta=rotation[:,1]*(1 if i==0 else-1)*(closed[i]-measured[i])
        result[name]=np.r_[points,points+delta]
    return result


class AcquisitionGeometry:
    """Only intended finger/phone and supported phone/Table contact is allowed."""
    def __init__(self,policy,side,mode='empty',allow_table_departure=False):
        self.p=policy;self.side=side;self.mode=mode;self.last_report=None;self.allow_table_departure=allow_table_departure;self.table_departure_origin=None
    def check(self,target=None,rotation=None,closing=False,opening=False):
        from .execution_design_e33_grasp import actual_mesh
        from .execution_design_thin_edge import table_bounds_task,material_collision_points_task
        p=self.p;side=self.side;other='left'if side=='right'else'right';tip=p.tip(side)
        if opening:
            from .execution_design_e13_release import actual_opening_bodies
            bodies=actual_opening_bodies(p,side)
        else:bodies=actual_closing_bodies(p,side)if closing else{n:actual_mesh(p.a,side,n)for n in('panda_hand',*p.a.scene.embodiment.fingers)}
        state,_=p.snapshot();props={name:collision_parts_task(p,name)for name in state if name!='phone'}
        links=('panda_link0','panda_link1','panda_link2','panda_link3','panda_link4','panda_link5','panda_link6','panda_link7','panda_hand',*p.a.scene.embodiment.fingers)
        passive={other+'_'+n:[actual_mesh(p.a,other,n)]for n in links}
        obstacles={**props,**passive};table=table_bounds_task(p.a.scene)['top'];target=tip if target is None else np.asarray(target,float);rotation=np.eye(3)if rotation is None else rotation
        report=swept_pose_clearance(bodies,tip,target,rotation,obstacles,table)
        phone=closed_phone_obstacle(p)
        # Fingers intentionally close against the phone; the palm never does.
        checked=bodies if self.mode=='empty'and not(closing or opening)else{'panda_hand':bodies['panda_hand']}
        proof=phone_sweep_separation(checked,tip,target,rotation,phone[0],np.asarray(state['phone']['mat']))
        if hasattr(p,'_camera_context'):p._camera_context['actual_phone_guard_last_separation']=proof
        swept_pose_clearance(checked,tip,target,rotation,{'phone':phone},table)
        if self.mode=='empty'and not(p.contact('phone','table')or p.contact('phone',p.s['stand'])):
            raise ToolExecutionError('Unheld phone lost support before camera acquisition')
        if self.mode=='lift':
            p.require_held(dict(actor='phone'),side);points=material_collision_points_task(p,dict(actor='phone'))
            supported=p.contact('phone','table')or p.contact('phone',p.s['stand'])
            low=float(points[:,2].min())
            if self.allow_table_departure and self.table_departure_origin is not None and low<=table+.001:
                delta=target-tip
                if low<self.table_departure_origin-.001 or np.linalg.norm(delta[:2])>1e-7 or delta[2]<-1e-7 or not np.allclose(rotation,np.eye(3),atol=1e-8):
                    raise ToolExecutionError('Actual short-width payload may only leave its source Table contact upwards')
                swept_pose_clearance({'payload':points},tip,target,rotation,passive,min(table,self.table_departure_origin-.001))
                report.update(payload_leaving_measured_table_contact=True,source_table_min_z=self.table_departure_origin,actual_payload_min_z=low)
            elif supported:
                # Original native contact supports the payload while it leaves
                # the table. The three robot bodies retain the same table guard.
                report['payload_has_actual_support_contact']=True
                swept_pose_clearance({'payload':points},tip,target,rotation,passive,table_top=min(table,float(points[:,2].min())-.001))
            else:
                swept_pose_clearance({'payload':points},tip,target,rotation,obstacles,table,allowed_payload=(p.s['stand'],))
        self.last_report=report;return report
    def __call__(self):return self.check()
    def rotate(self,axis,angle):return self.check(rotation=_axis_rotation(axis,angle))
    def move(self,target,tolerance=.001):
        self.check(target=target);self.p.move(self.side,target,guard=lambda:self.check(),tolerance=tolerance);self.check()


def _turn_empty(p,context,guard,target):
    from .execution_design_branch_rotation import turn_to_fixed_goal
    start=context.setdefault('camera_end_empty_rotation_phase_start_action',p.c.steps)
    context.setdefault('camera_end_empty_rotation_commands_used',0)
    context.setdefault('camera_end_empty_rotation_action_budget',500)
    def before_action():
        if p.c.steps-int(start)>=int(context['camera_end_empty_rotation_action_budget']):
            raise ToolExecutionError('Explicit camera empty-hand500 action budget exhausted')
    def count_rotation():
        context['camera_end_empty_rotation_commands_used']=int(context['camera_end_empty_rotation_commands_used'])+1
    context['camera_end_public_rotation_execution']=turn_to_fixed_goal(p,guard.side,target,guard,1.,count_rotation,before_action)


def run_branch(author,context,branch_name):
    from .execution_design_e13_branch import _policy
    if branch_name not in BRANCHES:raise ValueError('Unknown E13 camera-end branch')
    p=_policy(author,context);p._camera_context=context;start=p.c.steps;state,_=p.snapshot()
    if branch_name=='camera_end_finish_lift':
        if (p.variant!='A'or context.get('camera_end_strategy')!='actual_supported1337_right_camera_end_v1'
                or context.get('camera_end_phase')!='lift_above_stand'):
            raise ValueError('Measured incomplete right camera lift context required')
        p.require_held(dict(actor='phone'),'right')
        right=AcquisitionGeometry(p,'right',mode='lift');install_public_guard(p,right)
        context.setdefault('camera_end_first_actual_hold_action',p.c.steps)
        return _finish_lift(p,context,right,branch_name,start)
    if branch_name=='camera_end_inset_regrasp':return _inset_regrasp(p,context,start)
    if p.variant!='A'or any(state['phone']['grasp'])or not(p.contact('phone','table')or p.contact('phone',p.s['stand'])):
        raise ToolExecutionError('Measured unheld supported E13A fixture required')
    if any(any(o['grasp'])for o in state.values()):raise ToolExecutionError('Both hands must actually be empty before camera regrasp')
    if branch_name=='camera_end_reacquire':return _reacquire(p,context,start)
    if branch_name=='camera_end_finish_entry':return _finish_entry(p,context,start)
    if branch_name=='camera_end_resume_entry':return _resume_entry(p,context,start)
    point,target=camera_entry(state['phone']['pos'],state['phone']['mat'])
    context.update(camera_end_strategy='actual_supported1337_right_camera_end_v1',camera_end_phase='empty_left_park',
        camera_end_source_action=start,camera_end_entry_tcp=point.tolist(),camera_end_entry_rotation=target.tolist(),
        camera_end_source_phone_pose=dict(position=list(map(float,state['phone']['pos'])),rotation=np.asarray(state['phone']['mat']).tolist()))
    left=AcquisitionGeometry(p,'left');install_public_guard(p,left)
    tip=p.tip('left');left.move(np.array([tip[0],.10,tip[2]]))
    right=AcquisitionGeometry(p,'right');install_public_guard(p,right);tip=p.tip('right');high=max(float(tip[2]),1.04)
    context['camera_end_phase']='right_unpark_x';right.move(np.array([-.25,tip[1],high]))
    context['camera_end_phase']='right_unpark_y';right.move(np.array([-.25,-.22,high]))
    context['camera_end_phase']='right_down_safe_stage';right.move(np.array([-.25,-.22,1.04]))
    context['camera_end_phase']='empty_right_turn';_turn_empty(p,context,right,target)
    context['camera_end_phase']='camera_x';right.move(np.array([point[0],-.22,1.04]))
    context['camera_end_phase']='camera_y';right.move(np.array([*point[:2],1.04]))
    context['camera_end_phase']='camera_descent';right.move(point,tolerance=.0008)
    return _grasp_lift(p,context,right,branch_name,start)


def _grasp_lift(p,context,right,branch_name,start):
    from .execution_design_thin_edge import material_collision_points_task
    right.check(closing=True);right.mode='closing';context['camera_end_phase']='native_grasp'
    for _ in range(5):
        p.act('right','GRASP')
        if p.held(dict(actor='phone'),'right'):break
    else:raise ToolExecutionError('Camera-end pinch lacks actual bilateral hold')
    state,_=p.snapshot();context['camera_end_first_actual_hold_action']=p.c.steps
    context['camera_end_actual_grasp_local']=(np.asarray(state['phone']['mat']).T@(p.tip('right')-np.asarray(state['phone']['pos']))).tolist()
    context['carried_payload']=['phone','right'];right.mode='lift';context['camera_end_phase']='lift_above_stand'
    return _finish_lift(p,context,right,branch_name,start)


def _finish_lift(p,context,right,branch_name,start):
    from .execution_design_thin_edge import material_collision_points_task
    context['carried_payload']=['phone','right']
    for _ in range(40):
        right();points=material_collision_points_task(p,dict(actor='phone'));stand=collision_parts_task(p,p.s['stand'])
        top=max(float(part[:,2].max())for part in stand)
        if points[:,2].min()>top+.015:break
        p.act('right','UP',mm=12.)
    else:raise ToolExecutionError('Camera-end actual payload did not clear the stand')
    right();state,_=p.snapshot();points=material_collision_points_task(p,dict(actor='phone'))
    if p.contact('phone','table')or p.contact('phone',p.s['stand']):raise ToolExecutionError('Camera-end phone remains supported after the measured lift')
    context.update(camera_end_phase='free_held_above_stand',camera_end_actual_grasp_local=(np.asarray(state['phone']['mat']).T@(p.tip('right')-np.asarray(state['phone']['pos']))).tolist())
    from .execution_design_e13_release import native_orientation
    return dict(branch=branch_name,task='E13',local_completed=True,actions=p.c.steps-start,
        actual_bilateral_hold=True,actual_held_side='right',first_actual_hold_action=context['camera_end_first_actual_hold_action'],
        actual_table_contact=False,actual_stand_contact=False,actual_payload_min_z=float(points[:,2].min()),
        native_orientation=native_orientation(state['phone']['mat'],p.s,p.variant),
        original_cumulative_rotation_commands=int(context.get('rotation_commands_used',0)),
        whole_task_score=None,original_task_success_asserted=False,placement_not_yet_executed=True)


def _reacquire(p,context,start):
    if context.get('camera_end_strategy')!='actual_supported1337_right_camera_end_v1':
        raise ValueError('Previous native camera-end entry context required')
    if context.get('camera_end_phase')not in('camera_descent','native_grasp'):
        raise ValueError('Reacquire may only resume the measured camera descent/grasp boundary')
    state,_=p.snapshot();point,target=camera_entry(state['phone']['pos'],state['phone']['mat'],local_x=.075)
    if np.linalg.norm(point-p.tip('right'))>.060:
        raise ToolExecutionError('Camera regrasp is not near the measured native entry')
    right=AcquisitionGeometry(p,'right',mode='closing');install_public_guard(p,right)
    context['camera_end_phase']='reacquire_open';right.check(opening=True);p.act('right','RELEASE')
    state,_=p.snapshot()
    if any(state['phone']['grasp']):raise ToolExecutionError('Camera retry did not physically open the hand')
    right=AcquisitionGeometry(p,'right');install_public_guard(p,right)
    context['camera_end_phase']='reacquire_raise';right.move(p.tip('right')+[0,0,.024])
    state,_=p.snapshot();point,target=camera_entry(state['phone']['pos'],state['phone']['mat'],local_x=.075)
    context.update(camera_end_phase='reacquire_turn',camera_end_retry_source_action=start,
        camera_end_retry_local_x=.075,camera_end_entry_tcp=point.tolist(),camera_end_entry_rotation=target.tolist())
    _turn_empty(p,context,right,target)
    context['camera_end_phase']='reacquire_xy'
    for axis in(0,1):
        goal=p.tip('right').copy();goal[axis]=point[axis];right.move(goal)
    context['camera_end_phase']='camera_descent';right.move(point,tolerance=.0008)
    return _grasp_lift(p,context,right,'camera_end_reacquire',start)


def _resume_entry(p,context,start):
    if (context.get('camera_end_strategy')!='actual_supported1337_right_camera_end_v1'
            or context.get('camera_end_phase')!='empty_right_turn'):
        raise ValueError('Measured incomplete empty-right wrist entry required')
    params=context.get('branch_params',{})
    if 'camera_end_empty_rotation_commands_used'not in context:
        if (params.get('legacy_empty_rotation_commands')!=44
                or params.get('legacy_empty_rotation_start_action')!=1432
                or int(context.get('rotation_commands_used',-1))!=80):
            raise ValueError('Explicit native1476 legacy44 empty-command lineage required')
        context.update(camera_end_empty_rotation_commands_used=44,camera_end_empty_rotation_phase_start_action=1432,
            camera_end_legacy_rotation_counter_unchanged=80,camera_end_legacy_held_commands_before_empty=36)
    right=AcquisitionGeometry(p,'right');install_public_guard(p,right)
    target=np.asarray(context['camera_end_entry_rotation'],float)
    _turn_empty(p,context,right,target)
    state,_=p.snapshot();point,_=camera_entry(state['phone']['pos'],state['phone']['mat'],local_x=.075)
    context.setdefault('camera_end_original_entry_tcp',context['camera_end_entry_tcp'])
    context.update(camera_end_entry_tcp=point.tolist(),camera_end_deeper_entry_local_x=.075,
        camera_end_deeper_entry_reason='10mm source camera-edge overlap instead of submillimeter toe contact')
    high=float(p.tip('right')[2]);context['camera_end_phase']='camera_x'
    right.move(np.array([point[0],p.tip('right')[1],high]))
    context['camera_end_phase']='camera_y';right.move(np.array([*point[:2],high]))
    context['camera_end_phase']='camera_descent';right.move(point,tolerance=.0008)
    return _grasp_lift(p,context,right,'camera_end_resume_entry',start)


def closed_phone_obstacle(p):
    """A convex superset of every actual cooked phone component, not a subset."""
    import json,hashlib
    objects={o['id']:o for o in p.spec['objects']}
    if objects['phone']['source_asset']['sha256']!='877328ef32ace63e63f7ed3c60de990f5f3532a17208e1e74143bfb794c7f6bb':
        raise ToolExecutionError('Reviewed original closed phone source required')
    parts=collision_parts_task(p,'phone');cloud=np.concatenate(parts)
    if np.linalg.matrix_rank(cloud-cloud.mean(0),tol=1e-9)<3:
        raise ToolExecutionError('Complete native phone envelope lacks physical thickness')
    if not hasattr(p.a,'_camera_phone_convex_evidence'):
        pos,r=p.frame(dict(actor='phone'));local=[((part-pos)@r).tolist()for part in parts]
        data=dict(source='actual_native_cooked_convex_vertices_all_phone_components',source_sha256=objects['phone']['source_asset']['sha256'],
            actual_piece_count=len(parts),actual_piece_vertices_phone_local=local,
            guard_representation='convex hull of every actual cooked vertex; conservative superset of original component union',
            original_piece_removed=False,source_geometry_modified=False,expanded_margin_m=.001,robot_table_clearance_m=.0003)
        raw=json.dumps(data).encode();path=p.a.out/'camera-phone-cooked-envelope.private.json';path.write_bytes(raw)
        p.a._camera_phone_convex_evidence=dict(path=str(path),sha256=hashlib.sha256(raw).hexdigest(),actual_piece_count=len(parts))
    if hasattr(p,'_camera_context'):p._camera_context['actual_phone_cooked_envelope_evidence']=p.a._camera_phone_convex_evidence
    return [cloud]


def phone_sweep_separation(bodies,tip,target,rotation,phone,phone_rotation):
    """Independent actual support projections for the whole swept body cloud."""
    tip,target,rotation,phone=map(lambda a:np.asarray(a,float),(tip,target,rotation,phone))
    angle=math.acos(float(np.clip((np.trace(rotation)-1)/2,-1,1)));axes=np.r_[np.eye(3),np.asarray(phone_rotation).T];rows={}
    for name,points in bodies.items():
        points=np.asarray(points,float);cloud=np.r_[points,(points-tip)@rotation.T+target]
        arc=float(np.linalg.norm(points-tip,axis=1).max())*(1-math.cos(angle/2));best=None
        for axis in axes:
            a=cloud@axis;b=phone@axis;gap=max(float(a.min()-b.max()),float(b.min()-a.max()))
            if best is None or gap>best['raw_projection_gap_m']:
                best=dict(axis_task=axis.tolist(),robot_projection_minmax_m=[float(a.min()),float(a.max())],phone_projection_minmax_m=[float(b.min()),float(b.max())],raw_projection_gap_m=gap,arc_bound_m=arc,expanded_separation_m=gap-2*(.001+arc))
        rows[name]=best
    return dict(method='independent whole-actual-cloud support projections; hull LP additionally guards all separating axes',bodies=rows)


def _finish_entry(p,context,start):
    if (context.get('camera_end_strategy')!='actual_supported1337_right_camera_end_v1'
            or context.get('camera_end_phase')!='camera_descent'):
        raise ValueError('Measured completed camera XY/rotation boundary required')
    right=AcquisitionGeometry(p,'right');install_public_guard(p,right)
    target=np.asarray(context['camera_end_entry_tcp'],float)
    if np.max(abs(target[:2]-p.tip('right')[:2]))>.003:
        raise ToolExecutionError('Measured camera entry is not at the saved native XY')
    right.move(target,tolerance=.0008)
    return _grasp_lift(p,context,right,'camera_end_finish_entry',start)


def _inset_regrasp(p,context,start):
    from .execution_design_e13_release import landing_conditions
    from .execution_design_thin_edge import table_bounds_task
    from .execution_design_e33_grasp import actual_mesh
    if (p.variant!='A'or context.get('camera_end_strategy')!='actual_supported1337_right_camera_end_v1'
            or context.get('camera_end_phase')not in('lift_above_stand','inset_raise')):
        raise ValueError('Measured native1558 slip or native1559 released-contact boundary required')
    if not(p.contact('phone','table')or p.contact('phone',p.s['stand'])):
        raise ToolExecutionError('Camera slip retry requires actual phone support')
    if context.get('camera_end_phase')=='lift_above_stand':
        old=context.get('camera_end_first_actual_hold_action')
        if old is not None:context.setdefault('camera_end_previous_actual_hold_actions',[]).append(old)
        right=AcquisitionGeometry(p,'right',mode='closing');install_public_guard(p,right)
        context['camera_end_phase']='inset_open';right.check(opening=True);p.act('right','RELEASE')
        context['camera_end_phase']='inset_raise'
    from .execution_design_contact_retreat import retreat_phone_contact
    retreat_phone_contact(p,context,lambda:closed_phone_obstacle(p))
    right=AcquisitionGeometry(p,'right');install_public_guard(p,right)
    right.move(p.tip('right')+[0,0,.024])
    landing=landing_conditions(p)
    if landing['local_geometry_contact_allowed']and landing['native_current_conditions_passed']:
        context['camera_end_phase']='complete_after_supported_slip'
        return dict(branch='camera_end_inset_regrasp',local_completed=True,actions=p.c.steps-start,native_landing_conditions=landing,native_already_landed=True,whole_task_score=None)
    state,_=p.snapshot();r=np.asarray(state['phone']['mat']);normal=r[:,2];current=np.asarray(p.a.tcp_rotation_task('right'))
    z=current[:,2]-normal*float(normal@current[:,2]);z/=np.linalg.norm(z);y=-normal;target=np.column_stack((np.cross(y,z),y,z))
    context.update(camera_end_phase='inset_turn',camera_end_inset_source_action=start,camera_end_inset_material_local=[.065,0.,0.],
        camera_end_inset_absolute_hand_goal=target.tolist(),camera_end_inset_reason='NativeworkingX migrated75.06->81.20->83.57mm at edge; move to65mm and align actual face normal')
    _turn_empty(p,context,right,target)
    state,_=p.snapshot();position=np.asarray(state['phone']['pos']);r=np.asarray(state['phone']['mat']);point=position+r@np.array([.065,0,0.])
    tip=p.tip('right');bodies={n:actual_mesh(p.a,'right',n)for n in('panda_hand',*p.a.scene.embodiment.fingers)}
    low=min(float((a+point-tip)[:,2].min())for a in bodies.values());radius=max(float(np.linalg.norm(a-tip,axis=1).max())for a in bodies.values())
    extra=max(0.,table_bounds_task(p.a.scene)['top']+.0003+radius*math.sin(math.radians(1.))+.0005-low)
    point[2]+=extra;context.update(camera_end_inset_actual_tcp=point.tolist(),camera_end_inset_table_geometry_extra_z_m=extra)
    high=max(float(p.tip('right')[2]),float(point[2])+.030)
    context['camera_end_phase']='inset_xy';right.move(np.array([*p.tip('right')[:2],high]));right.move(np.array([point[0],p.tip('right')[1],high]));right.move(np.array([*point[:2],high]))
    context['camera_end_phase']='native_grasp';right.move(point,tolerance=.0008)
    return _grasp_lift(p,context,right,'camera_end_inset_regrasp',start)
