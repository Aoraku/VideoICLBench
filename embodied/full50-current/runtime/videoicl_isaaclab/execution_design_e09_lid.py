"""Original E09 thin lids: real supported two-axis push and side pinch.

Reuses E13's native-tested public side-entry prefix while retaining every E09
actor, fixture, original primitive and evaluator. Native grip is required anew.
"""
import itertools,json,math
import numpy as np
from .realworld_tool_expert import ToolExecutionError
from .execution_design_e09_reference import scope,log
from .execution_design_e13_edge import (plan_edge,edge_planning_margin,side_entry,
    side_path_clearance,side_waypoints,orient_phone,trailing_contact_gap)

SIDE_R=np.array([[1.,0.,0.],[0.,0.,-1.],[0.,1.,0.]])
EDGE_AXIS=np.array([0.,1.,0.])


def side_rotation(name):
    # The final far lid arrives through the reviewed tilted supported push.
    # Its equivalent -Z jaw uses the safe measured wrist branch, with the
    # same horizontal palm approach and the same original vertical pinch.
    sign=-1. if name=='group_box2_lid'else 1.
    return np.array([[sign,0.,0.],[0.,0.,-1.],[0.,sign,0.]])


def positive_y_waypoints(tip,entry,point):
    tip,entry,point=map(lambda x:np.asarray(x,float),(tip,entry,point))
    if any(x.shape!=(3,)for x in(tip,entry,point))or not np.isfinite(np.r_[tip,entry,point]).all():
        raise ToolExecutionError('Finite complete original-lid side-entry path required')
    inside=tip.copy();inside[2]=.92;stage=entry.copy();stage[2]=.92
    across=inside.copy();across[1]=stage[1]
    return[tip.copy(),inside,across,stage,entry.copy(),point.copy()]


def collision_points(p,name):
    """Read the original native collider, including USD Cube source primitives."""
    from pxr import Usd,UsdGeom,UsdPhysics
    import omni.usd
    stage=omni.usd.get_context().get_stage();body=stage.GetPrimAtPath(p.a.scene.root_path+'/Props/'+name)
    if not body:raise ToolExecutionError('Original E09 lid rigid body missing')
    cache=UsdGeom.XformCache();inverse=cache.GetLocalToWorldTransform(body).GetInverse();parts=[]
    for prim in Usd.PrimRange(body,Usd.TraverseInstanceProxies()):
        ancestor=prim;enabled=False
        while ancestor:
            if ancestor.HasAPI(UsdPhysics.CollisionAPI):enabled=bool(UsdPhysics.CollisionAPI(ancestor).GetCollisionEnabledAttr().Get());break
            if ancestor==body:break
            ancestor=ancestor.GetParent()
        if not enabled:continue
        if prim.IsA(UsdGeom.Cube):vertices=np.array(list(itertools.product([-1,1],repeat=3)))*float(UsdGeom.Cube(prim).GetSizeAttr().Get())/2
        elif prim.IsA(UsdGeom.Mesh):vertices=np.asarray(UsdGeom.Mesh(prim).GetPointsAttr().Get(),float)
        else:continue
        matrix=np.asarray(cache.GetLocalToWorldTransform(prim)*inverse,float);parts.append(vertices@matrix[:3,:3]+matrix[3,:3])
    if not parts:raise ToolExecutionError('Actual E09 lid collision vertices unavailable')
    pos,rot=p.frame({'actor':name});vertices=np.concatenate(parts)@rot.T+pos
    return vertices


def material(p,name):
    vertices=collision_points(p,name)
    if not .0058<np.ptp(vertices[:,2])<.0062:raise ToolExecutionError('Original upright 6mm lid required')
    return vertices


def validate_lid(p,name):
    scope(p)
    if name not in {f'group_box{i}_lid'for i in range(3)}:raise ToolExecutionError('Original E09 lid identity required')
    obj=p.objects[name]
    if obj.get('kind')!='box'or not np.allclose(obj['size'],[.063,.055,.003],atol=1e-10):raise ToolExecutionError('Original E09 thin lid primitive required')


