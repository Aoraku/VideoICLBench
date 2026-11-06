"""Resume real upright triangle transport using its actual lowest mesh vertex.

The original region/support rule permits a released triangle to settle. The
old local-Z bottom marker was above a vertical triangle's true lowest corner.
"""
from copy import deepcopy
import math
import numpy as np
from .realworld_tool_expert import ToolExecutionError,_axis_rotation
from .execution_design import REVISION_V3,source_sha256
from .execution_design_expert import ExecutionDesignAuthor
from .execution_design_segments_e17_regrasp import TRIANGLE


def lowest_reference(policy,name):
    pos,rotation=policy.frame({'actor':name});points=TRIANGLE@rotation.T+pos
    return {'actor':name,'local':TRIANGLE[int(np.argmin(points[:,2]))].tolist()}


def _escape_existing_plate(policy,name,guard):
    """Only lift away from an existing sub-2mm plate clearance failure."""
    from .execution_design_segments_e17_upper import _check,_native_parts
    from .execution_design_e24_transit import capture_model
    from .execution_design_e17_palm_escape import signed_sat_margin
    for _ in range(12):
        try:_check(policy,policy.tip('right')+[0,0,.004],payload=name);return
        except ToolExecutionError as exc:
            if 'held:'+name+'/0 / stand/1'not in str(exc):raise
        model,_=capture_model(policy,'right');parts=_native_parts(policy);plate=next(r for r in parts if r['name']=='stand/1')['points']
        clouds=list(model['clouds'])+[dict(name='held:'+r['name'],points=r['points'])for r in parts if r['actor']==name]
        before={c['name']:signed_sat_margin(c['points'],plate)for c in clouds}
        if min(before.values())<-.005:raise ToolExecutionError('Existing upper plate envelope overlap exceeds5mm escape scope')
        for c in clouds:
            prior=before[c['name']]
            for dz in(.0005,.001,.0015,.002):
                value=signed_sat_margin(c['points']+[0,0,dz],plate)
                if value<min(.002,prior)-2e-6:raise ToolExecutionError('Upward plate escape would deepen or create overlap')
                prior=value
        _check(policy,policy.tip('right')+[0,0,.002],payload=name,ignored_components=('stand/1',))
        policy.act('right','UP',mm=2.);guard();actual_parts=_native_parts(policy);actual,_=capture_model(policy,'right')
        actual_clouds=list(actual['clouds'])+[dict(name='held:'+r['name'],points=r['points'])for r in actual_parts if r['actor']==name]
        actual_plate=next(r for r in actual_parts if r['name']=='stand/1')['points']
        for c in actual_clouds:
            value=signed_sat_margin(c['points'],actual_plate)
            if value<min(.002,before[c['name']])-2e-6:raise ToolExecutionError('Actual upward plate escape deepened or added overlap')
        policy.operations.append(dict(operation='actual_nondeepening_plate_escape',before_minimum_signed_hull_margin_m=min(before.values()),requested_up_m=.002))
    _check(policy,payload=name)


def place_current(policy,name,xy,guard,*,west_entry=False):
    from .execution_design_segments_e17_remaining import _move
    from .execution_design_segments_e17_upper import _check
    from .execution_design_e17_reference import collision_shelf_target
    base,rotation=policy.frame({'actor':'stand'});ref=policy.ref(name)
    if west_entry:
        # Reverse the last northward approach before moving forward of the
        # idle elbow. No idle-arm state or collision exemption is installed.
        tip=policy.tip('right');_move(policy,None,[tip[0],.120,tip[2]],payload=name,carrying=True,short_cap_exit=True)
        tip=policy.tip('right');_move(policy,None,[base[0]-.230,.120,tip[2]],payload=name,carrying=True)
        tip=policy.tip('right');_move(policy,None,[tip[0],base[1]+xy[1],tip[2]],payload=name,carrying=True)
        for _ in range(5):
            desired=_axis_rotation([1,0,0],math.radians(-1.5))@policy.a.tcp_rotation_task('right')
            _check(policy,policy.tip('right'),payload=name,rotation=desired)
            policy.act('right','ROLL_RIGHT',degrees=1.5);guard();_check(policy,payload=name)
    else:_escape_existing_plate(policy,name,guard)
    material=lowest_reference(policy,name);lowest=policy.point(material);center=policy.frame({'actor':name})[0]
    surface=collision_shelf_target(policy,'stand','upper',[*xy,0.])[2]
    finger_low=min(float(f['aabb_min_task_m'][2])for f in policy.a.finger_geometry('right')['fingers'])
    release_height=float(base[2]+surface+max(.006,.003-(finger_low-lowest[2])))
    # Move the lowest actual vertex above the physical plate before entering.
    _move(policy,material,[*lowest[:2],max(release_height,float(lowest[2]))],payload=name,carrying=True)
    offset=rotation.T@(lowest-center);goal=base+rotation@np.r_[np.asarray(xy)+offset[:2],release_height-base[2]]
    if west_entry:
        entry=goal.copy();entry[0]=base[0]-.230
        _move(policy,material,entry,payload=name,carrying=True)
    else:
        point=policy.point(material);_move(policy,material,[goal[0],point[1],point[2]],payload=name,carrying=True)
    _move(policy,material,goal,payload=name,carrying=True)
    guard();policy.release(ref,'right')
    state,contacts=policy.snapshot()
    if any(state[name]['grasp'])or frozenset((name,'stand'))not in contacts:raise ToolExecutionError('Actual triangle release lacks real stand support')
    policy.operations.append(dict(operation='actual_lowest_vertex_upper_release',actor=name,release_gap_m=release_height-base[2]-surface))


