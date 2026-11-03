"""E39 read-only native IK screening; no action, state writes or acceptance."""
import json
import numpy as np


def route_positions(work_position, box_position, grasp_x, *,height=.88):
    """Candidate TCP points for the same physical tray, before any actuation.

    The work tray's lower face is local Z=-.018 and the reviewed tab is Z=.030.
    The optional near-side tab is hypothetical geometry until separately built
    and physically grasp-tested. This function never moves or adds a body.
    """
    work=np.asarray(work_position,float);box=np.asarray(box_position,float)
    if work.shape!=(3,) or box.shape!=(3,) or not np.isfinite([work,box]).all():
        raise ValueError('Invalid actual E39 body positions')
    start=work+np.array([grasp_x,0,.030]);end=box+np.array([grasp_x,0,-.030+.048+.001])
    rows=[('grasp',start),('empty-above-grasp',np.array([start[0],start[1],1.15])),
          ('loaded-lift',np.array([start[0],start[1],height+.048])),
          ('loaded-y-detour',np.array([start[0],box[1]+.010,height+.048]))]
    for i,x in enumerate(np.linspace(start[0],end[0],7)[1:]):
        rows.append(('loaded-x-%02d'%i,np.array([x,box[1]+.010,height+.048])))
    rows += [('above-box',np.array([end[0],box[1],height+.048])),('box-seat',end),
             ('high-path-mid',np.array([.10+grasp_x,box[1],1.27+.048])),
             ('high-path-end',np.array([end[0],box[1],1.27+.048]))]
    return rows


def inspect_key_routes(author):
    """Screen actual native kinematics for far/near grasp choices only."""
    from .execution_design_drawer_ik_probe import inspect,physical_grasp_targets
    state,_=author.c.snapshot();work=state['work_tray']['pos'];box=state['protective_box']['pos']
    side='left';rotations=physical_grasp_targets(author,author.c,side,[0,0,1],[1,0,0])
    targets=[];labels=[]
    for gx,choice in ((.055,'existing-far-tab'),(-.055,'hypothetical-near-tab')):
        for ri,rot in enumerate(rotations):
            for label,p in route_positions(work,box,gx):
                targets.append(dict(position=p.tolist(),rotation=rot.tolist()))
                labels.append(dict(grasp_choice=choice,grasp_x=gx,finger_assignment=ri,waypoint=label))
    # Each distinct pose uses the same deterministic start set. The general
    # helper advances its RNG across a target list, which can reject a repeated
    # pose solely because it receives different random initial guesses.
    cache={};results=[]
    for target in targets:
        key=tuple(np.round(np.r_[target['position'],np.asarray(target['rotation']).ravel()],10))
        if key not in cache:cache[key]=inspect(author,author.c,side,[target])[0]
        results.append(cache[key])
    rows=[dict(**label,**result)for label,result in zip(labels,results)]
    report=dict(schema='e39-native-route-ik-screen-v1',actions=author.c.steps,
        actuation_performed=False,collision_verified=False,native_task_acceptance=False,
        source='actual native Jacobian, measured joint limits and six deterministic bounded IK starts',
        work_position=np.asarray(work).tolist(),box_position=np.asarray(box).tolist(),rows=rows)
    (author.out/'e39-native-route-ik-screen.private.json').write_text(json.dumps(report,indent=2))
    return report


def require_near_low_route(author):
    if author.scene.spec['execution_design']['grasps']['work_tray'].get('hand')!='left':
        raise ValueError('E39 tray preflight requires the same explicit left hand as execution')
    report=inspect_key_routes(author)
    selected=[r for r in report['rows']if r['grasp_x']==-.055 and not r['waypoint'].startswith('high-')]
    if not selected or any(not r['kinematically_reachable'] or r['minimum_joint_margin_rad']<.02 for r in selected):
        from .realworld_tool_expert import ToolExecutionError
        raise ToolExecutionError('E39 near-tab full low route lacks native IK margin; no action started')
    return report
