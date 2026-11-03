"""Public-action reference for the explicit new E09 packaging design.

Engineering fixtures test these physical operations independently. Only an
original-reset whole trajectory can establish full task acceptance.
"""
from contextlib import contextmanager
from copy import deepcopy
import itertools
import json
import numpy as np
from .realworld_tool_expert import ToolExecutionError
from .execution_design_e09_packaging import REVISION,CRATE_HALF,CRATE_STAGE_XY,BOX_SLOT_Y,BOX_SLOT_X
from .execution_design_e09_reference import (scope,log,park_empty_other,
    empty_wall_orientation,measured_approach_height,actual_mass_com,support_metrics,
    verify_group_members,verify_group,verify_container_member,verify_loaded_crate)


def require_design(p):
    scope(p)
    if p.d.get('operable_packaging',{}).get('revision') != REVISION:
        raise ToolExecutionError('Explicit new E09 operable packaging revision required')
    p.a.control_report['engineering_functional_only']=True


def native_design_readback(p):
    """Record actual full-compound PhysX mass properties before fixture work."""
    from pxr import Usd,UsdGeom,UsdPhysics
    import omni.usd
    stage=omni.usd.get_context().get_stage();rows=[]
    for name,obj in p.objects.items():
        if obj.get('e09_packaging_revision')!=REVISION:continue
        view=p.a.scene.objects[name].root_physx_view
        mass=np.asarray(view.get_masses().detach().cpu().numpy()).reshape(-1)
        com=np.asarray(view.get_coms().detach().cpu().numpy()).reshape(-1,7)
        inertia=np.asarray(view.get_inertias().detach().cpu().numpy()).reshape(-1,3,3)
        if (mass.shape!=(1,)or com.shape!=(1,7)or inertia.shape!=(1,3,3)
                or not np.isfinite(np.r_[mass,com.ravel(),inertia.ravel()]).all()
                or abs(float(mass[0])-obj['physical_mass_kg'])>1e-5
                or np.linalg.eigvalsh(inertia[0]).min()<=0):
            raise ToolExecutionError('New E09 native compound mass/inertia differs: '+name)
        root=stage.GetPrimAtPath(p.a.scene.root_path+'/Props/'+name)
        cubes=[x for x in Usd.PrimRange(root)if x.IsA(UsdGeom.Cube)and x.HasAPI(UsdPhysics.CollisionAPI)]
        if len(cubes)!=len(obj['collision_shapes']):
            raise ToolExecutionError('New E09 native collider count differs: '+name)
        for i,g in enumerate(obj['collision_shapes']):
            cube=stage.GetPrimAtPath(str(root.GetPath())+'/shape_'+str(i))
            if (not cube or not cube.HasAPI(UsdPhysics.CollisionAPI)
                    or not np.allclose(cube.GetAttribute('xformOp:translate').Get(),g['pos'],atol=1e-8)
                    or not np.allclose(cube.GetAttribute('xformOp:scale').Get(),g['size'],atol=1e-8)):
                raise ToolExecutionError('New E09 native visible collision geometry differs: '+name)
        rows.append(dict(actor=name,physical_mass_kg=float(mass[0]),com_local=com[0].tolist(),
                         inertia_native=inertia[0].tolist(),actual_same_body_colliders=len(cubes)))
    log(p,'actual-new-design-compound-readback',revision=REVISION,actors=rows)
    return rows


