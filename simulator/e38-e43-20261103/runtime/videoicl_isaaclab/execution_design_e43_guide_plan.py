"""Static zero-restitution guide: target tangent plus actual final-yaw clearance."""
import numpy as np
from .realworld_tool_expert import ToolExecutionError,_axis_rotation

NATIVE_RESPONSE=dict(source_native_trajectory_sha256='947bb1296245a22b507baeb5a0d783f08567cf54b840fc3cafb5eed5fa1c6200',
    effective_normal_response=.10124856557411156,tangent_retention=.829525130214965,
    incoming_velocity_task_m_s=[-.57302322,-.02949499,0.],
    interpretation='measured held-guide/table response; not a material restitution parameter')


def configure_measured_reference(policy):
    """Bind the native engineering response to its exact source/profile."""
    from .execution_design_e43_ball import settings_for
    if (policy.task!='E43'or not policy.a.control_report.get('engineering_reference_only')
            or policy.spec.get('execution_design',{}).get('revision')!='embodied50-execution-v3-20261102'
            or policy.spec.get('embodiment_config_sha256')!='7548e7dcc5a5418ee460b31736e54ad1e917e7168db9a99a4a41c1897f2542be'):
        raise ToolExecutionError('Measured guide reference requires its exact E43 engineering profile')
    ball=next(o for o in policy.spec['objects']if o['id']=='ball')
    if ball.get('reviewed_collision_settings')!=settings_for(ball):
        raise ToolExecutionError('Measured guide reference requires the reviewed native source sphere')
    policy._engineering_guide_response=NATIVE_RESPONSE


def plan(point,incoming,target,ball_position,launcher_position,launcher_rotation,launcher_half,
         guide_rotation,guide_half,normal_local,center_relative_work=(0,0,0),clearance=.006):
    point=np.asarray(point,float).copy();direction=np.asarray(incoming,float).copy();direction[2]=0.
    if np.linalg.norm(direction)<1e-9:raise ToolExecutionError('Horizontal native launcher direction required')
    direction/=np.linalg.norm(direction);target=np.asarray(target,float)
    current=np.asarray(guide_rotation,float);half=np.asarray(guide_half,float);local=np.asarray(normal_local,float)
    world=current@local;world[2]=0.;world/=np.linalg.norm(world)
    center=np.asarray(launcher_position,float);ramp=np.asarray(launcher_rotation,float)
    front=float(center@direction+np.abs(ramp.T@direction)@np.asarray(launcher_half,float))
    lateral=np.asarray(ball_position,float).copy();lateral[2]=point[2]
    lateral-=direction*float(lateral@direction)
    maximum=float(target@direction)-front-.005
    if maximum<=clearance:raise ToolExecutionError('Target lies before any passive guide with real launcher clearance')
    def candidate(distance):
        p=lateral+direction*(front+distance);out=target-p;out[2]=0.
        if np.linalg.norm(out)<1e-9:raise ToolExecutionError('Guide may not coincide with its target')
        out/=np.linalg.norm(out);normal=np.array([-out[1],out[0],0.])
        if normal@world<0:normal=-normal
        yaw=float(np.arctan2(normal[1],normal[0])-np.arctan2(world[1],world[0]))
        rotation=_axis_rotation([0,0,1],yaw)@current
        offset=float((rotation@np.asarray(center_relative_work,float))@direction)
        extent=float(np.abs(rotation.T@direction)@half)
        return p,normal,rotation,distance+offset-extent-clearance,out
    low=0.;high=maximum
    if candidate(high)[3]<0:raise ToolExecutionError('No static guide footprint fits between launcher and target')
    for _ in range(60):
        mid=(low+high)/2
        if candidate(mid)[3]>=0:high=mid
        else:low=mid
    p,normal,rotation,residual,out=candidate(high)
    projected=direction-normal*float(direction@normal)
    if float(projected@out)<=0 or np.linalg.norm(projected)<.05:
        raise ToolExecutionError('Zero-restitution guide cannot supply the requested target tangent')
    return dict(point=p.tolist(),normal=normal.tolist(),rotation=rotation.tolist(),
        outgoing_tangent=out.tolist(),launcher_gap_m=float(clearance+residual),
        incoming_speed_projection=float(np.linalg.norm(projected)),
        passive_projection_direction=(projected/np.linalg.norm(projected)).tolist(),
        collision_or_material_modified=False,native_deflection_required=True)


def response_plan(point,incoming,target,ball_position,launcher_position,launcher_rotation,launcher_half,
                  guide_rotation,guide_half,normal_local,ball_radius,center_relative_work=(0,0,0),
                  response=None,clearance=.006,equivalent_plane=0):
    """Propose a control pose using one SHA-bound native impact observation."""
    if response!=NATIVE_RESPONSE:raise ToolExecutionError('Exact measured native guide response provenance required')
    if equivalent_plane not in (0,1):raise ToolExecutionError('Two equivalent source guide plane directions only')
    direction=np.asarray(incoming,float).copy();direction[2]=0.;direction/=np.linalg.norm(direction)
    current=np.asarray(guide_rotation,float);half=np.asarray(guide_half,float);normal_local=np.asarray(normal_local,float)
    world=current@normal_local;world[2]=0.;world/=np.linalg.norm(world)
    target=np.asarray(target,float);ramp=np.asarray(launcher_rotation,float);center=np.asarray(launcher_position,float)
    front=float(center@direction+np.abs(ramp.T@direction)@np.asarray(launcher_half,float))
    lateral=np.asarray(ball_position,float).copy();lateral[2]=float(point[2]);lateral-=direction*float(lateral@direction)
    vin=np.asarray(response['incoming_velocity_task_m_s'],float);offset=np.asarray(center_relative_work,float)
    choices=[]
    for degrees in np.linspace(-80.,80.,321):
        face=_axis_rotation([0,0,1],np.deg2rad(degrees))@direction
        normal=face if face@world>=0 else-face
        if equivalent_plane:normal=-normal
        yaw=float(np.arctan2(normal[1],normal[0])-np.arctan2(world[1],world[0]))
        r=_axis_rotation([0,0,1],yaw)@current
        body_offset=r@offset;extent=float(np.abs(r.T@direction)@half)
        p=lateral+direction*(front+extent-float(body_offset@direction)+clearance)
        support=float(np.abs(r.T@face)@half)
        contact=p+direction*((float(body_offset@face)-support-float(ball_radius))/float(direction@face))
        v=response['tangent_retention']*(vin-face*float(vin@face))-response['effective_normal_response']*face*float(vin@face)
        speed=float(np.linalg.norm(v));unit=v/max(speed,1e-12)
        delta=target-contact;delta[2]=0.;travel=float(delta@unit)
        if speed<.03 or travel<.005 or float(p@direction)>=float(target@direction)-.005:continue
        miss=float(np.linalg.norm(delta-travel*unit))
        choices.append((miss,abs(float(degrees)),p,normal,r,unit,contact,speed))
    if not choices:raise ToolExecutionError('Measured passive guide response has no target-facing clear pose')
    miss,angle,p,normal,r,unit,contact,speed=min(choices,key=lambda q:q[:2])
    return dict(point=p.tolist(),normal=normal.tolist(),rotation=r.tolist(),outgoing_tangent=unit.tolist(),
        predicted_ball_contact_center=contact.tolist(),predicted_target_ray_miss_m=miss,
        predicted_postcontact_speed_m_s=speed,launcher_gap_m=clearance,
        response_calibration=response,equivalent_plane=equivalent_plane,
        collision_or_material_modified=False,native_deflection_required=True)
