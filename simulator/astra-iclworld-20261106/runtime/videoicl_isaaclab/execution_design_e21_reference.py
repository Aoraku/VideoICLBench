"""E21 v3 engineering-only measured plate pickup and above-rim release.

No object pose, scene layout, goal, public controller or scoring modifications.
A clearance plan is not native acceptance; actual support/order remain scored.
"""
from copy import deepcopy
import itertools,json
import numpy as np
from .execution_design import REVISION_V3

PLATE_SHA='fed57b9b0e69a5b8b98d75324ed6856c0cdb21ebc56c8f98cb372670255b61bb'
TRAY_SHA='b6b5837110820a23f6dc743e0ea007259500124d8da632686c708732a4e3633c'


def enabled(author):
    spec=author.scene.spec
    return bool(getattr(author,'_execution_design_reference_authorized',False)
        and spec.get('id')=='E21' and spec.get('execution_design',{}).get('revision')==REVISION_V3)


def _scope(author):
    if not enabled(author):raise ValueError('E21 reference requires explicit v3 engineering scope')


def grasp_spec(author,obj):
    if not enabled(author) or obj['id'] not in author.scene.spec['semantic']['groups']['blocks']:return obj
    if obj.get('source_asset',{}).get('sha256')!=PLATE_SHA or obj.get('size')!=[.02,.02,.003]:
        raise ValueError('E21 pickup requires exact reviewed source plate')
    # Same signed X=-10mm mesh section reviewed for E02. Both real Y-side
    # surfaces remain at +/-20mm; this is a private pinch, not new geometry.
    result=deepcopy(obj);result['grasp_point_local']=[-.01,0.,0.];result['grasp_axis_local']=[0,1,0]
    return result


def verify_pickup_ik(author,side,point,ik_probe=None):
    _scope(author)
    if ik_probe is None:
        from .execution_design_drawer_ik_probe import inspect
        ik_probe=inspect
    point=np.asarray(point,float)
    if point.shape!=(3,) or not np.isfinite(point).all():raise ValueError('Finite actual E21 pickup required')
    result=ik_probe(author,author.c,side,[dict(position=point,rotation=author.tcp_rotation_task(side))])
    _record(author,'pickup_ik',dict(side=side,point=point.tolist(),ik=result,native_passed=False))
    if len(result)!=1 or not result[0].get('kinematically_reachable') or result[0].get('minimum_joint_margin_rad',-1.)<=.01:
        raise RuntimeError('E21 measured pickup endpoint lacks original IK joint margins')


def _record(author,phase,data):
    if getattr(author,'out',None) is not None:
        with (author.out/'e21-measured-release.private.jsonl').open('a')as stream:stream.write(json.dumps(dict(phase=phase,**data))+'\n')


def _geometry(author,side,name,target):
    _scope(author)
    if author.scene.embodiment.name!='franka':raise ValueError('E21 rim-release opening clearance reviewed for actual Panda only')
    spec=author.scene.spec;state,contacts=author.c.snapshot();semantic=spec['semantic'];tray=semantic['container']
    obj=next(o for o in spec['objects']if o['id']==tray)
    if obj.get('source_asset',{}).get('sha256')!=TRAY_SHA:raise ValueError('E21 tray geometry is not reviewed source')
    if target.get('anchor_object')!=tray or target['id']not in semantic['compartment_bounds']:
        raise ValueError('E21 release must use the original actual tray compartment')
    body=state[tray];rotation=np.asarray(body['mat']);position=np.asarray(body['pos'])
    if rotation[2,2]<np.cos(np.deg2rad(5)):raise RuntimeError('E21 tray is not stably upright for physical drop')
    midpoint=position+rotation@np.asarray(obj.get('local_bounds_center',[0,0,0]));half=np.asarray(obj.get('bounds_half_extent',obj['size']))
    rim=float(midpoint[2]+(np.abs(rotation)@half)[2]);fg=author.finger_geometry(side)
    if fg.get('source')!='actual_collision_mesh_current_body_pose' or len(fg['fingers'])!=2:
        raise ValueError('E21 requires actual bilateral finger collision geometry')
    origins=[np.asarray(x['body_origin_task_m'])for x in fg['fingers']];axis=origins[0]-origins[1];axis/=np.linalg.norm(axis)
    if abs(axis[2])>.05:raise RuntimeError('E21 opening jaw is too tilted for reviewed rim clearance')
    return state,contacts,tray,body,rim,fg


def release_height(author,side,name,target,original_tcp_z):
    state,contacts,tray,body,rim,fg=_geometry(author,side,name,target)
    obj=next(o for o in author.scene.spec['objects']if o['id']==name);piece=state[name]
    half=np.asarray(obj.get('bounds_half_extent',obj['size']));center=np.asarray(obj.get('local_bounds_center',[0,0,0]))
    bottom=float((np.asarray(piece['pos'])+np.asarray(piece['mat'])@center)[2]-(np.abs(piece['mat'])@half)[2])
    tip=np.asarray(author.tip(side));depth=tip[2]-bottom
    # Twelve millimetres over actual rim: both finger meshes stay above the
    # source rim when opening. The near-horizontal jaw guard bounds vertical
    # travel during the Panda's <=40mm per-finger opening to <=2mm.
    height=max(float(original_tcp_z),rim+depth+.006,float(author.floor_clear_tcp(side,floor=rim+.012)))
    _record(author,'release_plan',dict(object=name,tray=tray,actual_rim_z=rim,actual_payload_depth_m=float(depth),requested_tcp_z=float(original_tcp_z),release_tcp_z=height,native_passed=False))
    return height


