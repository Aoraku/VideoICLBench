"""Measured low side-entry transport for the E17 engineering reference."""
from copy import deepcopy
import numpy as np
from .realworld_tool_expert import ToolExecutionError


def collision_shelf_target(author, actor, layer, target):
    """Match the deployed dynamic component hull, without changing the rule.

    Convex hulls fill the shallow concave source plates. Their physical top
    differs from the old visual cavity floor; pushing to that floor wedges
    the held piece into the collider. Values are checked against source mesh
    vertices in the regression test, and apply only to this exact asset.
    """
    result = list(target)
    obj = author.objects[actor]
    if not obj.get('dynamic_mechanical_asset'):
        return result
    if (author.task != 'E17' or
            obj.get('mechanical_asset', {}).get('sha256') !=
            '6cd3a9ec1b8664a9bca2ed034ac49808e7fbf8b82d2482b927c4e2fa727f5186'):
        raise ToolExecutionError('Unreviewed dynamic shelf collision asset')
    surfaces = {'lower': .016795216, 'upper': .14980625}
    if layer not in surfaces:
        raise ToolExecutionError('Unreviewed dynamic shelf layer')
    lift=0.
    if obj.get('e17_stand_geometry'):
        from .execution_design_e17_stand import descriptor,LIFT_M
        if obj['e17_stand_geometry']!=descriptor():
            raise ToolExecutionError('Unreviewed derived E17 shelf geometry')
        lift=LIFT_M if layer=='upper' else 0.
    result[2] = surfaces[layer]+lift
    return result


def measured_shelf_release(author,name,side,actor,layer,target):
    """Keep real fingers above the plate and let the released piece settle."""
    target=np.asarray(collision_shelf_target(author,actor,layer,target),float)
    base,rot=author.frame({'actor':actor});base=np.asarray(base);rot=np.asarray(rot)
    if rot[2,2]<.99:raise ToolExecutionError('E17 gravity release requires upright stand')
    point=author.point({'actor':name,'local':author.bottom_local(name)})
    fingers=author.a.finger_geometry(side)['fingers']
    if not fingers:raise ToolExecutionError('Missing actual shelf finger geometry')
    corners=np.asarray([[x,y,z]for x in [-1,1]for y in [-1,1]for z in [-1,1]])
    relative=[]
    for finger in fingers:
        lo=np.asarray(finger['aabb_min_task_m']);hi=np.asarray(finger['aabb_max_task_m'])
        relative.extend(((lo+hi)/2+corners*(hi-lo)/2-point)@rot)
    relative=np.asarray(relative)
    target[2]+=max(.001,.010-float(relative[:,2].min()))
    lift=author.objects[actor].get('e17_stand_geometry',{}).get('upper_tier_lift_m',0.)
    if layer=='lower' and target[2]+float(relative[:,2].max())>.13299377+lift-.010:
        raise ToolExecutionError('Actual fingers do not fit between E17 plates')
    author.a.control_report.setdefault('e17_shelf_release',[]).append(dict(
        actor=name,layer=layer,bottom_local_z=float(target[2]),
        finger_relative_min_z=float(relative[:,2].min()),finger_relative_max_z=float(relative[:,2].max())))
    return target


def measured_triangle_grasps(spec, grasps):
    """Transfer the E09 native-proven pinch point only for the identical mesh.

    This is private engineering reference geometry; source poses, shapes and
    the evaluator remain unchanged. E17 support/layout still need validation.
    """
    if spec.get('id') != 'E17':
        raise ToolExecutionError('E17 triangle reference only')
    result = deepcopy(grasps)
    expected_sha = 'caae5e783af9afae7ee6c1933e42a1654d746635873c7a1bb221ea4554a70e7b'
    for obj in spec['objects']:
        if obj.get('source_asset', {}).get('sha256') != expected_sha:
            continue
        if not np.allclose(obj['size'], [.02, .017320508, .003], atol=1e-8):
            raise ToolExecutionError('Unexpected E17 triangle source scale')
        grasp = result[obj['id']]
        grasp['local'] = [0., -.017320508 / 3., 0.]
        grasp['jaw_axis_local'] = [1., 0., 0.]
    return result


