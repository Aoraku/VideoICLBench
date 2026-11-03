"""Private E31 motor-gap release, with a simultaneous public outward move.

Only real gripper motor targets change. Joint/object states and contacts are
never assigned; actual pad separation and a physically empty hand are required.
"""
import json
from pathlib import Path
import numpy as np


def outward_route(tip,plate_position,signs):
    delta=np.asarray(tip,float)[:2]-np.asarray(plate_position,float)[:2]
    if not np.isfinite(delta).all()or np.linalg.norm(delta)<.03:
        raise ValueError('Measured outward rim direction unavailable')
    axis=int(np.argmax(abs(delta)));sign=1 if delta[axis]>0 else-1
    labels=(('FWD','BACK'),('LEFT','RIGHT'))
    return axis,sign,labels[axis][0 if sign==signs[axis]else 1]


def release_inverted(a,name,side,*,already_released=False,preferred_axis=None):
    spec=a.scene.spec;semantic=spec['semantic'];ix=('left','right').index(side)
    if not(getattr(a,'_execution_design_reference_authorized',False)and spec['id']=='E31'
           and name==semantic['plate']):raise ValueError('Private actual E31 plate release required')
    from .execution_design_e33_grasp import actual_mesh
    from .execution_design_thin_edge import material_collision_points_task
    fingers=[side+'_finger1',side+'_finger2'];trace=[]
    def force(f):return float(a.c.contact_forces.get(frozenset((name,f)),0.))
    def snapshot():return a.c.snapshot()[0][name]
    body=snapshot()
    if not already_released and float(np.asarray(body['mat'])[2,2])>=-.85:
        raise RuntimeError('E31 narrow release requires genuinely held down-facing plate')
    if not already_released and(not body['grasp'][ix]or not all(force(f)>.001 for f in fingers)):
        raise RuntimeError('E31 narrow release requires actual bilateral grip')
    robot=a.scene.robots[side];ids=a.c.ids[side][1]
    initial=float(robot.data.joint_pos[0,ids].detach().cpu().numpy().max())
    # Retreat from the actually held rim, not a hardcoded robot local axis.
    axis,sign,token=outward_route(a.tip(side),body['pos'],a.generated_axis_signs[side])
    if preferred_axis is not None:
        if preferred_axis not in(0,1):raise ValueError('Horizontal measured outward escape axis required')
        delta=np.asarray(a.tip(side),float)-np.asarray(body['pos'],float)
        if abs(delta[preferred_axis])<.015:raise ValueError('Preferred escape must point away from measured plate centre')
        axis=int(preferred_axis);sign=1 if delta[axis]>0 else-1
        token=(('FWD','BACK'),('LEFT','RIGHT'))[axis][0 if sign==a.generated_axis_signs[side][axis]else 1]
    a.stage='checkpoint-e31-narrow-release-outward'
    released=already_released
    extras=(tuple(i*.001 for i in range(1,9))if preferred_axis is not None else(.001,.002,.003))
    for extra in(()if already_released else extras):
        opening=initial+extra
        if opening>.018:break
        a.c.grips[side]=opening
        a.act(token if side=='left'else'STILL',token if side=='right'else'STILL',20.)
        body=snapshot();forces=[force(f)for f in fingers]
        trace.append(dict(step=a.c.steps,per_finger_motor_target_m=opening,
            actual_pad_forces_n=forces,actual_grasp=body['grasp'][ix],normal_z=float(np.asarray(body['mat'])[2,2])))
        if not body['grasp'][ix]and max(forces)<=.001:released=True;break
    if not released:raise RuntimeError('E31 narrow outward release retained actual pad force/grasp')
    a.carried_payload=None
    from .execution_design_e31_release import _View
    a.stage='checkpoint-e31-narrow-empty-retreat'
    clear=False
    for _ in range(12):
        plate=material_collision_points_task(_View(a),{'actor':name})
        hand=np.concatenate([actual_mesh(a,side,n)for n in('panda_hand',*a.scene.embodiment.fingers)])
        if ((sign>0 and hand[:,axis].min()>plate[:,axis].max()+.005)or
                (sign<0 and hand[:,axis].max()<plate[:,axis].min()-.005)):
            clear=True;break
        a.act(token if side=='left'else'STILL',token if side=='right'else'STILL',8.)
    if not clear:raise RuntimeError('E31 empty hand did not reach measured outside-plane clearance')
    if any(snapshot()['grasp'])or any(force(f)>.001 for f in fingers):
        raise RuntimeError('E31 withdrawal did not establish actual pad/grasp separation')
    a.stage='checkpoint-e31-fully-open-outside-plate'
    a.act('RELEASE'if side=='left'else'STILL','RELEASE'if side=='right'else'STILL')
    report=dict(real_motor_targets_and_public_actions_only=True,direct_joint_state_written=False,
        actual_pad_separation=True,actual_hand_outside_plate_projection=True,trace=trace)
    (Path(a.out)/'e31-narrow-release.private.json').write_text(json.dumps(report,indent=2)+'\n')
    return report