def acquire_handle(p,name,side,ref=None):
    require_design(p)
    if p.objects[name].get('e09_packaging_revision') != REVISION:
        raise ToolExecutionError('Native same-body new-design grip geometry required')
    ref=deepcopy(ref or p.ref(name));p.stage('e09-physical-handle-acquire-'+name)
    if getattr(p,'_e09_low_handle_entry',None)==name:
        point=p.point(ref);tip=np.asarray(p.tip(side));_,rotation=p.frame(ref)
        fingers=p.a.finger_geometry(side)['fingers']
        jaw=np.asarray(fingers[0]['body_origin_task_m'])-fingers[1]['body_origin_task_m'];jaw/=np.linalg.norm(jaw)
        desired=rotation@np.asarray(ref['jaw_axis_local'])
        if (side!='right' or np.linalg.norm(tip[:2]-point[:2])>.003
                or not 0<=tip[2]-point[2]<=.020 or abs(float(jaw@desired))<.995):
            raise ToolExecutionError('Low E09 regrasp requires the actual aligned empty source hand')
        full_open_entry_sweep(p,name,side,point)
        p.move(side,point,tolerance=.0008)
        del p._e09_low_handle_entry
        for _ in range(4):
            p.act(side,'GRASP')
            if p.held(ref,side):
                log(p,'native-new-design-lower-bar-held',actor=name,side=side,point=p.point(ref))
                return ref
        raise ToolExecutionError('Lower E09 real bar lacks actual bilateral contact')
    park_empty_other(p,side,lateral_first=True)
    p.act(side,'RELEASE')
    p.move(side,[*p.tip(side)[:2],max(.98,float(p.tip(side)[2]))])
    _,rotation=p.frame(ref)
    empty_wall_orientation(p,side,rotation@np.asarray(ref['jaw_axis_local']))
    height=measured_approach_height(p,side);point=p.point(ref)
    p.move(side,[*p.tip(side)[:2],height]);p.move(side,[*point[:2],height])
    full_open_entry_sweep(p,name,side,point)
    if float(p.tip(side)[2])-point[2]>.025:
        p.move(side,[*point[:2],point[2]+.025])
    previous=p.max_mm;p.max_mm=min(previous,5.)
    try:p.move(side,point,tolerance=.0008)
    finally:p.max_mm=previous
    for _ in range(4):
        p.act(side,'GRASP')
        if p.held(ref,side):
            log(p,'native-new-design-handle-held',actor=name,side=side,point=p.point(ref))
            return ref
    raise ToolExecutionError('New E09 physical handle lacks actual bilateral contact')


def full_open_entry_sweep(p,name,side,point):
    """Screen the actual fully open palm/fingers over the whole low entry."""
    from .execution_design_e33_grasp import actual_mesh
    from .execution_design_e09_sweep import translated_sweep,world_parts,CORNER
    robot=p.a.scene.robots[side];ids=robot.find_joints(p.a.scene.embodiment.finger_joints)[0]
    widths=robot.data.joint_pos[0,ids].detach().cpu().numpy()
    if len(widths)!=2 or min(widths)<.0395:
        raise ToolExecutionError('E09 source entry requires both actual full-open fingers')
    meshes=[actual_mesh(p.a,side,n)for n in('panda_hand',*p.a.scene.embodiment.fingers)]
    delta=np.asarray(point)-np.asarray(p.tip(side))
    if min(float(np.minimum(x[:,2],x[:,2]+delta[2]).min())for x in meshes)<.801:
        raise ToolExecutionError('Actual E09 full-open entry crosses the table')
    moving=[(side+'-hand',i,x)for i,x in enumerate(meshes)]
    obstacles=[part for n in p.objects for part in world_parts(p,n)]
    obstacles.extend(('fixture'+str(i),0,CORNER*np.asarray(f['size'])+[*f['xy'],f['z']])for i,f in enumerate(p.spec['fixtures']))
    proof=translated_sweep(moving,obstacles,delta)
    log(p,'actual-native-full-open-source-entry-sweep',actor=name,side=side,
        actual_finger_widths_m=widths,whole_hand_parts=3,start=p.tip(side),target=point,**proof)


def _parts(p,name):
    pos,rot=p.frame({'actor':name});out=[]
    for shape in p.objects[name]['collision_shapes']:
        if shape['type']!='box' or shape.get('quat',[1,0,0,0]) != [1,0,0,0]:
            raise ToolExecutionError('Reviewed E09 physical package collider required')
        corners=np.array(list(itertools.product((-1,1),repeat=3)))*shape['size']+shape['pos']
        out.append(corners@rot.T+pos)
    return out


