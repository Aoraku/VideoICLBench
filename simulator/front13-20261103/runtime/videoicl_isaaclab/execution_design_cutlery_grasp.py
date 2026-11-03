"""Actual finger cross-section plans for private E27/E34 engineering grasping."""
import json
import math
import numpy as np
from .execution_design import REVISION_V3


def plane_section(points,z):
    from scipy.spatial import ConvexHull
    points=np.asarray(points,float)
    if points.ndim!=2 or points.shape[1]!=3 or not np.isfinite(points).all():raise ValueError('Actual finite finger vertices required')
    hull=ConvexHull(points)
    edges={tuple(sorted((int(a),int(b))))for face in hull.simplices for a,b in zip(face,np.roll(face,1))}
    section=[p for p in points if abs(p[2]-z)<1e-10]
    for i,j in edges:
        a,b=points[i],points[j]
        if (a[2]-z)*(b[2]-z)<=0 and abs(b[2]-a[2])>1e-12:
            section.append(a+(b-a)*(z-a[2])/(b[2]-a[2]))
    if not section:raise ValueError('Actual finger does not intersect material grasp height')
    return np.asarray(section)


def sectional_target(point,tcp,current,target,palm,fingers,floor):
    point,tcp,current,target,palm=map(lambda x:np.asarray(x,float),(point,tcp,current,target,palm))
    local=[(np.asarray(m)-tcp)@current for m in [palm,*fingers]]
    transformed=[m@target.T for m in local]
    z=floor-min(float(m[:,2].min())for m in transformed)+.0003
    sections=[plane_section(m+[0,0,z],point[2])for m in transformed[1:]]
    # Use centres of the two actual low-height sections, not the mean of all
    # finger vertices (which can be 14mm above a thin fork handle).
    midpoint=np.mean([(s.min(0)+s.max(0))/2 for s in sections],axis=0)
    position=np.r_[point[:2]-midpoint[:2],z]
    return position


def orient(author,side,target):
    from .author_orientation import _axis_angle
    labels=(('ROLL_LEFT','ROLL_RIGHT'),('PITCH_UP','PITCH_DOWN'),('ROTATE_CCW','ROTATE_CW'))
    history=[]
    for _ in range(180):
        current=np.asarray(author.tcp_rotation_task(side));axis,angle=_axis_angle(target@current.T)
        if angle<math.radians(1.):return
        i=int(np.argmax(abs(axis)));token=labels[i][int(axis[i]<0)]
        author.act(token if side=='left'else'STILL',token if side=='right'else'STILL',rotation_deg=min(7.,max(.5,abs(math.degrees(angle*axis[i])))))
        history.append(angle)
        if len(history)>=24 and min(history[-24:-16])-min(history[-8:])<math.radians(.2):raise RuntimeError('Measured cutlery wrist orientation stalled')
    raise RuntimeError('Measured cutlery wrist orientation did not converge')


def choose_staging(final,entries,staging):
    """Choose a short same-branch route among measured safe endpoint poses."""
    count=len(final);valid=[]
    if not count or len(staging)!=len(entries)*count:raise ValueError('Complete paired IK candidates required')
    for site_index,entry in enumerate(entries):
        for i,finish in enumerate(final):
            stage=staging[site_index*count+i]
            if not all(x['kinematically_reachable']for x in(entry,stage,finish)):continue
            margin=min(x['minimum_joint_margin_rad']for x in(entry,stage,finish))
            if margin<.08:continue
            # Panda joints are bounded, not angles that wrap modulo2pi. An
            # equivalent upside-down jaw may require a >pi branch change when
            # approaching the source. Endpoint reachability is not that route.
            travel=np.asarray(finish['candidate_joints_rad'])-stage['candidate_joints_rad']
            if np.max(np.abs(travel))>=math.pi:continue
            valid.append((site_index,i,margin))
    if not valid:raise RuntimeError('No measured joint-limit-safe cutlery grasp and high staging assignment')
    return min(valid,key=lambda x:(x[0]!=0,staging[x[0]*count+x[1]]['joint_distance_rad'],-x[2]))


