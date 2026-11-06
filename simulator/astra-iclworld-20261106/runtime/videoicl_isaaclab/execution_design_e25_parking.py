"""E25 engineering empty-wrist return and genuine two-point table regrasp."""
from copy import deepcopy
import json,math
import numpy as np
from .execution_design import REVISION_V3,source_sha256
from .author_orientation import _axis_angle,_rotation
from .realworld_tool_expert import _axis_rotation


def _scope(author):
    s=author.scene.spec
    if (s.get('id')!='E25'or s.get('execution_design',{}).get('revision')!=REVISION_V3
            or s['execution_design'].get('source_sha256')!=source_sha256(REVISION_V3)
            or not getattr(author,'_execution_design_reference_authorized',False)
            or not author.control_report.get('engineering_reference_only')
            or author.scene.embodiment.name!='franka'or author.smooth):
        raise ValueError('Checksum-pinned E25 v3 public engineering reference required')


def source_pickup_spec(author,obj,goal):
    _scope(author)
    source=next(o for o in author.scene.spec['objects']if o['id']==obj['id'])
    if (author.scene.spec['variant']!='B'or goal.get('_e07_relay_phase')!='place_on_table'
            or '_e07_after_relay'in goal or goal.get('object')!=obj['id']
            or goal['_e25_pickup_grasp_local']!=source['grasp_point_local']):
        raise ValueError('E25 B original handle pickup before genuine relay required')
    from .execution_design_e25_b_reference import candidate_grasp
    candidate_grasp(author,source)  # pin the identical source mesh
    result=deepcopy(obj);result['grasp_point_local']=list(source['grasp_point_local'])
    return result


def _valid(row,increment=False):
    return bool(row.get('kinematically_reachable')
        and all(np.isfinite(row.get(k,float('nan')))for k in ('position_error_m','orientation_error_rad','minimum_joint_margin_rad','joint_distance_rad'))
        and row['position_error_m']<.001 and row['orientation_error_rad']<math.radians(1.5)
        and row['minimum_joint_margin_rad']>.03
        and (not increment or row['joint_distance_rad']<.35))


