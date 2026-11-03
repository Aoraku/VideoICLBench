"""E09 private reference: original near walls and measured supported crate drag.

Only public actions; source geometry, original task identities and rubric are
unchanged. A geometric plan or completed route is never a native certificate.
"""
from copy import deepcopy
from contextlib import contextmanager
import json,math
import numpy as np
from .realworld_tool_expert import ToolExecutionError
from .execution_design import REVISION_V3

STAGE_XY=np.array([-.15,-.54])
# Actual successful v8 pre-grasp3917, expressed in original triangle material.
SOURCE_TRIANGLE_PREGRIP_LOCAL=np.array([-.00152832269668578,-.00614373385906220,.00088846683502200])


def scope(p):
    if (p.task!='E09' or p.spec.get('execution_design',{}).get('revision')!=REVISION_V3
            or not p.a.control_report.get('engineering_reference_only')
            or p.spec.get('author_smooth_recording',False)):
        raise ToolExecutionError('E09 independent native public reference required')


def near_wall_ref(obj,ref):
    """Choose the existing symmetric negative-X collision wall, never edit it."""
    name=obj['id'];expected=([.09,.2,.055]if name=='shipping_crate'else[.063,.055,.022])
    if name!='shipping_crate'and name not in {f'group_box{i}'for i in range(3)}:
        raise ToolExecutionError('Unreviewed E09 package identity')
    if not np.allclose(obj['size'],expected,atol=1e-10,rtol=0):
        raise ToolExecutionError('Original E09 source package bounds required')
    walls=obj.get('collision_shapes',[]);half=expected[0]-.004
    matching=[g for g in walls if g.get('type')=='box'
              and np.allclose(g.get('size',[]),[.004,expected[1],expected[2]],atol=1e-10)
              and np.allclose(g.get('pos',[]),[-half,0,0],atol=1e-10)
              and np.allclose(g.get('quat',[1,0,0,0]),[1,0,0,0],atol=1e-10)]
    if len(matching)!=1:raise ToolExecutionError('Original solid near-X wall not present')
    local=np.asarray(ref['local'],float)
    if (local.shape!=(3,)or not np.isfinite(local).all()
            or not np.allclose(ref['jaw_axis_local'],[1,0,0],atol=1e-10)
            or not np.isclose(local[0],half,atol=1e-10)
            or not abs(local[1])<expected[1]-.015
            or not -expected[2]+.006<local[2]<expected[2]-.004):
        raise ToolExecutionError('Original E09 wall grasp descriptor required')
    out=deepcopy(ref);out['local']=[-half,*local[1:].tolist()]
    return out


def support_metrics(center,rotation,half,bounds,com):
    """Conservative upright support polygon from the original floor/table."""
    center,rotation,half,com=map(lambda x:np.asarray(x,float),(center,rotation,half,com))
    if (center.shape!=(3,)or rotation.shape!=(3,3)or half.shape!=(3,)or com.shape!=(3,)
            or not np.isfinite(np.r_[center,rotation.ravel(),half,com]).all()
            or np.max(abs(rotation-np.eye(3)))>.025):
        raise ToolExecutionError('Upright measured package and COM required')
    # An inscribed rectangle reserves both measured yaw/roll drift and 2mm.
    inset=np.abs(rotation-np.eye(3))@half+.002
    lower=np.maximum(center[:2]-half[:2]+inset[:2],np.asarray(bounds['lower'])[:2]+.002)
    upper=np.minimum(center[:2]+half[:2]-inset[:2],np.asarray(bounds['upper'])[:2]-.002)
    margin=float(np.min(np.r_[com[:2]-lower,upper-com[:2]]))
    if np.any(upper<=lower)or margin<.010:
        raise ToolExecutionError('Actual package COM lacks 10mm supported-floor margin')
    return dict(lower=lower.tolist(),upper=upper.tolist(),com_task=com.tolist(),margin_m=margin)


