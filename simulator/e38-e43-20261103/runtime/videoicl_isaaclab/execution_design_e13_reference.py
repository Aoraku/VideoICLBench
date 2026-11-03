"""Measured side-band alignment for the v3 E13 engineering reference only."""
import numpy as np


def side_band(state, obj):
    pos=np.asarray(state['pos'],float);mat=np.asarray(state['mat'],float)
    half=np.asarray(obj['size'],float)
    if (pos.shape!=(3,) or mat.shape!=(3,3) or half.shape!=(3,)
            or not np.isfinite(np.r_[pos,mat.ravel(),half]).all()
            or mat[2,2]<.995 or not .009<2*half[2]<.010):
        raise ValueError('E13 reference requires the reviewed upright thin phone')
    center=pos+mat@np.asarray(obj.get('local_bounds_center',[0,0,0]),float)
    extent=np.abs(mat[2])@half
    bottom,top=float(center[2]-extent),float(center[2]+extent)
    if bottom<.799 or bottom>.803:
        raise ValueError('E13 phone is not on the measured table support')
    point=pos+mat@np.asarray(obj.get('grasp_point_local',[0,0,0]),float)
    return point,max(.8008,bottom+.0008),top


def align_phone_side_band(author, side, name):
    """Re-measure open fingers near the table instead of reusing high-pose toes."""
    spec=author.scene.spec
    if (name!='phone' or spec.get('id')!='E13'
            or spec.get('execution_design',{}).get('revision')!='embodied50-execution-v3-20261102'
            or not getattr(author,'_execution_design_reference_authorized',False)):
        raise ValueError('E13 v3 independent engineering reference required')
    obj=next(o for o in spec['objects'] if o['id']==name)
    # All adjustments use normal public moves. Failure remains an engineering
    # failure; no pose write, attachment or weakened grasp sensor is available.
    for _ in range(6):
        state,_=author.c.snapshot();point,toe_target,top=side_band(state[name],obj)
        tip=np.asarray(author.tip(side),float)
        geometry=author.finger_geometry(side)
        if geometry.get('source')!='actual_collision_mesh_current_body_pose':
            raise ValueError('Actual E13 finger collision geometry required')
        lowest=float(geometry['lowest_z_task_m'])
        if not np.isfinite(np.r_[tip,lowest]).all():raise ValueError('Nonfinite E13 finger pose')
        error=toe_target-lowest
        if abs(error)<=.0003 and np.max(np.abs(tip[:2]-point[:2]))<=.001:
            if not .8003<=lowest<=top-.001:
                raise RuntimeError('E13 toes are outside the supported side band')
            return
        target=[*point[:2],float(tip[2]+np.clip(error,-.003,.003))]
        author.move_generated({side:target},tolerance=.0003)
    raise RuntimeError('E13 actual open fingers did not converge to side contact band')