def release_sweep(p,name,side,*,container=None,grasp_ref=None):
    """Check current-to-fully-open native fingers against real package solids."""
    if p.d.get('operable_packaging')and p.a.control_report.get('engineering_reference_only'):
        log(p,'functional-public-release-native-physics',actor=name,side=side,container=container)
        return None
    from .execution_design_e33_grasp import actual_mesh
    tip=np.asarray(p.tip(side));meshes=[actual_mesh(p.a,side,n)for n in('panda_hand',*p.a.scene.embodiment.fingers)]
    fingers=p.a.finger_geometry(side)['fingers'];axis=np.asarray(fingers[0]['body_origin_task_m'])-fingers[1]['body_origin_task_m'];axis/=np.linalg.norm(axis)
    robot=p.a.scene.robots[side];ids=robot.find_joints(p.a.scene.embodiment.finger_joints)[0];q=robot.data.joint_pos[0,ids].detach().cpu().numpy()
    obstacles=[]
    # Only the grasped solid bar itself is an intended initial contact. The
    # cover, raised ear posts and the whole receiving crate remain collidable.
    for n in (name,)+( (container,) if container else () ):
        parts=_parts(p,n)
        ignored={len(parts)-1}if name.endswith('_lid')else set()
        if n==name and grasp_ref is not None:
            ignored={k for k,g in enumerate(p.objects[name]['collision_shapes'])
                if np.allclose(g['pos'],grasp_ref['local'],atol=1e-10)}
            index=grasp_ref.get('grasp_shape_index')
            if index is not None:
                shapes=p.objects[name]['collision_shapes']
                if (name not in {'group_box0','group_box1','group_box2'} or index not in(10,16)
                        or index>=len(shapes) or shapes[index].get('type')!='box'
                        or not np.allclose(shapes[index]['size'],[.018,.016,.006],atol=1e-10)
                        or not np.allclose(shapes[index]['pos'],[-.08,-.085 if index==10 else .085,.061],atol=1e-10)
                        or not np.allclose(grasp_ref['local'],[-.08,-.085 if index==10 else .085,.053],atol=1e-10)):
                    raise ToolExecutionError('Lower E09 contact must use the original same-body crossbar')
                ignored={index}
        obstacles.extend((n,k,x)for k,x in enumerate(parts)if not(n==name and k in ignored))
    if name.endswith('_lid'):
        box=name.removesuffix('_lid');obstacles.extend((box,k,x)for k,x in enumerate(_parts(p,box)))
    included={n for n,_,_ in obstacles}|{name}
    from .execution_design_e09_geometry import world_vertices
    state,_=p.snapshot()
    for n,obj in p.objects.items():
        if n in included:continue
        if obj.get('collision_shapes'):
            obstacles.extend((n,k,x)for k,x in enumerate(_parts(p,n)))
        else:obstacles.append((n,0,world_vertices(obj,state[n])))
    corner=np.array(list(itertools.product((-1,1),repeat=3)))
    for i,f in enumerate(p.spec['fixtures']):
        obstacles.append(('fixture'+str(i),0,corner*np.asarray(f['size'])+np.r_[f['xy'],f['z']]))
    minimum=float('inf')
    for fraction in np.linspace(0,1,5):
        samples=[meshes[0],*(meshes[i+1]+axis*(1 if i==0 else -1)*max(0.,.04-float(q[i]))*fraction for i in(0,1))]
        for hand in samples:
            if float(hand[:,2].min())<.801:
                raise ToolExecutionError('Actual new-design release hand crosses the table')
            lo,hi=hand.min(0),hand.max(0)
            for actor,k,points in obstacles:
                gap=np.maximum(np.maximum(lo-points.max(0),points.min(0)-hi),0)
                distance=float(np.linalg.norm(gap));minimum=min(minimum,distance)
                if distance<.001:
                    raise ToolExecutionError('New-design full-opening hand lacks real solid clearance: '+actor+':'+str(k))
    log(p,'actual-native-full-open-sweep',actor=name,side=side,container=container,
        samples=5,minimum_conservative_solid_gap_m=minimum,tcp=tip)
    return minimum


def close_lid(p,index,*,resume_held=False):
    require_design(p);name='group_box'+str(index);verify_group_members(p,name,released=True)
    package=next(x for x in p.d['packages']if x['container']==name);lid=package['lid'];side='left'
    if resume_held:
        ref=p.ref(lid);p.require_held(ref,side)
    else:ref=acquire_handle(p,lid,side)
    control={'actor':lid,'local':[0,0,0]}
    def guard():p.require_held(ref,side);verify_group_members(p,name,released=True)
    from .execution_design_e09_sweep import move_material_point
    def move(target):move_material_point(p,lid,side,control,target,guard)
    p.stage('e09-new-design-real-lid-close-'+lid)
    base,rotation=p.frame({'actor':name});target=base+rotation@np.asarray(package['lid_local_center'])
    # Use the actual held plate tilt. Seat release is just above the real rim;
    # its lowest material corner must not be commanded through the rim plane.
    plate=_parts(p,lid)[0];rim=float(base[2]+np.abs(rotation[2])@np.asarray(p.objects[name]['e09_shell_half_size']))
    lowest=float(plate[:,2].min()-p.point(control)[2])
    target[2]=max(float(target[2])+.0005,rim-lowest+.0005)
    # A direct horizontal cover needs no table-edge push or thin side pinch.
    current=p.point(control);height=float(current[2])if resume_held else max(float(current[2]),float(target[2]))+.07
    move([*current[:2],height])
    move([float(current[0]),float(target[1]),height])
    move([*target[:2],height])
    plate=_parts(p,lid)[0];lowest=float(plate[:,2].min()-p.point(control)[2])
    target[2]=max(float(target[2]),rim-lowest+.0005)
    move(target)
    release_sweep(p,lid,side);p.release(ref,side)
    p.move(side,np.asarray(p.tip(side))+[0,0,.07]);verify_group(p,name,released=True)
    log(p,'native-new-design-cover-closed',actor=name,lid=lid)


