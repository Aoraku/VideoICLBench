"""Explicit author-only timing of unchanged OMPL joint-space straight edges.

MPlib0.2.1's default TOPP fits a spline through geometric path vertices. This
opt-in sidecar instead stops smoothly at each vertex and never cuts a corner.
All source limits and the caller's complete native-world checks still apply.
"""
from contextlib import contextmanager
import math
import numpy as np


def quintic_geometric_path(path,dt,velocity_limits,acceleration_limits,max_seconds=30.):
    path=np.asarray(path,float);velocity=np.asarray(velocity_limits,float);acceleration=np.asarray(acceleration_limits,float)
    if path.ndim!=2 or len(path)<1 or path.shape[1]<1 or velocity.shape!=(path.shape[1],)or acceleration.shape!=velocity.shape or not np.isfinite(path).all()or not np.isfinite(np.r_[velocity,acceleration]).all()or not 0<max_seconds<=30. or np.any(velocity<=0)or np.any(acceleration<=0)or not math.isclose(float(dt),.004,abs_tol=1e-12):raise ValueError('Finite geometric path and original4ms/source caps required')
    keep=np.r_[True,np.max(abs(np.diff(path,axis=0)),axis=1)>1e-12];path=path[keep]
    if len(path)==1:return np.array([0.,dt]),np.repeat(path,2,axis=0),np.zeros((2,path.shape[1])),np.zeros((2,path.shape[1])),dt
    deltas=np.diff(path,axis=0);durations=np.maximum(np.max(1.875*abs(deltas)/velocity,axis=1),np.max(np.sqrt((10/math.sqrt(3))*abs(deltas)/acceleration),axis=1));ticks=np.maximum(2,np.ceil(durations/dt).astype(int))
    if float(ticks.sum()*dt)>max_seconds+1e-9:raise ValueError('Geometric source-limited timing exceeds original30s author bound')
    position=[path[:1]];speed=[np.zeros((1,path.shape[1]))];accel=[np.zeros((1,path.shape[1]))]
    for start,delta,n in zip(path[:-1],deltas,ticks):
        u=np.arange(1,int(n)+1)/n;T=float(n*dt);alpha=10*u**3-15*u**4+6*u**5;rate=(30*u**2-60*u**3+30*u**4)/T;second=(60*u-180*u**2+120*u**3)/(T*T)
        position.append(start+alpha[:,None]*delta);speed.append(rate[:,None]*delta);accel.append(second[:,None]*delta)
    q=np.concatenate(position);qd=np.concatenate(speed);qdd=np.concatenate(accel);time=np.arange(len(q))*dt
    return time,q,qd,qdd,float(time[-1])


@contextmanager
def geometric_timing(profile,audit):
    if profile.get('quintic_geometric_topp')is not True:yield;return
    import mplib
    original=mplib.Planner.TOPP
    def timed(planner,path,step=.1,verbose=False):
        result=quintic_geometric_path(path,step,planner.joint_vel_limits,planner.joint_acc_limits)
        audit.append(dict(method='unchanged_OMPL_straight_edges_stop_at_vertices_quintic',geometric_vertices=len(path),fixed_dt=float(step),duration_s=result[-1],source_velocity_cap=np.asarray(planner.joint_vel_limits).tolist(),source_acceleration_cap=np.asarray(planner.joint_acc_limits).tolist(),max_velocity=np.max(abs(result[2]),axis=0).tolist(),max_acceleration=np.max(abs(result[3]),axis=0).tolist(),corners_cut=False,limits_relaxed=False))
        return result
    mplib.Planner.TOPP=timed
    try:yield
    finally:mplib.Planner.TOPP=original
