"""New E08 reference placement from source axes/cavity, never historical action166."""
import math
import itertools
import numpy as np
from .realworld_tool_expert import ToolExecutionError


def _unit(x):
    x=np.asarray(x,float);n=float(np.linalg.norm(x))
    if x.shape!=(3,)or not np.isfinite(x).all()or n<1e-9:raise ValueError('Finite nonzero source axis required')
    return x/n


def make_source_plan(spec,actor,box_position,box_rotation,collision_points_local,release_clearance=.0005,measured_floor_local_z=None):
    if spec.get('id')!='E08'or spec.get('variant')not in('A','B','C')or spec.get('execution_design',{}).get('revision')!='embodied50-execution-v3-20261102':raise ValueError('E08 v3 source reference planning only')
    objects=spec['objects'];objects=objects if isinstance(objects,dict)else{o['id']:o for o in objects}
    obj=objects[actor];semantic=spec['semantic'];points=np.asarray(collision_points_local,float)
    if actor not in('left_shoe','right_shoe')or points.ndim!=2 or points.shape[1]!=3 or len(points)<4 or not np.isfinite(points).all():raise ValueError('Actual source shoe collision vertices required')
    if not 0<=release_clearance<=.002:raise ValueError('Reviewed small source-floor release clearance required')
    source=obj['source_asset']
    expected={'left_shoe':'fdd7d78b574ad7bd52485d063fbb48621a02651cd174235cfd6bd9f7b2e40b32','right_shoe':'d47101e06a14ea63e22b76f3444fce6bd4faf4e1a33ed3c38c0cd603c339e3b2'}
    if source.get('sha256')!=expected[actor]or source.get('source_rotation')!=[.5,.5,.5,.5]:raise ValueError('Pinned source shoe body frame required')
    half=np.asarray(obj['size'],float);center=np.asarray(obj.get('local_bounds_center',[0,0,0]),float)
    if np.any(points.min(0)<center-half-1e-5)or np.any(points.max(0)>center+half+1e-5):raise ValueError('Collision vertices do not match authored source bounds')
    box_position=np.asarray(box_position,float);box_rotation=np.asarray(box_rotation,float)
    if box_position.shape!=(3,)or box_rotation.shape!=(3,3)or not np.isfinite(np.r_[box_position,box_rotation.ravel()]).all()or not np.allclose(box_rotation.T@box_rotation,np.eye(3),atol=1e-5)or np.linalg.det(box_rotation)<.999:raise ValueError('Measured proper box transform required')
    # In these SHA-bound normalized USD frames +Z is sole-up and the source
    # semantic declares +X as the toe direction. Toe/heel landmarks cross-check it.
    up_local=np.array([0.,0.,1.]);toe=_unit(semantic['toe_axis_local']);toe=_unit(toe-up_local*float(toe@up_local));lateral=np.cross(up_local,toe)
    landmarks=semantic['shoe_axes'][actor];line=_unit(np.asarray(landmarks['toe_local'])-landmarks['heel_local'])
    if float(line@toe)<.98:raise ValueError('Source toe axis disagrees with actual toe/heel landmarks')
    box_up=box_rotation[:,2];label=box_rotation@np.asarray(semantic['label_end']['point_local'],float);label=_unit(label-box_up*float(label@box_up))
    signs=({'left_shoe':1,'right_shoe':1},{'left_shoe':-1,'right_shoe':-1},{'left_shoe':1,'right_shoe':-1})['ABC'.index(spec['variant'])]
    wanted=label*signs[actor];rotation=np.column_stack((wanted,np.cross(box_up,wanted),box_up))@np.column_stack((toe,lateral,up_local)).T
    native_label=box_rotation@np.asarray(semantic['label_end']['point_local'],float);native_label/=np.linalg.norm(native_label)
    native_cosine=float((rotation@line)@native_label)
    if native_cosine*signs[actor]<=.9:raise ToolExecutionError('New source pose violates unchanged native toe/heel direction threshold')
    relative=box_rotation.T@rotation;physical=points@relative.T
    cavity=semantic['containers']['box'];lower=np.asarray(cavity['lower'],float);upper=np.asarray(cavity['upper'],float)
    floor=float(semantic['container_interior']['floor_local_z']if measured_floor_local_z is None else measured_floor_local_z)
    if not lower[2]-.003<=floor<=lower[2]+.012:raise ValueError('Source floor ray conflicts with original support window')
    corners=(np.array(list(itertools.product((-1,1),repeat=3)))*half+center)@relative.T
    lo,hi=corners.min(0),corners.max(0);origin=np.zeros(3);slot=np.asarray(semantic['structural_expert']['box_positions'][actor],float)
    for k in(0,1):
        low=lower[k]+.002-lo[k];high=upper[k]-.002-hi[k]
        if low>high:raise ToolExecutionError('Original native cavity cannot contain source shoe footprint')
        origin[k]=np.clip(slot[k],low,high)
    origin[2]=floor+release_clearance-float(physical[:,2].min())
    actual_corners=corners+origin;native_margin=np.minimum(actual_corners.min(0)-(lower-[.002,.002,.003]),(upper+[.002,.002,.003])-actual_corners.max(0))
    if np.min(native_margin)<0:raise ToolExecutionError('New source pose does not satisfy unchanged native full containment bounds')
    projection=points@(relative.T@np.array([0.,0.,1.]));band=points[projection<=float(projection.min())+.0002];control=band.mean(0)
    destination=box_position+box_rotation@(origin+relative@control)
    return dict(reference_strategy='new_source_axes_and_measured_cavity_v1',not_historical_action166=True,actor=actor,
                target_actor_rotation=rotation.tolist(),target_actor_origin_task=(box_position+box_rotation@origin).tolist(),
                control_local=control.tolist(),destination_point_task=destination.tolist(),support=cavity['ref']['actor'],
                material_clearance_z=float(semantic['expert_clearance_z']),reference_orientation_acceptance='native_direction_and_actual_shape_cavity_margin',
                geometry=dict(native_cavity_lower=lower.tolist(),native_cavity_upper=upper.tolist(),native_tolerance_xyz_m=[.002,.002,.003],
                    native_obb_min_box_m=actual_corners.min(0).tolist(),native_obb_max_box_m=actual_corners.max(0).tolist(),
                    native_containment_margin_xyz_m=native_margin.tolist(),measured_source_floor_local_z_m=floor,
                    floor_source='original_source_ray_metadata'if measured_floor_local_z is None else'actual_native_cooked_convex_ray',
                    release_clearance_m=release_clearance,sole_band_vertex_count=len(band),
                    source_toe_landmark_alignment=float(line@toe),toe_toward_label_alignment=float((rotation@line)@label),native_toe_label_cosine=native_cosine,up_alignment=float((rotation@up_local)@box_up)),
                native_placement_verified=False,requires_actual_fullhand_sweeps_and_grip=True,requires_native_settled_support=True,whole_task_score=None)



