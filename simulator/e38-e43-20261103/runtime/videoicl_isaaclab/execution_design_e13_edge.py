"""E13 engineering-only real supported edge push and vertical-jaw pickup."""
import json
import math
import numpy as np
from .realworld_tool_expert import ToolAuthor,ToolExecutionError


def edge_planning_margin(relative):
    """Reserve the existing 1mm guard after public push/rotation tolerances."""
    if len(relative)!=3:raise ValueError('Actual full-hand radius required')
    radius=max(float(np.linalg.norm(np.asarray(x,float),axis=1).max())for x in relative)
    if not np.isfinite(radius)or not .02<radius<.3:raise ValueError('Unreviewed actual hand radius')
    return .001+.001+2*radius*math.sin(math.radians(.5))


def plan_edge(material,center,relative,bounds,axis,inset=.006,margin=.001):
    material=np.asarray(material,float);center=np.asarray(center,float);axis=np.asarray(axis,float)
    if material.ndim!=2 or material.shape[1]!=3 or not np.isfinite(np.r_[material.ravel(),center,axis]).all():raise ValueError('Finite actual phone mesh required')
    if not .003<np.ptp(material[:,2])<.012:raise ValueError('Reviewed upright thin phone required')
    k=int(np.argmax(abs(axis[:2])));sign=float(axis[k])
    if abs(sign)!=1 or np.count_nonzero(axis)!=1:raise ValueError('Axis-aligned real table edge required')
    grasp=center.copy();grasp[k]=(float(np.max(material@axis))-inset)*sign;grasp[2]=float((material[:,2].min()+material[:,2].max())/2)
    low=[np.asarray(v)[np.asarray(v)[:,2]+grasp[2]<bounds['top']+margin]for v in relative]
    if not any(len(v)for v in low):raise ValueError('A real lower finger is required')
    exterior=max(margin-float(np.min(v@axis))for v in low if len(v));target=grasp.copy();target[k]=bounds['upper'if sign>0 else'lower'][k]+sign*exterior
    delta=target-grasp;newcenter=center+delta
    if any(newcenter[i]<bounds['lower'][i]+.005 or newcenter[i]>bounds['upper'][i]-.005 for i in(0,1)):raise ValueError('Phone center loses real tabletop support')
    if not 0<=float(delta@axis)<=.6:raise ValueError('Phone edge route outside reviewed bound')
    return dict(grasp=grasp,target_grasp=target,translation=delta,translated_center=newcenter,axis=axis,component=k,sign=sign)


def trailing_contact_gap(material, finger_bodies, axis, table_top):
    """Actual convex finger sections clipped to the phone thickness band."""
    from scipy.spatial import ConvexHull
    from scipy.optimize import linprog
    material=np.asarray(material,float);axis=np.asarray(axis,float)
    floor=max(float(table_top),float(material[:,2].min()));top=float(material[:,2].max())
    trailing=float(np.min(material@axis));leading=[]
    for body in finger_bodies:
        hull=ConvexHull(np.asarray(body,float))
        solve=linprog(-axis,A_ub=np.r_[hull.equations[:,:3],[[0,0,1],[0,0,-1]]],
            b_ub=np.r_[-hull.equations[:,3],top,-floor],bounds=[(None,None)]*3,method='highs')
        if solve.success:leading.append(float(solve.x@axis))
        elif solve.status!=2:raise ToolExecutionError('Phone toe section solver failed')
    if not leading:raise ToolExecutionError('Actual toes do not overlap phone height')
    return trailing-max(leading)


