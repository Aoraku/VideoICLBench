"""Transmit a constitutive passive torque to the actual native DOF buffer."""
import math
import numpy as np


def apply_native_passive_effort(asset,index,effort,*,array_module):
    if not math.isfinite(effort):raise ValueError('Finite passive source torque required')
    if asset.actuators:raise ValueError('Passive source effort bridge requires no competing actuator')
    requested=array_module.zeros_like(asset.data.joint_pos)
    requested[:,index]=effort
    asset.set_joint_effort_target(requested)
    # IsaacLab2.1 writes its simulation buffer, which remains zero without
    # actuator models. Preserve its other native writes, then explicitly send
    # the source material effort through the supported PhysX tensor API.
    asset.write_data_to_sim()
    asset.root_physx_view.set_dof_actuation_forces(requested,asset._ALL_INDICES)
    actual=asset.root_physx_view.get_dof_actuation_forces()
    if hasattr(actual,'detach'):actual=actual.detach()
    if hasattr(actual,'cpu'):actual=actual.cpu()
    measured=np.asarray(actual,float)
    wanted=requested
    if hasattr(wanted,'detach'):wanted=wanted.detach()
    if hasattr(wanted,'cpu'):wanted=wanted.cpu()
    wanted=np.asarray(wanted,float)
    if measured.shape!=wanted.shape or not np.isfinite(measured).all():
        raise RuntimeError('Missing finite native material-torque readback')
    error=float(np.max(np.abs(measured-wanted)))
    if error>2e-8:raise RuntimeError('Actual native passive torque differs from source material effort')
    return dict(commanded_effort_nm=float(effort),native_readback_effort_nm=float(measured[0,index]),
                max_abs_native_effort_error_nm=error)