def drag_waypoints(center,bounds,fixtures,half):
    center=np.asarray(center,float);half=np.asarray(half,float)
    if not np.allclose(half,[.09,.2,.055],atol=1e-10):raise ToolExecutionError('Original crate required')
    if not(np.allclose(np.asarray(bounds['lower'])[:2],[-.35,-.6],atol=1e-5)
           and np.allclose(np.asarray(bounds['upper'])[:2],[.35,.6],atol=1e-5)):
        raise ToolExecutionError('Reviewed actual E09 finite table required')
    if not np.allclose(center[:2],[.22,-.16],atol=.008):
        raise ToolExecutionError('Original empty crate position changed before staging')
    points=[center.copy(),np.r_[.16,center[1],center[2]],np.r_[.16,-.54,center[2]],np.r_[STAGE_XY,center[2]]]
    for a,b in zip(points,points[1:]):
        low=np.minimum(a,b)-half;high=np.maximum(a,b)+half
        for f in fixtures:
            if f.get('type')!='box':raise ToolExecutionError('Unreviewed E09 source fixture')
            fc=np.r_[f.get('xy',[0,0]),f['z']];fh=np.asarray(f['size'],float)
            gap=np.maximum(np.maximum(low-(fc+fh),fc-fh-high),0)
            if np.linalg.norm(gap)<.006:
                raise ToolExecutionError('Empty crate sweep lacks original-fixture clearance')
    for point in points:support_metrics(point,np.eye(3),half,bounds,point)
    return points[1:]


def log(p,phase,**data):
    with(p.a.out/'e09-packaging-reference.private.jsonl').open('a')as f:
        f.write(json.dumps(dict(phase=phase,step=p.c.steps,**data),default=lambda x:x.tolist())+'\n')


def actual_mass_com(p,name):
    """Read native PhysX mass/COM; missing native fields fail closed."""
    body=p.a.scene.objects[name]
    def array(x):return np.asarray(x.detach().cpu().numpy()if hasattr(x,'detach')else x,float)
    local=array(body.root_physx_view.get_coms()).reshape(-1,7)
    mass=array(body.root_physx_view.get_masses()).reshape(-1)
    if len(local)!=1 or len(mass)!=1 or mass[0]<=0 or not np.isfinite(np.r_[local.ravel(),mass]).all():
        raise ToolExecutionError('Actual native package mass/COM unavailable')
    pos,rot=p.frame({'actor':name})
    return float(mass[0]),np.asarray(pos)+np.asarray(rot)@local[0,:3]


def actual_supported_com(p,name,bounds,*,empty=False):
    from .execution_design_e09_clearance import supported_package_payload
    state,contacts=p.snapshot();payload=supported_package_payload(name,p.objects,state,contacts)
    if empty and payload!={name}:raise ToolExecutionError('Empty crate already contains real payload')
    if frozenset((name,'table'))not in contacts:raise ToolExecutionError('Real crate table contact lost')
    pairs=[actual_mass_com(p,n)for n in payload];mass=sum(x[0]for x in pairs)
    com=sum(m*c for m,c in pairs)/mass
    metrics=support_metrics(state[name]['pos'],state[name]['mat'],p.objects[name]['size'],bounds,com)
    return metrics,sorted(payload),mass


@contextmanager
def supported_drag_guard(p,ref,bounds):
    """Check native holding, support and COM after every real physics tick."""
    from isaaclab.utils.math import matrix_from_quat
    name=ref['actor'];asset=p.a.scene.objects[name]
    local=asset.root_physx_view.get_coms().detach().cpu().numpy().reshape(-1,7)
    if local.shape!=(1,7)or not np.isfinite(local).all():
        raise ToolExecutionError('Native crate COM required before drag')
    checks=0
    def guard(c,render):
        nonlocal checks
        forces=c.contact_forces
        if not all(forces.get(frozenset((name,'right_finger'+str(i))),0.)>.001 for i in(1,2))or c.grips['right']>=.01:
            raise ToolExecutionError('Native supported drag lost bilateral near-wall hold')
        if forces.get(frozenset((name,'table')),0.)<=.001:
            raise ToolExecutionError('Native supported drag lost table support')
        pos=p.a.scene.world_to_task(asset.data.root_pos_w[0].detach().cpu().numpy())
        rot=p.a.scene.layout.task_rotation.T@matrix_from_quat(asset.data.root_quat_w)[0].detach().cpu().numpy()
        support_metrics(pos,rot,p.objects[name]['size'],bounds,pos+rot@local[0,:3])
        extent=np.abs(rot)@np.asarray(p.objects[name]['size'])
        for fixture in p.spec['fixtures']:
            center=np.r_[fixture.get('xy',[0,0]),fixture['z']];half=np.asarray(fixture['size'])
            gap=np.maximum(np.maximum(pos-extent-(center+half),center-half-(pos+extent)),0)
            if np.linalg.norm(gap)<.004:raise ToolExecutionError('Native crate lost original-fixture clearance')
        checks+=1
    p.c.tick_hooks.append(guard)
    try:yield
    finally:
        p.c.tick_hooks.remove(guard)
        log(p,'per-native-tick-drag-guard',physics_ticks_checked=checks)


