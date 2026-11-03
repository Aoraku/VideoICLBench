"""C's two real supported blue pieces stay in place; finish the two greens."""
from copy import deepcopy
import numpy as np
from .execution_design import REVISION_V3,source_sha256
from .execution_design_expert import ExecutionDesignAuthor
from .execution_design_e17_geometry import contained
from .realworld_tool_expert import ToolExecutionError


def place_right_column(p,name,xy,*,edge_grip=False,already_held=False):
    from .execution_design_e17_rail_top_grasp import acquire,material_vertices
    from .execution_design_segments_e17_remaining import _move,_retreat
    from .execution_design_e17_reference import collision_shelf_target
    original=p.acquire_chip_with_wrist_margin
    def source_acquire(ref,side):
        if edge_grip:
            _,rotation=p.frame(ref)
            if name.endswith('square')or abs(float(rotation[2,1]))<=.1:
                from .execution_design_e17_edge_grasp import acquire as edge_acquire
                return edge_acquire(p,ref,side)
            if name=='green_triangle':
                from .execution_design_e17_nudge_grasp import acquire as nudge_acquire
                return nudge_acquire(p,ref,side,edge_grip=True)
        return acquire(p,ref,side)
    if already_held:
        from .execution_design_segments_e17_e20 import _held_with_contacts
        ref,side=p.ref(name),'right';_held_with_contacts(p,name,side)
    else:
        p.acquire_chip_with_wrist_margin=source_acquire
        try:ref,side=p.pickup(name,side_override='right')
        finally:p.acquire_chip_with_wrist_margin=original
    if edge_grip:
        return place_edge_held(p,name,ref,side,xy)
    pos,rotation=p.frame({'actor':name});vertices,_=material_vertices(p.objects[name]);material={'actor':name,'local':vertices[int(np.argmin((vertices@rotation.T)[:,2]))].tolist()}
    base,standrot=p.frame({'actor':'stand'});point=p.point(material);height=max(1.12,float(point[2]));world=base+standrot@np.r_[xy,0.]
    p.stage('local-e17c-two-blue-'+name+'-right-column-carry')
    _move(p,material,[*point[:2],height],payload=name,carrying=True)
    point=p.point(material);_move(p,material,[point[0],base[1]-.230,height],payload=name,carrying=True)
    _move(p,material,[world[0],base[1]-.230,height],payload=name,carrying=True)
    point=p.point(material);center=p.frame({'actor':name})[0];offset=point-center
    _move(p,material,[world[0]+offset[0],world[1]+offset[1],height],payload=name,carrying=True)
    point=p.point(material);finger_low=min(float(f['aabb_min_task_m'][2])for f in p.a.finger_geometry(side)['fingers']);surface=base[2]+collision_shelf_target(p,'stand','upper',[*xy,0.])[2]
    goal=world+offset;goal[2]=surface+max(.006,.003-(finger_low-point[2]))
    p.stage('local-e17c-two-blue-'+name+'-actual-lowest-release')
    _move(p,material,goal,payload=name,carrying=True);p.act(side,'RELEASE');state,contacts=p.snapshot();region=next(r for r in p.d['local_regions']if r['id']=='upper')
    if any(state[name]['grasp'])or frozenset((name,'stand'))not in contacts or not contained(p.objects[name],state[name],state['stand'],region,p.d.get('geometry_tolerance_m',.003)):
        raise ToolExecutionError('Remaining green lacks source region and actual stand support: '+name)
    _retreat(p,name,-1)


def place_edge_held(p,name,ref,side,xy):
    """Descend outside the cap, then enter horizontally with the palm east.

    The native100 green was already held well above the plate. Carrying it
    farther east at that height exhausted nearby IK; descending over the cap
    would also put the palm through it. Keep that real grip and descend south.
    """
    import math
    from .realworld_tool_expert import _axis_rotation
    from .execution_design_e17_rail_top_grasp import material_vertices
    from .execution_design_segments_e17_remaining import _move
    from .execution_design_segments_e17_upper import _check
    from .execution_design_e17_reference import collision_shelf_target
    from .execution_design_segments_e17_e20 import _held_with_contacts
    base,standrot=p.frame({'actor':'stand'});outside=float(base[1]-.230)
    p.stage('local-e17-held-edge-south-exterior-before-low-ingress')
    tip=p.tip(side);_move(p,None,[tip[0],outside,tip[2]],payload=name,carrying=True)
    # Jaw directions are lines. Choose the shortest public yaw to world Y.
    jaw=p.a.tcp_rotation_task(side)[:,1];yaw=(math.pi/2-math.atan2(jaw[1],jaw[0])+math.pi/2)%math.pi-math.pi/2
    for _ in range(18):
        if abs(yaw)<=math.radians(5):break
        angle=math.copysign(min(abs(yaw),math.radians(5)),yaw)
        _check(p,p.tip(side),payload=name,rotation=_axis_rotation([0,0,1],angle)@p.a.tcp_rotation_task(side))
        p.act(side,'ROTATE_CCW'if angle>0 else'ROTATE_CW',degrees=abs(math.degrees(angle)))
        _held_with_contacts(p,name,side);yaw-=angle
    # The eastward palm lean occurs only in this empty southern airspace.
    for _ in range(6):
        _check(p,p.tip(side),payload=name,rotation=_axis_rotation([0,1,0],math.radians(3))@p.a.tcp_rotation_task(side))
        p.act(side,'PITCH_UP',degrees=3.);_held_with_contacts(p,name,side)
    pos,rotation=p.frame({'actor':name});vertices,_=material_vertices(p.objects[name]);local=vertices[int(np.argmin((vertices@rotation.T)[:,2]))]
    material={'actor':name,'local':local.tolist()};point=p.point(material);offset=point-pos
    surface=float((base+standrot@np.array([*xy,collision_shelf_target(p,'stand','upper',[*xy,0.])[2]]))[2])
    finger_low=min(float(f['aabb_min_task_m'][2])for f in p.a.finger_geometry(side)['fingers'])
    release_z=surface+max(.006,.003-(finger_low-point[2]))
    world=base+standrot@np.r_[xy,0.];goal=world+offset;goal[2]=release_z
    p.stage('local-e17-held-edge-descend-outside-cap')
    _move(p,material,[point[0],outside,release_z],payload=name,carrying=True)
    _move(p,material,[goal[0],outside,release_z],payload=name,carrying=True)
    p.stage('local-e17-held-edge-horizontal-upper-ingress')
    _move(p,material,goal,payload=name,carrying=True)
    p.act(side,'RELEASE');state,contacts=p.snapshot();region=next(r for r in p.d['local_regions']if r['id']=='upper')
    if any(state[name]['grasp'])or frozenset((name,'stand'))not in contacts or not contained(p.objects[name],state[name],state['stand'],region,p.d.get('geometry_tolerance_m',.003)):
        raise ToolExecutionError('Released edge-held chip lacks original upper region/support: '+name)
    # Leave perpendicular to the open jaws, then rise. Sliding along the jaw
    # line pushed the previously released blue in the immutable C12 failure.
    p.stage('local-e17-released-edge-east-empty-exit')
    tip=p.tip(side);_move(p,None,tip+[.015,0,0],payload=name,carrying=False,short_cap_exit=True)
    tip=p.tip(side);_move(p,None,[*tip[:2],max(1.12,float(tip[2]))],payload=name,carrying=False)
    tip=p.tip(side);_move(p,None,[tip[0],outside,tip[2]],payload=name,carrying=False)