def verify_before_release(author,side,name,target):
    state,contacts,tray,body,rim,fg=_geometry(author,side,name,target)
    if fg['lowest_z_task_m']<rim+.004:raise RuntimeError('E21 actual fingers are still below rim release clearance')
    if any(frozenset((tray,f'{side}_finger{i}'))in contacts for i in (1,2)):
        raise RuntimeError('E21 hand is contacting tray before release')
    piece=state[name];obj=next(o for o in author.scene.spec['objects']if o['id']==name)
    if not piece['grasp'][0 if side=='left'else 1]:raise RuntimeError('E21 payload grip lost before controlled drop')
    half=np.asarray(obj.get('bounds_half_extent',obj['size']));center=np.asarray(obj.get('local_bounds_center',[0,0,0]))
    corners=np.array([center+half*np.array(s)for s in itertools.product((-1,1),repeat=3)])
    world=corners@np.asarray(piece['mat']).T+piece['pos'];local=(world-body['pos'])@body['mat'];bounds=author.scene.spec['semantic']['compartment_bounds'][target['id']]
    if np.any(local.min(0)[:2]<np.asarray(bounds['lower'])[:2]+.001) or np.any(local.max(0)[:2]>np.asarray(bounds['upper'])[:2]-.001):
        raise RuntimeError('E21 actual payload projection does not clear original cell walls')
    _record(author,'before_release',dict(object=name,actual_rim_z=rim,actual_finger_lowest_z=fg['lowest_z_task_m'],payload_local_min=local.min(0).tolist(),payload_local_max=local.max(0).tolist(),native_passed=False))


def transport_above_rim(author,side,name,target,clear_z):
    """Re-establish measured clearance between short public XY segments.

    B's old long maximum-error waypoint accumulated 30mm of vertical drift
    before correcting Z; the fingers physically pushed the tray. Correcting Z
    between bounded XY segments changes only the engineering action sequence.
    """
    state,contacts,tray,body,rim,fg=_geometry(author,side,name,target)
    initial_tray=np.asarray(body['pos'],float).copy();previous_stage=author.stage
    obj=next(o for o in author.scene.spec['objects']if o['id']==name)
    half=np.asarray(obj.get('bounds_half_extent',obj['size']));center=np.asarray(obj.get('local_bounds_center',[0,0,0]))
    hand=('left','right').index(side);author.stage='grasped-'+name+'-above-rim-transfer'
    previous_errors=[]
    def measured():
        s,c,t,b,r,g=_geometry(author,side,name,target);piece=s[name];tip=np.asarray(author.tip(side),float)
        if not piece['grasp'][hand] or not all(frozenset((name,f'{side}_finger{i}'))in c for i in (1,2)):
            raise RuntimeError('E21 above-rim transfer lost actual bilateral payload grip')
        if any(frozenset((t,f'{side}_finger{i}'))in c for i in (1,2)):
            raise RuntimeError('E21 above-rim transfer detected actual finger-tray contact')
        if np.linalg.norm(np.asarray(b['pos'])-initial_tray)>.002:
            raise RuntimeError('E21 tray moved during above-rim transfer')
        midpoint=np.asarray(piece['pos'])+np.asarray(piece['mat'])@center
        bottom=float(midpoint[2]-(np.abs(piece['mat'])@half)[2])
        flight=max(float(clear_z),r+.025+max(0.,float(tip[2]-g['lowest_z_task_m'])),r+.025+max(0.,float(tip[2]-bottom)))
        destination=np.asarray(b['pos'])+np.asarray(b['mat'])@np.asarray(target['anchor_local_center'],float)
        error=destination[:2]-np.asarray(piece['pos'])[:2]
        return tip,g,bottom,r,flight,error
    for i in range(180):
        tip,fg,bottom,rim,flight,error=measured()
        # Correct vertical tracking first even when XY error is much larger.
        author.move_generated({side:[*tip[:2],flight]},tolerance=.0015)
        tip,fg,bottom,rim,flight,error=measured()
        if min(float(fg['lowest_z_task_m']),bottom)<rim+.018:
            raise RuntimeError('E21 measured transfer clearance not established')
        if np.max(np.abs(error))<=.002:
            _record(author,'above_rim_transfer',dict(object=name,segments=i,payload_xy_error_m=error.tolist(),
                actual_finger_lowest_z=fg['lowest_z_task_m'],actual_payload_bottom_z=bottom,actual_rim_z=rim,
                source_goal_unchanged=True,native_passed=False))
            author.stage=previous_stage
            return
        previous_errors.append(float(np.linalg.norm(error)))
        if len(previous_errors)>=24 and min(previous_errors[-24:-16])-min(previous_errors[-8:])<.0005:
            raise RuntimeError('E21 measured above-rim transfer stalled')
        axis=int(np.argmax(np.abs(error)));next_tip=tip.copy();next_tip[axis]+=np.clip(error[axis],-.006,.006)
        author.move_generated({side:next_tip.tolist()},tolerance=.0015)
        tip,fg,bottom,rim,flight,error=measured()
        if min(float(fg['lowest_z_task_m']),bottom)<rim+.012:
            raise RuntimeError('E21 actual short transfer consumed rim clearance')
    raise RuntimeError('E21 above-rim transfer did not converge')