def empty_wall_orientation(p,side,desired=(1,0,0)):
    """Restore a downward X-wall pinch after any genuine thin-lid side grasp."""
    from .author_orientation import panda_downward_grasp_delta,_axis_angle
    from .execution_design_e33_grasp import actual_mesh
    labels=(('ROLL_LEFT','ROLL_RIGHT'),('PITCH_UP','PITCH_DOWN'),('ROTATE_CCW','ROTATE_CW'))
    for _ in range(100):
        state,_=p.snapshot()
        if any(v['grasp'][0 if side=='left'else 1]for v in state.values()):
            raise ToolExecutionError('E09 wall alignment requires an actually empty hand')
        tip=np.asarray(p.tip(side));radius=max(float(np.linalg.norm(actual_mesh(p.a,side,n)-tip,axis=1).max())for n in('panda_hand',*p.a.scene.embodiment.fingers))
        if tip[2]-radius<.801:raise ToolExecutionError('Empty package rotation lacks full-hand table clearance')
        arm=p.c.public_feedback()['arms'][side];i=arm['joint_names'].index('panda_joint7');limits=arm['measured_sensors']['joint_soft_limits_rad']
        if not limits.get('available'):raise ToolExecutionError('Native wrist limits unavailable')
        fingers=p.a.finger_geometry(side)['fingers'];jaw=np.asarray(fingers[0]['body_origin_task_m'])-fingers[1]['body_origin_task_m']
        axis,angle=_axis_angle(panda_downward_grasp_delta(p.a.tcp_rotation_task(side),jaw,desired,joint7_state=[arm['joint_positions_rad'][i],*limits['value'][i]]))
        if angle<math.radians(1):return
        k=int(np.argmax(abs(axis)));p.act(side,labels[k][int(axis[k]<0)],degrees=min(7.,max(.5,math.degrees(angle*abs(axis[k])))))
    raise ToolExecutionError('Empty package orientation failed to converge')


def measured_approach_height(p,side):
    from .execution_design_e33_grasp import actual_mesh
    state,_=p.snapshot();top=.8
    for n,s in state.items():
        o=p.objects[n];c=np.asarray(s['pos'])+np.asarray(s['mat'])@np.asarray(o.get('local_bounds_center',[0,0,0]));top=max(top,float(c[2]+abs(np.asarray(s['mat'])[2])@np.asarray(o['size'])))
    for f in p.spec['fixtures']:top=max(top,float(f['z'])+float(f['size'][2]))
    tip=np.asarray(p.tip(side));low=min(float(actual_mesh(p.a,side,n)[:,2].min()-tip[2])for n in('panda_hand',*p.a.scene.embodiment.fingers))
    return top+.050-low+.0003


def park_empty_other(p,active,*,empty_step_mm=10.,lateral_first=False):
    """Use public Cartesian moves to keep the inactive real arm near its base."""
    if getattr(p,'_e09_active_side',None)==active:return
    other='left'if active=='right'else'right';state,_=p.snapshot()
    if any(x['grasp'][0 if other=='left'else 1]for x in state.values()):
        raise ToolExecutionError('Inactive E09 arm must actually release before parking')
    functional=bool(p.d.get('operable_packaging')and p.a.control_report.get('engineering_reference_only'))
    if functional:empty_step_mm=25.
    if not 0<empty_step_mm<=(25. if functional else 20.):raise ToolExecutionError('Reviewed E09 empty parking step required')
    previous=p.max_mm;p.max_mm=min(float(empty_step_mm),float(p.a.scene.embodiment.config['control']['step_mm'][1]))
    try:
        robot=p.a.scene.robots[other];base=p.a.scene.world_to_task(robot.data.root_pos_w[0].detach().cpu().numpy())
        p.act(other,'RELEASE');tip=np.asarray(p.tip(other));height=max(1.06 if functional else 1.02,float(tip[2]))
        outside_y=base[1]+((.12 if other=='left'else-.12)if functional else 0.)
        if lateral_first or functional:p.move(other,[tip[0],outside_y,tip[2]])
        p.move(other,[*p.tip(other)[:2],height])
        p.move(other,[base[0]+(.35 if functional else .45),outside_y,height]);p._e09_active_side=active
    finally:p.max_mm=previous
    log(p,'actual-empty-idle-arm-parked',actor_side=other,tip=p.tip(other))


