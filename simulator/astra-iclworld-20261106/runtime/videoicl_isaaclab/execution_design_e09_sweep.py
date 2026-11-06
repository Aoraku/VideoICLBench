"""Continuous translation sweeps of actual E09 material, including payloads.

Each native box collider stays separate, so an open carrier is never replaced
by a solid envelope. Source CAD hulls are conservative rejection geometry.
This is geometric screening; real holding/support/closure still need physics.
"""
import itertools
import numpy as np
from scipy.spatial import ConvexHull
from scipy.optimize import linprog
from .realworld_tool_expert import ToolExecutionError

CORNER=np.array(list(itertools.product((-1,1),repeat=3)))


def overlap_radius(a,b):
    equations=np.r_[ConvexHull(a).equations,ConvexHull(b).equations]
    result=linprog([0.,0.,0.,-1.],
        A_ub=np.c_[equations[:,:3],np.linalg.norm(equations[:,:3],axis=1)],
        b_ub=-equations[:,3],bounds=[(None,None)]*4,method='highs')
    if not result.success:raise ToolExecutionError('E09 material sweep LP did not resolve')
    return float(result.x[3])


def translated_sweep(parts,obstacles,delta):
    """Exact swept convex solids for one straight translation segment."""
    delta=np.asarray(delta,float);checks=0;maximum=0.;nearest=None
    for name,index,vertices in parts:
        swept=np.r_[vertices,vertices+delta];lo,hi=swept.min(0),swept.max(0)
        for actor,k,solid in obstacles:
            gap=np.maximum(np.maximum(lo-solid.max(0),solid.min(0)-hi),0)
            if np.linalg.norm(gap)>.0001:continue
            checks+=1;radius=overlap_radius(swept,solid)
            if radius>maximum:maximum=radius;nearest=[name,index,actor,k]
            if radius>.002:
                raise ToolExecutionError('E09 actual cargo material sweep intersects '+str([name,index,actor,k]))
    return dict(exact_convex_checks=checks,maximum_overlap_radius_m=maximum,nearest=nearest)


def world_parts(p,name):
    obj=p.objects[name]
    if obj.get('collision_shapes'):
        pos,rotation=p.frame({'actor':name});out=[]
        for i,shape in enumerate(obj['collision_shapes']):
            if shape['type']!='box' or shape.get('quat',[1,0,0,0])!=[1,0,0,0]:
                raise ToolExecutionError('Reviewed E09 authored material collider required')
            out.append((name,i,(CORNER*np.asarray(shape['size'])+shape['pos'])@rotation.T+pos))
        return out
    from .execution_design_e09_lid import collision_points
    return [(name,0,collision_points(p,name))]


def payload_names(p,name):
    if name.startswith('group_box')and not name.endswith('_lid'):
        from .execution_design_e09_reference import group_members
        return {name,name+'_lid',*group_members(p,name)}
    if name=='shipping_crate':
        from .execution_design_e09_reference import group_members
        return {name,*[n for i in range(3)for n in
            ['group_box'+str(i),'group_box'+str(i)+'_lid',*group_members(p,'group_box'+str(i))]]}
    return {name}


def move_material_point(p,name,side,control,target,guard,*,tolerance=.002,table_support=False,floor_min_z=None):
    """Screen the whole real carried cluster, then use public Cartesian acts."""
    target=np.asarray(target,float);current=np.asarray(p.point(control));delta=target-current
    if np.count_nonzero(abs(delta)>.010)>1:
        raise ToolExecutionError('Cargo material sweep requires explicit single-axis waypoints')
    names=payload_names(p,name);moving=[part for n in names for part in world_parts(p,n)]
    obstacles=[part for n in p.objects if n not in names for part in world_parts(p,n)]
    for i,f in enumerate(p.spec['fixtures']):
        obstacles.append(('fixture'+str(i),0,CORNER*np.asarray(f['size'])+[*f['xy'],f['z']]))
    # Leaving an actual source support by a pure upward lift is intentional.
    upward=delta[2]>0 and max(abs(delta[:2]))<=.002
    if not table_support and not upward:
        obstacles.append(('table',0,CORNER*np.array([.35,.6,.025])+[0,0,.775]))
    result=translated_sweep(moving,obstacles,delta)
    from .execution_design_e09_reference import log
    log(p,'actual-cargo-material-sweep',actor=name,payload=sorted(names),
        real_collider_parts=len(moving),start=current,target=target,**result)
    history=[];seen=-1
    def monitored():
        nonlocal seen
        guard()
        if p.c.steps==seen:return
        seen=p.c.steps;error=float(np.max(abs(target-p.point(control))));history.append(error)
        if len(history)>=14 and error>max(.003,tolerance) and min(history[-14:-8])-min(history[-6:])<.0005:
            raise ToolExecutionError('Held E09 cargo lacks actual material-point progress: '+name)
    previous=getattr(p,'_e09_package_step_mm',None)
    package=(name in {'group_box0','group_box1','group_box2'}
        and p.objects[name].get('e09_packaging_revision')==p.d.get('operable_packaging',{}).get('revision'))
    operable_lid=(name.endswith('_lid')and p.objects[name].get('e09_packaging_revision')
        ==p.d.get('operable_packaging',{}).get('revision'))
    if package or operable_lid:
        # Recompute from actual cargo after every public pulse. An inner fixed
        # TCP waypoint otherwise chases load-induced lateral drift and reverses
        # the real lift while the payload is still far below its target.
        tolerance=max(tolerance,.005)
        for _ in range(1000):
            monitored();error=target-np.asarray(p.point(control))
            if floor_min_z is not None:
                minimum=float(world_parts(p,name)[0][2][:,2].min())
                if minimum<float(floor_min_z):
                    lift=min(25.,max(5.,(float(floor_min_z)+.010-minimum)*1000.))
                    target[2]=max(float(target[2]),float(p.point(control)[2])+lift/1000.)
                    p.act(side,'UP',mm=lift);continue
            if float(np.max(abs(error)))<=tolerance:return
            axis=int(np.argmax(abs(error)))
            token=(('FWD','BACK'),('LEFT','RIGHT'),('UP','DOWN'))[axis][int(error[axis]<0)]
            maximum=(5. if operable_lid else 2.)if token=='DOWN'and abs(float(error[axis]))<.020 else 25.
            p.act(side,token,mm=min(maximum,abs(float(error[axis]))*1000.))
        raise ToolExecutionError('Actual closed E09 cargo exhausted public material-point actions: '+name)
    if package:p._e09_package_step_mm=5. if delta[2]>=-.002 else 2.
    try:p.move_point(side,control,target,monitored,tolerance=tolerance)
    finally:
        if previous is None:
            if hasattr(p,'_e09_package_step_mm'):del p._e09_package_step_mm
        else:p._e09_package_step_mm=previous