def side_entry(material,relative,grasp,axis,margin=.003):
    """Minimum exterior open-hand entry from all three actual collision meshes."""
    material=np.asarray(material,float);grasp=np.asarray(grasp,float);axis=np.asarray(axis,float)
    if len(relative)!=3 or not np.isclose(np.linalg.norm(axis),1.):raise ValueError('Actual full hand and unit edge axis required')
    arrays=[np.asarray(x,float)for x in relative]
    if not all(x.ndim==2 and x.shape[1]==3 and len(x)>=4 and np.isfinite(x).all()for x in arrays):raise ValueError('Finite full hand meshes required')
    if not np.isfinite(np.r_[material.ravel(),grasp,axis,margin]).all()or margin<.001:raise ValueError('Finite positive side-entry margin required')
    projection=float(np.max(material@axis))
    nearest=min(float(np.min(x@axis))for x in arrays)
    offset=max(0.,projection+margin-nearest-float(grasp@axis))
    if offset>.15:raise ValueError('Measured open-hand side entry exceeds reviewed workspace')
    return grasp+axis*offset,dict(exterior_offset_m=offset,phone_outer_projection_m=projection,
        hand_nearest_relative_projection_m=nearest,entry_clearance_m=margin)


def side_path_clearance(material,relative,waypoints,bounds,margin=.0003):
    """Convex swept volumes cover every point on each translation segment."""
    from scipy.spatial import ConvexHull
    from scipy.optimize import linprog
    material=np.asarray(material,float);waypoints=np.asarray(waypoints,float)
    if len(relative)!=3 or len(waypoints)<2 or not np.isfinite(np.r_[material.ravel(),waypoints.ravel()]).all():raise ValueError('Complete finite side-entry path required')
    phone=ConvexHull(material);table_a=np.array([[1,0,0],[-1,0,0],[0,1,0],[0,-1,0],[0,0,1]],float)
    table_b=np.array([bounds['upper'][0],-bounds['lower'][0],bounds['upper'][1],-bounds['lower'][1],bounds['top']],float)
    for start,end in zip(waypoints[:-1],waypoints[1:]):
        for body in relative:
            body=np.asarray(body,float);hull=ConvexHull(np.r_[body+start,body+end])
            for label,a,b in [('phone',phone.equations[:,:3],-phone.equations[:,3]),('table',table_a,table_b)]:
                result=linprog([0,0,0],A_ub=np.r_[hull.equations[:,:3],a],
                    b_ub=np.r_[-hull.equations[:,3]+margin,b+margin],bounds=[(None,None)]*3,method='highs')
                if result.success:raise ToolExecutionError(f'Actual phone side-entry sweep intersects {label}')
                if result.status!=2:raise ToolExecutionError('Phone swept separation solver failed')
    return dict(segments=len(waypoints)-1,robot_bodies=3,expanded_hull_margin_m=margin,
        entire_translation_sweeps_clear=True,waypoints=waypoints.tolist())


def choose_edge_candidate(candidates):
    """Equivalent vertical jaws use the reviewed continuous negative-X route."""
    reviewed=[row for row in candidates if np.allclose(row[1]['axis'],[-1.,0.,0.])
              and np.allclose(row[2],[[0.,0.,1.],[-1.,0.,0.],[0.,-1.,0.]])]
    if not reviewed:raise ToolExecutionError('No reviewed continuous phone side-pinch route')
    return min(reviewed,key=lambda row:row[0])


def side_waypoints(tip,entry,point):
    """Lower over cleared table before extending to the exterior entry."""
    tip=np.asarray(tip,float);entry=np.asarray(entry,float);point=np.asarray(point,float)
    inside=tip.copy();inside[2]=.92
    stage=entry.copy();stage[2]=.92
    across=inside.copy();across[0]=stage[0]
    return [tip.copy(),inside,across,stage,entry.copy(),point.copy()]


def orient_phone(policy,side,target,guard):
    """Keep the actual empty-hand/table guard around every public turn."""
    from .author_orientation import _axis_angle
    labels=(('ROLL_LEFT','ROLL_RIGHT'),('PITCH_UP','PITCH_DOWN'),('ROTATE_CCW','ROTATE_CW'))
    history=[]
    for _ in range(180):
        guard();current=np.asarray(policy.a.tcp_rotation_task(side));axis,angle=_axis_angle(target@current.T)
        if angle<math.radians(1.):return
        i=int(np.argmax(abs(axis)))
        policy.act(side,labels[i][int(axis[i]<0)],degrees=min(7.,max(.5,abs(math.degrees(angle*axis[i])))))
        guard();history.append(angle)
        if len(history)>=24 and min(history[-24:-16])-min(history[-8:])<math.radians(.2):raise ToolExecutionError('Measured phone wrist orientation stalled')
    raise ToolExecutionError('Measured phone wrist orientation did not converge')


