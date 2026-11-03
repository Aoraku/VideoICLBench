"""Read-only native COM-to-TCP Jacobian reference; never actuates."""
import numpy as np


def shift_to_tcp(jacobian,com_world,tcp_world):
    jacobian=np.asarray(jacobian,float).copy();lever=np.asarray(tcp_world,float)-np.asarray(com_world,float)
    if jacobian.shape!=(6,7)or lever.shape!=(3,)or not np.isfinite(np.r_[jacobian.ravel(),lever]).all():
        raise ValueError('Finite native COM Jacobian and measured TCP required')
    x,y,z=lever;skew=np.array([[0,-z,y],[z,0,-x],[-y,x,0]])
    jacobian[:3]-=skew@jacobian[3:]
    return jacobian


def capture(author,controller,side):
    from .author_mplib_planner import _rotation
    def array(value):
        return np.asarray(value.detach().cpu().numpy()if hasattr(value,'detach')else value,float)
    robot=author.scene.robots[side];arm,_,bid=controller.ids[side]
    wrist=_rotation(array(robot.data.body_quat_w[0,bid]));body=array(robot.data.body_pos_w[0,bid])
    local=array(robot.root_physx_view.get_coms()[0,bid,:3])
    if local.shape!=(3,)or not np.isfinite(local).all():raise ValueError('Actual native hand COM unavailable')
    com=body+wrist@local;tcp=body+wrist@np.asarray(author.scene.embodiment.tcp,float)
    evidence=dict(native_body_index=bid,body_position_world=body.tolist(),body_rotation_world=wrist.tolist(),
        native_com_local=local.tolist(),computed_com_world=com.tolist(),tcp_world=tcp.tolist(),
        tcp_minus_com_world=(tcp-com).tolist(),jacobian_reference='native_rigid_body_COM_to_actual_TCP')
    for field,expected in [('body_com_pos_w',com),('body_link_pos_w',body)]:
        value=getattr(robot.data,field,None)
        evidence[field]=array(value[0,bid]).tolist()if value is not None else None
        if value is not None:
            error=float(np.linalg.norm(array(value[0,bid])-expected));evidence[field+'_agreement_m']=error
            if error>2e-5:raise ValueError('Native body/COM reference mismatch: '+field)
    if callable(getattr(author.scene,'world_to_task',None)):
        error=float(np.linalg.norm(author.scene.world_to_task(tcp)-np.asarray(author.tip(side))))
        evidence['tcp_task_agreement_m']=error
        if error>2e-5:raise ValueError('Native measured TCP reference mismatch')
    raw=array(robot.root_physx_view.get_jacobians()[0,bid-1 if robot.is_fixed_base else bid][:,arm])
    shifted=shift_to_tcp(raw,com,tcp);task=np.asarray(author.scene.layout.task_rotation,float).T
    jac=np.vstack((task@shifted[:3],task@shifted[3:]))
    return dict(position=np.asarray(author.tip(side),float).tolist(),rotation_task=np.asarray(author.tcp_rotation_task(side),float).tolist(),
        q=array(robot.data.joint_pos[0,arm]).tolist(),limits=array(robot.data.joint_pos_limits[0,arm]).tolist(),
        jacobian=jac.tolist(),reference=evidence)