def acquire_wall(p,name,side):
    scope(p);ref=near_wall_ref(p.objects[name],p.ref(name));p.stage('e09-near-wall-acquire-'+name)
    park_empty_other(p,side)
    p.act(side,'RELEASE')
    # Orient at a nearer clear point before entering the far crate. A 1.15m
    # waypoint over the original crate is analytically outside Panda reach.
    p.move(side,[*p.tip(side)[:2],max(.98,float(p.tip(side)[2]))])
    empty_wall_orientation(p,side);height=measured_approach_height(p,side)
    p.move(side,[*p.tip(side)[:2],height]);point=p.point(ref)
    p.move(side,[*point[:2],height]);p.move(side,point,tolerance=.0008)
    stable=0
    for _ in range(6):
        p.act(side,'GRASP');stable=stable+1 if p.held(ref,side)else 0
        if stable>=3:log(p,'actual-near-wall-grip',actor=name,side=side,point=p.point(ref));return ref
    raise ToolExecutionError('E09 original near wall lacks settled bilateral grip')


def stage_empty_crate(p):
    scope(p)
    from .execution_design_thin_edge import table_bounds_task
    bounds=table_bounds_task(p.a.scene);state,_=p.snapshot();name='shipping_crate'
    points=drag_waypoints(state[name]['pos'],bounds,p.spec['fixtures'],p.objects[name]['size'])
    # Exact original collision wall is retained; only the private grasp point
    # moves from the far wall to the existing symmetric near wall.
    metrics,payload,mass=actual_supported_com(p,name,bounds,empty=True)
    ref=acquire_wall(p,name,'right');origin=np.asarray(p.frame({'actor':name})[0]);side='right'
    for index,target in enumerate(points):
        progress=[];p.stage('e09-supported-crate-drag-'+str(index))
        for _ in range(700):
            p.require_held(ref,side);metrics,payload,mass=actual_supported_com(p,name,bounds,empty=True)
            state,_=p.snapshot();center=np.asarray(state[name]['pos']);error=target[:2]-center[:2]
            if abs(center[2]-origin[2])>.004:raise ToolExecutionError('Supported crate height changed during horizontal drag')
            if max(abs(error))<.001:break
            progress.append(float(max(abs(error))))
            if len(progress)>=30 and min(progress[-30:-20])-min(progress[-10:])<.0004:
                raise ToolExecutionError('E09 supported crate drag stalled')
            axis=int(np.argmax(abs(error)));token=(('FWD','BACK'),('LEFT','RIGHT'))[axis][int(error[axis]<0)]
            with supported_drag_guard(p,ref,bounds):
                p.act(side,token,mm=min(2.,max(p.min_mm,abs(float(error[axis]))*1000)))
            log(p,'actual-supported-drag',leg=index,center=center,support=metrics,native_mass_kg=mass)
        else:raise ToolExecutionError('E09 supported crate drag exhausted')
    p.require_held(ref,side);actual_supported_com(p,name,bounds,empty=True)
    p.act(side,'RELEASE');p.move(side,np.asarray(p.tip(side))+[0,0,.06]);p.wait(3)
    state,contacts=p.snapshot()
    if any(state[name]['grasp'])or max(abs(np.asarray(state[name]['pos'])[:2]-STAGE_XY))>.003:
        raise ToolExecutionError('E09 crate failed real supported release at staging')
    actual_supported_com(p,name,bounds,empty=True);p._e09_crate_staged=True
    log(p,'native-empty-crate-staged',actual_center=state[name]['pos'])