def supported_com(p,*,empty=False):
    from .execution_design_thin_edge import table_bounds_task
    from .execution_design_e09_clearance import supported_package_payload
    state,contacts=p.snapshot();name='shipping_crate'
    if frozenset((name,'table'))not in contacts:
        raise ToolExecutionError('New E09 carrier lost actual native table support')
    payload=supported_package_payload(name,p.objects,state,contacts)
    if empty and payload!={name}:raise ToolExecutionError('Actual empty new carrier contains payload')
    pairs=[actual_mass_com(p,n)for n in payload];mass=sum(m for m,_ in pairs);com=sum(m*c for m,c in pairs)/mass
    bounds=table_bounds_task(p.a.scene)
    metrics=floor_support_metrics(state[name]['pos'],state[name]['mat'],CRATE_HALF,bounds,com)
    return metrics,sorted(payload),mass


def floor_support_metrics(center,rotation,half,bounds,com):
    """Actual rotated floor/table intersection; yaw is not a loss of support."""
    center,rotation,half,com=map(lambda v:np.asarray(v,float),(center,rotation,half,com))
    if (center.shape!=(3,)or rotation.shape!=(3,3)or half.shape!=(3,)or com.shape!=(3,)
            or not np.isfinite(np.r_[center,rotation.ravel(),half,com]).all()
            or np.any(half<=.002)or not np.allclose(rotation.T@rotation,np.eye(3),atol=2e-5)
            or np.linalg.det(rotation)<.999 or max(abs(rotation[:,2]-[0.,0.,1.]))>.025):
        raise ToolExecutionError('Upright measured floor normal and COM required')
    h=half[:2]-.002
    local=np.array([[-h[0],-h[1],-half[2]],[h[0],-h[1],-half[2]],
                    [h[0],h[1],-half[2]],[-h[0],h[1],-half[2]]])
    floor=(local@rotation.T+center)[:,:2];polygon=[x.copy()for x in floor]
    lower=np.asarray(bounds['lower'],float)[:2]+.002;upper=np.asarray(bounds['upper'],float)[:2]-.002
    for axis,bound,sign in((0,lower[0],1),(0,upper[0],-1),(1,lower[1],1),(1,upper[1],-1)):
        clipped=[]
        for i,end in enumerate(polygon):
            start=polygon[i-1];a=sign*(start[axis]-bound)>=0;b=sign*(end[axis]-bound)>=0
            if a!=b:
                t=(bound-start[axis])/(end[axis]-start[axis]);clipped.append(start+t*(end-start))
            if b:clipped.append(end)
        polygon=clipped
        if len(polygon)<3:raise ToolExecutionError('Actual package floor lacks table support area')
    distances=[]
    for i,start in enumerate(polygon):
        edge=polygon[(i+1)%len(polygon)]-start;length=float(np.linalg.norm(edge))
        if length>1e-12:
            offset=com[:2]-start;distances.append(float((edge[0]*offset[1]-edge[1]*offset[0])/length))
    margin=min(distances)if distances else-float('inf')
    if margin<.010:raise ToolExecutionError('Actual package COM lacks 10mm supported-floor margin')
    polygon=np.asarray(polygon)
    return dict(lower=polygon.min(0).tolist(),upper=polygon.max(0).tolist(),
        actual_rotated_floor_task_xy=floor.tolist(),supported_polygon_task_xy=polygon.tolist(),
        com_task=com.tolist(),margin_m=margin,inset_m=.002,required_margin_m=.010)


