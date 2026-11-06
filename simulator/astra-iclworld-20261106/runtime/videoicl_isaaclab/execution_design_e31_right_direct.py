"""Private E31 normal-axis spin and original-hand physical bowl placement."""
import json,math
from types import SimpleNamespace
import numpy as np


def run(a,parameters=None):
    parameters=parameters or {};spec=a.scene.spec;side='right';name=spec['semantic']['plate'];bowl=spec['semantic']['bowl']
    if not(getattr(a,'_execution_design_reference_authorized',False)and spec['id']=='E31'
           and spec['seed']==4201 and spec.get('execution_design',{}).get('condition')=='I'):
        raise ValueError('Private fixed-primary E31 original-hand placement required')
    from scipy.spatial.transform import Rotation
    from scipy.spatial import ConvexHull
    from .execution_design_jacobian_reference import capture
    from .execution_design_e31_continuation import screen
    from .execution_design_e31_arm_clearance import capture_native_meshes,transformed_meshes,LiveTableGuard
    from .execution_design_branch_geometry import collision_parts_task
    from .execution_design_e34_debug import preview_clearance
    from .execution_design_thin_edge import table_bounds_task
    from .execution_design_e31_release import lower_for_release,check_actual_limits
    from .engineering_checkpoint import capture as checkpoint
    from .engineering_native_tick import diagnostic_tick_scope
    reader=getattr(a,'_e31_native_contact_reader',None)
    if reader is None:
        from .execution_design_e31_hand_contacts import install
        reader=install(a,all_robot_links=True);a.act()
    def actual_table_forces():
        values={k:v for k,v in reader['current_forces_n'].items()if k.startswith('robot_table/right/')}
        if not values or any(v is None for v in values.values()):raise RuntimeError('Actual whole-arm native table force readback required')
        return values
    floor=float(table_bounds_task(a.scene)['top']);meshes,omitted=capture_native_meshes(a,side);table=LiveTableGuard(a,side,meshes,floor)
    def force(part):return float(a.c.contact_forces.get(frozenset((name,side+'_finger'+str(part))),0.))
    def guard():
        state,contacts=a.c.snapshot()
        if not state[name]['grasp'][1]or min(force(i)for i in(1,2))<=.001:
            raise RuntimeError('Original real bilateral plate grip lost during direct path')
        if float(state[name]['mat'][2,2])>-.75:raise RuntimeError('Actual down plate face drifted during normal-axis spin')
        if any(frozenset((bowl,side+'_finger'+str(i)))in contacts for i in(1,2)):
            raise RuntimeError('Original hand contacted receiving bowl')
        check_actual_limits(a,side);table.check()
    def frame(ref):
        b=a.c.snapshot()[0][ref['actor']];return np.asarray(b['pos']),np.asarray(b['mat'])
    view=SimpleNamespace(a=a,frame=frame);state,_=a.c.snapshot();body=state[name];support=state[bowl]
    measured=capture(a,a.c,side);p=np.array(measured['position']);r=np.array(measured['rotation_task'])
    normal=np.asarray(body['mat'])[:,2];angle=float(parameters.get('normal_spin_degrees',-45.))
    if angle!=-45.:raise ValueError('Only the independently whole-arm-screened primary spin is admitted')
    turn=Rotation.from_rotvec(math.radians(angle)*normal).as_matrix();target=turn@r
    actual_parts=collision_parts_task(view,name);bowl_parts=collision_parts_task(view,bowl)
    allplate=np.concatenate(actual_parts);predicted=(allplate-p)@turn.T+p
    gap=float(predicted[:,2].min()-max(part[:,2].max()for part in bowl_parts))
    offset=np.asarray(parameters.get('placement_offset_xy',[-.018,0.]),float)
    if offset.shape!=(2,)or not np.isfinite(offset).all()or np.max(abs(offset))>.025:
        raise ValueError('Finite bounded actual-cover offset required')
    off=turn@(np.asarray(body['pos'])-p);desired_xy=np.asarray(support['pos'])[:2]+offset
    over=np.r_[desired_xy-off[:2],p[2]];low=over.copy();low[2]-=gap-.001
    poses=[dict(position=p.tolist(),rotation=target.tolist()),dict(position=over.tolist(),rotation=target.tolist()),dict(position=low.tolist(),rotation=target.tolist())]
    trial=screen(measured,poses);report=dict(source_initial_positive=False,proposal_only=True,omitted_noncolliding_native_bodies=omitted,
        actual_initial_arm_min_z=table.initial,measured=measured,normal=normal.tolist(),poses=poses,screen=trial)
    def write():
        (a.out/'e31-original-right-direct-path.private.json').write_text(json.dumps(report,indent=2,default=lambda x:x.tolist())+'\n')
    write()
    if not trial['passed']:raise RuntimeError('Actual right normal-spin/lower joint continuation rejected')
    obstacles={bowl:bowl_parts}
    left_meshes,left_omitted=capture_native_meshes(a,'left')
    for key,points in left_meshes.items():obstacles['left_'+key]=[points]
    table_min=[]
    for row in trial['samples']:
        posed=transformed_meshes(measured,meshes,row['candidate_joints_rad']);minimum=min(float(points[:,2].min())for points in posed.values());table_min.append(minimum)
        if minimum<table.initial_min-.0003:raise RuntimeError('Actual whole-arm/table sweep rejected before physical rotation')
        clear,reason=preview_clearance(list(posed.values()),[0,0,0],obstacles)
        if not clear:raise RuntimeError('Actual original right arm recipient/peer sweep rejected: '+str(reason))
    report.update(sampled_whole_arm_table_min_z=table_min,whole_arm_and_recipient_peer_sweep_passed=True,left_omitted_noncolliding_bodies=left_omitted,
        before_actual_spin_whole_right_table_forces_n=actual_table_forces());write()
    footprint=predicted[:,:2]+(over-p)[:2];hull=ConvexHull(footprint)
    bowl_cloud=np.concatenate(bowl_parts);rim=bowl_cloud[bowl_cloud[:,2]>bowl_cloud[:,2].max()-.003,:2]
    rim_margin=-float(np.max(rim@hull.equations[:,:2].T+hull.equations[:,2]))
    report['actual_rim_projection_cover_margin_m']=rim_margin;report['placement_offset_xy']=offset.tolist();write()
    if rim_margin<0:raise RuntimeError('Actual native bowl rim exceeds projected carried plate footprint')
    a.stage='e31-original-right-plate-normal-spin';guard()
    report['private_orientation_started']=dict(steps=a.c.steps,physics_ticks=a.c.physics_ticks,
        real_PD_cartesian_orientation=True,native_state_assignment=False,delta_task=turn.tolist());write()
    # The preceding completed public hold must not classify this separate
    # private rotation as a new nonrotation command. Match author_joint_path's
    # bookkeeping boundary; targets and physical native states are preserved.
    a.c._public_action=None;a.c._public_blocked={};a.c._public_hold_q={};a.c._public_limit_seen={}
    with diagnostic_tick_scope(a):
        a.rotate_tcp_smooth(side,turn,guard=guard)
    guard();table_forces=actual_table_forces();report['after_actual_spin']=dict(arm_table_min_z=table.values(),plate=a.c.snapshot()[0][name],whole_right_table_forces_n=table_forces);write()
    if not table.cleared or max(table_forces.values())>.001:
        raise RuntimeError('Normal-axis spin did not actually clear whole right arm/table contact')
    cp=checkpoint(a.c,'e31-original-right-normal-spin-complete');(a.out/'e31-original-right-after-spin.checkpoint.private.json').write_text(json.dumps(cp,indent=2)+'\n')
    original=a.act
    def guarded(*args,**kwargs):guard();result=original(*args,**kwargs);guard();return result
    a.act=guarded
    try:
        a.stage='e31-original-right-actual-xy-over-bowl'
        labels=(('FWD','BACK'),('LEFT','RIGHT'))
        for _ in range(40):
            current=a.c.snapshot()[0][name];xy=desired_xy-np.asarray(current['pos'])[:2]
            if np.max(abs(xy))<.006:break
            i=int(np.argmax(abs(xy)));token=labels[i][0 if np.sign(xy[i])==a.generated_axis_signs[side][i]else 1]
            a.act('STILL',token,float(min(8.,abs(xy[i])*1000)))
        else:raise RuntimeError('Original actual plate coarse XY cover waypoint stalled')
        goal=dict(next(g for g in spec['goals']if g['object']==name),pitch=math.pi,roll=0.)
        a.stage='e31-original-right-true-contact-lower'
        stop=lower_for_release(a,name,side,goal,maximum_drop_gap_m=.030,require_bowl_contact=True,centering_offset_xy=offset)
    finally:a.act=original
    cp=checkpoint(a.c,'e31-original-right-real-bowl-contact-before-release');(a.out/'e31-original-right-before-release.checkpoint.private.json').write_text(json.dumps(cp,indent=2)+'\n')
    a.carried_payload=None;a.stage='e31-original-right-supported-release';a.release_generated(side)
    for _ in range(5):a.act('STILL','UP',8.)
    for _ in range(3):a.act()
    report.update(proposal_only=False,actual_path_completed=True,actual_release_stop=stop,final_plate=a.c.snapshot()[0][name],final_arm_table_min_z=table.values());write();return report
