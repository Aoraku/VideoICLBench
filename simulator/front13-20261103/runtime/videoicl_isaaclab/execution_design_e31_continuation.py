"""Private E31 pose continuation, read-only measured bounded-joint screening.

Candidates are not executed here and are never a native grasp/score witness.
The measured TCP Jacobian defines one POE model. Each small pose is solved
from the previous joint vector, retaining an explicit margin and jump bound.
"""
import math
import numpy as np


def pinch_rotations(outward):
    """Vertical opposed fingers may enter the exposed rim at an oblique yaw."""
    outward=np.asarray(outward,float)
    if outward.shape!=(3,) or not np.isfinite(outward).all() or not np.allclose(abs(outward),[1,0,0]):
        raise ValueError('Measured X table edge required')
    for jaw_sign in (-1.,1.):
        jaw=np.array([0.,0.,jaw_sign])
        base=np.column_stack((-np.cross(jaw,outward),jaw,-outward))
        for yaw in (-30.,-60.,0.):
            angle=math.radians(yaw);c,s=math.cos(angle),math.sin(angle)
            rz=np.array([[c,-s,0.],[s,c,0.],[0.,0.,1.]])
            yield rz@base


def screen(measured,waypoints,margin=.08,max_joint_step=.45):
    from scipy.optimize import least_squares
    from scipy.spatial.transform import Rotation
    from .execution_design_drawer_ik_probe import forward_at_delta
    from .author_orientation import _axis_angle
    p=np.asarray(measured['position'],float);r=np.asarray(measured['rotation_task'],float)
    jac=np.asarray(measured['jacobian'],float);q=np.asarray(measured['q'],float);limits=np.asarray(measured['limits'],float)
    if p.shape!=(3,)or r.shape!=(3,3)or jac.shape!=(6,7)or q.shape!=(7,)or limits.shape!=(7,2):
        raise ValueError('Complete measured Panda pose/Jacobian/joints required')
    if not np.isfinite(np.r_[p,r.ravel(),jac.ravel(),q,limits.ravel()]).all():raise ValueError('Finite native reference required')
    lo=limits[:,0]+margin+1e-5-q;hi=limits[:,1]-margin-1e-5-q
    if np.any(lo>=0)or np.any(hi<=0):return dict(passed=False,reason='initial_joint_margin',samples=[])
    delta=np.zeros(7);last_p=p.copy();last_r=r.copy();rows=[]
    for phase,target in enumerate(waypoints):
        ep=np.asarray(target['position'],float);er=np.asarray(target['rotation'],float)
        if ep.shape!=(3,)or er.shape!=(3,3)or not np.isfinite(np.r_[ep,er.ravel()]).all():raise ValueError('Finite pose required')
        rotation_delta=Rotation.from_matrix(er@last_r.T).as_rotvec()
        count=max(1,math.ceil(float(np.linalg.norm(ep-last_p))/.02),math.ceil(float(np.linalg.norm(rotation_delta))/math.radians(6)))
        for i in range(1,count+1):
            fraction=i/count;tp=last_p+fraction*(ep-last_p);tr=Rotation.from_rotvec(fraction*rotation_delta).as_matrix()@last_r
            previous=delta.copy()
            def residual(d):
                fp,fr=forward_at_delta(p,r,jac,d);axis,angle=_axis_angle(tr@fr.T)
                return np.r_[10*(fp-tp),axis*angle,.01*(d-previous),.001*(q+d-limits.mean(axis=1))/(limits[:,1]-limits[:,0])]
            fit=least_squares(residual,np.clip(previous,lo+1e-8,hi-1e-8),bounds=(lo,hi),max_nfev=120,ftol=1e-8,xtol=1e-8,gtol=1e-8)
            delta=fit.x;fp,fr=forward_at_delta(p,r,jac,delta)
            pe=float(np.linalg.norm(fp-tp));oe=float(_axis_angle(tr@fr.T)[1]);remaining=float(np.min(np.minimum(q+delta-limits[:,0],limits[:,1]-q-delta)))
            jump=float(np.max(abs(delta-previous)))
            row=dict(phase=phase,position=tp.tolist(),rotation=tr.tolist(),position_error_m=pe,orientation_error_rad=oe,minimum_joint_margin_rad=remaining,maximum_joint_step_rad=jump,candidate_joints_rad=(q+delta).tolist())
            rows.append(row)
            if pe>=.001 or oe>=math.radians(1.5)or remaining<margin or jump>=max_joint_step:
                return dict(passed=False,reason='continuation_pose_or_branch_rejected',samples=rows)
        last_p=ep;last_r=er
    return dict(passed=True,reason='measured_continuation_screen_only',samples=rows,minimum_joint_margin_rad=min(x['minimum_joint_margin_rad']for x in rows),maximum_joint_step_rad=max(x['maximum_joint_step_rad']for x in rows))


def orient_empty(a,side,target):
    """Public rotations with achieved-angle feedback, strict one-degree end."""
    from .author_orientation import _axis_angle
    from .execution_design_author_rotation import command_degrees,update_loss
    from .execution_design_thin_edge import table_bounds_task
    target=np.asarray(target,float);loss=0.;history=[]
    labels=(('ROLL_LEFT','ROLL_RIGHT'),('PITCH_UP','PITCH_DOWN'),('ROTATE_CCW','ROTATE_CW'))
    floor=float(table_bounds_task(a.scene)['top'])
    def guard():
        state,_=a.c.snapshot()
        index=0 if side=='left'else 1
        if any(body['grasp'][index]for body in state.values()):raise RuntimeError('Empty plate wrist orientation unexpectedly holds an object')
        if a.finger_geometry(side)['lowest_z_task_m']<floor+.002:raise RuntimeError('E31 empty wrist lost actual table clearance')
        robot=a.scene.robots[side];arm,_,_=a.c.ids[side]
        def array(x):return np.asarray(x.detach().cpu().numpy()if hasattr(x,'detach')else x,float)
        q=array(robot.data.joint_pos[0,arm]);limits=array(robot.data.joint_pos_limits[0,arm])
        if np.min(np.minimum(q-limits[:,0],limits[:,1]-q))<.03:raise RuntimeError('E31 empty wrist approaches actual joint limit')
    for _ in range(180):
        guard();current=np.asarray(a.tcp_rotation_task(side));axis,angle=_axis_angle(target@current.T)
        if angle<math.radians(1.):return
        component=int(np.argmax(abs(axis)));token=labels[component][int(axis[component]<0)]
        requested=command_degrees(angle*axis[component],loss,maximum=8.)
        a.act(token if side=='left'else'STILL',token if side=='right'else'STILL',rotation_deg=requested)
        guard()
        feedback=a.c.action_feedback()['control_feedback'][side]
        if feedback['status']=='blocked' or feedback.get('joint_limit_names'):
            raise RuntimeError('E31 empty wrist actual IK/limit feedback refused rotation: '+str(feedback.get('reason')))
        loss,actual=update_loss(current,a.tcp_rotation_task(side),component,axis[component],requested,loss)
        history.append(angle)
        if len(history)>=24 and min(history[-24:-16])-min(history[-8:])<math.radians(.2):raise RuntimeError('Measured E31 empty wrist orientation stalled')
    raise RuntimeError('Measured E31 empty wrist orientation action bound exhausted')
