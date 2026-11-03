"""Low public transport for E17B: recycle packaging, then deliver the loaded stand.

The old carrier raised the packing-box bottom to1.15m, making the far-Y target
unreachable. Only public actions are used; native regions/contacts decide release.
"""
from copy import deepcopy
import numpy as np
from .execution_design import REVISION_V3,source_sha256
from .execution_design_expert import ExecutionDesignAuthor
from .execution_design_e17_geometry import bounds,contained
from .realworld_tool_expert import ToolExecutionError


def park_left(p):
    if any(row['grasp'][0]for row in p.snapshot()[0].values()):raise ToolExecutionError('Recycling needs genuinely empty left hand')
    tip=p.tip('left')
    if tip[0]<=-.315:return
    p.stage('local-e17-park-empty-left-clear-recycle')
    tip=p.tip('left');p.move('left',tip+[0,0,.040],tolerance=.008)
    for _ in range(20):
        tip=p.tip('left')
        if tip[0]<=-.315:break
        p.act('left','BACK',mm=10.)
        if p.tip('left')[0]>tip[0]-.001:raise ToolExecutionError('Empty left hand failed to enter clear recycling corridor')
    else:raise ToolExecutionError('Empty left recycling retreat exceeded bounded corridor')


def move_payload(p,name,ref,side,control,target):
    target=np.asarray(target,float)
    for _ in range(180):
        p.require_held(ref,side);point=p.point(control);error=target-point
        if np.max(abs(error))<=.008:return
        axis=int(np.argmax(abs(error)));token=(('FWD','BACK'),('LEFT','RIGHT'),('UP','DOWN'))[axis][int(error[axis]<0)]
        p.act(side,token,mm=min(12.,abs(float(error[axis]))*1000))
        if np.max(abs(p.point(control)-point))<.0002:raise ToolExecutionError('Actual packaging transport did not advance')
    raise ToolExecutionError('Actual packaging transport exceeded bounded waypoint')


def hand_box_to_left(p):
    """Three measured left grips precede the real right RELEASE, without reset."""
    from .execution_design_segments_e17_e20 import _held_with_contacts
    right=p.ref('packing_box');_held_with_contacts(p,'packing_box','right')
    west=dict(actor='packing_box',local=[-.086,0.,.010],jaw_axis_local=[1.,0.,0.])
    p.stage('local-e17-held-box-public-left-wall-handover')
    p.act('left','RELEASE');point=p.point(west);height=float(point[2]+.060)
    p.move('left',[*p.tip('left')[:2],height],lambda:p.require_held(right,'right'),tolerance=.008)
    _,rotation=p.frame(west);p.a.align_gripper_axis('left',rotation@np.array([1.,0.,0.]))
    point=p.point(west);p.move('left',[*point[:2],height],lambda:p.require_held(right,'right'),tolerance=.008)
    p.move('left',point,lambda:p.require_held(right,'right'),tolerance=.002)
    for _ in range(3):
        p.require_held(right,'right');p.act('left','GRASP')
    _held_with_contacts(p,'packing_box','left');p.act('right','RELEASE');_held_with_contacts(p,'packing_box','left')
    if p.held(right,'right'):raise ToolExecutionError('Right hand did not really release transferred box')
    p.stage('local-e17-empty-right-south-clear-box-before-lowering')
    tip=p.tip('right');p.move('right',[tip[0],-.120,tip[2]],lambda:p.require_held(west,'left'),tolerance=.008)
    tip=p.tip('right');p.move('right',[*tip[:2],min(1.0,float(tip[2]))],lambda:p.require_held(west,'left'),tolerance=.008)
    return west,'left'


def clear_left_after_recycle(p):
    # Its open jaws now run along X, so the old TCP-X-only idle test no
    # longer describes their footprint. Leave above the low lid corridor.
    if any(row['grasp'][0]for row in p.snapshot()[0].values()):raise ToolExecutionError('Left recycling exit still holds an object')
    p.stage('local-e17-empty-left-above-low-lid-corridor')
    tip=p.tip('left');p.move('left',[*tip[:2],max(1.03,float(tip[2]))],tolerance=.008)


def _xy_inside(p,name,anchor,region):
    state,_=p.snapshot();low,high=bounds(p.objects[name],state[name],state[anchor]);tol=float(p.d.get('geometry_tolerance_m',.003))
    return bool(np.all(low[:2]>=np.asarray(region['lower'])[:2]-tol)and np.all(high[:2]<=np.asarray(region['upper'])[:2]+tol))


def descend_release(p,name,ref,side,control,support,floor_z):
    if not p.contact(name,support):
        point=p.point(control);move_payload(p,name,ref,side,control,[*point[:2],max(floor_z+.008,min(float(point[2]),floor_z+.018))])
    for _ in range(20):
        p.require_held(ref,side)
        if p.contact(name,support):break
        gap=float(p.point(control)[2]-floor_z)
        p.act(side,'DOWN',mm=min(5.,max(1.,gap*1000)))
    else:raise ToolExecutionError('Original support contact was not reached: '+name)
    p.release(ref,side)
    if not p.contact(name,support):raise ToolExecutionError('Actual released packaging lost its support: '+name)


