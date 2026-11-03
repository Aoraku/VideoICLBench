"""E31 engineering-only real tabletop edge exposure and opposed rim pinch.

No body, joint, contact, evaluator or source-spec state is written. A proposed
mesh plan becomes a grasp only after the native two-finger contact checks.
"""
import json
import math
import numpy as np
from .execution_design import REVISION_V3


def rim_plan(points,center,fingers,bounds,outward,inset=.012):
    points,center,axis=map(lambda x:np.asarray(x,float),(points,center,outward))
    fingers=[np.asarray(x,float)for x in fingers]
    if points.ndim!=2 or points.shape[1]!=3 or len(points)<8 or len(fingers)!=2:
        raise ValueError('Actual plate and two finger meshes required')
    if not np.isfinite(np.r_[points.ravel(),center,axis,*[f.ravel()for f in fingers]]).all():
        raise ValueError('Finite plate/finger geometry required')
    if not np.allclose(abs(axis),[1,0,0]) or not .006<=inset<=.018:
        raise ValueError('Reviewed X-edge and physical rim inset required')
    sign=float(axis[0]);projected=points@axis;outer=float(projected.max())
    # Restrict to the actual rim band near the centre line. Do not infer the
    # surface from a full-body box including the empty interior of the dish.
    band=points[(projected>=outer-inset-.004)&(projected<=outer-inset+.004)&(abs(points[:,1]-center[1])<=.022)]
    if len(band)<4:raise ValueError('Source mesh lacks a measured rim section')
    grasp=np.array([sign*(outer-inset),center[1],.5*(band[:,2].min()+band[:,2].max())])
    thickness=float(np.ptp(band[:,2]))
    if not .001<=thickness<=.03:raise ValueError('Rim thickness outside opposed-finger aperture')
    low=[f[f[:,2]+grasp[2]<bounds['top']+.002]for f in fingers]
    if not any(len(f)for f in low):raise ValueError('Real lower finger required')
    exterior=max(.002-float(np.min(f@axis))for f in low if len(f))
    target=grasp.copy();target[0]=bounds['upper'if sign>0 else'lower'][0]+sign*exterior
    delta=target-grasp;translated=center+delta
    if any(translated[k]<bounds['lower'][k]+.025 or translated[k]>bounds['upper'][k]-.025 for k in (0,1)):
        raise ValueError('Plate centre loses measured tabletop support margin')
    if not 0<float(delta@axis)<.40:raise ValueError('Plate edge slide exceeds bounded tabletop route')
    return dict(grasp=grasp,target_grasp=target,translation=delta,translated_center=translated,
                rim_thickness=thickness,required_exterior=exterior,inset=inset)


class _PlateView:
    def __init__(self,a,name):self.a=a;self.name=name
    def frame(self,ref):
        state,_=self.a.c.snapshot();b=state[ref['actor']]
        return np.asarray(b['pos']),np.asarray(b['mat'])


def choose_edge_route(routes):
    """Endpoint IK alone cannot certify a bounded-joint approach branch."""
    valid=[]
    for index,rows in enumerate(routes):
        if len(rows)!=5:raise ValueError('Entry, oriented stage, exterior, near and rim required')
        if not all(r['kinematically_reachable'] and r['minimum_joint_margin_rad']>=.08 for r in rows):continue
        joints=np.asarray([r['candidate_joints_rad']for r in rows],float)
        if joints.shape!=(5,7)or not np.isfinite(joints).all():raise ValueError('Finite seven bounded joints required')
        travel=np.diff(joints,axis=0)
        if np.max(abs(travel))>=math.pi:continue
        valid.append((rows[0]['joint_distance_rad']+float(np.linalg.norm(travel,axis=1).sum()),index))
    if not valid:raise RuntimeError('No same-branch measured plate edge orientation route')
    return min(valid)[1]