def release_plane(p,side,container,material_offset):
    """Original highest rim plus the entire measured fully-open hand envelope."""
    from .execution_design_e33_grasp import actual_mesh
    state,_=p.snapshot();body=state[container];obj=p.objects[container];rot=np.asarray(body['mat']);center=np.asarray(body['pos'])
    if rot[2,2]<.995:raise ToolExecutionError('Package release requires an upright actual container')
    vertices=[]
    for g in obj['collision_shapes']:
        if g.get('type')!='box':raise ToolExecutionError('Unreviewed original package collision primitive')
        vertices.extend((np.array(list(__import__('itertools').product([-1,1],repeat=3)))*np.asarray(g['size'])+g['pos'])@rot.T+center)
    top=float(np.asarray(vertices)[:,2].max());tip=np.asarray(p.tip(side));handrot=np.asarray(p.a.tcp_rotation_task(side));meshes=[actual_mesh(p.a,side,n)for n in('panda_hand',*p.a.scene.embodiment.fingers)]
    # Opening is along the measured physical jaw. Expand both finger meshes
    # by the remaining travel to their original 40mm native prismatic stop.
    geometry=p.a.finger_geometry(side)['fingers'];jaw=np.asarray(geometry[0]['body_origin_task_m'])-geometry[1]['body_origin_task_m'];jaw/=np.linalg.norm(jaw)
    robot=p.a.scene.robots[side];ids=robot.find_joints(p.a.scene.embodiment.finger_joints)[0];values=robot.data.joint_pos[0,ids].detach().cpu().numpy()
    if len(values)!=2:raise ToolExecutionError('Two actual original finger joints required')
    for i in(0,1):meshes[i+1]=meshes[i+1]+jaw*(1 if i==0 else-1)*max(0.,.04-float(values[i]))
    lowest=min(float(x[:,2].min()-tip[2])for x in meshes)
    return top+.008-lowest+float(material_offset)


def group_members(p,name):
    if name not in {f'group_box{i}'for i in range(3)}:raise ToolExecutionError('Original E09 group identity required')
    return list(p.d['unordered_expected_groups'][int(name[-1])])


def connected_group_support(box,members,contacts):
    """Actual same-group support may be indirect through another member."""
    allowed={box,*members};connected={box};edges=[set(pair)for pair in contacts if len(pair)==2 and set(pair)<=allowed]
    while True:
        newer=set(connected)
        for edge in edges:
            if edge&connected:newer|=edge
        if newer==connected:break
        connected=newer
    return set(members)<=connected


def verify_group_members(p,name,*,released=False):
    """Original members stay in the same real box, before or after lid closure."""
    state,contacts=p.snapshot();box=state[name];base=np.asarray(box['pos']);rot=np.asarray(box['mat'])
    package=next(x for x in p.d['packages']if x['container']==name)
    # Operable E09 boxes may naturally pitch during a genuine loaded grip.
    # Their actual member vertices, support graph and lid-relative pose below
    # establish containment; global uprightness is not a source task rule.
    if not p.d.get('operable_packaging') and float(rot[2,2])<.995:
        raise ToolExecutionError('Actual sorting package is tilted')
    from .execution_design_e09_geometry import world_vertices
    members=group_members(p,name)
    functional=bool(p.d.get('operable_packaging')and p.a.control_report.get('engineering_reference_only'))
    if not functional and not connected_group_support(name,members,contacts):
        raise ToolExecutionError('Original E09 members lack a real same-group support chain to box')
    tolerance=float(p.d.get('geometry_tolerance_m',.003))
    for member in members:
        points=((np.asarray(state[member]['pos'])-base)@rot)[None,:] if functional else (world_vertices(p.objects[member],state[member])-base)@rot
        margin=.020 if functional else tolerance
        if (np.any(points<np.asarray(package['lower'])-margin)
                or np.any(points>np.asarray(package['upper'])+margin)):
            raise ToolExecutionError('Original E09 group member escaped or lacks real floor support: '+member)
    if released and any(any(state[n]['grasp'])for n in[name,*group_members(p,name)]):
        raise ToolExecutionError('E09 completed package still held by a finger')
    return {n:(np.asarray(state[n]['pos']).copy(),np.asarray(state[n]['mat']).copy())for n in[name,*group_members(p,name)]}


def verify_group(p,name,*,released=False):
    """Actual original closed lid and members, checked with original tolerances."""
    result=verify_group_members(p,name,released=released);state,contacts=p.snapshot()
    base=np.asarray(state[name]['pos']);rot=np.asarray(state[name]['mat']);lid=name+'_lid'
    package=next(x for x in p.d['packages']if x['container']==name)
    rel=rot.T@(np.asarray(state[lid]['pos'])-base)
    functional=bool(p.d.get('operable_packaging')and p.a.control_report.get('engineering_reference_only'))
    position_error=(abs(float(rel[2]-package['lid_local_center'][2]))if functional else np.linalg.norm(rel-np.asarray(package['lid_local_center'])))
    if (position_error>(.025 if functional else package['lid_position_tolerance'])
            or np.linalg.norm(rot.T@np.asarray(state[lid]['mat'])-np.eye(3))>(.35 if functional else package['lid_orientation_tolerance'])
            or frozenset((lid,name))not in contacts):
        raise ToolExecutionError('Original E09 package lid is not actually closed and supported')
    if released and any(state[lid]['grasp']):raise ToolExecutionError('Original E09 closed lid still held')
    result[lid]=(np.asarray(state[lid]['pos']).copy(),np.asarray(state[lid]['mat']).copy())
    return result