def recycle_box(p,ref,side):
    name='packing_box';region=next(r for r in p.d['cleanup_regions']if r['id']=='recycling');base,rotation=p.frame({'actor':'recycle_box'});control={'actor':name,'local':p.bottom_local(name)}
    p.stage('local-e17-held-box-west-then-low-carry')
    point=p.point(control);move_payload(p,name,ref,side,control,[-.230,point[1],point[2]])
    p.rotate_actor(name,side,np.eye(3))
    control={'actor':name,'local':p.bottom_local(name)}
    point=p.point(control);rim=float(base[2]+np.abs(rotation[2])@np.asarray(p.objects['recycle_box']['size']));height=rim+.025
    move_payload(p,name,ref,side,control,[*point[:2],height])
    point=p.point(control);move_payload(p,name,ref,side,control,[point[0],base[1],height]);move_payload(p,name,ref,side,control,[base[0],base[1],height])
    if not _xy_inside(p,name,'recycle_box',region):
        p.move_point(side,control,[base[0],base[1],height],lambda:p.require_held(ref,side),tolerance=.003)
        if not _xy_inside(p,name,'recycle_box',region):raise ToolExecutionError('Actual box does not fit original recycling footprint')
    p.stage('local-e17-recycle-box-stop-on-real-floor-contact')
    descend_release(p,name,ref,side,control,'recycle_box',float(base[2]+region['lower'][2]))
    state,contacts=p.snapshot()
    if not contained(p.objects[name],state[name],state['recycle_box'],region,p.d.get('geometry_tolerance_m',.003)):raise ToolExecutionError('Released box is outside original recycling region')
    p.move(side,p.tip(side)+[0,0,.040],tolerance=.008)


def recycle_lid(p):
    p.stage('local-e17-empty-west-corridor-to-lid')
    tip=p.tip('right');p.move('right',[-.250,tip[1],tip[2]],tolerance=.008);tip=p.tip('right');p.move('right',[tip[0],-.360,tip[2]],tolerance=.008)
    tip=p.tip('right');p.move('right',[*tip[:2],min(1.0,float(tip[2]))],tolerance=.008)
    p.grasps['packing_lid']['hand']='right';p.clearance=.95;ref,side=p.pickup('packing_lid');name='packing_lid';control={'actor':name,'local':p.bottom_local(name)}
    base,_=p.frame({'actor':'recycle_box'});height=.915;p.stage('local-e17-held-lid-west-low-carry')
    point=p.point(control);move_payload(p,name,ref,side,control,[*point[:2],height]);point=p.point(control);move_payload(p,name,ref,side,control,[-.230,point[1],height])
    move_payload(p,name,ref,side,control,[-.230,base[1],height]);boxpos,boxrot=p.frame({'actor':'packing_box'});p.rotate_actor(name,side,boxrot)
    move_payload(p,name,ref,side,control,[boxpos[0],boxpos[1],height]);top=float(boxpos[2]+np.abs(boxrot[2])@np.asarray(p.objects['packing_box']['size']))
    region=next(r for r in p.d['cleanup_regions']if r['id']=='recycling')
    if not _xy_inside(p,name,'recycle_box',region):
        p.rotate_actor(name,side,np.eye(3));p.move_point(side,control,[base[0],base[1],height],lambda:p.require_held(ref,side),tolerance=.003)
        if not _xy_inside(p,name,'recycle_box',region):raise ToolExecutionError('Actual lid does not fit original recycling footprint')
    p.stage('local-e17-recycle-lid-stop-on-real-box-contact');descend_release(p,name,ref,side,control,'packing_box',top)
    state,_=p.snapshot()
    if not contained(p.objects[name],state[name],state['recycle_box'],region,p.d.get('geometry_tolerance_m',.003)):raise ToolExecutionError('Actual released lid is outside original recycling region')
    p.move(side,p.tip(side)+[0,0,.040],tolerance=.008)


