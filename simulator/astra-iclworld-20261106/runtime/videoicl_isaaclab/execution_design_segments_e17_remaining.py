"""C's remaining original public workflow after the successful upper blue.

The successful1-action source has no final native core checkpoint. Its sealed
same-tick terminal measurements are hydrated honestly as a measured-pose debug
fixture. No completed placement, lid opening or score/history is replayed.
"""
from copy import deepcopy
import math
import numpy as np
from .execution_design import REVISION_V3,source_sha256
from .execution_design_expert import ExecutionDesignAuthor
from .execution_design_segments_e17 import STAND_ROTATION_MATRIX_LIMIT,relevel_empty,_empty
from .realworld_tool_expert import ToolExecutionError,_axis_rotation

SLOTS={'blue_triangle':[-.044,.044],'green_square':[.044,.044],'green_triangle':[.044,-.044]}


def _move(policy,material,target,*,payload,carrying,short_cap_exit=False,tolerance=.006):
    from .execution_design_segments_e17_upper import _check
    target=np.asarray(target,float)
    for _ in range(400):
        point=policy.point(material)if material is not None else policy.tip('right');error=target-point
        if np.max(abs(error))<=tolerance:return
        axis=int(np.argmax(abs(error)));distance=min(.004 if short_cap_exit else .010,abs(float(error[axis])))
        delta=np.zeros(3);delta[axis]=np.sign(error[axis])*distance
        kw=dict(payload=payload,carrying=carrying)
        if short_cap_exit:kw['maximum_swept_bound_m']=.0005
        # A10mm Cartesian request can need more than the local joint probe's
        # allowed step near a singularity. Subdivide that same motion instead
        # of rejecting a physically reachable smaller public increment.
        for attempt in range(4):
            try:_check(policy,policy.tip('right')+delta,**kw);break
            except ToolExecutionError as exc:
                if str(exc)!='E17 upper next public increment has no nearby IK'or attempt==3:raise
                distance*=.5;delta[axis]=np.sign(error[axis])*distance
        old=policy.tip('right').copy();token=(('FWD','BACK'),('LEFT','RIGHT'),('UP','DOWN'))[axis][int(error[axis]<0)]
        policy.act('right',token,mm=distance*1000)
        if np.max(abs(policy.tip('right')-old))<.0001:raise ToolExecutionError('E17 remaining public increment did not advance')
        _check(policy,**kw)
    raise ToolExecutionError('E17 remaining public waypoint exhausted')


def _retreat(policy,name,sign):
    policy.stage('local-e17c-released-'+name+'-exterior-retreat')
    point=policy.tip('right');_move(policy,None,[point[0],.230*sign,point[2]],payload=name,carrying=False,short_cap_exit=True)
    point=policy.tip('right');_move(policy,None,[*point[:2],max(1.12,float(point[2]))],payload=name,carrying=False)


def _place_upper(policy,name,xy,*,relevel=True):
    """Original pickup; the same measured exterior upper ingress as passed C."""
    from .execution_design_e17_reference import collision_shelf_target,measured_shelf_release
    from .execution_design_segments_e17_upper import _check
    # Finish levelling only at the empty exterior, before the original source
    # pickup. The tilt used for upper ingress is performed while truly held
    # and outside the cap, never at the former848 contact boundary.
    if relevel:relevel_empty(policy,'right',retreat_south=False)
    ref,side=policy.pickup(name,side_override='right')
    if side!='right':raise ToolExecutionError('E17 upper continuation requires actual right held piece')
    bottom={'actor':name,'local':policy.bottom_local(name)};base,rotation=policy.frame({'actor':'stand'})
    sign=1 if xy[1]>0 else-1;current=policy.point(bottom);height=max(1.12,float(current[2]))
    policy.stage('local-e17c-remaining-'+name+'-exterior-carry')
    _move(policy,bottom,[*current[:2],height],payload=name,carrying=True)
    _move(policy,bottom,[current[0],float(base[1]+.230*sign),height],payload=name,carrying=True)
    entry_x=float((base+rotation@np.r_[xy,0.])[0])
    _move(policy,bottom,[entry_x,float(base[1]+.230*sign),height],payload=name,carrying=True)
    policy.stage('local-e17c-remaining-'+name+'-exterior-tilt')
    for _ in range(5):
        policy.require_held(ref,'right');desired=_axis_rotation([1,0,0],math.radians(-1.5*sign))@policy.a.tcp_rotation_task('right')
        _check(policy,policy.tip('right'),payload=name,rotation=desired)
        policy.act('right','ROLL_RIGHT'if sign>0 else'ROLL_LEFT',degrees=1.5);policy.require_held(ref,'right')
        _check(policy,payload=name)
    local=collision_shelf_target(policy,'stand','upper',[*xy,0.]);local=measured_shelf_release(policy,name,'right','stand','upper',local)
    goal=base+rotation@np.asarray(local);entry=goal.copy();entry[1]=base[1]+.230*sign
    policy.stage('local-e17c-remaining-'+name+'-upper-insert')
    _move(policy,bottom,entry,payload=name,carrying=True);_move(policy,bottom,goal,payload=name,carrying=True)
    policy.release(ref,'right');state,contacts=policy.snapshot()
    if any(state[name]['grasp'])or frozenset((name,'stand'))not in contacts:raise ToolExecutionError('E17 remaining upper release lacks actual stand support')
    _retreat(policy,name,sign)


