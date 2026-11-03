"""Real supported negative-X phone push, centered face pinch, and stand placement."""
import math
import numpy as np
from .realworld_tool_expert import ToolExecutionError,_axis_rotation

BRANCHES=frozenset(('edge_face_complete_supported',))
SIDE_ROTATION=np.array([[0.,0.,1.],[-1.,0.,0.],[0.,-1.,0.]])


def centered_face_plan(position,rotation,com_local,relative,bounds,support_inset=.020):
    """Choose one Y-centered material point from finite Table and actual COM."""
    from .execution_design_e13_edge import edge_planning_margin
    pos,r,com=map(lambda x:np.asarray(x,float),(position,rotation,com_local));margin=edge_planning_margin(relative)
    if pos.shape!=(3,)or r.shape!=(3,3)or com.shape!=(3,)or not np.isfinite(np.r_[pos,r.ravel(),com]).all()or abs(r[0,0])<1e-6 or abs(r[2,2])<.99:
        raise ToolExecutionError('Reviewed flat source phone and negative-X centered face route required')
    low=[np.asarray(a)[np.asarray(a)[:,2]+pos[2]<bounds['top']+margin]for a in relative]
    exterior=max(margin+float(a[:,0].max())for a in low if len(a))
    edge=float(bounds['lower'][0]);world_com=pos+r@com
    u=-.065*float(np.sign(r[0,0]))
    if not .025<=abs(u)<=.065:raise ToolExecutionError('Centered face point is outside the reviewed interior end band')
    grasp=pos+r@np.array([u,0.,0.]);shift=np.array([edge-exterior-grasp[0],0.,0.]);target=grasp+shift
    supported_inset=float(world_com[0]+shift[0]-edge)
    if supported_inset<.005:raise ToolExecutionError('Phone COM loses original finite Table support')
    if not -.6<shift[0]<=0 or abs(target[0]-(edge-exterior))>1e-8:raise ToolExecutionError('Bounded source phone supported slide required')
    return dict(grasp_local=[u,0.,0.],grasp=grasp,target_grasp=target,translation=shift,axis=np.array([-1.,0.,0.]),
        translated_com=world_com+shift,planning_table_margin_m=margin,lower_finger_exterior_m=exterior,
        actual_com_supported_inset_m=supported_inset,original_table_guard_m=.001)


def finite_table_sweep(bodies,tip,target,rotation,bounds,margin=.001):
    """Full swept convex robot bodies against the actual finite Table solid."""
    from scipy.spatial import ConvexHull
    from scipy.optimize import linprog
    tip,target,r=map(lambda x:np.asarray(x,float),(tip,target,rotation));angle=math.acos(float(np.clip((np.trace(r)-1)/2,-1,1)))
    a=np.array([[1,0,0],[-1,0,0],[0,1,0],[0,-1,0],[0,0,1]],float)
    b=np.array([bounds['upper'][0],-bounds['lower'][0],bounds['upper'][1],-bounds['lower'][1],bounds['top']],float)
    for name,points in bodies.items():
        points=np.asarray(points,float);end=(points-tip)@r.T+target;arc=float(np.linalg.norm(points-tip,axis=1).max())*(1-math.cos(angle/2));cloud=np.r_[points,end]
        if cloud[:,2].min()-arc>=bounds['top']+margin:continue
        hull=ConvexHull(cloud);pad=margin+arc
        result=linprog([0.,0.,0.],A_ub=np.r_[hull.equations[:,:3],a],b_ub=np.r_[-hull.equations[:,3]+pad,b],bounds=[(None,None)]*3,method='highs')
        if result.success:raise ToolExecutionError('Actual centered face '+name+' sweep intersects finite Table')
        if result.status!=2:raise ToolExecutionError('Finite Table swept separation unresolved')
    return dict(actual_finite_table_fullhand_clear=True,table_clearance_m=margin)