def run_segment(author,segment,parameters):
    spec=author.scene.spec;d=spec.get('execution_design',{});cp=getattr(author,'_engineering_resume_checkpoint',{});s=cp.get('source',{})
    boundaries={'e17_c_resume_after_two_blues_1':(1,102),'e17_c_resume_before_sweep11':(11,1102),'e17_c_edge_grip_remaining90':(90,9002),'e17_c_low_ingress_from_held100':(100,10002),'e17_c_low_ingress_from_held2':(2,202)}
    if (segment not in boundaries or not isinstance(parameters,dict)or parameters or spec.get('id')!='E17'or spec.get('variant')!='C'or spec.get('seed')!=4201
            or d.get('condition')!='I'or d.get('revision')!=REVISION_V3 or d.get('source_sha256')!=source_sha256(REVISION_V3)
            or not author.control_report.get('engineering_reference_only')or not getattr(author,'_execution_design_reference_authorized',False)or author.smooth
            or cp.get('diagnostic_only')is not True or cp.get('state_quality')!='measured_native_state'or (s.get('steps'),s.get('physics_ticks'))!=boundaries[segment]):raise ToolExecutionError('Exact native two-blue completion boundary required')
    p=ExecutionDesignAuthor(author)
    from .execution_design_e17_stand import descriptor,native_readback
    actual=native_readback(author.scene)
    if not actual or actual.get('derived_geometry_sha256')!=descriptor()['derived_geometry_sha256']or actual.get('kinematic_enabled')is not False or actual.get('gravity_disabled')is not False:raise ToolExecutionError('Actual dynamic reviewed stand required')
    protected={'blue_square','blue_triangle'};region=next(r for r in d['local_regions']if r['id']=='upper');base,rotation=p.frame({'actor':'stand'});base=base.copy();rotation=rotation.copy();delivering=False
    def guard():
        state,contacts=p.snapshot();pos,rot=p.frame({'actor':'stand'})
        if not delivering and(np.linalg.norm(pos-base)>.005 or np.linalg.norm(rot-rotation)>.12):raise ToolExecutionError('Stand moved materially before intended delivery')
        for name in protected:
            if any(state[name]['grasp'])or frozenset((name,'stand'))not in contacts or not contained(p.objects[name],state[name],state['stand'],region,d.get('geometry_tolerance_m',.003)):
                raise ToolExecutionError('Completed C piece lost actual source region/support: '+name)
    guard();before=p.c.steps;old=author.act;had='act'in author.__dict__;previous=author.__dict__.get('act')
    def guarded(*args,**kwargs):
        if p.c.steps-before>=2500:raise ToolExecutionError('C remaining suffix exhausted2500 public actions')
        guard();value=old(*args,**kwargs);guard();return value
    author.act=guarded
    try:
        from .execution_design_e17_empty_exit import retreat_west
        if s['steps']==1:retreat_west(p,'blue_triangle')
        elif s['steps']==11:
            from .execution_design_segments_e17_remaining import _move
            tip=p.tip('right');p.stage('local-e17c11-empty-up-before-open-finger-sweep')
            _move(p,None,[*tip[:2],max(1.12,float(tip[2]))],payload='blue_triangle',carrying=False)
        for name,xy in [('green_square',[.044,.035]),('green_triangle',[.044,-.035])]:
            if s['steps']in(90,100,2):place_right_column(p,name,xy,edge_grip=True,already_held=s['steps']in(100,2) and name=='green_square')
            else:place_right_column(p,name,xy)
            protected.add(name);guard()
        if s['steps']in(90,100,2):
            from .execution_design_e17_recycle_delivery import recycle_all,deliver_stand
            recycle_all(p);guard();delivering=True;deliver_stand(p);guard()
        else:p.package_stage();guard();delivering=True;p.deliver();guard()
    finally:
        if had:author.act=previous
        else:del author.act
    return dict(local_completed=True,operations=deepcopy(p.operations),active_actions=p.c.steps-before)
