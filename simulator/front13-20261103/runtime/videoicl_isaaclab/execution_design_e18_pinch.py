"""Reject-only source-bar pinch geometry; native contacts still decide grip."""
import numpy as np
from scipy.spatial import ConvexHull
from scipy.optimize import linprog


def finite_bar_pinch_candidate(geometry,rotation,point,outward,bar_axis):
    """Use the original finite bar volume, including its 2.742 mm thickness.

    A centreline has zero thickness and cannot predict a vertical thin-bar
    pinch. This is a geometric rejection screen, never a native grip claim.
    """
    if geometry.get('source')!='actual_native_collision_mesh_current_body_pose':
        raise ValueError('Actual native E18 hand geometry required')
    normal=np.asarray(outward,float);normal/=np.linalg.norm(normal)
    bar=np.asarray(bar_axis,float);bar/=np.linalg.norm(bar)
    short=np.cross(normal,bar);short/=np.linalg.norm(short)
    rotation=np.asarray(rotation,float);point=np.asarray(point,float)
    clouds=[np.asarray(c,float)@rotation.T for c in geometry['closed_clouds_tcp']]
    if len(clouds)!=3 or any(c.ndim!=2 or c.shape[1]!=3 or not np.isfinite(c).all()for c in clouds):
        raise ValueError('Complete finite closed E18 collision clouds required')
    jaw=rotation@np.asarray(geometry['jaw_axis_tcp'],float)
    # Vertical opposed pads: no oblique long-axis edge pinch in this candidate.
    if abs(jaw@bar)>.1:
        raise ValueError('Finite-bar support candidate requires transverse jaw')
    basis=np.column_stack((normal,short,bar));half=np.array([.001304,.001371,.04897])
    hulls=[ConvexHull(c).equations for c in clouds[:2]];matrix=[];rhs=[]
    for i,sign in enumerate((1.,-1.)):
        for eq in hulls[i]:
            n=eq[:3];row=np.zeros(8);row[0]=-n@normal;row[1]=-sign*n@jaw
            row[2+3*i:5+3*i]=n@basis;matrix.append(row);rhs.append(-eq[3])
        extent=float(np.max(clouds[i]@(-normal)))
        row=np.zeros(8);row[0]=-1.;row[1]=sign*jaw@(-normal)
        matrix.append(row);rhs.append(.006-extent)
        row=np.zeros(8);row[0]=-1.;matrix.append(row)
        rhs.append(.006-extent-sign*.04*(jaw@(-normal)))
    bounds=[(0.,.06),(.0003,.035)]+[(-h,h)for _ in range(2)for h in half]
    objective=np.zeros(8);objective[1]=-1.
    solution=linprog(objective,A_ub=matrix,b_ub=rhs,bounds=bounds,method='highs')
    radius=max(float(np.max(np.linalg.norm(c,axis=1)))for c in geometry['clouds_tcp'])
    fallback=dict(feasible=False,target_position=point.tolist(),
        rotation_safe_z_m=float(geometry['table_top']+radius+.015),
        collision_verified=False,native_grip_verified=False,geometry_model='original_finite_bar_box')
    if not solution.success:return fallback
    distance,opening=map(float,solution.x[:2]);tcp=point+normal*distance
    floor=[float(np.min((clouds[2]+tcp)[:,2])-geometry['table_top'])]
    overlap=False
    for i,sign in enumerate((1.,-1.)):
        for q in (opening,.04):
            floor.append(float(np.min((clouds[i]+tcp+sign*q*jaw)[:,2])-geometry['table_top']))
        eq=hulls[i];offset=normal*distance+sign*.04*jaw
        # Exact convex finger/finite bar intersection at fully open position.
        intersect=linprog(np.zeros(3),A_ub=eq[:,:3]@basis,
            b_ub=-eq[:,3]+eq[:,:3]@offset,bounds=[(-h,h)for h in half],method='highs')
        overlap=overlap or intersect.success
    palm=float(np.min((clouds[2]+tcp-point)@normal))
    return dict(feasible=min(floor)>.002 and palm>.003 and not overlap,
        target_position=tcp.tolist(),rotation_safe_z_m=fallback['rotation_safe_z_m'],
        closing_opening_m=opening,hand_floor_clearances_m=floor,
        palm_outside_handle_plane_m=palm,open_fingers_intersect_bar=overlap,
        bar_half_extents_m=half.tolist(),bar_contact_coordinates_m=solution.x[2:].reshape(2,3).tolist(),
        geometry_model='original_finite_bar_box',collision_verified=False,native_grip_verified=False)