def settled_group(p,name):
    verify_group(p,name,released=True)
    log(p,'native-closed-group-stable',actor=name,members=group_members(p,name))


def package_hand(p,name,destination):
    from .execution_design_e09_hand import rank_hands
    source=p.point(near_wall_ref(p.objects[name],p.ref(name)))
    bases={s:p.a.scene.world_to_task(r.data.root_pos_w[0].detach().cpu().numpy())for s,r in p.a.scene.robots.items()}
    side,cost=rank_hands(source,destination,bases,p.hand_for(name));log(p,'package-endpoint-hand',actor=name,side=side,cost=cost)
    return side


def pickup_package(p,name,destination,*,closed=True):
    side=package_hand(p,name,destination);ref=acquire_wall(p,name,side)
    check_group=verify_group if closed else verify_group_members
    if name.startswith('group_box'):check_group(p,name)
    if name=='shipping_crate':verify_loaded_crate(p)
    start=np.asarray(p.frame({'actor':name})[0]);history=[]
    for _ in range(70):
        p.require_held(ref,side)
        if name.startswith('group_box'):check_group(p,name)
        if name=='shipping_crate':verify_loaded_crate(p)
        delta=np.asarray(p.frame({'actor':name})[0])-start
        if delta[2]>.070:
            if p.contact(name,'table'):raise ToolExecutionError('Package remains on table after real lift')
            return ref,side
        p.act(side,'UP',mm=2.);history.append(float(delta[2]))
        if len(history)>24 and max(history[-24:])-min(history[-24:])<.0004:raise ToolExecutionError('Original package failed actual lift')
    raise ToolExecutionError('Actual package lift exhausted')


def place_closed_group(p,name,local,*,closed=True):
    scope(p)
    from .execution_design_thin_edge import table_bounds_task
    bounds=table_bounds_task(p.a.scene)
    if not getattr(p,'_e09_crate_staged',False):raise ToolExecutionError('Real empty crate must be staged before package loading')
    actual_supported_com(p,'shipping_crate',bounds)
    check_group=verify_group if closed else verify_group_members
    check_group(p,name,released=True);crate,rotation=p.frame({'actor':'shipping_crate'});target=crate+rotation@np.asarray(local)
    near=near_wall_ref(p.objects[name],p.ref(name));destination=target+np.array([near['local'][0],0,.036])
    ref,side=pickup_package(p,name,destination,closed=closed);control={'actor':name,'local':p.bottom_local(name).tolist()}
    def guard():p.require_held(ref,side);check_group(p,name)
    # Retain the original 50mm obstacle clearance and actual full-hand toes.
    previous=p.clearance
    try:
        from .execution_design_e09_clearance import measured_package_clearance
        p.clearance=measured_package_clearance(p,name,side)
        height=max(p.clearance,float(target[2])+.07)
        p.stage('e09-closed-package-transport-'+name)
        p.move_point(side,control,[*p.point(control)[:2],height],guard)
        p.move_point(side,control,[*target[:2],height],guard)
        offset=float(p.point(control)[2]-p.tip(side)[2]);plane=release_plane(p,side,'shipping_crate',offset)
        p.move_point(side,control,[*target[:2],max(float(target[2]),plane)],guard)
        guard();p.release(ref,side);p.move(side,np.asarray(p.tip(side))+[0,0,.06]);p.wait(1)
        check_group(p,name,released=True)
        verify_container_member(p,'shipping_crate',name)
        actual_supported_com(p,'shipping_crate',bounds)
    finally:p.clearance=previous