def measured_shelf_entry(author,name,side,actor,target_local,minimum_entry):
    if author.task!='E17' or not getattr(author.a,'control_report',{}).get('engineering_reference_only'):
        raise ToolExecutionError('E17 independent engineering control required')
    state=author.snapshot()[0];base,rot=author.frame({'actor':actor});base=np.asarray(base);rot=np.asarray(rot)
    if rot[2,2]<.99:raise ToolExecutionError('E17 lower entry requires an upright real stand')
    point=author.point({'actor':name,'local':author.bottom_local(name)})
    def bound(n):
        r=np.asarray(state[n]['mat']);obj=author.objects[n]
        c=np.asarray(state[n]['pos'])+r@np.asarray(obj.get('local_bounds_center',[0,0,0]))
        h=np.abs(r)@np.asarray(obj['size']);return c-h,c+h
    lo,hi=bound(name);extent=np.maximum(abs(lo-point),abs(hi-point))
    for f in author.a.finger_geometry(side)['fingers']:
        extent=np.maximum(extent,np.maximum(abs(np.asarray(f['aabb_min_task_m'])-point),abs(np.asarray(f['aabb_max_task_m'])-point)))
    # Include the full actual finger boxes at the outside entry. The original
    # +/-150mm entry left a palm near the rim and required high 1.15m travel.
    stand=author.objects[actor];stand_half=np.asarray(stand['size']);stand_center=np.asarray(stand.get('local_bounds_center',[0,0,0]))
    hand_x=float(np.abs(rot[:,0])@extent)
    sign=-1 if float(target_local[0])<0 else 1
    boundary=float(stand_center[0]+sign*stand_half[0])
    entry_x=sign*max(float(minimum_entry),abs(boundary)+hand_x+.015)
    entry=np.array([entry_x,float(target_local[1]),.025]);outside=base+rot@entry
    corridor_lo=np.minimum(point[:2],outside[:2])-extent[:2]-.010
    corridor_hi=np.maximum(point[:2],outside[:2])+extent[:2]+.010
    top=.8
    def include(lo,hi):
        nonlocal top
        if np.all(hi[:2]>=corridor_lo)and np.all(lo[:2]<=corridor_hi):top=max(top,float(hi[2]))
    for n in state:
        if n!=name:include(*bound(n))
    for fixture in author.spec.get('fixtures',[]):
        if fixture.get('type')!='box':raise ToolExecutionError('Unreviewed E17 route fixture')
        c=np.array([*fixture['xy'],fixture['z']]);h=np.asarray(fixture['size']);include(c-h,c+h)
    offset=float(point[2]-author.tip(side)[2])
    height=max(.98,top+.030+float(extent[2]),author.a.floor_clear_tcp(side,floor=top+.030)+offset)
    author.a.control_report.setdefault('e17_lower_entry_routes',[]).append(dict(actor=name,entry_x_local_m=entry_x,actual_obstacle_top_m=top,transport_bottom_z_m=height,actual_finger_payload_halfspan=extent.tolist()))
    return entry_x,height


def source_side_lower_slot(author,index,count):
    """Use the existing reviewed negative-X quadrants; the rule is layer only."""
    if author.task!='E17':raise ToolExecutionError('E17 lower-slot reference only')
    positions=author.geometry.get('shelf_positions',{})
    choices=sorted({(float(p[0]),float(p[1]))for p in positions.values()if float(p[0])<0},key=lambda p:p[1])
    if count>len(choices)or not 0<=index<count:
        raise ToolExecutionError('No distinct source-side reviewed lower-layer slots')
    # The original +/-38mm quadrants clear the rod for the piece alone, but
    # the measured closed finger boxes need another 10mm. +/-48mm keeps even
    # the 40mm square's far corner within the source plate's >=102mm radius.
    xy=[value+np.sign(value)*.010 for value in choices[index]]
    return [*xy,float(author.s['shelves']['lower']['center_local'][2])]