def run_segment(author,segment,parameters):
    boundaries={'e17_b_release_actual_upper_green_492':('B',492,49202,'green_triangle',{'blue_square','green_square','blue_triangle'}),
                'e17_c_place_actual_held_blue_336':('C',336,33602,'blue_triangle',{'blue_square'})}
    if segment not in boundaries or not isinstance(parameters,dict)or parameters:raise ToolExecutionError('Explicit actual-held upper boundary required')
    variant,steps,tick,name,protected=boundaries[segment];spec=author.scene.spec;design=spec.get('execution_design',{});cp=getattr(author,'_engineering_resume_checkpoint',{});source=cp.get('source',{})
    if (spec.get('id')!='E17'or spec.get('variant')!=variant or spec.get('seed')!=4201 or design.get('condition')!='I'
            or design.get('revision')!=REVISION_V3 or design.get('source_sha256')!=source_sha256(REVISION_V3)
            or not author.control_report.get('engineering_reference_only')or not getattr(author,'_execution_design_reference_authorized',False)
            or author.smooth or cp.get('diagnostic_only')is not True or cp.get('state_quality')!='measured_native_state'
            or source.get('steps')!=steps or source.get('physics_ticks')!=tick):raise ToolExecutionError('Exact native current-held E17 checkpoint required')
    p=ExecutionDesignAuthor(author)
    from .execution_design_e17_stand import descriptor,native_readback
    actual=native_readback(author.scene)
    if not actual or actual.get('derived_geometry_sha256')!=descriptor()['derived_geometry_sha256']or actual.get('kinematic_enabled')is not False or actual.get('gravity_disabled')is not False:raise ToolExecutionError('Actual dynamic reviewed stand required')
    from .execution_design_segments_e17_e20 import _held_with_contacts
    _held_with_contacts(p,name,'right');base,rotation=p.frame({'actor':'stand'});base=base.copy();rotation=rotation.copy()
    regions={member:r for r in design['local_regions']for member in r['members']}
    def guard():
        state,contacts=p.snapshot();pos,rot=p.frame({'actor':'stand'})
        # Native region+support protects the work, without a1mm micro-motion rule.
        if np.linalg.norm(pos-base)>.005 or np.linalg.norm(rot-rotation)>.12:raise ToolExecutionError('Stand moved materially during held upper suffix')
        for piece in protected:
            row=state[piece];obj=p.objects[piece];r=regions[piece];local=rot.T@(row['pos']+row['mat']@np.asarray(obj.get('local_bounds_center',[0,0,0]))-pos);radius=np.abs(rot.T@row['mat'])@np.asarray(obj['size']);tol=float(design.get('geometry_tolerance_m',.003))
            if any(row['grasp'])or frozenset((piece,'stand'))not in contacts or np.any(local-radius<np.asarray(r['lower'])-tol)or np.any(local+radius>np.asarray(r['upper'])+tol):raise ToolExecutionError('Completed piece lost native region/support: '+piece)
    guard();before=p.c.steps;old=author.act;had='act'in author.__dict__;previous=author.__dict__.get('act')
    def guarded(*args,**kwargs):
        if p.c.steps-before>=500:raise ToolExecutionError('Actual upper suffix exhausted500 public actions')
        guard();value=old(*args,**kwargs);guard();return value
    author.act=guarded
    try:
        place_current(p,name,[.030,-.044]if variant=='B'else[-.030,.044],lambda:(_held_with_contacts(p,name,'right'),guard()),west_entry=variant=='C')
        protected.add(name);guard()
    finally:
        if had:author.act=previous
        else:del author.act
    return dict(local_completed=True,operations=deepcopy(p.operations),active_actions=p.c.steps-before)