class PhoneMoves(ToolAuthor):
    """Only adapts existing public moves; does not admit E13 to tool task dispatch."""
    def __init__(self,a):
        self.a=a;self.c=a.c;self.spec=a.scene.spec;self.s=self.spec['semantic'];self.task='E13';self.variant=self.spec['variant'];self.start=0;self.limit=3000
        cfg=a.scene.embodiment.config['control'];self.min_mm=float(cfg['step_mm'][0]);self.max_mm=min(12.,float(cfg['step_mm'][1]));self.min_deg=float(cfg['rotation_deg'][0]);self.max_deg=min(10.,float(cfg['rotation_deg'][1]));self.clearance=.98;self.operations=[]


def acquire_edge(a,side,name):
    if (name!='phone' or a.scene.spec.get('id')!='E13' or a.scene.spec.get('execution_design',{}).get('revision')!='embodied50-execution-v3-20261102'
            or not a.control_report.get('engineering_reference_only') or a.scene.embodiment.name!='franka'):
        raise ValueError('E13 v3 Panda engineering-only edge acquisition required')
    from .execution_design_thin_edge import table_bounds_task,material_collision_points_task,actual_finger_points_task,trailing_edge_push_pose
    from .execution_design_e33_grasp import actual_mesh
    from .execution_design_drawer_ik_probe import inspect
    p=PhoneMoves(a);ref=dict(actor=name,local=[0,0,0]);bounds=table_bounds_task(a.scene);up=np.array([0.,0.,1.])
    path=a.out/'e13-edge-public.private.jsonl'
    def log(phase,**data):
        with path.open('a')as stream:stream.write(json.dumps(dict(phase=phase,step=p.c.steps,**data))+'\n')
    p.act(side,'RELEASE');p.move(side,[*p.tip(side)[:2],p.clearance])
    rotation=a.tcp_rotation_task(side);tcp=p.tip(side);meshes=[actual_mesh(a,side,n)for n in ('panda_hand',*a.scene.embodiment.fingers)]
    local=[(m-tcp)@rotation for m in meshes];material=material_collision_points_task(p,ref);pos,r=p.frame(ref);candidates=[]
    for axis in ([1.,0,0],[-1.,0,0],[0,1.,0],[0,-1.,0]):
        axis=np.asarray(axis,float)
        for jaw_sign in(1.,-1.):
            jaw=up*jaw_sign;target_r=np.column_stack((-np.cross(jaw,axis),jaw,-axis));transformed=[m@target_r.T for m in local]
            try:
                margin=edge_planning_margin(transformed)
                plan=plan_edge(material,pos,transformed,bounds,axis,margin=margin)
                plan['planning_table_margin_m']=margin
                plan['public_push_tolerance_m']=.001
                plan['public_orientation_tolerance_degrees']=1.
            except ValueError as exc:log('geometry-rejected',axis=axis.tolist(),jaw_sign=jaw_sign,error=str(exc));continue
            entry,_=side_entry(material+plan['translation'],transformed,plan['target_grasp'],axis)
            stage=entry.copy();stage[2]=p.clearance
            try:geometry=side_path_clearance(material+plan['translation'],transformed,[stage,entry,plan['target_grasp']],bounds)
            except ToolExecutionError as exc:log('side-sweep-rejected',axis=axis.tolist(),jaw_sign=jaw_sign,error=str(exc));continue
            checks=inspect(a,p.c,side,[dict(position=t.tolist(),rotation=target_r.tolist())for t in(stage,plan['target_grasp'])])
            log('candidate',axis=axis.tolist(),jaw_sign=jaw_sign,ik=checks,side_geometry=geometry)
            if all(row['kinematically_reachable']for row in checks):candidates.append((float(np.linalg.norm(plan['translation'])),plan,target_r,stage))
    if not candidates:raise ToolExecutionError('No physically supported phone edge pinch in measured joint workspace')
    _,plan,target_r,stage=choose_edge_candidate(candidates);axis=plan['axis'];k=plan['component'];sign=plan['sign'];token=(('FWD','BACK'),('LEFT','RIGHT'))[k][int(sign<0)]
    grasp=dict(ref,local=(r.T@(plan['grasp']-pos)).tolist());log('plan',**{k:v.tolist()if isinstance(v,np.ndarray)else v for k,v in plan.items()})
    def contact():return any(p.contact(name,f'{side}_finger{i}')for i in(1,2))
    def supported():return p.contact(name,'table')
    p.stage('phone-supported-edge-push');p.act(side,'GRASP')
    def seat():
        material=material_collision_points_task(p,ref);start,receipt=trailing_edge_push_pose(material,actual_finger_points_task(a,side),p.tip(side),axis,bounds['top'])
        start[2]+=.0004
        log('seat',**receipt);height=max(float(p.tip(side)[2])+.012,float(start[2])+.02)
        p.move(side,[*p.tip(side)[:2],height]);p.move(side,[*start[:2],height]);p.move(side,start,tolerance=.0003)
        if a.finger_geometry(side)['lowest_z_task_m']<bounds['top']+.0003:raise ToolExecutionError('Phone push toes lack actual table clearance')
        for _ in range(30):
            if contact():return
            if not supported():raise ToolExecutionError('Phone lost support before push contact')
            if a.finger_geometry(side)['lowest_z_task_m']<bounds['top']+.0003:raise ToolExecutionError('Phone push toes crossed table clearance')
            gap=trailing_contact_gap(material_collision_points_task(p,ref),
                [actual_mesh(a,side,n)for n in a.scene.embodiment.fingers],axis,bounds['top'])
            log('contact-search',gap_m=gap,tip=p.tip(side).tolist(),supported=True)
            if gap<-.001:raise ToolExecutionError('Phone toe overlap without native contact')
            p.act(side,token,mm=max(p.min_mm,min(.5,(gap+.0002)*1000)))
        raise ToolExecutionError('Phone trailing-edge contact absent')
    seat();history=[];reseats=0
    for _ in range(600):
        remaining=float((plan['target_grasp']-p.point(grasp))@axis)
        if remaining<=.001:break
        if not supported():raise ToolExecutionError('Phone lost native table support during edge push')
        if not contact():
            reseats+=1
            if reseats>60:raise ToolExecutionError('Phone bounded edge reseats exhausted')
            seat()
        low=float(a.finger_geometry(side)['lowest_z_task_m'])
        if low<bounds['top']+.0003:raise ToolExecutionError('Phone push toes crossed table clearance')
        if low>bounds['top']+.0007:p.act(side,'DOWN',mm=min(.5,(low-bounds['top']-.0006)*1000))
        p.act(side,token,mm=min(2.,remaining*1000));progress=float(p.point(grasp)@axis);history.append(progress)
        log('actual-push',point=p.point(grasp).tolist(),support=supported(),finger_contact=contact())
        if len(history)>=20 and max(history[-20:])-min(history[-20:])<.0005:raise ToolExecutionError('Phone fails to advance under real edge contact')
    else:raise ToolExecutionError('Bounded phone edge slide exhausted')
    p.act(side,'UP',mm=12.);p.act(side,'RELEASE');p.move(side,[*p.tip(side)[:2],p.clearance])
    # The exterior endpoint was checked for vertical jaws, not for the old
    # palm-down entry. Turn over the cleared table before moving outside.
    current_r=a.tcp_rotation_task(side);tip=p.tip(side)
    hand_radius=max(float(np.linalg.norm(actual_mesh(a,side,n)-tip,axis=1).max())for n in('panda_hand',*a.scene.embodiment.fingers))
    if float(tip[2])-hand_radius<bounds['top']+.001:raise ToolExecutionError('Phone rotation sphere lacks table clearance')
    # This continuous public route was checked from the measured push-end
    # branch through the complete side descent; nearer endpoint IK can still
    # require an inaccessible wrist branch.
    sites=[np.array([-.2,float(tip[1]),p.clearance])]
    old_poses=inspect(a,p.c,side,[dict(position=x.tolist(),rotation=current_r.tolist())for x in sites])
    new_poses=inspect(a,p.c,side,[dict(position=x.tolist(),rotation=target_r.tolist())for x in sites])
    valid=[i for i in range(len(sites))if all(row['kinematically_reachable']and row['minimum_joint_margin_rad']>=.02 for row in(old_poses[i],new_poses[i]))]
    if not valid:raise ToolExecutionError('No dual-pose phone side-pinch staging point')
    i=min(valid,key=lambda i:float(np.linalg.norm(sites[i]-tip)))
    log('turn-staging',point=sites[i].tolist(),entry_ik=old_poses[i],turned_ik=new_poses[i])
    p.move(side,sites[i]);turn_point=p.point(grasp).copy()
    def turn_guard():
        state,_=p.snapshot()
        if any(v['grasp'][0 if side=='left'else 1]for v in state.values()):raise ToolExecutionError('Phone orientation requires an actual empty hand')
        now=p.tip(side)
        radius=max(float(np.linalg.norm(actual_mesh(a,side,n)-now,axis=1).max())for n in('panda_hand',*a.scene.embodiment.fingers))
        if float(now[2])-radius<bounds['top']+.001:raise ToolExecutionError('Phone actual rotation sphere crossed table clearance')
        if not supported()or np.linalg.norm(p.point(grasp)-turn_point)>.001:raise ToolExecutionError('Phone moved or lost support during empty wrist turn')
    orient_phone(p,side,target_r,turn_guard)
    point=p.point(grasp)
    for n in('panda_hand',*a.scene.embodiment.fingers):
        points=actual_mesh(a,side,n)+point-p.tip(side);below=points[points[:,2]<bounds['top']+.001]
        if len(below) and float(np.min(below@axis))<float(bounds['upper'if sign>0 else'lower'][k])*sign+.001:
            raise ToolExecutionError('Actual phone side-pinch hand would intersect table')
    tip=p.tip(side);relative=[actual_mesh(a,side,n)-tip for n in('panda_hand',*a.scene.embodiment.fingers)]
    material=material_collision_points_task(p,ref);entry,entry_receipt=side_entry(material,relative,point,axis)
    waypoints=side_waypoints(tip,entry,point);geometry=side_path_clearance(material,relative,waypoints,bounds)
    samples=[]
    for start,end in zip(waypoints[:-1],waypoints[1:]):
        count=max(1,int(np.ceil(np.linalg.norm(end-start)/.02)))
        samples.extend(start+(end-start)*t/count for t in range(1,count+1))
    actual_r=a.tcp_rotation_task(side)
    checks=inspect(a,p.c,side,[dict(position=t.tolist(),rotation=actual_r.tolist())for t in samples])
    log('actual-side-entry',**entry_receipt,geometry=geometry,ik_sample_spacing_max_m=.02,ik=checks)
    if not all(x['kinematically_reachable']and x['minimum_joint_margin_rad']>=.02 for x in checks):raise ToolExecutionError('Phone side-entry sampled path lacks joint-safe IK')
    def guard_segment(target):
        def guard():
            if not supported() or np.linalg.norm(p.point(grasp)-point)>.001:raise ToolExecutionError('Phone moved or lost support before side pinch')
            now=p.tip(side);bodies=[actual_mesh(a,side,n)-now for n in('panda_hand',*a.scene.embodiment.fingers)]
            side_path_clearance(material_collision_points_task(p,ref),bodies,[now,target],bounds)
        return guard
    for target in waypoints[1:]:p.move(side,target,tolerance=.0008,guard=guard_segment(target))
    stable=0
    for _ in range(5):
        p.act(side,'GRASP');stable=stable+1 if p.held(ref,side)else 0
        if stable>=3:log('native-bilateral-grip',held=True,point=p.point(grasp).tolist());return
    raise ToolExecutionError('Phone edge pinch lacks native bilateral hold')