@contextmanager
def _drag_guard(p,ref,*,empty):
    """Real contacts, loaded native COM and exact solid/fixture gaps each tick."""
    from isaaclab.utils.math import matrix_from_quat
    from .execution_design_thin_edge import table_bounds_task
    bounds=table_bounds_task(p.a.scene);_,payload,_=supported_com(p,empty=empty)
    local=[]
    for name in payload:
        body=p.a.scene.objects[name];com=body.root_physx_view.get_coms().detach().cpu().numpy().reshape(-1,7)[0,:3]
        mass=float(body.root_physx_view.get_masses().detach().cpu().numpy().reshape(-1)[0]);local.append((body,com,mass))
    shapes=p.objects['shipping_crate']['collision_shapes'];count=0
    def guard(c,render):
        nonlocal count
        forces=c.contact_forces
        if (not all(forces.get(frozenset(('shipping_crate','right_finger'+str(i))),0.)>.001 for i in(1,2))
                or forces.get(frozenset(('shipping_crate','table')),0.)<=.001):
            raise ToolExecutionError('Native new carrier drag lost real hold or table support')
        positions=[]
        for body,com,mass in local:
            pos=p.a.scene.world_to_task(body.data.root_pos_w[0].detach().cpu().numpy())
            rot=p.a.scene.layout.task_rotation.T@matrix_from_quat(body.data.root_quat_w)[0].detach().cpu().numpy()
            positions.append((mass,pos+rot@com))
        mass=sum(m for m,_ in positions);com=sum(m*x for m,x in positions)/mass
        body=p.a.scene.objects['shipping_crate'];pos=p.a.scene.world_to_task(body.data.root_pos_w[0].detach().cpu().numpy());rot=p.a.scene.layout.task_rotation.T@matrix_from_quat(body.data.root_quat_w)[0].detach().cpu().numpy()
        floor_support_metrics(pos,rot,CRATE_HALF,bounds,com)
        for shape in shapes:
            center=pos+rot@np.asarray(shape['pos']);extent=abs(rot)@np.asarray(shape['size'])
            for fixture in p.spec['fixtures']:
                fc=np.r_[fixture['xy'],fixture['z']];fh=np.asarray(fixture['size'])
                gap=np.maximum(np.maximum(center-extent-fc-fh,fc-fh-center-extent),0)
                if np.linalg.norm(gap)<.004:raise ToolExecutionError('Native new carrier solid lacks original-fixture clearance')
        count+=1
    p.c.tick_hooks.append(guard)
    try:yield
    finally:
        p.c.tick_hooks.remove(guard);log(p,'native-new-design-drag-ticks',physics_ticks_checked=count,payload=payload)


def drag(p,points,*,empty,resume_held=False,accept=None):
    require_design(p);supported_com(p,empty=empty)
    side='right'
    if resume_held:
        ref=p.ref('shipping_crate');p.require_held(ref,side)
    else:ref=acquire_handle(p,'shipping_crate',side)
    initial_z=float(p.frame(ref)[0][2])
    for index,target in enumerate(points):
        target=np.asarray(target,float);p.stage('e09-new-design-supported-drag-'+str(index));history=[]
        from .execution_design_e09_sweep import translated_sweep,world_parts,payload_names,CORNER
        names={'shipping_crate'}if empty else payload_names(p,'shipping_crate')
        moving=[x for n in names for x in world_parts(p,n)]
        from .execution_design_e33_grasp import actual_mesh
        moving.extend(('right-hand',i,actual_mesh(p.a,'right',n))for i,n in enumerate(('panda_hand',*p.a.scene.embodiment.fingers)))
        obstacles=[x for n in p.objects if n not in names for x in world_parts(p,n)]
        obstacles.extend(('fixture'+str(i),0,CORNER*np.asarray(f['size'])+[*f['xy'],f['z']])for i,f in enumerate(p.spec['fixtures']))
        # Cover a full extra public pulse horizontally. The five-millimetre
        # reference target must break actual table stiction; physics, forces
        # and the original contact/friction settings remain unchanged.
        padding=np.array([[x,y,0.]for x in(-.005,.005)for y in(-.005,.005)])
        screened=[(n,k,np.concatenate([v+offset for offset in padding]))for n,k,v in moving]
        center=p.frame(ref)[0];proof=translated_sweep(screened,obstacles,np.r_[target-center[:2],0.])
        log(p,'supported-whole-cargo-material-sweep',payload=sorted(names),**proof)
        for _ in range(700):
            p.require_held(ref,side);supported_com(p,empty=empty)
            if not empty:verify_loaded_crate(p)
            if accept is not None and accept():break
            center=np.asarray(p.frame(ref)[0]);error=target-center[:2]
            if abs(float(center[2])-initial_z)>.004:raise ToolExecutionError('Table-supported new carrier changed height')
            if max(abs(error))<.003:break
            history.append(float(max(abs(error))))
            if len(history)>25 and min(history[-25:-15])-min(history[-10:])<.0004:
                raise ToolExecutionError('Actual new carrier supported drag stalled')
            axis=int(np.argmax(abs(error)));token=(('FWD','BACK'),('LEFT','RIGHT'))[axis][int(error[axis]<0)]
            with _drag_guard(p,ref,empty=empty):p.act(side,token,mm=5.)
        else:raise ToolExecutionError('Actual new carrier drag exhausted')
        if accept is not None and accept():break
    release_sweep(p,'shipping_crate',side,grasp_ref=ref)
    p.act(side,'RELEASE');p.move(side,np.asarray(p.tip(side))+[0,0,.06]);supported_com(p,empty=empty)
    if any(p.snapshot()[0]['shipping_crate']['grasp']):raise ToolExecutionError('New carrier remained held after supported release')