def sectional_contact_gap(material,fingers,axis,table_top):
    """First real convex contact along the push ray, clipped to phone height."""
    from scipy.spatial import ConvexHull
    from scipy.optimize import linprog
    material=np.asarray(material,float);axis=np.asarray(axis,float);phone=ConvexHull(material);gaps=[]
    for points in fingers:
        hand=ConvexHull(np.asarray(points,float));a=np.r_[np.c_[hand.equations[:,:3],-hand.equations[:,:3]@axis],np.c_[phone.equations[:,:3],np.zeros(len(phone.equations))],[[0.,0.,1.,0.],[0.,0.,-1.,0.]]]
        b=np.r_[-hand.equations[:,3],-phone.equations[:,3],material[:,2].max(),-max(float(table_top),float(material[:,2].min()))]
        result=linprog([0.,0.,0.,1.],A_ub=a,b_ub=b,bounds=[(None,None)]*3+[(-.05,.10)],method='highs')
        if result.success:gaps.append(float(result.x[3]))
        elif result.status!=2:raise ToolExecutionError('Actual push contact section unresolved')
    if not gaps:raise ToolExecutionError('Actual closed toe push ray misses phone thickness')
    return min(gaps)


class EdgeGeometry:
    def __init__(self,p,side='right',mode='empty'):
        self.p=p;self.side=side;self.mode=mode;self.last_report=None
    def check(self,target=None,rotation=None,closing=False,opening=False):
        from .execution_design_e33_grasp import actual_mesh
        from .execution_design_thin_edge import table_bounds_task
        from .execution_design_branch_geometry import collision_parts_task,swept_pose_clearance
        from .execution_design_e13_camera import actual_closing_bodies,closed_phone_obstacle
        from .execution_design_e13_release import actual_opening_bodies
        p=self.p;tip=p.tip(self.side);target=tip if target is None else np.asarray(target,float);r=np.eye(3)if rotation is None else rotation
        bodies=actual_closing_bodies(p,self.side)if closing else actual_opening_bodies(p,self.side)if opening else{n:actual_mesh(p.a,self.side,n)for n in('panda_hand',*p.a.scene.embodiment.fingers)}
        bounds=table_bounds_task(p.a.scene);finite_table_sweep(bodies,tip,target,r,bounds)
        state,_=p.snapshot();other='left'if self.side=='right'else'right';links=('panda_link0','panda_link1','panda_link2','panda_link3','panda_link4','panda_link5','panda_link6','panda_link7','panda_hand',*p.a.scene.embodiment.fingers)
        props={n:collision_parts_task(p,n)for n in state if n!='phone'};passive={other+'_'+n:[actual_mesh(p.a,other,n)]for n in links};obstacles={**props,**passive}
        # The finite-solid proof above replaces only the infinite tabletop plane.
        swept_pose_clearance(bodies,tip,target,r,obstacles,-100.)
        checked=bodies if self.mode=='empty'and not(closing or opening)else{'panda_hand':bodies['panda_hand']}
        swept_pose_clearance(checked,tip,target,r,{'phone':closed_phone_obstacle(p)},-100.)
        if self.mode=='held':
            p.require_held(dict(actor='phone'),self.side)
            # Native Table contact may support the phone while it hinges up.
            # Robot/Table remains fully checked; payload may only depart UP.
            points=np.concatenate(collision_parts_task(p,'phone'));delta=target-tip
            if p.contact('phone','table'):
                if np.linalg.norm(delta[:2])>1e-7 or delta[2]<-1e-7 or not np.allclose(r,np.eye(3),atol=1e-8):raise ToolExecutionError('Supported edge phone may only lift UP')
            else:finite_table_sweep({'payload':points},tip,target,r,bounds)
            swept_pose_clearance({'payload':points},tip,target,r,obstacles,-100.)
        self.last_report=dict(mode=self.mode,actual_finite_table_guard_m=.001,phone_cooked_pieces=len(collision_parts_task(p,'phone')))
        return self.last_report
    def __call__(self):return self.check()
    def rotate(self,axis,angle):return self.check(rotation=_axis_rotation(axis,angle))
    def move(self,target,tolerance=.0008):self.check(target=target);self.p.move(self.side,target,guard=self,tolerance=tolerance);self.check()


