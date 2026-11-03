"""Measured XY obstacle detours for E32's private public-action author.

This proposes waypoints from current rigid-body bounds. It is not a global
robot collision certificate, never changes the scene, and never grants success.
"""
import heapq
import json
import numpy as np
from .execution_design import REVISION_V3


def intersects_segment(start, end, lower, upper):
    start,end,lower,upper=map(lambda x:np.asarray(x,float),(start,end,lower,upper))
    delta=end-start;enter,leave=0.,1.
    for axis in range(2):
        if abs(delta[axis])<1e-12:
            if start[axis]<lower[axis] or start[axis]>upper[axis]:return False
        else:
            t0,t1=sorted(((lower[axis]-start[axis])/delta[axis],(upper[axis]-start[axis])/delta[axis]))
            enter=max(enter,t0);leave=min(leave,t1)
            if enter>leave:return False
    return True


def planar_route(start,end,rectangles,lower,upper):
    start,end,lower,upper=map(lambda x:np.asarray(x,float),(start,end,lower,upper))
    rectangles=[(np.asarray(lo,float),np.asarray(hi,float))for lo,hi in rectangles]
    if not all(np.isfinite(x).all()for x in [start,end,lower,upper,*[x for r in rectangles for x in r]]):raise ValueError('Finite measured routing bounds required')
    if np.any(upper<=lower) or any(np.any(hi<=lo)for lo,hi in rectangles):raise ValueError('Ordered routing bounds required')
    def valid(p):return bool(np.all(p>=lower)and np.all(p<=upper)and not any(np.all(p>=lo)and np.all(p<=hi)for lo,hi in rectangles))
    if not valid(start)or not valid(end):raise RuntimeError('Current payload or target overlaps measured obstacle envelope')
    nodes=[start,end]
    for lo,hi in rectangles:
        for x in (lo[0]-.002,hi[0]+.002):
            for y in (lo[1]-.002,hi[1]+.002):
                p=np.array([x,y])
                if valid(p):nodes.append(p)
    queue=[(0.,0)];distance={0:0.};parent={}
    while queue:
        cost,i=heapq.heappop(queue)
        if cost!=distance[i]:continue
        if i==1:
            route=[]
            while i!=0:route.append(nodes[i]);i=parent[i]
            return list(reversed(route))
        for j,p in enumerate(nodes):
            if i==j or any(intersects_segment(nodes[i],p,lo,hi)for lo,hi in rectangles):continue
            proposed=cost+float(np.linalg.norm(p-nodes[i]))
            if proposed<distance.get(j,float('inf')):
                distance[j]=proposed;parent[j]=i;heapq.heappush(queue,(proposed,j))
    raise RuntimeError('No measured tabletop transfer corridor for E32')


def climb_candidates(start,rectangles,lower,upper):
    """Short near-base staging segments clear the current payload envelope."""
    start,lower,upper=map(lambda x:np.asarray(x,float),(start,lower,upper))
    candidates=[]
    for dx in (0.,-.04,-.08,-.12,-.16):
        p=start+np.array([dx,0.])
        if np.any(p<lower)or np.any(p>upper):continue
        if any(intersects_segment(start,p,lo,hi)for lo,hi in rectangles):continue
        candidates.append(p)
    return candidates


def raised_transfer(a,name,side,target_xy,z,rectangles,bounds,obstacle_top,carried_depth):
    """Use reject-only measured IK to choose an overhead corridor if feasible."""
    from .execution_design_drawer_ik_probe import inspect
    tcp=np.asarray(a.tip(side));z=max(float(z),float(tcp[2]));plane=max(z,float(obstacle_top)+float(carried_depth)+.025)
    if plane<=z+.01:return False
    candidates=climb_candidates(tcp[:2],rectangles,np.asarray(bounds['lower'])[:2],np.asarray(bounds['upper'])[:2])
    if not candidates:return False
    rotation=np.asarray(a.tcp_rotation_task(side))
    targets=[dict(position=[*target_xy,plane],rotation=rotation)]
    for xy in candidates:
        targets.extend([dict(position=[*xy,z],rotation=rotation),dict(position=[*xy,plane],rotation=rotation)])
    results=inspect(a,a.c,side,targets)
    valid=[i for i in range(len(candidates))if results[0]['kinematically_reachable']and results[1+2*i]['kinematically_reachable']and results[2+2*i]['kinematically_reachable']]
    with (a.out/'e32-raised-transfer.private.jsonl').open('a')as stream:
        stream.write(json.dumps(dict(object=name,side=side,step=a.c.steps,plane=plane,carried_depth=carried_depth,candidates=[p.tolist()for p in candidates],ik_results=results,valid_candidates=valid,collision_verified=False,native_passed=False))+'\n')
    if not valid:return False
    i=min(valid,key=lambda i:results[2+2*i]['joint_distance_rad']);xy=candidates[i]
    old=a.scene.spec.get('expert_loaded_step_mm');a.scene.spec['expert_loaded_step_mm']=8.
    try:
        a.move_generated({side:[*xy,z]},tolerance=.006)
        a.move_generated({side:[*xy,plane]},tolerance=.006)
        # Entire actual payload lies above all measured clutter tops here.
        a.move_generated({side:[*target_xy,plane]},tolerance=.006)
    finally:
        if old is None:a.scene.spec.pop('expert_loaded_step_mm',None)
        else:a.scene.spec['expert_loaded_step_mm']=old
    return True