def closed_hand_geometry(author,side):
    from .execution_design_e18_geometry import actual_hand_clouds
    geometry=actual_hand_clouds(author,side)
    robot=author.scene.robots[side]
    ids,names=robot.find_joints('panda_finger_joint[1-2]')
    if list(names)!=['panda_finger_joint1','panda_finger_joint2']:
        raise RuntimeError('Measured E18 finger joint order required')
    q=robot.data.joint_pos[0,ids].detach().cpu().numpy()
    if q.shape!=(2,)or not np.isfinite(q).all()or np.any(q<-.0001)or np.any(q>.041):
        raise RuntimeError('Measured E18 finger opening invalid')
    jaw=np.asarray(geometry['jaw_axis_tcp'])
    closed=[np.asarray(c).copy() for c in geometry['clouds_tcp']]
    for i,sign in enumerate((1.,-1.)):closed[i]-=sign*q[i]*jaw
    geometry.update(closed_clouds_tcp=closed,measured_opening_m=q.tolist())
    return geometry


def bar_pinch_candidate(geometry,rotation,point,outward,bar_axis):
    """Both finger convex hulls must reach the bar while clearing its panel.

    Predicts closure geometry only. No pose writes, no contact/score injection.
    The bar dimensions/panel gap are the reviewed original source geometry.
    """
    if geometry.get('source')!='actual_native_collision_mesh_current_body_pose':
        raise ValueError('Actual native E18 hand geometry required')
    normal=np.asarray(outward,float);normal/=np.linalg.norm(normal)
    bar=np.asarray(bar_axis,float);bar/=np.linalg.norm(bar)
    short=np.cross(normal,bar);short/=np.linalg.norm(short)
    rotation=np.asarray(rotation,float);point=np.asarray(point,float)
    clouds=[np.asarray(c,float)@rotation.T for c in geometry['closed_clouds_tcp']]
    if len(clouds)!=3 or any(c.ndim!=2 or c.shape[1]!=3 or not np.isfinite(c).all()for c in clouds):
        raise ValueError('Complete finite closed E18 collision clouds required')
    jaw=rotation@np.asarray(geometry['jaw_axis_tcp'],float)
    hulls=[ConvexHull(c).equations for c in clouds[:2]]
    # d: TCP outward offset; q: symmetric physical finger opening;
    # t1/t2: distinct points along the original 97.94 mm handle bar.
    matrix=[];rhs=[]
    for i,(equations,sign)in enumerate(zip(hulls,(1.,-1.))):
        for eq in equations:
            n=eq[:3];row=np.zeros(4)
            row[0]=-n@normal;row[1]=-sign*n@jaw;row[2+i]=n@bar
            matrix.append(row);rhs.append(-eq[3])
        inward=-normal;extent=float(np.max(clouds[i]@inward))
        matrix.append([-1.,sign*jaw@inward,0,0]);rhs.append(.006-extent)
        matrix.append([-1.,0,0,0]);rhs.append(.006-extent-sign*.04*(jaw@inward))
    result=linprog([0,-1,0,0],A_ub=matrix,b_ub=rhs,
                   bounds=[(0.,.06),(.003,.035),(-.048,.048),(-.048,.048)],method='highs')
    radius=max(float(np.max(np.linalg.norm(c,axis=1)))for c in geometry['clouds_tcp'])
    fallback=dict(feasible=False,target_position=point.tolist(),rotation_safe_z_m=float(geometry['table_top']+radius+.015),
                  collision_verified=False,native_grip_verified=False,reason='no bilateral closure geometry')
    if not result.success:return fallback
    distance,opening,t1,t2=map(float,result.x);tcp=point+normal*distance
    floor=[float(np.min((clouds[2]+tcp)[:,2])-geometry['table_top'])]
    open_overlap=False
    # Whole hand floor and panel clearance throughout linear finger closure.
    # For convex translated vertices, endpoint bounds cover intermediate q.
    for i,sign in enumerate((1.,-1.)):
        for q in (opening,.04):
            cloud=clouds[i]+tcp+sign*q*jaw
            floor.append(float(cloud[:,2].min()-geometry['table_top']))
        equations=hulls[i];offset=normal*distance+sign*.04*jaw
        A=list(equations[:,:3]);b=list(-equations[:,3]+equations[:,:3]@offset)
        # World positions relative to actual bar centre; convex bar box.
        for axis,half in ((normal,.001304),(short,.001371),(bar,.04897)):
            A.extend((axis,-axis));b.extend((half,half))
        overlap=linprog([0,0,0],A_ub=A,b_ub=b,bounds=[(None,None)]*3,method='highs')
        open_overlap|=bool(overlap.success)
    palm_out=float(np.min((clouds[2]+tcp-point)@normal))
    return dict(target_position=tcp.tolist(),rotation_safe_z_m=fallback['rotation_safe_z_m'],
                hand_floor_clearances_m=floor,closing_opening_m=opening,bar_contact_parameters_m=[t1,t2],
                palm_outside_handle_plane_m=palm_out,open_fingers_intersect_bar=open_overlap,
                feasible=bool(min(floor)>.002 and palm_out>.003 and not open_overlap),
                collision_verified=False,native_grip_verified=False)
