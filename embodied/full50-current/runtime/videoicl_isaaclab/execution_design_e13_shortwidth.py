"""Original phone short-width camera-end grip from a measured flat Table pose."""
import numpy as np
from .realworld_tool_expert import ToolExecutionError

BRANCHES=frozenset(('shortwidth_complete_supported',))


def downward_shortwidth_rotation(phone_rotation):
    r=np.asarray(phone_rotation,float)
    if r.shape!=(3,3)or not np.isfinite(r).all()or not np.allclose(r.T@r,np.eye(3),atol=1e-5)or r[2,2]<.995:
        raise ValueError('Actual flat original phone frame required')
    y=r[:,1].copy();y[2]=0.;y/=np.linalg.norm(y);z=np.array([0.,0.,-1.])
    return np.column_stack((np.cross(y,z),y,z))


def camera_band_tcp(position,rotation,tip,bodies,table_top):
    point=np.asarray(position,float)+np.asarray(rotation,float)@np.array([.065,0.,0.])
    low=min(float((np.asarray(a)-tip)[:,2].min())for a in bodies.values())
    # Actual source body height, plus the existing public translation tolerance
    # reserve. This still places the real toe inside the ~10mm side band.
    point[2]=float(table_top)+.0015-low
    return point


def descend_centered_shortwidth(p,context,right):
    """Keep real jaw centering while descending into the tight75mm side band."""
    from .execution_design_e13_camera import closed_phone_obstacle
    from .execution_design_e33_grasp import actual_mesh
    from .execution_design_thin_edge import table_bounds_task
    table=table_bounds_task(p.a.scene)['top'];side='right'
    while True:
        right();state,_=p.snapshot();phone=state['phone'];r=np.asarray(phone['mat']);pos=np.asarray(phone['pos']);cloud=(closed_phone_obstacle(p)[0]-pos)@r
        center_y=float((cloud[:,1].min()+cloud[:,1].max())/2)
        if abs(center_y)>.002:raise ToolExecutionError('Original phone short-width center differs from reviewed source')
        point=pos+r@np.array([.065,center_y,0.]);tip=p.tip(side);error=point[:2]-tip[:2]
        context['shortwidth_actual_centered_material_local']=[.065,center_y,0.]
        if max(abs(error))>.0003:
            axis=int(np.argmax(abs(error)));token=(('FWD','BACK'),('LEFT','RIGHT'))[axis][int(error[axis]<0)]
            p.act(side,token,mm=min(4.,max(p.min_mm,abs(error[axis])*1000)));continue
        toe=min(float(actual_mesh(p.a,side,n)[:,2].min())for n in('panda_hand',*p.a.scene.embodiment.fingers))
        context['shortwidth_actual_final_toe_z']=toe
        remaining=toe-(table+.0015)
        if remaining<=.0008:return
        p.act(side,'DOWN',mm=min(4.,max(p.min_mm,remaining*1000)))


def establish_shortwidth_hold(p,context,right,branch_name,start,prior_receipts=0):
    """Finish the original grip closure; one impact contact is not completion."""
    from .execution_design_e13_camera import _finish_lift
    stable=int(prior_receipts);right.check(closing=True);right.mode='closing'
    context['camera_end_phase']='native_grasp';context['shortwidth_phase']='gripper_closure'
    for _ in range(5):
        p.act('right','GRASP');stable=stable+1 if p.held(dict(actor='phone'),'right')else 0
        context['shortwidth_consecutive_native_grasp_receipts']=stable
        if stable==1:context['shortwidth_closure_first_streak_action']=p.c.steps
        if stable>=3:break
    else:raise ToolExecutionError('Short-width closure lacks original three consecutive native bilateral receipts')
    state,_=p.snapshot()
    if not prior_receipts:
        old=context.get('camera_end_first_actual_hold_action')
        if old is not None:context.setdefault('camera_end_previous_actual_hold_actions',[]).append(old)
        context['camera_end_first_actual_hold_action']=context.get('shortwidth_closure_first_streak_action',p.c.steps)
    else:context.setdefault('camera_end_first_actual_hold_action',context.get('shortwidth_closure_first_streak_action',p.c.steps))
    context.update(camera_end_actual_grasp_local=(np.asarray(state['phone']['mat']).T@(p.tip('right')-np.asarray(state['phone']['pos']))).tolist(),
        carried_payload=['phone','right'],camera_end_phase='lift_above_stand',shortwidth_phase='lift')
    right.mode='lift';return _finish_lift(p,context,right,branch_name,start)