def settled_pose_geometry(physical_local,obb_local,actor_rotation,box_position,box_rotation,control_local,destination_point,floor,lower,upper,toe_axis_local,label_point_local,expected_sign):
    """Anticipated floor pose from actual orientation; native support stays unasserted."""
    physical,obb,r,bp,br,control,destination=map(lambda x:np.asarray(x,float),
        (physical_local,obb_local,actor_rotation,box_position,box_rotation,control_local,destination_point))
    if physical.ndim!=2 or physical.shape[1]!=3 or obb.shape!=(8,3)or not np.isfinite(np.r_[physical.ravel(),obb.ravel(),r.ravel(),bp,br.ravel(),control,destination,floor]).all():
        raise ValueError('Finite actual source shape and transforms required')
    relative=br.T@r;origin=np.zeros(3);origin[:2]=((destination-bp)@br-relative@control)[:2]
    origin[2]=float(floor)-float((physical@relative.T)[:,2].min())
    corners=obb@relative.T+origin;lo=np.asarray(lower)-[.002,.002,.003];hi=np.asarray(upper)+[.002,.002,.003]
    margin=np.minimum(corners.min(0)-lo,hi-corners.max(0))
    cosine=float(_unit(relative@np.asarray(toe_axis_local,float))@_unit(label_point_local))
    inside=bool(np.all(margin>=0));direction=bool(cosine*int(expected_sign)>.9)
    return dict(method='actual_orientation_source_shape_on_cooked_floor_and_original_native_bounds',
                acceptable=inside and direction,inside_original_cavity=inside,correct_label_direction=direction,
                native_cavity_margin_xyz_m=margin.tolist(),native_toe_label_cosine=cosine,
                anticipated_body_origin_box_m=origin.tolist(),actual_supported_in_box_not_yet_verified=True)