def clear_lower_ingress(author,name,side,actor,entry,target):
    """Route the low entry around the actual source carton, not through it.

    Both points are stand-local; the held body and current finger collision
    boxes determine clearance. The return is a four-point horizontal route
    at the existing reviewed carry height, with no world/shape modifications.
    """
    base,rot=author.frame({'actor':actor});base=np.asarray(base);rot=np.asarray(rot)
    if rot[2,2]<.99:raise ToolExecutionError('E17 ingress requires upright actual stand')
    state=author.snapshot()[0];point=author.point({'actor':name,'local':author.bottom_local(name)})
    lo=np.full(3,np.inf);hi=np.full(3,-np.inf)
    corners=np.asarray([[x,y,z]for x in [-1,1]for y in [-1,1]for z in [-1,1]])
    def actor_bounds(n):
        obj=author.objects[n];r=np.asarray(state[n]['mat']);c=np.asarray(state[n]['pos'])+r@np.asarray(obj.get('local_bounds_center',[0,0,0]))
        pts=c+corners*np.asarray(obj['size'])@r.T
        return pts.min(axis=0),pts.max(axis=0)
    a,b=actor_bounds(name);lo=np.minimum(lo,a-point);hi=np.maximum(hi,b-point)
    for f in author.a.finger_geometry(side)['fingers']:
        fmin=np.asarray(f['aabb_min_task_m']);fmax=np.asarray(f['aabb_max_task_m'])
        pts=(fmin+fmax)/2+corners*(fmax-fmin)/2-point
        lo=np.minimum(lo,pts.min(axis=0));hi=np.maximum(hi,pts.max(axis=0))
    obstacles=[]
    for n in state:
        if n not in (name,actor):obstacles.append((n,*actor_bounds(n)))
    for i,f in enumerate(author.spec.get('fixtures',[])):
        if f.get('type')!='box':raise ToolExecutionError('Unreviewed E17 ingress fixture')
        center=np.array([*f['xy'],f['z']]);pts=center+corners*np.asarray(f['size'])
        obstacles.append(('fixture'+str(i),pts.min(axis=0),pts.max(axis=0)))
    mechanical=author.objects[actor].get('mechanical_asset')
    if mechanical:
        if mechanical.get('sha256')!='6cd3a9ec1b8664a9bca2ed034ac49808e7fbf8b82d2482b927c4e2fa727f5186':
            raise ToolExecutionError('Unreviewed E17 stand inner collision geometry')
        # Source-component bounds, not a fabricated whole-stand solid box.
        for label,center,half in [
            ('stand_central_rod',[0,0,.126],[.009787,.009314,.126]),
            ('stand_lower_ornament',[0,0,(.01681+.02660)/2],[.01681,.01681,(.02660-.01681)/2])]:
            pts=base+(np.asarray(center)+corners*np.asarray(half))@rot.T
            obstacles.append((label,pts.min(axis=0),pts.max(axis=0)))
    entry=base+rot@np.asarray(entry,float);target=base+rot@np.asarray(target,float);gate=entry.copy();avoided=[]
    # Positive task-Y is the clear side of the source carton in this layout.
    # Do not project all obstacle boxes into a slightly rotated stand frame:
    # that needlessly fills the measured narrow gap between the two cartons.
    # Expand until the complete measured cargo/finger footprint fits.
    for _ in range(len(obstacles)+1):
        blockers=[(n,a,b)for n,a,b in obstacles if np.all(gate+hi+.010>a)and np.all(gate+lo-.010<b)]
        if not blockers:break
        gate[1]=max(float(b[1]-lo[1]+.012)for _,_,b in blockers)
        avoided.extend(n for n,_,_ in blockers)
    else:raise ToolExecutionError('No measured clear E17 outside descent')
    # Turn before the central rod, then approach the chosen quadrant along X.
    # Candidate X boundaries come only from real measured obstacle edges.
    candidates={float(target[0])}
    for _,a,b in obstacles:
        candidates.update((float(a[0]-hi[0]-.008),float(b[0]-lo[0]+.008)))
    candidates=sorted((x for x in candidates if min(gate[0],target[0])<=x<=max(gate[0],target[0])),reverse=target[0]>gate[0])
    blocked=[]
    def unobstructed(route):
        for start,end in zip(route,route[1:]):
            sweep_lo=np.minimum(start,end)+lo-.004;sweep_hi=np.maximum(start,end)+hi+.004
            for obstacle,a,b in obstacles:
                if np.all(sweep_hi>a)and np.all(sweep_lo<b):
                    blocked.append(dict(obstacle=obstacle,start=start.tolist(),end=end.tolist(),obstacle_min=a.tolist(),obstacle_max=b.tolist()))
                    return False
        return True
    route=None
    for x in candidates:
        proposed=[gate,np.array([x,gate[1],entry[2]]),np.array([x,target[1],entry[2]]),target]
        if unobstructed(proposed):route=proposed;break
    if route is None:
        author.a.control_report.setdefault('e17_rejected_ingress',[]).append(dict(actor=name,candidates=blocked))
        raise ToolExecutionError('E17 low ingress still blocked by measured solids')
    scene=author.a.scene;table=scene.layout.config['table'];origin=np.asarray(getattr(scene,'origin',(0,0,0)))
    table_center=np.asarray(table['position'])+origin;table_half=np.asarray(table['size'])/2
    table_points=np.array([scene.world_to_task(table_center+sign*table_half)for sign in corners])
    table_lo,table_hi=table_points.min(axis=0),table_points.max(axis=0)
    for waypoint in route:
        envelope=waypoint+(lo+hi)/2+corners*(hi-lo)/2
        if np.any(envelope[:,:2].min(axis=0)<table_lo[:2])or np.any(envelope[:,:2].max(axis=0)>table_hi[:2]):
            raise ToolExecutionError('E17 ingress leaves actual table footprint')
    route=[rot.T@(p-base)for p in route]
    author.a.control_report.setdefault('e17_clear_ingress',[]).append(
        dict(actor=name,stand_base_task_m=base.tolist(),actual_envelope_min=lo.tolist(),actual_envelope_max=hi.tolist(),
             avoided=sorted(set(avoided)),waypoints_stand_local=[p.tolist()for p in route]))
    return route
