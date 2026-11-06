"""Source E29 engineering: public lifted transport before a real key stroke."""
import json
from pathlib import Path
import numpy as np
from .execution_design import REVISION_V3,source_sha256


def bottom_face_center(vertices):
    """Measured flat source head support, not the off-centre semantic marker."""
    v=np.asarray(vertices,float)
    if v.ndim!=2 or v.shape[1]!=3 or len(v)<4 or not np.isfinite(v).all():
        raise ValueError('Actual mallet collision vertices required')
    low=float(v[:,2].min());face=v[v[:,2]<=low+.0002]
    if len(face)<4:raise ValueError('Reviewed flat mallet support face missing')
    extent=np.ptp(face,axis=0)
    if not (.02<extent[0]<.06 and .04<extent[1]<.09):
        raise ValueError('Unexpected source mallet bottom footprint')
    point=(face.min(0)+face.max(0))*.5;point[2]=low
    return point


def collision_centered_head(p,head):
    from .execution_design_thin_edge import material_collision_points_task
    from .execution_design_mallet_grasp import MALLET_SHA
    d=p.spec.get('execution_design',{})
    if (p.task!='E29' or d.get('revision')!=REVISION_V3
            or d.get('source_sha256')!=source_sha256(REVISION_V3)
            or not p.a.control_report.get('engineering_reference_only')):
        raise ValueError('Source-checked isolated E29 engineering required')
    obj=next(o for o in p.spec['objects']if o['id']==head['actor'])
    if obj.get('source_asset',{}).get('sha256')!=MALLET_SHA:
        raise ValueError('Unreviewed mallet source')
    pos,rotation=p.frame(head)
    vertices=(material_collision_points_task(p,head)-pos)@rotation
    point=bottom_face_center(vertices)
    row=dict(source='actual_collision_mesh_bottom_face',source_marker_local=list(head['local']),
             author_working_local=point.tolist(),source_rule_and_evaluator_unchanged=True)
    with (Path(p.a.out)/'mallet-head-geometry.private.jsonl').open('a')as f:f.write(json.dumps(row)+'\n')
    return dict(head,local=point.tolist())


def approach_key(p,head,grip,side,target):
    design=p.spec.get('execution_design',{})
    if (p.task!='E29'or design.get('revision')!=REVISION_V3
            or design.get('source_sha256')!=source_sha256(REVISION_V3)
            or not p.a.control_report.get('engineering_reference_only')):
        raise ValueError('Isolated source-checked E29 engineering required')
    target=np.asarray(target,float)
    if target.shape!=(3,)or not np.isfinite(target).all():raise ValueError('Finite actual key approach required')
    def held():p.require_held(grip,side)
    # Lift first: a diagonal low transfer from the source handle exhausted
    # native Panda joint3 before reaching key 1 in the archived physical run.
    # Every point is recomputed from the actually held mallet, without a fixed
    # TCP attachment or changed private key order.
    tip=p.tip(side);height=max(p.clearance,float(tip[2]),float(target[2])+.08)
    p.move(side,[*tip[:2],height],held)
    actual=p.point(head);p.move_point(side,head,[*target[:2],max(float(actual[2]),float(target[2])+.08)],held)
    p.move_point(side,head,target,held)
    row=dict(stage=p.a.stage,step=p.c.steps,target_working_point=target.tolist(),
             actual_working_point=p.point(head).tolist(),actual_tcp=p.tip(side).tolist(),
             real_bilateral_grip=p.held(grip,side),source_key_order_unchanged=True)
    p.operations.append(row)
    with (Path(p.a.out)/'mallet-public-route.private.jsonl').open('a')as f:f.write(json.dumps(row)+'\n')


def level_held_mallet(p,actor,grip,side):
    import math
    from .author_orientation import _axis_angle
    from .realworld_tool_expert import ToolExecutionError
    p.stage('engineering-level-real-mallet')
    tip=p.tip(side);p.move(side,[*tip[:2],max(p.clearance,float(tip[2]))],lambda:p.require_held(grip,side))
    for _ in range(60):
        p.require_held(grip,side);rotation=np.asarray(p.snapshot()[0][actor]['mat'],float)
        axis,angle=_axis_angle(rotation.T)
        if angle<math.radians(1.):return
        k=int(np.argmax(abs(axis)));token=(('ROLL_LEFT','ROLL_RIGHT'),('PITCH_UP','PITCH_DOWN'),('ROTATE_CCW','ROTATE_CW'))[k][int(axis[k]<0)]
        p.act(side,token,degrees=min(3.,max(.5,abs(math.degrees(angle*axis[k])))))
    raise ToolExecutionError('Actual held mallet failed public level orientation')


def actual_strike_events(p,since):
    """Read native per-tick contacts, including impacts ending within one action.

    Engineering author only. No score/goal query and no mutation of evidence.
    """
    e=p.c.evaluator
    if not hasattr(e,'strikes')or not hasattr(e,'pending_strikes'):
        raise RuntimeError('Actual per-physics-tick strike recorder required')
    return [dict(v)for v in list(e.strikes)+list(e.pending_strikes.values())if int(v['step'])>=since]


def strike_key(p,tool,grip,head,side,name,target,normal):
    from .realworld_tool_expert import ToolExecutionError
    normal=np.asarray(normal,float)
    if np.max(np.abs(normal-[0,0,1]))>.001:raise ValueError('Reviewed horizontal key plane required')
    expected=int(name.rsplit('_',1)[1]);start=int(p.c.evaluator.steps)+1
    previous=set(getattr(p,'_reviewed_mallet_impact_ids',()))
    existing={(int(v['key']),int(v['step']))for v in actual_strike_events(p,0)}
    if existing!=previous:raise ToolExecutionError('Unplanned native mallet contact during transport')
    def check():
        p.require_held(grip,side);events=actual_strike_events(p,start)
        if any(int(v['key'])!=expected for v in events):raise ToolExecutionError('Actual mallet struck unexpected native key')
        if len(events)>1:raise ToolExecutionError('Repeated native impacts during one intended strike')
        return events
    for _ in range(100):
        if check():break
        # Correct measured in-grip/servo XY drift before another descent.
        # Source head is 40.5mm along X, key pitch 42.5mm: blind DOWN
        # accumulated 6.6mm drift and hit key7 during intended key6 natively.
        if hasattr(p,'point'):
            tolerance=max(.00035,float(getattr(p,'min_mm',.1))*.00055)
            for _ in range(20):
                if check():break
                error=np.asarray(target,float)[:2]-p.point(head)[:2]
                if np.max(np.abs(error))<=tolerance:break
                axis=int(np.argmax(abs(error)))
                token=(('FWD','BACK'),('LEFT','RIGHT'))[axis][int(error[axis]<0)]
                p.act(side,token,mm=min(2.,abs(error[axis])*1000))
            else:raise ToolExecutionError('Actual mallet bottom failed key XY alignment')
            if check():break
        p.act(side,'DOWN',mm=.5)
    else:raise ToolExecutionError('Public mallet stroke missed actual key contact')
    # Measured contact terminates pressing; do not demand a penetrating 1mm
    # material waypoint and oscillate against the key collision surface.
    p.move_point(side,head,np.asarray(target)+normal*.035,lambda:check())
    p.wait(2);events=check()
    if len(events)!=1 or 'release_step'not in events[0]or p.contact(tool['actor'],name):
        raise ToolExecutionError('Native key impact did not fully separate')
    p._reviewed_mallet_impact_ids=previous|{(int(events[0]['key']),int(events[0]['step']))}
    p.operations.append(dict(stage=p.a.stage,native_strike=dict(events[0]),action_step=p.c.steps))