def supported_push(p,name,side,axis,target):
    from .execution_design_thin_edge import actual_finger_points_task,trailing_edge_push_pose
    from .execution_design_e33_grasp import actual_mesh
    axis=np.asarray(axis,float);target=np.asarray(target,float);k=int(np.argmax(abs(axis[:2])));token=(('FWD','BACK'),('LEFT','RIGHT'))[k][int(axis[k]<0)]
    protected={n:(np.asarray(x['pos']).copy(),np.asarray(x['mat']).copy())for n,x in p.snapshot()[0].items()if n!=name}
    def contact():return any(p.contact(name,side+'_finger'+str(i))for i in(1,2))
    def support():
        state,_=p.snapshot()
        if not p.contact(name,'table')or abs(float(state[name]['mat'][2,2]))<.995:
            raise ToolExecutionError('E09 real lid lost upright table support while pushed')
        if min(float(actual_mesh(p.a,side,n)[:,2].min())for n in('panda_hand',*p.a.scene.embodiment.fingers))<.8003:
            raise ToolExecutionError('Actual full push hand crosses original table clearance')
        for n,(pos,rot)in protected.items():
            if np.linalg.norm(np.asarray(state[n]['pos'])-pos)>.003 or np.linalg.norm(np.asarray(state[n]['mat'])-rot)>.03:
                raise ToolExecutionError('E09 supported lid push disturbed original actor: '+n)
    p.stage('e09-supported-lid-push-'+name);p.act(side,'GRASP')
    def seat():
        support();pts=material(p,name);start,receipt=trailing_edge_push_pose(pts,actual_finger_points_task(p.a,side),p.tip(side),axis,.8);start[2]+=.0004
        height=max(float(p.tip(side)[2])+.012,float(start[2])+.02)
        p.move(side,[*p.tip(side)[:2],height],guard=support);p.move(side,[*start[:2],height],guard=support);p.move(side,start,tolerance=.0003,guard=support)
        for _ in range(30):
            support()
            if p.a.finger_geometry(side)['lowest_z_task_m']<.8003:raise ToolExecutionError('E09 lid push fingers cross original table')
            if contact():return
            gap=trailing_contact_gap(material(p,name),[actual_mesh(p.a,side,n)for n in p.a.scene.embodiment.fingers],axis,.8)
            if gap<-.001:raise ToolExecutionError('Lid toe penetration without native contact')
            p.act(side,token,mm=max(p.min_mm,min(.5,(gap+.0002)*1000)))
        raise ToolExecutionError('Actual E09 lid trailing-edge contact absent')
    seat();history=[];reseats=0
    for _ in range(700):
        support();center=np.asarray(p.frame({'actor':name})[0]);remaining=float((target-center)@axis)
        if remaining<=.001:break
        if not contact():
            reseats+=1
            if reseats>60:raise ToolExecutionError('E09 bounded lid contact reseats exhausted')
            seat()
        low=float(p.a.finger_geometry(side)['lowest_z_task_m'])
        if low<.8003:raise ToolExecutionError('E09 actual lid toes crossed original table')
        if low>.8007:p.act(side,'DOWN',mm=min(.5,(low-.8006)*1000))
        p.act(side,token,mm=min(2.,remaining*1000));history.append(float(p.frame({'actor':name})[0]@axis))
        log(p,'native-lid-supported-push',actor=name,axis=axis,center=center,table_contact=True)
        if len(history)>=24 and max(history[-24:])-min(history[-24:])<.0005:raise ToolExecutionError('E09 actual supported lid push stalled')
    else:raise ToolExecutionError('E09 lid push exhausted')
    p.act(side,'UP',mm=12.);p.act(side,'RELEASE');p.move(side,[*p.tip(side)[:2],.98])