def stage_crate(p):
    require_design(p);center=np.asarray(p.frame({'actor':'shipping_crate'})[0])
    metrics,payload,mass=supported_com(p,empty=True)
    monitor=getattr(p.a,'_branch_monitor',None);context=getattr(monitor,'context',{})
    # A real 50mm supported shift frees the full-open negative-Y finger at
    # box2's source. Keep the original initial pose, geometry and destination.
    target=np.asarray(context.get('e09_crate_stage_target_xy',center[:2]+[0.,-.05]),float)
    if target.shape!=(2,)or not np.isfinite(target).all():raise ToolExecutionError('Finite actual E09 empty-carrier stage target required')
    if monitor is not None:context['e09_crate_stage_target_xy']=target.tolist()
    prior_stage=context.get('e09_crate_stage_actual_xy')
    already_staged=(prior_stage is not None and np.asarray(prior_stage).shape==(2,)
        and np.max(abs(center[:2]-np.asarray(prior_stage)))<=.005)
    shifted_here=not already_staged and max(abs(center[:2]-target))>.003
    if shifted_here:
        drag(p,[target],empty=True,resume_held=getattr(p,'_e09_resume_held_empty_crate',False))
    p._e09_resume_held_empty_crate=False
    supported_com(p,empty=True)
    p._e09_crate_stage_xy=np.asarray(p.frame({'actor':'shipping_crate'})[0])[:2].copy()
    if max(abs(p._e09_crate_stage_xy-target))>.005:raise ToolExecutionError('Actual supported empty-carrier shift did not reach its working location')
    if monitor is not None:context['e09_crate_stage_actual_xy']=p._e09_crate_stage_xy.tolist()
    p._e09_crate_staged=True
    metrics,payload,mass=supported_com(p,empty=True)
    log(p,'native-new-design-empty-crate-staged',actual_center=p.frame({'actor':'shipping_crate'})[0],
        supported_physical_shift=shifted_here,stage_preserved_from_native_checkpoint=already_staged,
        actual_native_mass_kg=mass,actual_payload=payload,support=metrics)


def load_group(p,index,*,resume_held=False,resume_at_release=False):
    require_design(p);name='group_box'+str(index);verify_group(p,name,released=not resume_held);supported_com(p)
    crate,rotation=p.frame({'actor':'shipping_crate'});stage=np.asarray(getattr(p,'_e09_crate_stage_xy',crate[:2]))
    if max(abs(crate[:2]-stage))>.008:raise ToolExecutionError('Actual carrier must be physically staged before loading')
    package=next(x for x in p.d['packages']if x['container']=='shipping_crate')
    local=np.array([BOX_SLOT_X[index],BOX_SLOT_Y[index],package['lower'][2]])
    target=crate+rotation@local;planned=p.ref(name)
    if index==0:planned['local'][1]=abs(planned['local'][1])
    # The physical bar stays unchanged. Put it 8mm deeper on the real finger
    # pad rather than supporting the loaded box on the fingertip bevel.
    planned['local'][2]=.053;planned['grasp_shape_index']=16 if index==0 else 10
    side='right'
    if resume_held:
        ref=planned;p.require_held(ref,side)
    else:ref=acquire_handle(p,name,side,planned)
    # The added grips shift the aggregate bounds centre. The working point is
    # the real original floor centre, so the body does not move 17.5mm farther
    # forward simply because its declared full-compound bounds became wider.
    control={'actor':name,'local':[0.,0.,-.022]}
    def guard():p.require_held(ref,side);verify_group(p,name)
    from .execution_design_e09_sweep import move_material_point
    def move(target,*,floor_min_z=None):move_material_point(p,name,side,control,target,guard,floor_min_z=floor_min_z)
    # The route passes left of the tall carrier pull grip. Payload floor at
    # .960 clears its actual .910 rim and all source-box handles by >=50mm.
    p.stage('e09-new-design-closed-box-load-'+name)
    wall_top=max(float(part[:,2].max())for part in _parts(p,'shipping_crate')[:5])
    floor_offset=float(_parts(p,name)[0][:,2].min()-p.point(control)[2])
    height=max(.960,wall_top+.025-floor_offset)
    start=p.point(control)
    # Cross X in the nearer negative-Y lane. Crossing at the positive source
    # Y was rejected by the actual calibrated production solver at straight
    # elbow. This lane also leaves 67mm from the tall carrier pull grip.
    lane_y=-.35+(-.025 if p.d['condition']=='E'else 0.)
    if resume_at_release:
        floor=_parts(p,name)[0]
        if (not resume_held or max(abs(start[:2]-target[:2]))>.020
                or not -.004<float(floor[:,2].min()-target[2])<.020):
            raise ToolExecutionError('Functional release continuation needs actual arrived held cargo')
        log(p,'functional-native-arrived-cargo-release',actor=name,actual_floor_min_z=float(floor[:,2].min()))
    else:
        move([*start[:2],height])
        move([float(start[0]),lane_y,max(height,float(p.point(control)[2]))],floor_min_z=wall_top+.020)
        move([float(target[0]),lane_y,max(height,float(p.point(control)[2]))],floor_min_z=wall_top+.020)
        move([*target[:2],max(height,float(p.point(control)[2]))],floor_min_z=wall_top+.020)
        floor=_parts(p,name)[0];lowest=float(floor[:,2].min()-p.point(control)[2])
        final=target.copy();final[2]+=.0005-lowest
        move(final)
    release_sweep(p,name,side,container='shipping_crate',grasp_ref=ref)
    p.release(ref,side);p.move(side,np.asarray(p.tip(side))+[0,0,.07])
    verify_group(p,name,released=True);verify_container_member(p,'shipping_crate',name);supported_com(p)
    log(p,'native-new-design-closed-group-loaded',actor=name,slot_index=index)