def prepare_plate_edge(a,name,side,clearance):
    spec=a.scene.spec
    if not(getattr(a,'_execution_design_reference_authorized',False) and spec['id']=='E31'
           and spec.get('execution_design',{}).get('revision')==REVISION_V3
           and name==spec['semantic']['plate'] and a.scene.embodiment.name=='franka'
           and not getattr(a,'smooth',False)):
        raise ValueError('Explicit E31 Panda discrete engineering plate control required')
    from .execution_design_thin_edge import (table_bounds_task,material_collision_points_task,
        actual_finger_points_task,trailing_edge_push_pose,check_under_table_clearance,seek_actual_contact)
    from .execution_design_e33_grasp import actual_mesh
    from .execution_design_e31_continuation import orient_empty as orient
    from .execution_design_drawer_ik_probe import inspect
    from .execution_design_e31_continuation import pinch_rotations,screen
    from .execution_design_jacobian_reference import capture
    p=_PlateView(a,name);ref={'actor':name};bounds=table_bounds_task(a.scene)
    state,_=a.c.snapshot()
    if any(any(b['grasp'])for b in state.values()):raise RuntimeError('Empty hands required before plate edge pushing')
    initial={k:np.array(b['pos'],copy=True)for k,b in state.items()if k!=name}
    def log(phase,**values):
        with(a.out/'e31-edge-grasp.private.jsonl').open('a')as f:
            f.write(json.dumps(dict(phase=phase,step=a.c.steps,**values),default=lambda x:x.tolist())+'\n')
    def act(token,mm=None):
        kw={}if mm is None else{'mm':float(mm)}
        a.act(token if side=='left'else'STILL',token if side=='right'else'STILL',**kw)
    def snapshot():
        s,c=a.c.snapshot()
        if any(np.linalg.norm(np.asarray(s[k]['pos'])-v)>.008 for k,v in initial.items()):
            raise RuntimeError('Plate edge route moved another task object')
        if frozenset((name,'table'))not in c:raise RuntimeError('Plate lost tabletop support during edge exposure')
        return s,c
    def contact():
        _,c=snapshot();return any(frozenset((name,side+'_finger'+str(i)))in c for i in(1,2))
    act('RELEASE')
    pos,rot=p.frame(ref);points=material_collision_points_task(p,ref)
    tcp=np.asarray(a.tip(side));current=a.tcp_rotation_task(side)
    local=[(actual_mesh(a,side,f)-tcp)@current for f in a.scene.embodiment.fingers]
    candidates=[]
    for sign in(-1.,1.):
        outward=np.array([sign,0.,0.])
        for rotation in pinch_rotations(outward):
            for inset in(.012,.008,.016):
                try:plan=rim_plan(points,pos,[f@rotation.T for f in local],bounds,outward,inset)
                except ValueError as exc:log('geometry-rejected',outward=outward,inset=inset,error=str(exc));continue
                proposals=inspect(a,a.c,side,[dict(position=plan['target_grasp'].tolist(),rotation=rotation.tolist())])
                log('candidate',plan=plan,rotation=rotation,kinematics=proposals)
                if all(q['kinematically_reachable']and q['minimum_joint_margin_rad']>.08 for q in proposals):
                    candidates.append((float(np.linalg.norm(plan['translation'])),outward,rotation,plan))
                    break
            if candidates:break
        if candidates:break
    if not candidates:raise RuntimeError('No supported and reachable measured plate edge pinch')
    _,outward,rotation,plan=min(candidates,key=lambda x:x[0]);token='FWD'if outward[0]>0 else'BACK'
    local_grasp=rot.T@(plan['grasp']-pos)
    def point():
        b,r=p.frame(ref);return b+r@local_grasp
    log('selected',plan=plan,outward=outward,rotation=rotation,initial_plate=pos)
    a.stage='e31-plate-real-edge-push';act('GRASP')
    high=max(1.06,float(clearance),float(a.tip(side)[2]))
    a.move_generated({side:[*a.tip(side)[:2],high]})
    def seat():
        material=material_collision_points_task(p,ref)
        # The push planner uses the conservative convex section. Reduce the
        # dense source tessellation without changing that section geometry.
        from scipy.spatial import ConvexHull
        material=material[ConvexHull(material).vertices]
        start,receipt=trailing_edge_push_pose(material,actual_finger_points_task(a,side),a.tip(side),outward,bounds['top'],clearance=.0003)
        log('push-contact-plan',receipt=receipt)
        a.move_generated({side:[*a.tip(side)[:2],high]})
        a.move_generated({side:[*start[:2],high]})
        a.move_generated({side:start},tolerance=.0008)
        count=seek_actual_contact(contact,lambda:act(token,.5),16)
        if count is None:raise RuntimeError('Real plate trailing-rim contact absent')
        log('actual-push-contact',seek_actions=count)
    seat();history=[];reseats=0
    for _ in range(250):
        remaining=float((plan['target_grasp']-point())@outward)
        if remaining<=.001:break
        snapshot()
        if not contact():
            reseats+=1
            if reseats>6:raise RuntimeError('Bounded plate push contact reacquisition exhausted')
            seat()
        act(token,min(3.,remaining*1000));s,c=snapshot();history.append(float(point()@outward))
        log('public-push',plate_position=s[name]['pos'],grasp=point(),table_supported=True,finger_contact=contact())
        if len(history)>=12 and max(history[-12:])-min(history[-12:])<.001:
            raise RuntimeError('Actual plate stalled under real pushing contact')
    else:raise RuntimeError('Bounded plate edge exposure exhausted')
    act('RELEASE');act('UP',15.)
    # Re-measure after the actual push. The old exterior-only orientation had
    # an endpoint IK solution on a distant branch: native joint4 hit its stop
    # before the empty wrist could turn. Turn above the table with both real
    # jaw assignments available, then retain the same bounded-joint branch.
    snapshot();grasp=point();tcp=np.asarray(a.tip(side));current=a.tcp_rotation_task(side)
    meshes=[actual_mesh(a,side,f)for f in ('panda_hand',*a.scene.embodiment.fingers)]
    radius=max(float(np.linalg.norm(m-tcp,axis=1).max())for m in meshes)
    tops=[bounds['top']]
    for obj in spec['objects']:
        s,_=a.c.snapshot();b=s[obj['id']];r=np.asarray(b['mat'])
        centre=np.asarray(b['pos'])+r@np.asarray(obj.get('local_bounds_center',[0,0,0]))
        tops.append(float(centre[2]+(abs(r)@np.asarray(obj.get('bounds_half_extent',obj['size'])))[2]))
    high=max(high,max(tops)+radius+.015)
    # A horizontal entry 8cm outside the rim folded the near-base wrist to
    # its limit. The rim itself is already outside the real table boundary;
    # use a short exterior approach whose actual fingers remain clear.
    outside=grasp+outward*.025;outside[2]=high;near=grasp+outward*.015
    robot=a.scene.robots[side];base_value=robot.data.root_pos_w[0]
    if hasattr(base_value,'detach'):base_value=base_value.detach().cpu().numpy()
    base=np.asarray(a.scene.world_to_task(np.asarray(base_value,float)))
    sites=[np.array([tcp[0],base[1],high]),np.r_[tcp[:2],high],np.array([.5*(tcp[0]+grasp[0]),base[1],high])]
    local=[(m-tcp)@current for m in meshes[1:]];selected=None
    measured=capture(a,a.c,side)
    for target in pinch_rotations(outward):
        lower=np.vstack([m@target.T+grasp for m in local]);lower=lower[lower[:,2]<bounds['top']+.001]
        edge=bounds['lower'if outward[0]<0 else'upper'][0]
        if len(lower) and np.min(outward[0]*(lower[:,0]-edge))<.001:continue
        for site in sites:
            waypoints=[dict(position=q.tolist(),rotation=r.tolist())for q,r in
                ((np.r_[tcp[:2],high],current),(site,current),(site,target),(outside,target),(near,target),(grasp,target))]
            result=screen(measured,waypoints)
            log('post-push-continuation-candidate',site=site,rotation=target,measured=measured,continuation=result)
            if result['passed']:
                selected=(site,target,result);break
        if selected is not None:break
    if selected is None:raise RuntimeError('No continuous bounded-joint measured plate edge route')
    site,rotation,result=selected
    log('post-push-route-selected',site=site,rotation=rotation,continuation=result)
    a.stage='e31-plate-empty-wrist-staging'
    a.move_generated({side:[*tcp[:2],high]});a.move_generated({side:site});orient(a,side,rotation)
    a.move_generated({side:outside})
    snapshot();grasp=point()
    check_under_table_clearance(grasp,a.tip(side),a.finger_geometry(side),bounds,0,float(outward[0]),margin=.001)
    near=grasp+outward*.015
    check_under_table_clearance(near,a.tip(side),a.finger_geometry(side),bounds,0,float(outward[0]),margin=.001)
    a.move_generated({side:near},tolerance=.002);a.move_generated({side:grasp},tolerance=.0015)
    log('actual-pregrasp',tcp=a.tip(side),plate_position=p.frame(ref)[0],finger_geometry=a.finger_geometry(side))
    a._e31_edge_grasp=(name,side)
    return np.asarray(a.tip(side))