def run_segment(author,segment,parameters):
    boundaries={'e17_c_resume_remaining_after_blue_release_1':(1,102,'measured_pose_fixture'),
                'e17_c_resume_remaining_after_relevel_93':(93,9302,'measured_native_state'),
                'e17_c_resume_remaining_above_rail_121':(121,12102,'measured_native_state')}
    if segment not in boundaries or not isinstance(parameters,dict)or parameters:
        raise ToolExecutionError('Explicit C post-success1 remaining workflow entry required')
    steps,tick,quality=boundaries[segment]
    spec=author.scene.spec;d=spec.get('execution_design',{});cp=getattr(author,'_engineering_resume_checkpoint',{});source=cp.get('source',{});context=cp.get('context',{})
    if (spec.get('id')!='E17'or spec.get('variant')!='C'or spec.get('seed')!=4201
            or d.get('revision')!=REVISION_V3 or d.get('condition')!='I'or d.get('source_sha256')!=source_sha256(REVISION_V3)
            or not author.control_report.get('engineering_reference_only')or not getattr(author,'_execution_design_reference_authorized',False)
            or author.smooth or cp.get('diagnostic_only')is not True or cp.get('state_quality')!=quality
            or source.get('steps')!=steps or source.get('physics_ticks')!=tick
            or steps==1 and context.get('scene_input_provenance',{}).get('terminal_measurement_hydrated')is not True):
        raise ToolExecutionError('Successful C1/102 sealed terminal measurement required; not old222/490')
    p=ExecutionDesignAuthor(author)
    from .execution_design_e17_stand import descriptor,native_readback
    actual=native_readback(author.scene)
    if not actual or actual.get('measured')is not True or actual.get('derived_geometry_sha256')!=descriptor()['derived_geometry_sha256']:
        raise ToolExecutionError('Original actual dynamic stand required')
    upper=next(r for r in d['local_regions']if r['id']=='upper')
    if upper['members']!=['blue_square','blue_triangle','green_square','green_triangle']or any(r['members']for r in d['local_regions']if r['id']!='upper'):
        raise ToolExecutionError('Original C four upper-layer assignment required')
    _empty(p);base,rotation=p.frame({'actor':'stand'});base=base.copy();rotation=rotation.copy();protected={'blue_square'};delivering=False
    def supported(name):
        state,contacts=p.snapshot();pos,rot=p.frame({'actor':'stand'});row=state[name];local=(row['pos']-pos)@rot
        if any(row['grasp'])or frozenset((name,'stand'))not in contacts or np.any(local<upper['lower'])or np.any(local>upper['upper']):
            raise ToolExecutionError('Previously completed upper piece lost real layer/support: '+name)
    def guard():
        pos,rot=p.frame({'actor':'stand'})
        if not delivering and(np.linalg.norm(pos-base)>.001 or np.linalg.norm(rot-rotation)>STAND_ROTATION_MATRIX_LIMIT):
            raise ToolExecutionError('Actual stand moved before original delivery')
        for name in protected:supported(name)
    guard();state,contacts=p.snapshot()
    if frozenset(('stand','table'))not in contacts or frozenset(('packing_lid','table'))not in contacts:
        raise ToolExecutionError('C success boundary requires real stand/table and removed lid/table support')
    before=p.c.steps;old=author.act;had='act'in author.__dict__;previous=author.__dict__.get('act')
    def guarded(*args,**kwargs):
        if p.c.steps-before>=2500:raise ToolExecutionError('E17 remaining workflow exhausted2500 public actions')
        guard();result=old(*args,**kwargs);guard();return result
    author.act=guarded
    try:
        if steps==1:_retreat(p,'blue_square',-1)
        if steps in(93,121):
            original_acquire=p.acquire_chip_with_wrist_margin
            def acquire(ref,side):
                if ref['actor']=='blue_triangle'or steps==121 and ref['actor']=='green_triangle':
                    if steps==93:
                        from .execution_design_e17_tilted_grasp import acquire as triangle_acquire
                    else:
                        from .execution_design_e17_rail_top_grasp import acquire as triangle_acquire
                    return triangle_acquire(p,ref,side)
                return original_acquire(ref,side)
            p.acquire_chip_with_wrist_margin=acquire
        for name,xy in SLOTS.items():
            if steps==121 and name=='blue_triangle':_place_upper(p,name,xy,relevel=False)
            else:_place_upper(p,name,xy)
            protected.add(name);guard()
        p.package_stage();guard();delivering=True;p.deliver();guard()
    finally:
        if had:author.act=previous
        else:del author.act
    return dict(local_completed=True,operations=deepcopy(p.operations),active_actions=p.c.steps-before)