def acquire(p,name,side='left'):
    validate_lid(p,name)
    from .execution_design_e09_reference import empty_wall_orientation,park_empty_other
    from .execution_design_thin_edge import table_bounds_task
    from .execution_design_e33_grasp import actual_mesh
    from .execution_design_drawer_ik_probe import inspect
    bounds=table_bounds_task(p.a.scene);ref={'actor':name,'local':[0,0,0]};side_r=side_rotation(name)
    park_empty_other(p,side)
    p.act(side,'RELEASE');p.move(side,[*p.tip(side)[:2],max(.98,float(p.tip(side)[2]))]);empty_wall_orientation(p,side)
    # The original other-batch rack obstructs an immediate -X edge slide at
    # source Y=.245. Stage the actual lid in the clear .40 lane before moving
    # it nearer X=-.28 and pushing to the original +Y edge. No pose is assigned.
    pos,_=p.frame(ref)
    if not .23<float(pos[1])<.26:raise ToolExecutionError('Original E09 lid supply row changed')
    supported_push(p,name,side,[0,1,0],[pos[0],.40,pos[2]])
    pos,_=p.frame(ref)
    if pos[0]<-.281:raise ToolExecutionError('Actual lid crossed the reviewed near staging coordinate')
    if pos[0]>-.279:
        if pos[0]>.05:
            # The far +X edge of lid2 otherwise demands TCP X~.18 with a
            # vertical palm. A public 25deg empty-hand pitch keeps the same
            # actual toe contact while moving the wrist inward. Larger tilts
            # were rejected because the original palm would cross the table.
            from .realworld_tool_expert import _axis_rotation
            p.move(side,[-.2,.4,1.0]);start_r=np.asarray(p.a.tcp_rotation_task(side))
            def tilt_guard():
                state,contacts=p.snapshot()
                if any(v['grasp'][0 if side=='left'else 1]for v in state.values())or frozenset((name,'table'))not in contacts:
                    raise ToolExecutionError('Empty tilted push needs released supported original lid')
                now=p.tip(side);radius=max(float(np.linalg.norm(actual_mesh(p.a,side,n)-now,axis=1).max())for n in('panda_hand',*p.a.scene.embodiment.fingers))
                if now[2]-radius<.801:raise ToolExecutionError('Empty push tilt lacks full-hand sphere clearance')
            orient_phone(p,side,_axis_rotation([0,1,0],-math.radians(25))@start_r,tilt_guard)
        supported_push(p,name,side,[-1,0,0],[-.28,pos[1],pos[2]])
        empty_wall_orientation(p,side)
    tcp=np.asarray(p.tip(side));r=p.a.tcp_rotation_task(side);meshes=[actual_mesh(p.a,side,n)for n in('panda_hand',*p.a.scene.embodiment.fingers)]
    local=[(x-tcp)@r for x in meshes];relative=[x@side_r.T for x in local];pts=material(p,name);pos,rotation=p.frame(ref)
    plan=plan_edge(pts,pos,relative,bounds,EDGE_AXIS,margin=edge_planning_margin(relative))
    supported_push(p,name,side,EDGE_AXIS,plan['translated_center'])
    # Keep the original lid supported and stationary during the empty wrist
    # turn and all public side-entry segments; all three hand bodies are used.
    p.move(side,[-.2,.4,.98]);fixed=np.asarray(p.frame(ref)[0]).copy()
    def guard_turn():
        state,contacts=p.snapshot()
        if any(x['grasp'][0 if side=='left'else 1]for x in state.values()):raise ToolExecutionError('Lid turn requires actual empty hand')
        if frozenset((name,'table'))not in contacts or np.linalg.norm(np.asarray(state[name]['pos'])-fixed)>.001:
            raise ToolExecutionError('Actual lid changed during empty side-pinch turn')
        now=np.asarray(p.tip(side));radius=max(float(np.linalg.norm(actual_mesh(p.a,side,n)-now,axis=1).max())for n in('panda_hand',*p.a.scene.embodiment.fingers))
        if now[2]-radius<.801:raise ToolExecutionError('Actual full-hand rotation sphere crosses table')
    orient_phone(p,side,side_r,guard_turn)
    pos,rotation=p.frame(ref);pts=material(p,name)
    # Recompute the grasp from actual post-push collision geometry, avoiding
    # accumulated displacement/yaw assumptions from the plan.
    point=pos.copy();point[1]=float(pts[:,1].max())-.006;point[2]=(float(pts[:,2].min())+float(pts[:,2].max()))/2
    ref={'actor':name,'local':(rotation.T@(point-pos)).tolist()}
    now=p.tip(side);relative=[actual_mesh(p.a,side,n)-now for n in('panda_hand',*p.a.scene.embodiment.fingers)]
    entry,_=side_entry(pts,relative,point,EDGE_AXIS);waypoints=positive_y_waypoints(now,entry,point);side_path_clearance(pts,relative,waypoints,bounds)
    samples=[]
    for a,b in zip(waypoints,waypoints[1:]):
        count=max(1,int(np.ceil(np.linalg.norm(b-a)/.02)));samples.extend(a+(b-a)*i/count for i in range(1,count+1))
    checks=inspect(p.a,p.c,side,[dict(position=x.tolist(),rotation=p.a.tcp_rotation_task(side).tolist())for x in samples])
    if not all(x['kinematically_reachable']and x['minimum_joint_margin_rad']>=.02 for x in checks):raise ToolExecutionError('Original lid full side path lacks joint-safe native calibrated IK')
    for target in waypoints[1:]:
        def guard():
            state,contacts=p.snapshot()
            if frozenset((name,'table'))not in contacts or np.linalg.norm(np.asarray(state[name]['pos'])-fixed)>.001:raise ToolExecutionError('Actual lid moved before side pinch')
            tip=p.tip(side);body=[actual_mesh(p.a,side,n)-tip for n in('panda_hand',*p.a.scene.embodiment.fingers)]
            side_path_clearance(material(p,name),body,[tip,target],bounds)
        p.move(side,target,guard=guard,tolerance=.0008)
    stable=0
    for _ in range(6):
        p.act(side,'GRASP');stable=stable+1 if p.held(ref,side)else 0
        if stable>=3:break
    else:raise ToolExecutionError('Original E09 lid has no actual bilateral side pinch')
    p.move(side,np.asarray(p.tip(side))+[0,0,.07],guard=lambda:p.require_held(ref,side))
    log(p,'native-lid-side-pinch-and-lift',actor=name,side=side,actual_position=p.frame({'actor':name})[0])
    return ref,side
