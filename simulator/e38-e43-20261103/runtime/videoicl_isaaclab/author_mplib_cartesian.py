"""Explicit private official-MPlib screw candidates with unchanged outer gates.

This temporarily routes only the supplied callback's plan_pose calls. The
stable a596 planner still builds the actual world/attachments, retimes at4ms,
and rejects source-limit, endpoint and every sampled/refined FCL violation.
No native articulation or object is written by this module.
"""
from __future__ import annotations
import numpy as np


def run_screw_candidate(callback, *, qpos_step=.005, planner_class=None):
    if not np.isfinite(qpos_step)or not 0<qpos_step<=.01:
        raise ValueError('Private screw q step must be finite and <=.01rad')
    if planner_class is None:
        import mplib
        planner_class=mplib.Planner
    original=planner_class.plan_pose;audits=[]
    def screw(self,goal_pose,current_qpos,mask=None,**options):
        current=np.asarray(current_qpos,float)
        expected=np.ones(len(current),dtype=bool);expected[list(self.move_group_joint_indices)]=False
        if mask is None or not np.array_equal(np.asarray(mask,bool),expected):
            raise ValueError('Screw candidate requires the original exact non-arm joint mask')
        if not np.isclose(float(options.get('time_step',0.)),.004,atol=1e-9,rtol=0.):
            raise ValueError('Screw candidate must use actual4ms discretization')
        result=self.plan_screw(goal_pose,current.copy(),qpos_step=qpos_step,time_step=.004,wrt_world=options.get('wrt_world',True),verbose=False)
        last=np.asarray(self.robot.get_qpos(),float);limits=np.asarray(self.joint_limits)
        row=dict(official_method='mplib.Planner.plan_screw',qpos_step_rad=qpos_step,dt=.004,
                 wrt_world=options.get('wrt_world',True),status=result.get('status'),native_execution=False,
                 actual_start_q=current.tolist(),official_last_model_q=last.tolist(),
                 source_joint_limit_violations=[dict(joint=self.user_joint_names[i],value=float(q),lower=float(limits[i,0]),upper=float(limits[i,1]))for i,q in enumerate(last)if q<limits[i,0]or q>limits[i,1]])
        if result.get('status')!='Success':
            from .author_mplib_planner import _collisions
            row['search_failure_collision_pairs']=_collisions(self,last)
        audits.append(row)
        return result
    planner_class.plan_pose=screw
    try:
        result=callback()
    finally:
        planner_class.plan_pose=original
    result.setdefault('diagnostics',{})['private_screw_candidate']=audits
    result.setdefault('metadata',{})['private_cartesian_method']='official_mplib_plan_screw_with_original_outer_fullworld_verification'
    return result