def deliver_stand(p):
    p.stage('local-e17-empty-withdraw-before-right-stand-acquire')
    tip=p.tip('right');p.move('right',[tip[0],min(float(tip[1]),-.120),tip[2]],tolerance=.008)
    p.grasps['stand']['hand']='right';p.clearance=.95;ref,side=p.pickup('stand');control={'actor':'stand','local':p.bottom_local('stand')};zone=next(z for z in p.spec['zones']if z['id']==p.d['destination_zone'])
    if zone['xy'][1]>=0:raise ToolExecutionError('This reviewed B delivery requires its original south zone')
    p.stage('local-e17-deliver-loaded-stand-low-carry')
    point=p.point(control);height=max(.860,float(point[2]));move_payload(p,'stand',ref,side,control,[*point[:2],height]);point=p.point(control)
    move_payload(p,'stand',ref,side,control,[zone['xy'][0],point[1],height]);move_payload(p,'stand',ref,side,control,[*zone['xy'],height])
    # Keep the carried display upright enough for its real supports; no exact
    # identity-rotation target is pursued when already within8degrees.
    rotation=p.frame({'actor':'stand'})[1];angle=float(np.arccos(np.clip((np.trace(rotation)-1)/2,-1,1)))
    if angle>np.deg2rad(8):p.rotate_actor('stand',side,np.eye(3))
    def in_zone():
        row=p.snapshot()[0]['stand'];obj=p.objects['stand'];center=row['pos']+row['mat']@np.asarray(obj.get('local_bounds_center',[0,0,0]));half=np.abs(row['mat'])@np.asarray(obj['size'])
        return bool(np.all(abs(center[:2]-zone['xy'])+half[:2]<=np.asarray(zone['half_size'])+.003)),center,half
    for _ in range(20):
        inside,center,half=in_zone()
        if inside:break
        allowed=np.asarray(zone['half_size'])+.003-half[:2]
        if np.any(allowed<0):p.rotate_actor('stand',side,np.eye(3));continue
        error=np.asarray(zone['xy'])-center[:2];axis=int(np.argmax(abs(error)-allowed));distance=min(.005,max(.001,float(abs(error[axis])-allowed[axis]+.001)))
        p.act(side,(('FWD','BACK'),('LEFT','RIGHT'))[axis][int(error[axis]<0)],mm=distance*1000)
    else:raise ToolExecutionError('Actual loaded stand could not enter original delivery footprint')
    p.stage('local-e17-delivery-stop-on-real-table-contact')
    descend_release(p,'stand',ref,side,control,p.d.get('delivery_support_actor','table'),float(zone.get('surface_z',.8)))
    p.wait(2)
    if not in_zone()[0]:raise ToolExecutionError('Released stand left the original delivery zone')


def recycle_all(p):
    p.clearance=.95;p.grasps['packing_box']['hand']='left'
    ref,side=p.pickup('packing_box');recycle_box(p,ref,side);clear_left_after_recycle(p);recycle_lid(p)


def run_segment(author,segment,parameters):
    spec=author.scene.spec;d=spec.get('execution_design',{});cp=getattr(author,'_engineering_resume_checkpoint',{});s=cp.get('source',{})
    boundaries={'e17_b_recycle_low_from_held999':(999,99902),'e17_b_handover_recycle_from_held187':(187,18702)}
    if (segment not in boundaries or not isinstance(parameters,dict)or parameters or spec.get('id')!='E17'or spec.get('variant')!='B'or spec.get('seed')!=4201
            or d.get('condition')!='I'or d.get('revision')!=REVISION_V3 or d.get('source_sha256')!=source_sha256(REVISION_V3)
            or not author.control_report.get('engineering_reference_only')or not getattr(author,'_execution_design_reference_authorized',False)or author.smooth
            or cp.get('diagnostic_only')is not True or cp.get('state_quality')!='measured_native_state'or (s.get('steps'),s.get('physics_ticks'))!=boundaries[segment]):raise ToolExecutionError('Exact native B held-box boundary required')
    p=ExecutionDesignAuthor(author)
    from .execution_design_e17_stand import descriptor,native_readback
    from .execution_design_segments_e17_e20 import _held_with_contacts
    actual=native_readback(author.scene)
    if not actual or actual.get('derived_geometry_sha256')!=descriptor()['derived_geometry_sha256']or actual.get('kinematic_enabled')is not False or actual.get('gravity_disabled')is not False:raise ToolExecutionError('Actual dynamic reviewed stand required')
    _held_with_contacts(p,'packing_box','right');regions={name:r for r in d['local_regions']for name in r['members']};base,rotation=p.frame({'actor':'stand'});base=base.copy();rotation=rotation.copy();delivering=False
    def guard():
        state,contacts=p.snapshot();pos,rot=p.frame({'actor':'stand'})
        if not delivering and(np.linalg.norm(pos-base)>.005 or np.linalg.norm(rot-rotation)>.12):raise ToolExecutionError('Stand moved materially before B delivery')
        for name in d['target_members']:
            if any(state[name]['grasp'])or frozenset((name,'stand'))not in contacts or not contained(p.objects[name],state[name],state['stand'],regions[name],d.get('geometry_tolerance_m',.003)):
                raise ToolExecutionError('Completed piece lost original region/support: '+name)
    guard();before=p.c.steps;old=author.act;had='act'in author.__dict__;previous=author.__dict__.get('act')
    def guarded(*args,**kwargs):
        if p.c.steps-before>=1200:raise ToolExecutionError('Low recycle/delivery exceeded1200 public actions')
        guard();value=old(*args,**kwargs);guard();return value
    author.act=guarded
    try:
        if s['steps']==187:
            ref,side=hand_box_to_left(p);recycle_box(p,ref,side);clear_left_after_recycle(p)
        else:park_left(p);recycle_box(p,p.ref('packing_box'),'right')
        recycle_lid(p);guard();delivering=True;deliver_stand(p);guard()
    finally:
        if had:author.act=previous
        else:del author.act
    return dict(local_completed=True,operations=deepcopy(p.operations),active_actions=p.c.steps-before)