def run_branch(author,context,branch_name):
    from .execution_design_e13_branch import _policy,goal_rotation
    from .execution_design_branch_geometry import install_public_guard,HeldGeometry,collision_parts_task
    from .execution_design_e13_camera import AcquisitionGeometry,closed_phone_obstacle
    from .execution_design_contact_retreat import retreat_phone_contact
    from .execution_design_e08_midfoot import native_local_com
    from .execution_design_e33_grasp import actual_mesh
    from .execution_design_thin_edge import table_bounds_task,material_collision_points_task,actual_finger_points_task,trailing_edge_push_pose
    from .execution_design_e13_edge import trailing_contact_gap,side_entry,side_waypoints,side_path_clearance
    from .execution_design_branch_rotation import turn_to_fixed_goal,finish_accepted_public_rotation
    from .execution_design_e13_release import native_orientation,actual_opening_bodies
    if branch_name not in BRANCHES:raise ValueError('Unknown supported centered-face E13 branch')
    if context.get('branch_params',{}).get('coarse_functional')is True:
        from .execution_design_e13_functional import run
        if context.get('branch_params',{}).get('resume_healthy_held_prefix')is True:
            if context.get('task')!='E13'or context.get('variant')!='A'or not 1059<=author.c.steps<=1061 or int(context.get('rotation_commands_used',0))!=0:raise ValueError('Exact healthy native1059 held-prefix admission required')
            context.update(functional_phase='transport_near_stand',functional_side='left',functional_source_initial=False,functional_prefix_lineage='OriginalsourceinitialA real1005grasp/1012lift/1036 thennative1059; coarse suffix only')
        context.setdefault('functional_phase','push_support');context.setdefault('functional_side','right')
        return run(author,context)
    p=_policy(author,context);start=p.c.steps;side='right';ref=dict(actor='phone');bounds=table_bounds_task(author.scene);p._camera_context=context
    state,_=p.snapshot()
    held_phase=context.get('edge_face_phase')in('face_lift','orient_original_native','stand_place')
    if p.variant!='A':raise ValueError('Reviewed native E13A continuation required')
    if held_phase:p.require_held(dict(actor='phone'),side)
    elif any(any(o['grasp'])for o in state.values())or not p.contact('phone','table'):raise ToolExecutionError('Actual flat supported unheld phone required before edge acquisition')
    context['edge_face_strategy']='actual1786_centered_negativeX_face_v1';context.setdefault('edge_face_source_action',start)
    context.setdefault('edge_face_phase','withdraw_closed_shortwidth')
    context.setdefault('edge_face_empty_rotation_commands',0)
    context.setdefault('edge_face_empty_action_start',start)
    def turn(guard,target):
        def count():context['edge_face_empty_rotation_commands']+=1
        context['edge_face_last_empty_turn']=turn_to_fixed_goal(p,side,target,guard,1.,count)
    if context['edge_face_phase']=='withdraw_closed_shortwidth':
        original_params=dict(context.get('branch_params',{}));context.setdefault('branch_params',{})['phone_contact_retreat_public_axis']='UP'
        retreat_phone_contact(p,context,lambda:closed_phone_obstacle(p),opening_envelope=False,audited_boundary_fingers=('right_finger1','right_finger2'))
        context['branch_params']=original_params;context['edge_face_phase']='pusher_stage'
    if context['edge_face_phase']=='pusher_stage':
        empty=AcquisitionGeometry(p,side);install_public_guard(p,empty);tip=p.tip(side);empty.move(np.array([*tip[:2],.98]));empty.check(opening=True);p.act(side,'RELEASE')
        empty=AcquisitionGeometry(p,side);install_public_guard(p,empty);tip=p.tip(side);empty.move(np.array([-.2,tip[1],.98]));turn(empty,np.array([[0.,1.,0.],[1.,0.,0.],[0.,0.,-1.]]));empty.check(closing=True);p.act(side,'GRASP')
        context['edge_face_phase']='supported_push'
    if context['edge_face_phase']=='supported_push':
        guard=AcquisitionGeometry(p,side,mode='closing');install_public_guard(p,guard);axis=np.array([-1.,0.,0.]);com,mass=native_local_com(p,'phone')
        state,_=p.snapshot();pos=np.asarray(state['phone']['pos']);r=np.asarray(state['phone']['mat']);tip=p.tip(side);rr=np.asarray(author.tcp_rotation_task(side));local=[(a-tip)@rr for a in actual_opening_bodies(p,side).values()]
        rel=[a@SIDE_ROTATION.T for a in local];plan=centered_face_plan(pos,r,com,rel,bounds)
        context.update(edge_face_actual_com_local=com.tolist(),edge_face_actual_mass_kg=mass,edge_face_plan={k:a.tolist()if isinstance(a,np.ndarray)else a for k,a in plan.items()})
        def search_contact():
            for _ in range(30):
                if any(p.contact('phone',f'right_finger{i}')for i in(1,2)):return
                if not p.contact('phone','table'):raise ToolExecutionError('Phone lost Table support before push contact')
                gap=sectional_contact_gap(np.concatenate(collision_parts_task(p,'phone')),[actual_mesh(author,side,n)for n in author.scene.embodiment.fingers],axis,bounds['top'])
                context['edge_face_actual_push_contact_gap_m']=gap
                if gap<-.001:raise ToolExecutionError('Push toe overlaps without native phone contact')
                p.act(side,'BACK',mm=max(p.min_mm,min(.5,(gap+.0002)*1000)))
            raise ToolExecutionError('No native trailing phone push contact')
        def seat():
            material=material_collision_points_task(p,ref);point,receipt=trailing_edge_push_pose(material,actual_finger_points_task(author,side),p.tip(side),axis,bounds['top'],clearance=.0008,center_leading_toe=True)
            context['edge_face_last_push_seat']=receipt;high=max(float(p.tip(side)[2])+.016,float(point[2])+.02)
            guard.move(np.array([*p.tip(side)[:2],high]));guard.move(np.array([*point[:2],high]));guard.move(point,tolerance=.0004)
            search_contact()
        if context.get('branch_params',{}).get('resume_push_contact_search')is True:
            point=np.asarray(context['edge_face_last_push_seat']['public_start_tip'])
            if np.linalg.norm(point-p.tip(side))>.003:raise ToolExecutionError('Exact measured seated push boundary required')
            search_contact()
        elif any(p.contact('phone',f'right_finger{i}')for i in(1,2)):pass
        else:seat()
        history=[]
        while True:
            state,_=p.snapshot();center=np.asarray(state['phone']['pos'])+np.asarray(state['phone']['mat'])@com
            now=p.tip(side);rr=np.asarray(author.tcp_rotation_task(side));relative=[(a-now)@rr@SIDE_ROTATION.T for a in actual_opening_bodies(p,side).values()]
            plan=centered_face_plan(state['phone']['pos'],state['phone']['mat'],com,relative,bounds)
            context['edge_face_plan']={k:a.tolist()if isinstance(a,np.ndarray)else a for k,a in plan.items()}
            remaining=float(center[0]-plan['translated_com'][0])
            if remaining<=.001:break
            if not p.contact('phone','table'):raise ToolExecutionError('Phone lost actual Table support during push')
            if not any(p.contact('phone',f'right_finger{i}')for i in(1,2)):seat()
            low=float(author.finger_geometry(side)['lowest_z_task_m'])
            if low<bounds['top']+.0003:raise ToolExecutionError('Actual phone pusher toes cross Table')
            if low>bounds['top']+.0015:p.act(side,'DOWN',mm=min(.5,(low-bounds['top']-.001)*1000))
            push_mm=float(context.get('branch_params',{}).get('supported_push_step_mm',2.))
            if not 2.<=push_mm<=8.:raise ValueError('Reviewed public supported push step2to8mm required')
            p.act(side,'BACK',mm=min(push_mm,max(p.min_mm,remaining*1000)))
            history.append(float(center[0]));context['edge_face_actual_push_progress']=dict(actual_com_task=center.tolist(),remaining_m=remaining)
            if len(history)>=20 and max(history[-20:])-min(history[-20:])<.0005:raise ToolExecutionError('Actual phone edge push makes no progress')
        guard.move(p.tip(side)+[0,0,.024]);guard.check(opening=True);p.act(side,'RELEASE');context['edge_face_phase']='empty_side_turn'
    if context['edge_face_phase']=='empty_side_turn':
        empty=AcquisitionGeometry(p,side);install_public_guard(p,empty);tip=p.tip(side);empty.move(np.array([*tip[:2],.98]));empty.move(np.array([-.2,p.tip(side)[1],.98]));turn(empty,SIDE_ROTATION)
        context['edge_face_phase']='side_entry'
    if context['edge_face_phase']=='side_entry':
        state,_=p.snapshot();r=np.asarray(state['phone']['mat']);pos=np.asarray(state['phone']['pos']);tip=p.tip(side);rel=[actual_mesh(author,side,n)-tip for n in('panda_hand',*author.scene.embodiment.fingers)];com=np.asarray(context['edge_face_actual_com_local']);plan=context['edge_face_plan']
        # Compute the point from actual final supported pose, not predicted slide.
        point=pos+r@np.array(plan['grasp_local']);material=material_collision_points_task(p,ref);entry,_=side_entry(material,rel,point,[-1.,0.,0.]);waypoints=[tip.copy(),np.array([tip[0],entry[1],tip[2]]),np.array([tip[0],entry[1],.92]),np.array([entry[0],entry[1],.92]),entry.copy(),point.copy()]
        context['edge_face_actual_side_point']=dict(local=plan['grasp_local'],task=point.tolist(),entry=entry.tolist());context['edge_face_actual_side_sweep']=side_path_clearance(material,rel,waypoints,bounds)
        guard=EdgeGeometry(p);install_public_guard(p,guard)
        for target in waypoints[1:]:guard.move(target)
        guard.check(closing=True);guard.mode='closing';context['edge_face_phase']='native_face_grasp';stable=0
        for _ in range(5):
            p.act(side,'GRASP');stable=stable+1 if p.held(ref,side)else 0
            if stable>=3:break
        else:raise ToolExecutionError('Centered phone face pinch lacks three actual bilateral receipts')
        context.update(edge_face_first_actual_hold=p.c.steps,carried_payload=['phone',side],edge_face_phase='face_lift')
    if context['edge_face_phase']=='face_lift':
        guard=EdgeGeometry(p,mode='held');install_public_guard(p,guard);history=[]
        while True:
            guard();points=material_collision_points_task(p,ref);low=float(points[:,2].min());standtop=max(float(a[:,2].max())for a in collision_parts_task(p,p.s['stand']))
            if low>standtop+.015:break
            p.act(side,'UP',mm=12.);history.append(low)
            if len(history)>=13 and max(history[-12:])-history[-13]<.0003:raise ToolExecutionError('Centered phone face lift stalled')
        context['edge_face_phase']='orient_original_native'
    if context['edge_face_phase']=='orient_original_native':
        guard=HeldGeometry(p,'phone',side);install_public_guard(p,guard);tip=p.tip(side);guard.move(np.array([-.22,tip[1],max(float(tip[2]),1.04)]));target=goal_rotation(context['goal'])
        from .author_orientation import _axis_angle
        while True:
            guard();state,_=p.snapshot()
            if native_orientation(state['phone']['mat'],p.s,p.variant)['allowed']:break
            baseline=int(context.get('camera_end_legacy_held_commands_before_empty',36));used=int(context.get('camera_end_additional_held_rotation_commands_used',0))
            if baseline+used>=80:raise ToolExecutionError('Original80 cumulative held-phone rotation bound exhausted')
            axis,angle=_axis_angle(target@np.asarray(state['phone']['mat']).T);k=int(np.argmax(abs(axis)));labels=(('ROLL_LEFT','ROLL_RIGHT'),('PITCH_UP','PITCH_DOWN'),('ROTATE_CCW','ROTATE_CW'))
            context['camera_end_additional_held_rotation_commands_used']=used+1;p.act(side,labels[k][int(axis[k]<0)],degrees=min(10.,max(.5,abs(math.degrees(angle*axis[k])))));finish_accepted_public_rotation(p,side,guard)
        context.update(edge_face_phase='stand_place',camera_end_strategy='actual_supported1337_right_camera_end_v1',camera_end_phase='free_held_above_stand')
        for key in('camera_end_place_phase','camera_end_stand_plane_hand_goal','camera_end_bottom_front_edge_local'):context.pop(key,None)
    if context['edge_face_phase']=='stand_place':
        from .execution_design_e13_camera_place import run_branch as place
        result=place(author,context,'camera_end_place');context['edge_face_phase']='complete'
        return dict(result,branch=branch_name,actions=author.c.steps-start,edge_face_strategy=context['edge_face_strategy'])
    raise ToolExecutionError('Unsupported edge face continuation phase')