def drop_envelope(corners_box,physical_min_height_over_floor,floor_task_z,box_position,box_rotation,linear_velocity_task,angular_velocity_task,gravity_task,radius,lower,upper):
    """Conservative free-flight geometry only; impact/settlement still need native evidence."""
    corners=np.asarray(corners_box,float);velocity=np.asarray(linear_velocity_task,float);omega=np.asarray(angular_velocity_task,float);gravity=np.asarray(gravity_task,float)
    if corners.ndim!=2 or corners.shape[1]!=3 or len(corners)<4 or not np.isfinite(np.r_[corners.ravel(),velocity,omega,gravity,radius,physical_min_height_over_floor]).all():raise ValueError('Finite measured release geometry and velocities required')
    if gravity.shape!=(3,)or np.linalg.norm(gravity[:2])>1e-5 or gravity[2]>=0:raise ValueError('Measured vertical native gravity required')
    h=float(physical_min_height_over_floor);g=-float(gravity[2])
    if h<=0:raise ValueError('Above-floor source release required')
    time=(float(velocity[2])+math.sqrt(float(velocity[2])**2+2*g*h))/g
    angular_bound=2*float(radius)*math.sin(min(math.pi,float(np.linalg.norm(omega))*time)/2)
    world_shift=np.r_[velocity[:2]*time,-h];box_shift=np.asarray(box_rotation).T@world_shift
    predicted=corners+box_shift;lo=np.asarray(lower)-[.002,.002,.003];hi=np.asarray(upper)+[.002,.002,.003]
    margin=np.minimum(predicted.min(0)-lo,hi-predicted.max(0))-angular_bound
    if np.any(margin<0):raise ToolExecutionError('Measured full-shape drop envelope leaves original native cavity bounds')
    return dict(model='free_flight_only_not_impact_or_settlement',flight_seconds=time,linear_velocity_task_m_s=velocity.tolist(),angular_velocity_task_rad_s=omega.tolist(),
                horizontal_speed_m_s=float(np.linalg.norm(velocity[:2])),angular_speed_rad_s=float(np.linalg.norm(omega)),gravity_task_m_s2=gravity.tolist(),
                predicted_box_min_m=(predicted.min(0)-angular_bound).tolist(),predicted_box_max_m=(predicted.max(0)+angular_bound).tolist(),
                residual_native_cavity_margin_xyz_m=margin.tolist(),rotation_displacement_bound_m=angular_bound,native_landed_support_verified=False)


def measured_source_pose_plan(points_local,rotation,box_position,box_rotation,control_local,floor,lower,upper,slot,toe_local,label_local,expected_sign):
    """Place the complete actual source shape; no empty OBB corners or up test."""
    points,r,bp,br,control,lower,upper,slot=map(lambda x:np.asarray(x,float),(points_local,rotation,box_position,box_rotation,control_local,lower,upper,slot))
    if points.ndim!=2 or points.shape[1]!=3 or len(points)<4 or not np.isfinite(np.r_[points.ravel(),r.ravel(),bp,br.ravel(),control,lower,upper,slot,floor]).all():raise ValueError('Complete actual source pose required')
    relative=br.T@r;shape=points@relative.T;mn,mx=shape.min(0),shape.max(0);origin=np.zeros(3);room=True
    for k in(0,1):
        low=lower[k]+.002-mn[k];high=upper[k]-.002-mx[k]
        if low>high:room=False;origin[k]=(low+high)/2
        else:origin[k]=np.clip(slot[k],low,high)
    origin[2]=float(floor)-mn[2];posed=shape+origin
    margin=np.minimum(posed.min(0)-(lower-[.002,.002,.003]),(upper+[.002,.002,.003])-posed.max(0))
    cosine=float(_unit(relative@np.asarray(toe_local))@_unit(label_local));direction=cosine*int(expected_sign)>.9
    return dict(method='all_original_source_collision_vertices_original_native_cavity_and_tolerances',acceptable=bool(room and np.all(margin>=0)and direction),
        inside_original_cavity=bool(np.all(margin>=0)),correct_label_direction=bool(direction),native_toe_label_cosine=cosine,
        native_cavity_margin_xyz_m=margin.tolist(),actual_source_extent_box_m=(mx-mn).tolist(),
        anticipated_body_origin_box_m=origin.tolist(),destination_point_task=(bp+br@(origin+relative@control)).tolist(),
        original_tolerance_xyz_m=[.002,.002,.003],no_source_up_or_flat_requirement=True,actual_supported_in_box_not_yet_verified=True)