def grasp_position(a,side,obj):
    spec=a.scene.spec
    if not getattr(a,'_execution_design_reference_authorized',False)or spec['id']not in('E27','E34')or spec.get('execution_design',{}).get('revision')!=REVISION_V3 or a.scene.embodiment.name!='franka':raise ValueError('Explicit Panda E27/E34 v3 engineering grasp required')
    from .execution_design_e33_grasp import actual_mesh
    from .execution_design_thin_edge import table_bounds_task
    from .execution_design_drawer_ik_probe import inspect,physical_grasp_targets,skew
    state,_=a.c.snapshot();body=state[obj['id']]
    if any(value['grasp'][0 if side=='left'else 1]for value in state.values()):raise RuntimeError('Cutlery orientation requires an empty hand')
    point=np.asarray(body['pos'])+np.asarray(body['mat'])@np.asarray(obj['grasp_point_local'])
    jaw=np.asarray(body['mat'])@np.asarray(obj['grasp_axis_local']);jaw[2]=0.;jaw/=np.linalg.norm(jaw)
    tcp=np.asarray(a.tip(side));current=np.asarray(a.tcp_rotation_task(side));floor=table_bounds_task(a.scene)['top']
    palm=actual_mesh(a,side,'panda_hand');fingers=[actual_mesh(a,side,n)for n in a.scene.embodiment.fingers]
    theta=math.radians(-30.);k=skew(jaw);tilt=np.eye(3)+math.sin(theta)*k+(1-math.cos(theta))*(k@k)
    rotations=[tilt@r for r in physical_grasp_targets(a,a.c,side,[0.,0.,1.],pinch_axis=jaw)]
    targets=[dict(position=sectional_target(point,tcp,current,r,palm,fingers,floor).tolist(),rotation=r.tolist())for r in rotations]
    final=inspect(a,a.c,side,targets)
    # Turning at the low parked TCP can drive joint6 into its hard boundary
    # even though a distant nonlinear IK solution exists. First select an
    # empty-hand waypoint with measured margin for BOTH entry and final pose.
    obstacle_tops=[floor]
    for spec_object in spec['objects']:
        value=state[spec_object['id']];rot=np.asarray(value['mat'])
        centre=np.asarray(value['pos'])+rot@np.asarray(spec_object.get('local_bounds_center',[0,0,0]))
        extent=np.abs(rot)@np.asarray(spec_object.get('bounds_half_extent',spec_object['size']))
        obstacle_tops.append(float(centre[2]+extent[2]))
    hand_radius=max(float(np.linalg.norm(mesh-tcp,axis=1).max())for mesh in [palm,*fingers])
    safe_z=max(float(tcp[2]),max(obstacle_tops)+hand_radius+.015)
    sites=[np.r_[tcp[:2]+fraction*(point[:2]-tcp[:2]),safe_z]for fraction in(0.,.5,1.)]
    entries=inspect(a,a.c,side,[dict(position=site,rotation=current)for site in sites])
    staging=inspect(a,a.c,side,[dict(position=site,rotation=r)for site in sites for r in rotations])
    site_index,chosen,margin=choose_staging(final,entries,staging)
    stage=staging[site_index*len(targets)+chosen]
    with (a.out/'cutlery-section-grasp.private.jsonl').open('a')as f:f.write(json.dumps(dict(object=obj['id'],side=side,step=a.c.steps,target=targets[chosen],final_ik=final[chosen],staging_ik=stage,entry_ik=entries[site_index],staging_position=sites[site_index].tolist(),minimum_route_margin_rad=margin,hand_rotation_radius_m=hand_radius,native_grasp_verified=False))+'\n')
    a.move_generated({side:[*tcp[:2],safe_z]})
    a.move_generated({side:sites[site_index]})
    orient(a,side,rotations[chosen])
    return np.asarray(targets[chosen]['position'])
