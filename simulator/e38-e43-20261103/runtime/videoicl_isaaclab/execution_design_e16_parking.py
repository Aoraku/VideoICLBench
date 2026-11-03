"""E16-only released-wrist unwinding before the normal high parking route."""
import json,math
import numpy as np
from .execution_design import REVISION_V3
from .author_orientation import _rotation,_axis_angle
from .realworld_tool_expert import _axis_rotation


def _valid_ik(row,increment=False):
    fields=('position_error_m','orientation_error_rad','minimum_joint_margin_rad','joint_distance_rad')
    if not all(np.isfinite(row.get(k,float('nan'))) for k in fields):return False
    return bool(row.get('kinematically_reachable') and row['position_error_m']<.001
                and row['orientation_error_rad']<math.radians(1.5)
                and row['minimum_joint_margin_rad']>.03
                and (not increment or row['joint_distance_rad']<.35))


def remember_empty_home(author):
    spec=author.scene.spec
    if (spec.get('id')=='E16' and spec.get('execution_design',{}).get('revision')==REVISION_V3
            and getattr(author,'_execution_design_reference_authorized',False)):
        if not hasattr(author,'_e16_home_rotations'):
            author._e16_home_rotations={s:_rotation(author.tcp_rotation_task(s),'actual E16 home').copy()
                                       for s in ('left','right')}


def _joints(author,side):
    def arr(x):
        if hasattr(x,'detach'):x=x.detach()
        if hasattr(x,'cpu'):x=x.cpu()
        return np.asarray(x,float)
    robot=author.scene.robots[side];ids,_=robot.find_joints('panda_joint[1-7]')
    if len(ids)!=7:raise RuntimeError('Actual seven-joint E16 Panda arm required')
    q=arr(robot.data.joint_pos)[0,ids];limits=arr(robot.data.joint_pos_limits)[0,ids]
    if not np.isfinite(q).all()or not np.isfinite(limits).all():raise RuntimeError('Finite E16 joints required')
    return q,limits


def restore_released_wrist(author,side,clearance,ik_probe=None):
    spec=author.scene.spec
    if (spec.get('id')!='E16' or spec.get('execution_design',{}).get('revision')!=REVISION_V3
            or not getattr(author,'_execution_design_reference_authorized',False)
            or not getattr(author,'control_report',{}).get('engineering_reference_only')
            or author.scene.embodiment.name!='franka' or getattr(author,'smooth',False)):
        raise ValueError('E16 explicit public engineering parking required')
    target=_rotation(author._e16_home_rotations[side],'measured E16 home rotation')
    def empty():
        state,_=author.c.snapshot()
        if author.carried_payload is not None or any(any(b.get('grasp',[]))for b in state.values()):
            raise RuntimeError('E16 wrist restoration requires actual released objects')
    empty();current=_rotation(author.tcp_rotation_task(side),'actual empty E16 wrist')
    axis,angle=_axis_angle(target@current.T)
    if angle<math.radians(1.5):return
    q,limits=_joints(author,side)
    # At pi, select the equivalent winding that returns joint7 toward its
    # measured initial value rather than continuing its loaded yaw direction.
    if angle>math.radians(150)and abs(axis[2])>.9:
        initial=float(author.scene.embodiment.config['robots'][side]['initial_joints']['panda_joint7'])
        desired_yaw=-np.sign(initial-q[-1])
        if axis[2]*desired_yaw<0:axis=-axis;angle=2*math.pi-angle
    centre=np.asarray(author.tip(side),float).copy();centre[2]=max(centre[2],float(clearance)+.08,.95)
    count=max(1,math.ceil(math.degrees(angle)/12))
    waypoints=[_axis_rotation(axis,angle*i/count)@current for i in range(1,count+1)]
    if ik_probe is None:
        from .execution_design_drawer_ik_probe import inspect
        ik_probe=inspect
    screened=ik_probe(author,author.c,side,[dict(position=centre,rotation=r)for r in waypoints])
    if len(screened)!=len(waypoints)or not all(_valid_ik(r) for r in screened):
        raise RuntimeError('E16 released-wrist arc has no verified IK margin')
    author.stage='e16-restore-empty-wrist-'+side
    author.move_generated({side:centre.tolist()},tolerance=.001)
    waypoint=0;labels=(('ROLL_LEFT','ROLL_RIGHT'),('PITCH_UP','PITCH_DOWN'),('ROTATE_CCW','ROTATE_CW'))
    for _ in range(280):
        empty();current=_rotation(author.tcp_rotation_task(side),'actual empty E16 wrist')
        if _axis_angle(target@current.T)[1]<math.radians(1.5):return
        geometry=author.finger_geometry(side)
        if geometry.get('source')!='actual_collision_mesh_current_body_pose' or geometry['lowest_z_task_m']<clearance-.015:
            raise RuntimeError('E16 empty wrist lost measured obstacle clearance')
        if np.max(np.abs(np.asarray(author.tip(side))-centre))>.002:
            author.move_generated({side:centre.tolist()},tolerance=.001)
            if np.max(np.abs(np.asarray(author.tip(side))-centre))>.002:raise RuntimeError('E16 actual rotation centre not recovered')
            current=_rotation(author.tcp_rotation_task(side),'actual empty E16 wrist')
        while waypoint<len(waypoints)-1 and _axis_angle(waypoints[waypoint]@current.T)[1]<math.radians(1.5):waypoint+=1
        a,error=_axis_angle(waypoints[waypoint]@current.T);choices=[]
        for i in range(3):
            degrees=min(4.,max(.5,abs(math.degrees(error*a[i]))))
            for sign in (1.,-1.):
                r=_axis_rotation(np.eye(3)[i],sign*math.radians(degrees))@current
                residual=_axis_angle(waypoints[waypoint]@r.T)[1]
                if residual<error-math.radians(.01):choices.append((residual,labels[i][int(sign<0)],degrees,r))
        checked=ik_probe(author,author.c,side,[dict(position=centre,rotation=x[3])for x in choices])
        if len(checked)!=len(choices):raise RuntimeError('Incomplete E16 incremental IK')
        valid=[(i,r)for i,r in enumerate(checked)if _valid_ik(r,increment=True)]
        if not valid:raise RuntimeError('No safe nearby E16 empty-wrist increment')
        i,_=min(valid,key=lambda x:choices[x[0]][0]);_,token,degrees,_=choices[i]
        author.act(token if side=='left'else'STILL',token if side=='right'else'STILL',rotation_deg=degrees)
        q,limits=_joints(author,side);feedback=author.c.action_feedback()['control_feedback'][side]
        with (author.out/'e16-empty-wrist.private.jsonl').open('a')as f:
            f.write(json.dumps(dict(step=author.c.steps,side=side,token=token,waypoint=waypoint,q=q.tolist(),feedback=feedback,source_or_score_written=False))+'\n')
        if (np.any(q<limits[:,0]+.005)or np.any(q>limits[:,1]-.005)
                or feedback.get('status')=='blocked' or feedback.get('joint_limit_names')):
            raise RuntimeError('E16 public empty-wrist action reached native limit/refusal')
    raise RuntimeError('E16 released-wrist rotation did not converge')