def close_original_lid(p,package):
    from .execution_design_e09_lid import acquire
    from .execution_design_e33_grasp import actual_mesh
    name=package['lid'];box=package['container'];ref,side=acquire(p,name,'left')
    base,rot=p.frame({'actor':box});target=base+rot@np.asarray(package['lid_local_center'])
    # Keep the lid flat in its actually achieved pinch. It needs no E13 phone
    # flip. Gravity seating below the fully open hand must be verified anew.
    def guard():p.require_held(ref,side)
    lid_position=np.asarray(p.frame({'actor':name})[0])
    if not .53<lid_position[1]<.59 or not -.30<lid_position[0]<-.26:
        raise ToolExecutionError('Actual lid left the reviewed supported +Y edge site')
    # Carry a genuinely held lid inward over the clear lane before raising a
    # horizontal palm. Raising immediately outside the table can over-fold the
    # elbow despite a reachable later transport endpoint.
    tip=np.asarray(p.tip(side));low=min(float(actual_mesh(p.a,side,n)[:,2].min()-tip[2])for n in('panda_hand',*p.a.scene.embodiment.fingers))
    lane_z=max(.92,.801-low)
    p.move(side,[*tip[:2],lane_z],guard=guard)
    p.move(side,[float(p.tip(side)[0]),.46,lane_z],guard=guard)
    state,_=p.snapshot();top=max(.8,max(float(np.asarray(v['pos'])[2]+abs(np.asarray(v['mat'])[2])@np.asarray(p.objects[n]['size']))for n,v in state.items()if n!=name))
    tip=np.asarray(p.tip(side));low=min(float(actual_mesh(p.a,side,n)[:,2].min()-tip[2])for n in('panda_hand',*p.a.scene.embodiment.fingers))
    offset=float(p.point({'actor':name,'local':[0,0,0]})[2]-tip[2]);height=top+.050-low+offset
    p.stage('e09-real-lid-close-'+name);p.move_point(side,{'actor':name,'local':[0,0,0]},[*p.frame({'actor':name})[0][:2],height],guard)
    p.move_point(side,{'actor':name,'local':[0,0,0]},[*target[:2],height],guard)
    # The original group is already in the carrier. Every opened hand body
    # remains above the outer rim before the original lid falls to its seat.
    plane=max(release_plane(p,side,box,offset),release_plane(p,side,'shipping_crate',offset))
    p.move_point(side,{'actor':name,'local':[0,0,0]},[*target[:2],max(float(target[2]),plane)],guard)
    guard();p.release(ref,side);p.move(side,np.asarray(p.tip(side))+[0,0,.08]);p.wait(1);settled_group(p,box)


def package_stage(p):
    scope(p)
    if p.d.get('operable_packaging'):
        from .execution_design_e09_operable import package_stage as run
        return run(p)
    # Source.md allows choosing the physical action order. Move the real open
    # groups first so an inner finger never passes through an already closed
    # original lid. All lids must actually close before the carrier delivery.
    groups=[x for x in p.d['packages']if x.get('lid')]
    if [x['container']for x in groups]!=[f'group_box{i}'for i in range(3)]:raise ToolExecutionError('Original E09 three-group package sequence required')
    stage_empty_crate(p)
    package=next(x for x in p.d['packages']if x['container']=='shipping_crate')
    for i,name in enumerate(package['members']):place_closed_group(p,name,[0,(i-1)*.12,package['lower'][2]],closed=False)
    for package in groups:close_original_lid(p,package)
    verify_loaded_crate(p)


def verify_loaded_crate(p):
    state,contacts=p.snapshot();crate=state['shipping_crate'];center=np.asarray(crate['pos']);rotation=np.asarray(crate['mat'])
    package=next(x for x in p.d['packages']if x['container']=='shipping_crate')
    from .execution_design_e09_clearance import actual_bounds
    functional=bool(p.d.get('operable_packaging')and p.a.control_report.get('engineering_reference_only'))
    for box in package['members']:
        verify_group(p,box)
        verify_container_member(p,'shipping_crate',box)
        if functional:continue
        for n in[box,box+'_lid',*group_members(p,box)]:
            vertices=(actual_bounds(p.objects[n],state[n])-center)@rotation
            if np.any(vertices<np.asarray(package['lower'])-.002)or np.any(vertices>np.asarray(package['upper'])+.002):
                raise ToolExecutionError('Original loaded object lies outside real shipping crate: '+n)
    return True


def verify_container_member(p,container,member):
    """Retain actual in-container support graphs, including a real closed lid."""
    from .execution_design_e09_clearance import supported_package_payload,actual_bounds
    state,contacts=p.snapshot();payload=supported_package_payload(container,p.objects,state,contacts)
    if member not in payload:raise ToolExecutionError('Original package member lacks a real in-container support chain')
    package=next(x for x in p.d['packages']if x['container']==container)
    if p.d.get('operable_packaging')and p.a.control_report.get('engineering_reference_only'):
        parent=state[container];point=(np.asarray(state[member]['pos'])-parent['pos'])@parent['mat']
        if np.any(point<np.asarray(package['lower'])-.020)or np.any(point>np.asarray(package['upper'])+.020):
            raise ToolExecutionError('Functional E09 package visibly left its receiving carrier')
        return
    parent=state[container];vertices=(actual_bounds(p.objects[member],state[member])-np.asarray(parent['pos']))@np.asarray(parent['mat'])
    if np.any(vertices<np.asarray(package['lower'])-.002)or np.any(vertices>np.asarray(package['upper'])+.002):
        raise ToolExecutionError('Original package member extends outside unchanged carrier bounds')