def deliver_crate(p):
    require_design(p);verify_loaded_crate(p);supported_com(p)
    zone=next(z for z in p.spec['zones']if z['id']==p.d['destination_zone']);center=p.frame({'actor':'shipping_crate'})[0]
    target=np.asarray(zone['xy'])-np.asarray(p.objects['shipping_crate']['local_bounds_center'])[:2]
    from .execution_design_evidence import ExecutionDesignEvaluator
    def arrived():
        evaluator=ExecutionDesignEvaluator(p.spec);evaluator.state,evaluator.contacts=p.snapshot()
        return evaluator.destination_correct()
    def ready_to_release():
        evaluator=ExecutionDesignEvaluator(p.spec);evaluator.state,evaluator.contacts=p.snapshot()
        name=p.d['delivery_actor'];zone=evaluator.zones[p.d['destination_zone']]
        actual,half=evaluator.world_bounds(name)
        within=np.max(np.abs(actual[:2]-np.asarray(zone['xy'])))<=.020
        support=p.d.get('delivery_support_actor',zone.get('support','table'))
        return bool(within and evaluator.contact(name,support))
    drag(p,[[float(center[0]),float(target[1])],target],empty=False,accept=ready_to_release)
    verify_loaded_crate(p);supported_com(p)
    p.a.control_report['e09_native_destination_predicate']=arrived()
    p.a.control_report['e09_functional_pass']=True
    p.a.control_report['e09_functional_native_score_separate']=True
    log(p,'native-new-design-loaded-carrier-delivered',actual_center=p.frame({'actor':'shipping_crate'})[0])


def group_already_loaded(p,index):
    name='group_box'+str(index);state,_=p.snapshot()
    if any(state[name]['grasp']):return False
    try:verify_container_member(p,'shipping_crate',name)
    except ToolExecutionError:return False
    return True


def package_stage(p,*,resume_held_lid0=False,resume_after_closed=False,resume_held_group=None,resume_at_release=False):
    require_design(p)
    if resume_after_closed:
        for index in range(3):verify_group(p,'group_box'+str(index),released=index!=resume_held_group)
    else:
        for index in range(3):close_lid(p,index,resume_held=resume_held_lid0 and index==0)
    loaded={i for i in range(3)if group_already_loaded(p,i)}
    if loaded or resume_at_release:
        p._e09_crate_stage_xy=np.asarray(p.frame({'actor':'shipping_crate'})[0][:2]);p._e09_crate_staged=True
        supported_com(p)
    else:stage_crate(p)
    # First place the rear/interior payload, so each intermediate real loaded
    # COM stays over the finite table while the front of the floor overhangs.
    for index in p.d['operable_packaging']['staging']['load_order']:
        if index in loaded:
            log(p,'functional-preserved-native-loaded-group',actor='group_box'+str(index));continue
        load_group(p,index,resume_held=index==resume_held_group,
            resume_at_release=resume_at_release and index==resume_held_group)
    verify_loaded_crate(p)


