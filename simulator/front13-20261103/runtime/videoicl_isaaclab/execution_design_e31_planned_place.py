"""Private E31 verified held-plate path; actual recipient contact stops motors."""
import json
from types import SimpleNamespace
import numpy as np


def held_normal_spin_goal(plate_pos, plate_rotation, tcp_pos, tcp_rotation,
                          material_points, desired_xy, gap_target, bowl_top,
                          degrees=0.):
    """Turn about the measured plate normal, preserving the held transform."""
    from scipy.spatial.transform import Rotation
    angle=float(degrees)
    if not np.isfinite(angle) or abs(angle)>90.:
        raise ValueError('Bounded plate-normal orientation freedom required')
    center=np.asarray(plate_pos,float);rotation=np.asarray(plate_rotation,float)
    turn=Rotation.from_rotvec(np.deg2rad(angle)*rotation[:,2]).as_matrix()
    points=(np.asarray(material_points,float)-center)@turn.T+center
    gap=float(points[:,2].min()-float(bowl_top))
    desired=center.copy();desired[:2]=desired_xy
    if gap_target is not None:desired[2]-=gap-float(gap_target)
    target=desired+turn@(np.asarray(tcp_pos,float)-center)
    return target,turn@np.asarray(tcp_rotation,float),gap


def run(a, parameters=None):
    parameters=parameters or {};spec=a.scene.spec;side='right'
    diagnostic=bool(getattr(a.c,'_engineering_diagnostic_only',False))
    source_c=(spec.get('variant')=='C'and spec.get('execution_design',{}).get('revision')=='embodied50-execution-v3-20261102'
        and getattr(a,'_execution_design_reference_authorized',False))
    if not (spec['id']=='E31' and spec['seed']==4201
            and spec.get('execution_design',{}).get('condition')=='I'
            and(diagnostic or source_c)
            and a.control_report.get('engineering_reference_only') is True):
        raise ValueError('Explicit E31 I4201 checkpoint planning required')
    from .author_mplib_planner import plan,_quat
    from .engineering_native_tick import diagnostic_tick_scope
    from .engineering_checkpoint import capture as checkpoint
    from .execution_design_branch_geometry import collision_parts_task
    from .execution_design_e31_arm_clearance import capture_native_meshes,LiveTableGuard
    from .execution_design_thin_edge import table_bounds_task
    name=spec['semantic']['plate'];bowl=spec['semantic']['bowl']
    reader=getattr(a,'_e31_native_contact_reader',None)
    if reader is None:raise ValueError('Actual all-link native contact reader required')
    meshes,_=capture_native_meshes(a,side)
    table=LiveTableGuard(a,side,meshes,float(table_bounds_task(a.scene)['top']))
    def guard():
        state,contacts=a.c.snapshot()
        forces=[float(a.c.contact_forces.get(frozenset((name,side+'_finger'+str(i))),0.))for i in(1,2)]
        if not state[name]['grasp'][1] or min(forces)<=.001:
            raise RuntimeError('Real bilateral plate grip lost during verified path')
        for s in('left','right'):
            values={k:v for k,v in reader['current_forces_n'].items()if k.startswith('robot_table/'+s+'/')}
            if not values or any(v is None for v in values.values()):
                raise RuntimeError('Actual all-arm table contact readback incomplete')
            if max(values.values())>1.:
                raise RuntimeError('Actual robot link contacted native table')
        bowl_hits={k:v for k,v in reader['current_forces_n'].items()if k.startswith('bowl/')and v is not None and v>.1}
        if bowl_hits:raise RuntimeError('Robot physically contacted receiving bowl: '+str(bowl_hits))
        table.check()
    def frame(ref):
        value=a.c.snapshot()[0][ref['actor']]
        return np.asarray(value['pos']),np.asarray(value['mat'])
    view=SimpleNamespace(a=a,frame=frame)
    def recipient_contact():
        return frozenset((name,bowl))in a.c.snapshot()[1]
    def save(stem):
        payload=checkpoint(a.c,stem)
        (a.out/(stem+'.checkpoint.private.json')).write_text(json.dumps(payload,indent=2)+'\n')
    offset=np.asarray(parameters.get('placement_offset_xy',[-.018,0.]),float)
    if offset.shape!=(2,)or not np.isfinite(offset).all()or np.max(abs(offset))>.025:
        raise ValueError('Bounded physical-cover placement offset required')
    reports=[];a.carried_payload=(name,side)
    drop=float(parameters.get('ordinary_drop_gap_m',0.))
    if not np.isfinite(drop)or not 0<=drop<=.080:raise ValueError('Bounded ordinary gravity-drop height required')
    # The second target is only 1 mm beyond the material support envelope.
    # Its held-object/bowl exemption never exempts any robot/environment pair.
    # The first measured real plate/bowl contact stops native motor following.
    phases=('support-contact',)if parameters.get('resume_over_bowl')is True else('over-bowl','support-contact')
    for phase in phases:
        guard();state,_=a.c.snapshot();body=state[name];support=state[bowl]
        points=np.concatenate(collision_parts_task(view,name));bowl_points=np.concatenate(collision_parts_task(view,bowl))
        desired=np.asarray(support['pos'])[:2]+offset
        spin=float(parameters.get('normal_spin_degrees',0.))if phase=='support-contact'else 0.
        target,target_rotation,gap=held_normal_spin_goal(
            body['pos'],body['mat'],a.tip(side),a.tcp_rotation_task(side),points,desired,
            (-.001 if drop==0. else drop)if phase=='support-contact'else None,
            bowl_points[:,2].max(),spin)
        goal=dict(position=target.tolist(),quaternion=_quat(target_rotation).tolist())
        if phase=='support-contact':goal['allowed_contact_pairs']=[[name,bowl]]
        a.stage='e31-verified-held-plate-'+phase
        proposed=plan(a.scene,a.c,side,goal)
        (a.out/('e31-'+phase+'-plan.private.json')).write_text(json.dumps(proposed,indent=2,default=lambda v:v.tolist())+'\n')
        if proposed.get('status')!='Success' or proposed.get('verified')is not True:
            raise RuntimeError('E31 full-world held-plate path unavailable: '+str(proposed.get('status')))
        previous=getattr(a,'_engineering_e31_verified_path',False);a._engineering_e31_verified_path=True
        try:
            with diagnostic_tick_scope(a,reference_authorization=not diagnostic):
                receipt=a.execute_joint_path(side,proposed,guard=guard,done=recipient_contact if phase=='support-contact'else None)
        finally:a._engineering_e31_verified_path=previous
        guard();save('e31-'+phase+'-complete')
        if parameters.get('allow_approximate_demo')is not True and float(a.c.snapshot()[0][name]['mat'][2,2])>-.85:
            raise RuntimeError('Actual down-facing plate orientation not retained at verified endpoint')
        reports.append(dict(phase=phase,actual_plate=a.c.snapshot()[0][name],receipt=receipt,
            material_gap_before_m=gap,normal_spin_degrees=spin))
    actual_contact=recipient_contact()
    if not actual_contact and drop==0.:raise RuntimeError('Verified endpoint did not establish real plate/bowl support contact')
    save('e31-supported-before-real-release'if actual_contact else'e31-ordinary-gravity-release-height')
    if parameters.get('place_only')is True:
        return dict(verified_native_motor_phases=reports,actual_recipient_contact=actual_contact,ordinary_drop_gap_m=drop,
            diagnostic_only=diagnostic,not_task_acceptance=True)
    from .execution_design_e31_narrow_release import release_inverted
    release_inverted(a,name,side)
    for _ in range(3):a.act()
    report=dict(diagnostic_only=True,source_initial_positive=False,verified_native_motor_phases=reports,
        final_plate=a.c.snapshot()[0][name],actual_recipient_contact=recipient_contact())
    (a.out/'e31-verified-placement-result.private.json').write_text(json.dumps(report,indent=2,default=lambda v:v.tolist())+'\n')
    return report