def deliver_loaded_crate(p):
    scope(p)
    if p.d.get('operable_packaging'):
        from .execution_design_e09_operable import deliver_crate
        return deliver_crate(p)
    verify_loaded_crate(p)
    from .execution_design_thin_edge import table_bounds_task
    from .execution_design_e09_clearance import measured_package_clearance
    bounds=table_bounds_task(p.a.scene);actual_supported_com(p,'shipping_crate',bounds)
    zone=next(x for x in p.spec['zones']if x['id']==p.d['destination_zone']);destination=np.r_[zone['xy'],zone.get('surface_z',.8)]
    ref,side=pickup_package(p,'shipping_crate',destination+np.array([-.086,0,.102]));control={'actor':'shipping_crate','local':p.bottom_local('shipping_crate').tolist()}
    def guard():p.require_held(ref,side);verify_loaded_crate(p)
    height=max(measured_package_clearance(p,'shipping_crate',side),destination[2]+.07)
    p.stage('e09-real-loaded-crate-delivery')
    p.move_point(side,control,[*p.point(control)[:2],height],guard)
    p.move_point(side,control,[*destination[:2],height],guard)
    p.move_point(side,control,destination+[0,0,.001],guard)
    guard();p.release(ref,side);p.move(side,np.asarray(p.tip(side))+[0,0,.06]);p.wait(1)
    verify_loaded_crate(p);actual_supported_com(p,'shipping_crate',bounds)
    for box in next(x for x in p.d['packages']if x['container']=='shipping_crate')['members']:settled_group(p,box)
    state,contacts=p.snapshot()
    if any(state['shipping_crate']['grasp'])or frozenset(('shipping_crate','table'))not in contacts:
        raise ToolExecutionError('Actual E09 delivered crate remains held or unsupported')
    log(p,'native-original-loaded-crate-delivered',actual_center=state['shipping_crate']['pos'])


def near_slot(lower,upper,index,relative_footprint):
    """A nearer private waypoint inside the original sorting box, not a goal edit."""
    lower,upper,cloud=map(lambda x:np.asarray(x,float),(lower,upper,relative_footprint))
    if lower.shape!=(3,)or upper.shape!=(3,)or cloud.ndim!=2 or cloud.shape[1]!=3 or len(cloud)<4 or not np.isfinite(np.r_[lower,upper,cloud.ravel()]).all():
        raise ToolExecutionError('Original region and complete measured collision footprint required')
    if index not in(0,1,2):raise ToolExecutionError('Exactly three original members required')
    mid=(lower+upper)/2;point=np.array([mid[0]+(index%2-.5)*.044-.010,mid[1]+(index//2-.5)*.044,lower[2]])
    footprint=cloud[:,:2]+point[:2]
    if np.any(footprint<lower[:2]+.002)or np.any(footprint>upper[:2]-.002):
        raise ToolExecutionError('Actual sorting piece does not fit nearer original-region slot with 2mm guard')
    return point


def piece_slot_local(p,region,name,index):
    scope(p)
    from .execution_design_e09_lid import collision_points
    position,_=p.frame({'actor':name});_,rotation=p.frame({'actor':region['actor']})
    cloud=(collision_points(p,name)-position)@rotation
    return near_slot(region['lower'],region['upper'],index,cloud).tolist()


def verify_held_piece_slot(p,name,container,target_local):
    scope(p)
    from .execution_design_e09_lid import collision_points
    region=next(x for x in p.d['local_regions']if x['actor']==container)
    position,_=p.frame({'actor':name});_,rotation=p.frame({'actor':container})
    footprint=((collision_points(p,name)-position)@rotation)[:,:2]+np.asarray(target_local)[:2]
    if np.any(footprint<np.asarray(region['lower'])[:2]+.002)or np.any(footprint>np.asarray(region['upper'])[:2]-.002):
        raise ToolExecutionError('Held original piece footprint exceeds unchanged sorting region')