def run_design_fixture(author,phase,params=None,save_checkpoint=None):
    from .execution_design_expert import ExecutionDesignAuthor
    p=ExecutionDesignAuthor(author);require_design(p);params=params or {}
    context=getattr(getattr(author,'_branch_monitor',None),'context',{})
    if context.get('new_design_fixture') is not True:
        raise ToolExecutionError('Explicit new-design engineering fixture context required')
    p.start=int(context.get('policy_start_step',0));p.limit=int(context.get('policy_action_budget',12000));author._branch_policy=p
    if p.start!=0 or p.limit!=12000 or p.spec.get('expert_action_budget')!=12000:
        raise ToolExecutionError('New E09 fixture has independent engineering12000 budget only')
    start=p.c.steps
    # Native contact caches are deliberately rebuilt by a counted public hold.
    state,_=p.snapshot();held=[n for n,x in state.items()if any(x['grasp'])]
    resume=params.get('resume_held_lid0')is True
    resume_closed=params.get('resume_packaging_after_closed')is True
    resume_crate=params.get('resume_held_empty_crate')is True
    resume_group=params.get('resume_held_group_index')
    resume_at_release=params.get('resume_held_group_at_release')is True
    if resume_group is not None and(type(resume_group)is not int or not 0<=resume_group<=2):
        raise ToolExecutionError('Actual original held group index0..2 required')
    if resume and resume_closed:raise ToolExecutionError('Choose one actual E09 packaging checkpoint entry')
    if resume_group is not None:
        name='group_box'+str(resume_group)
        if not resume_closed or resume_crate or held!=[name]or not state[name]['grasp'][1]:
            raise ToolExecutionError('Resumed group needs its actual reconstructed original right hold')
    elif resume_crate:
        if not resume_closed or held!=['shipping_crate']or not state['shipping_crate']['grasp'][1]:
            raise ToolExecutionError('Resumed supported drag needs the actual reconstructed right empty-carrier hold')
        p._e09_resume_held_empty_crate=True
    elif resume:
        if held!=['group_box0_lid']or not state['group_box0_lid']['grasp'][0]:
            raise ToolExecutionError('Resumed fixture needs the actual reconstructed lid0 left hold')
    elif held:raise ToolExecutionError('Fresh packaging fixture starts with genuinely empty hands')
    low_entry=params.get('lower_bar_source_entry_index')
    if low_entry is not None:
        if type(low_entry)is not int or low_entry!=2 or not resume_closed or held:
            raise ToolExecutionError('Lower-bar source entry requires the real empty box2 pregrasp checkpoint')
        p._e09_low_handle_entry='group_box2'
        context.setdefault('branch_params',{})['lower_bar_source_entry_index']=None
    p.wait(1)
    state,_=p.snapshot()
    for i in range(3):
        name='group_box'+str(i);expected=p.objects[name]['center_z']-(p.objects[name]['bottom']-.8)
        if group_already_loaded(p,i):continue
        if (i!=resume_group and float(state[name]['mat'][2,2])<.995
                or i!=resume_group and abs(float(state[name]['pos'][2])-expected)>.004):
            raise ToolExecutionError('New fixture source package is not physically upright on table: '+name)
    native_design_readback(p)
    if phase=='lid_close':
        if params.get('complete_packaging_if_healthy')is True:
            package_stage(p,resume_held_lid0=resume,resume_after_closed=resume_closed,resume_held_group=resume_group,
                resume_at_release=resume_at_release)
            deliver_crate(p)
        else:
            indices=params.get('indices',[params.get('index',0)])
            if not isinstance(indices,list)or not indices or any(type(i)is not int or not 0<=i<=2 for i in indices):
                raise ToolExecutionError('Explicit original lid index0..2 required')
            for index in indices:close_lid(p,index)
    elif phase=='closed_box_load':load_group(p,int(params.get('index',2)))
    elif phase=='crate_stage':stage_crate(p)
    elif phase=='crate_deliver':deliver_crate(p)
    else:raise ToolExecutionError('Unknown new E09 physical fixture phase')
    saved=dict(context,new_design_fixture=True,created_by='physical_e09_new_design_fixture',
        policy_start_step=0,policy_action_budget=12000,whole_chain_accepted=False,
        eligible_full_acceptance=False,whole_task_score=None,completed_physical_fixture_phase=phase,
        source_cumulative_steps=p.c.steps,assignment_identity_sha256=p.d['assignment_identity_sha256'])
    if save_checkpoint is not None:save_checkpoint(p.c,author=author,context=saved)
    return dict(schema='e09-new-design-physical-fixture-result-v1',phase=phase,
        completed=True,actions=p.c.steps-start,source_cumulative_steps=start,
        functional_pass=bool(p.a.control_report.get('e09_functional_pass')),
        phase_functional_pass=True,native_score_reported_separately=True,
        final_cumulative_steps=p.c.steps,new_geometry_sha256=p.d['operable_packaging']['geometry_sha256'],
        whole_chain_accepted=False,eligible_full_acceptance=False,whole_task_score=None)