def restore_before_return(author,side,clearance,ik_probe=None):
    """Unwind the released hand before translation can drive q6 to its stop.

    Native IK rejects candidate waypoints. Every executed rotation and move
    remains a public action; measured joints, fingers and empty hand are checked.
    """
    _scope(author)
    from .execution_design_e25_b_reference import _joints
    target=_rotation(author._e25_home_rotations[side],'actual initial E25 hand')
    def empty():
        state,_=author.c.snapshot()
        if author.carried_payload is not None or any(any(b.get('grasp',[]))for b in state.values()):
            raise RuntimeError('E25 wrist return requires actual released objects')
    empty();current=_rotation(author.tcp_rotation_task(side),'actual released E25 hand')
    axis,angle=_axis_angle(target@current.T)
    if angle<math.radians(1.5):return
    if ik_probe is None:
        from .execution_design_drawer_ik_probe import inspect
        ik_probe=inspect
    tip=np.asarray(author.tip(side),float).copy();geo=author.finger_geometry(side)
    if geo.get('source')!='actual_collision_mesh_current_body_pose':raise ValueError('Actual E25 finger mesh required')
    floor=float(clearance)-float(tip[2]-geo['lowest_z_task_m'])-.015
    # C's released knife hand can remain below the return clearance. An IK
    # solution at that same low point does not establish rotation clearance.
    # Lift the real empty hand first; retain the original measured floor and
    # every per-increment joint/contact/TCP guard below.
    lift=0.
    if author.scene.spec.get('variant')=='C':
        lift=max(0.,float(clearance)-float(tip[2]))
        fingers=geo.get('fingers',[])
        if fingers:
            import itertools
            radius=max(float(np.linalg.norm(np.asarray(corner)-tip))for finger in fingers
                for corner in itertools.product(*zip(finger['aabb_min_task_m'],finger['aabb_max_task_m'])))
            lift=max(lift,max(.84,floor)+radius+.015-float(tip[2]))
    log=author.out/'e25-empty-return.private.jsonl'
    def record(**row):
        with log.open('a')as f:f.write(json.dumps(dict(side=side,native_passed=False,**row))+'\n')
    # Choose a nearby clear rotation site before the horizontal return, rather
    # than asking the loaded wrist orientation to reach the opposite workspace.
    selected=None
    windings=(angle,angle-2*math.pi)if angle>math.radians(150)else(angle,)
    offsets=(-.08,-.04,0.)if author.scene.spec.get('variant')=='B'and side=='left'else(0.,-.04,-.08)
    for dz in (lift,lift+.04,lift+.08):
        for dx in offsets:
            centre=tip+np.array([dx,0,dz])
            for winding in windings:
                waypoints=[_axis_rotation(axis,winding*f)@current for f in np.linspace(0,1,13)]
                rows=ik_probe(author,author.c,side,[dict(position=centre.tolist(),rotation=r.tolist())for r in waypoints])
                if len(rows)==len(waypoints)and all(_valid(r)for r in rows):
                    selected=(centre,waypoints);break
            if selected is not None:break
        if selected is not None:break
    if selected is None:
        record(phase='screen_rejected',actual_tip=tip.tolist())
        raise RuntimeError('E25 released-wrist return has no measured local IK arc')
    centre,waypoints=selected
    record(phase='screen_selected',centre=centre.tolist(),original_angle_rad=angle)
    author.stage='e25-restore-empty-wrist-'+side
    author.move_generated({side:centre.tolist()},tolerance=.001)
    labels=(('ROLL_LEFT','ROLL_RIGHT'),('PITCH_UP','PITCH_DOWN'),('ROTATE_CCW','ROTATE_CW'))
    waypoint=1;errors=[]
    for _ in range(280):
        empty();actual=_rotation(author.tcp_rotation_task(side),'actual public E25 hand')
        total=_axis_angle(target@actual.T)[1]
        if total<math.radians(1.5):return
        geometry=author.finger_geometry(side)
        if geometry.get('source')!='actual_collision_mesh_current_body_pose'or geometry['lowest_z_task_m']<max(.84,floor):
            raise RuntimeError('E25 empty return lost actual obstacle clearance')
        if np.max(np.abs(np.asarray(author.tip(side))-centre))>.002:
            author.move_generated({side:centre.tolist()},tolerance=.001)
            if np.max(np.abs(np.asarray(author.tip(side))-centre))>.002:raise RuntimeError('E25 actual empty rotation centre drifted')
            actual=_rotation(author.tcp_rotation_task(side),'recovered public E25 hand')
        while waypoint<len(waypoints)-1 and _axis_angle(waypoints[waypoint]@actual.T)[1]<math.radians(1.5):waypoint+=1
        _,error=_axis_angle(waypoints[waypoint]@actual.T);choices=[]
        for k in range(3):
            for sign in (1.,-1.):
                for degrees in (3.,1.,.5):
                    r=_axis_rotation(np.eye(3)[k],sign*math.radians(degrees))@actual
                    residual=_axis_angle(waypoints[waypoint]@r.T)[1]
                    if residual<error-math.radians(.01):choices.append((residual,labels[k][int(sign<0)],degrees,r))
        rows=ik_probe(author,author.c,side,[dict(position=centre.tolist(),rotation=x[3].tolist())for x in choices])
        if len(rows)!=len(choices):raise RuntimeError('Incomplete E25 public increment screening')
        valid=[i for i,r in enumerate(rows)if _valid(r,True)]
        if not valid:raise RuntimeError('No safe measured E25 empty return increment')
        chosen=min(valid,key=lambda i:choices[i][0]);_,token,degrees,_=choices[chosen]
        author.act(token if side=='left'else'STILL',token if side=='right'else'STILL',rotation_deg=degrees)
        q,limits,names=_joints(author,side);feedback=author.c.action_feedback()['control_feedback'][side]
        record(phase='public_step',waypoint=waypoint,token=token,degrees=degrees,actual_joints_rad=q.tolist(),feedback=feedback)
        if (np.any(q<=limits[:,0]+.005)or np.any(q>=limits[:,1]-.005)
                or feedback.get('status')=='blocked'or feedback.get('joint_limit_names')or feedback.get('consecutive_ik_refusals',0)):
            raise RuntimeError('E25 public empty return reached native limit/refusal')
        errors.append((waypoint,error))
        if len(errors)>=25 and all(w==waypoint for w,e in errors[-25:])and min(e for w,e in errors[-12:])>min(e for w,e in errors[-25:-12])-math.radians(.1):
            raise RuntimeError('E25 actual empty return stopped progressing')
    raise RuntimeError('E25 actual empty return did not converge')