def run_branch(author,context,branch_name):
    from .execution_design_e13_branch import _policy
    from .execution_design_e13_camera import AcquisitionGeometry,_turn_empty,_grasp_lift,_finish_lift
    from .execution_design_e13_camera_place import run_branch as place
    from .execution_design_branch_geometry import install_public_guard
    from .execution_design_branch_rotation import finish_accepted_public_rotation
    from .execution_design_thin_edge import table_bounds_task,material_collision_points_task
    from .execution_design_e33_grasp import actual_mesh
    if branch_name not in BRANCHES:raise ValueError('Unknown flat phone short-width branch')
    p=_policy(author,context);p._camera_context=context;start=p.c.steps;side='right';state,_=p.snapshot()
    if p.variant!='A'or context.get('camera_end_strategy')!='actual_supported1337_right_camera_end_v1':
        raise ValueError('Measured E13A right short-width candidate required')
    phase=context.get('shortwidth_phase')
    if phase=='stand_place':
        result=place(author,context,'camera_end_place');return dict(result,branch=branch_name,actions=p.c.steps-start)
    if phase=='lift':
        continuation=context.get('branch_params',{}).get('complete_native_gripper_closure')is True
        right=AcquisitionGeometry(p,side,mode='closing'if continuation else'lift',allow_table_departure=True)
        right.table_departure_origin=float(context['shortwidth_source_table_min_z']);install_public_guard(p,right)
        if continuation:establish_shortwidth_hold(p,context,right,branch_name,start,prior_receipts=1)
        else:
            p.require_held(dict(actor='phone'),side);_finish_lift(p,context,right,branch_name,start)
    else:
        if any(state['phone']['grasp'])or not p.contact('phone','table'):raise ToolExecutionError('Actual unheld Table-supported phone required for short-width acquisition')
        downward_shortwidth_rotation(state['phone']['mat']);cloud=material_collision_points_task(p,dict(actor='phone'))
        if not .003<float(np.ptp(cloud[:,2]))<.012:raise ToolExecutionError('Original phone is not in the reviewed flat thin side band')
        right=AcquisitionGeometry(p,side);install_public_guard(p,right)
        if phase is None:
            context.update(shortwidth_phase='reanchor',shortwidth_strategy='native1604_camera65_center_shortwidth_v1',shortwidth_source_action=start,
                shortwidth_hand_goal=downward_shortwidth_rotation(state['phone']['mat']).tolist(),shortwidth_old_blocked_target_reason='native no_safe_ik_step at old vertical-face jaw goal; use new measured flat short-width strategy')
            context['camera_end_empty_rotation_commands_used']=int(context.get('camera_end_empty_rotation_commands_used',0))+1
            p.act(side,'PITCH_DOWN',degrees=2.)
            finish_accepted_public_rotation(p,side,right)
            context['shortwidth_phase']='empty_stage';phase='empty_stage'
        if phase in('reanchor','empty_stage'):
            if phase=='reanchor':finish_accepted_public_rotation(p,side,right)
            right.move(np.array([-.25,p.tip(side)[1],.98]));right.move(np.array([-.25,-.3,.98]));context['shortwidth_phase']='empty_turn';phase='empty_turn'
        if phase=='empty_turn':
            _turn_empty(p,context,right,np.asarray(context['shortwidth_hand_goal']));context['shortwidth_phase']='approach';phase='approach'
        if phase not in('approach','descent'):raise ValueError('Known actual short-width acquisition phase required')
        if phase=='approach':
            state,_=p.snapshot();tip=p.tip(side);bodies={n:actual_mesh(p.a,side,n)for n in('panda_hand',*p.a.scene.embodiment.fingers)}
            point=camera_band_tcp(state['phone']['pos'],state['phone']['mat'],tip,bodies,table_bounds_task(p.a.scene)['top'])
            context['shortwidth_actual_entry_tcp']=point.tolist();high=float(tip[2]);right.move(np.array([point[0],tip[1],high]));right.move(np.array([*point[:2],high]));context['shortwidth_phase']='descent'
        descend_centered_shortwidth(p,context,right)
        cloud=material_collision_points_task(p,dict(actor='phone'));context['shortwidth_source_table_min_z']=float(cloud[:,2].min());right.allow_table_departure=True;right.table_departure_origin=context['shortwidth_source_table_min_z']
        context['shortwidth_phase']='lift';context['camera_end_grasp_strategy']='flat_table_camera_end_shortwidth65_v1'
        establish_shortwidth_hold(p,context,right,branch_name,start)
    context['shortwidth_phase']='stand_place'
    result=place(author,context,'camera_end_place');context['shortwidth_phase']='complete'
    return dict(result,branch=branch_name,actions=p.c.steps-start,shortwidth_strategy=context['shortwidth_strategy'],shortwidth_first_actual_hold_action=context['camera_end_first_actual_hold_action'])