def transfer(author,name,side,target_xy,z):
    a=author;spec=a.scene.spec
    if not getattr(a,'_execution_design_reference_authorized',False)or spec['id']!='E32'or spec.get('execution_design',{}).get('revision')!=REVISION_V3:raise ValueError('Explicit E32 v3 engineering transfer required')
    from .execution_design_thin_edge import table_bounds_task
    state,_=a.c.snapshot();objects={o['id']:o for o in spec['objects']};tcp=np.asarray(a.tip(side));body=state[name]
    if a.carried_payload!=(name,side)or not body['grasp'][0 if side=='left'else 1]:raise RuntimeError('E32 transfer requires actual current payload grasp')
    rotation=np.asarray(body['mat']);offset=np.asarray(body['pos'])-tcp
    center=offset+rotation@np.asarray(objects[name].get('local_bounds_center',[0,0,0]))
    half=np.abs(rotation)@np.asarray(objects[name].get('bounds_half_extent',objects[name]['size']))
    rectangles=[];evidence=[];margin=.020;obstacle_tops=[.8]
    # Axis-wise public actions can deviate from a diagonal segment. Execute
    # each graph edge as small, bounded public steps below.
    for key,obj in objects.items():
        if key==name:continue
        current=state[key];rot=np.asarray(current['mat']);pos=np.asarray(current['pos'])+rot@np.asarray(obj.get('local_bounds_center',[0,0,0]));extent=np.abs(rot)@np.asarray(obj.get('bounds_half_extent',obj['size']))
        obstacle_tops.append(float(pos[2]+extent[2]))
        if z+center[2]-half[2]>pos[2]+extent[2]+margin:continue
        if z+center[2]+half[2]<pos[2]-extent[2]-margin:continue
        lo=pos[:2]-extent[:2]-center[:2]-half[:2]-margin
        hi=pos[:2]+extent[:2]-center[:2]+half[:2]+margin
        rectangles.append((lo,hi));evidence.append(dict(object=key,lower=lo.tolist(),upper=hi.tolist()))
    bounds=table_bounds_task(a.scene)
    geometry=a.finger_geometry(side)
    if geometry.get('source')!='actual_collision_mesh_current_body_pose':raise ValueError('E32 route requires actual loaded finger geometry')
    loaded_depth=max(0.,float(half[2]-center[2]),float(tcp[2])-float(geometry['lowest_z_task_m']))
    if raised_transfer(a,name,side,target_xy,z,rectangles,bounds,max(obstacle_tops),loaded_depth):return
    route=planar_route(tcp[:2],target_xy,rectangles,np.asarray(bounds['lower'])[:2],np.asarray(bounds['upper'])[:2])
    with (a.out/'e32-obstacle-transfer.private.jsonl').open('a')as stream:
        stream.write(json.dumps(dict(object=name,side=side,step=a.c.steps,measured_obstacles=evidence,waypoints=[p.tolist()for p in route],z=z,full_robot_collision_verified=False))+'\n')
    # Keep intermediate waypoints loose enough to tolerate measured loaded
    # vertical drift. The 20mm inflated envelope exceeds the 10mm segment,
    # 4mm waypoint tolerance and 3mm public step combined. Native final goal
    # and protected-object checks are unchanged.
    old=spec.get('expert_loaded_step_mm');spec['expert_loaded_step_mm']=3.
    try:
        start=tcp[:2]
        for p in route:
            segments=max(1,int(np.ceil(np.linalg.norm(p-start)/.010)))
            for i in range(1,segments+1):
                waypoint=start+(p-start)*i/segments
                a.move_generated({side:[*waypoint,z]},tolerance=.004)
            start=p
    finally:
        if old is None:spec.pop('expert_loaded_step_mm',None)
        else:spec['expert_loaded_step_mm']=old
