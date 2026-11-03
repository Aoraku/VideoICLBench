"""E11 engineering: move the real empty dynamic tray before filling it.

No authored poses, altered goals, attachments, or success overrides. Every
motion goes through the same public Cartesian action interface as the reference.
"""
import math
import numpy as np
from .execution_design import REVISION_V3

TRAY_SHA='b6b5837110820a23f6dc743e0ea007259500124d8da632686c708732a4e3633c'


def checked_plan(author):
    spec=author.scene.spec
    if not (getattr(author,'_execution_design_reference_authorized',False)
            and spec.get('id')=='E11' and spec.get('execution_design',{}).get('revision')==REVISION_V3):
        raise ValueError('E11 tray reference requires explicit v3 engineering scope')
    tray=next(o for o in spec['objects']if o['id']=='tray')
    if tray.get('role')!='movable' or tray.get('source_asset',{}).get('sha256')!=TRAY_SHA or not np.allclose(tray['size'],[.12,.10,.02],atol=1e-10,rtol=0):
        raise ValueError('Exact dynamic four-grid source tray required')
    state,_=author.c.snapshot();body=state['tray'];position=np.asarray(body['pos'],float);rotation=np.asarray(body['mat'],float)
    if not np.isfinite(np.r_[position,rotation.ravel()]).all() or np.max(np.abs(rotation-np.eye(3)))>.02:
        raise ValueError('E11 empty tray must start upright and axis-aligned')
    target=position.copy();target[0]-=.060
    # Conservative swept original body bounds. Source cargo must stay outside
    # the tray path; otherwise this reference cannot preserve initial layout.
    lo=np.minimum(position,target)-np.asarray(tray['size'])-.004
    hi=np.maximum(position,target)+np.asarray(tray['size'])+.004
    for obj in spec['objects']:
        if obj['id']=='tray':continue
        b=state[obj['id']];p=np.asarray(b['pos']);half=np.abs(np.asarray(b['mat']))@np.asarray(obj['size'])
        if np.all(p[:2]+half[:2]>=lo[:2]) and np.all(p[:2]-half[:2]<=hi[:2]):
            raise ValueError('E11 original cargo overlaps empty-tray sweep')
    # Source collision near-X wall, away from the central partition. Centered
    # source asset: X[-.12217,-.10418], Z[.0062,.04166] before recentering.
    # X=-.112,Y=.045,Z=.010 is within that real wall after normalization.
    point=position+rotation@np.array([-.112,.045,.010])
    return point,target,position.copy()


def move_empty_tray(author):
    point,target,initial=checked_plan(author);side='left';index=0
    author.note('e11-empty-tray-approach')
    author.act('RELEASE','RELEASE')
    height=max(.96,float(author.tip(side)[2]))
    author.move_generated({side:[*author.tip(side)[:2],height]})
    author.align_gripper_axis(side,[1,0,0])
    author.move_generated({side:[*point[:2],height]})
    author.move_generated({side:point},tolerance=.001)
    for _ in range(3):author.act('GRASP','STILL')
    state,_=author.c.snapshot()
    if not state['tray']['grasp'][index]:raise RuntimeError('E11 near-wall tray pinch not physically held')
    author.carried_payload=('tray',side)
    author.note('e11-empty-tray-held')
    # Keep the weight supported by the table. A single-wall lift produced
    # measurable tilt and stalled despite ample joint margins. The original
    # cargo-clear swept footprint permits an actual horizontal pull instead.
    # move_generated still checks measured holding before every public action.
    progress=[]
    for _ in range(100):
        state,_=author.c.snapshot();body=state['tray']
        if not body['grasp'][index]:raise RuntimeError('E11 real tray grip lost')
        error=target[:2]-np.asarray(body['pos'])[:2]
        remaining=float(np.max(np.abs(error)))
        if remaining<.002:break
        progress.append(remaining)
        if len(progress)>=24 and min(progress[-24:-16])-min(progress[-8:])<.0005:
            raise RuntimeError('E11 measured supported pull stalled')
        # Re-observe actual body after each action; do not insist on reaching
        # a tiny intermediate TCP Y correction while the main X error is 4cm.
        axis=int(np.argmax(np.abs(error)));positive=1 if error[axis]>0 else -1
        sign=getattr(author,'generated_axis_signs',{}).get(side,{}).get(axis,1)
        token=(('FWD','BACK'),('LEFT','RIGHT'))[axis][0 if positive==sign else 1]
        author.act(token,'STILL',min(6.,max(.5,abs(float(error[axis]))*1000)))
    else:raise RuntimeError('E11 measured supported pull did not converge')
    author.act('RELEASE','STILL');author.carried_payload=None
    author.move_generated({side:[*author.tip(side)[:2],height]})
    for _ in range(3):author.act('STILL','STILL')
    state,contacts=author.c.snapshot()
    if any(state['tray']['grasp']) or frozenset(('tray','table'))not in contacts:
        raise RuntimeError('E11 moved tray lacks released table contact')
    if np.max(np.abs(np.asarray(state['tray']['pos'])[:2]-target[:2]))>.004:
        raise RuntimeError('E11 moved tray not at measured staging location')
    author.note('e11-empty-tray-released')
    # The tray wall requires an X-axis pinch. Original cargo has no explicit
    # grasp-axis override, so retaining that pose spreads an open finger into
    # the moved near wall (measured 0.88N in candidate v3). Restore the Y-axis
    # plate pinch only after release and high clearance, using public rotation.
    restore_cargo_axis(author,side)
    author.note('e11-cargo-gripper-axis-restored')


def cargo_orientation_delta(current,jaw,arm_feedback):
    from .author_orientation import panda_downward_grasp_delta
    names=arm_feedback['joint_names'];index=names.index('panda_joint7')
    limits=arm_feedback['measured_sensors']['joint_soft_limits_rad']
    if not limits.get('available'):raise ValueError('Actual native wrist limits required')
    joint=[arm_feedback['joint_positions_rad'][index],*limits['value'][index]]
    return panda_downward_grasp_delta(current,jaw,[0,1,0],joint7_state=joint)


def restore_cargo_axis(author,side):
    """Choose an empty-palm finger assignment using measured wrist margin."""
    from .author_orientation import _axis_angle
    if (author.scene.spec.get('id')!='E11' or
        not getattr(author,'_execution_design_reference_authorized',False) or
        author.scene.spec.get('execution_design',{}).get('revision')!=REVISION_V3 or
        getattr(author,'smooth',False)):
        raise ValueError('E11 native public-action scope required')
    if author.scene.embodiment.name!='franka':
        return author.align_gripper_axis(side,[0,1,0])
    initial=np.asarray(author.tip(side),float)
    if initial[2]<.94:raise RuntimeError('Restore cargo pinch above table clearance')
    tokens=(('ROLL_LEFT','ROLL_RIGHT'),('PITCH_UP','PITCH_DOWN'),('ROTATE_CCW','ROTATE_CW'))
    for _ in range(64):
        state,_=author.c.snapshot()
        if any(body['grasp'][0 if side=='left'else 1] for body in state.values()):
            raise RuntimeError('Restore cargo axis requires an actually empty hand')
        geometry=author.finger_geometry(side)
        if geometry.get('source')!='actual_collision_mesh_current_body_pose':
            raise ValueError('Actual finger geometry required')
        f=geometry['fingers'];jaw=np.asarray(f[0]['body_origin_task_m'])-f[1]['body_origin_task_m']
        current=author.tcp_rotation_task(side)
        arm=author.c.public_feedback()['arms'][side]
        axis,angle=_axis_angle(cargo_orientation_delta(current,jaw,arm))
        if angle<math.radians(1.):return
        tip=np.asarray(author.tip(side),float)
        if tip[2]<.92 or np.linalg.norm(tip-initial)>.025:
            raise RuntimeError('Empty cargo-axis rotation left safe high envelope')
        component=int(np.argmax(np.abs(axis)));token=tokens[component][int(axis[component]<0)]
        degrees=min(5.,max(.5,abs(math.degrees(angle*axis[component]))))
        author.act(token if side=='left'else'STILL',token if side=='right'else'STILL',rotation_deg=degrees)
    raise RuntimeError('Native-limit-aware cargo rotation did not converge')


PLATE_SHA='fed57b9b0e69a5b8b98d75324ed6856c0cdb21ebc56c8f98cb372670255b61bb'

def grasp_spec(author,obj):
    """Pinch the existing near-side plate cross-section, no mesh changes."""
    from copy import deepcopy
    spec=author.scene.spec
    if not(getattr(author,'_execution_design_reference_authorized',False) and
           spec.get('id')=='E11' and spec.get('execution_design',{}).get('revision')==REVISION_V3):
        return obj
    if (obj.get('id')not in spec['semantic']['groups']['blocks'] or
        obj.get('source_asset',{}).get('sha256')!=PLATE_SHA or
        not np.allclose(obj['size'],[.02,.02,.003],atol=1e-10,rtol=0)):
        raise ValueError('Exact original E11 source plate required')
    result=deepcopy(obj);result['grasp_point_local']=[-.010,0.,0.];result['grasp_axis_local']=[0,1,0]
    return result


def reachable_cell_xy(author,name,target):
    """Choose a legal near-side point inside the unchanged original cell."""
    spec=author.scene.spec
    if not(getattr(author,'_execution_design_reference_authorized',False) and
           spec.get('id')=='E11' and spec.get('execution_design',{}).get('revision')==REVISION_V3):
        raise ValueError('E11 engineering cell waypoint scope required')
    if target.get('anchor_object')!='tray':raise ValueError('Original measured tray anchor required')
    bounds=spec['semantic']['compartment_bounds'][target['id']]
    state,_=author.c.snapshot();tray=state['tray'];obj=next(o for o in spec['objects']if o['id']==name)
    if obj.get('source_asset',{}).get('sha256')!=PLATE_SHA:raise ValueError('Exact original cargo shape required')
    from types import SimpleNamespace
    from .execution_design_thin_edge import material_collision_points_task
    policy=SimpleNamespace(a=author,frame=lambda ref:(np.asarray(state[name]['pos']),np.asarray(state[name]['mat'])))
    vertices=material_collision_points_task(policy,dict(actor=name))
    local,certificate=cell_point_from_vertices(state[name]['pos'],vertices,tray,bounds,target['anchor_local_center'])
    if hasattr(author,'out'):
        import json
        with (author.out/'e11-cell-waypoints.private.jsonl').open('a')as f:
            f.write(json.dumps(dict(object=name,target=target['id'],step=author.c.steps,**certificate))+'\n')
    return (np.asarray(tray['pos'])+np.asarray(tray['mat'])@local)[:2]


def cell_point_from_vertices(position,vertices,tray,bounds,preferred):
    vertices=np.asarray(vertices,float);position=np.asarray(position,float)
    if vertices.ndim!=2 or vertices.shape[1]!=3 or len(vertices)<4 or not np.isfinite(vertices).all():
        raise ValueError('Full actual collision vertex cloud required')
    offsets=(vertices-position)@np.asarray(tray['mat'])
    lower=np.asarray(bounds['lower'],float);upper=np.asarray(bounds['upper'],float)
    local=np.asarray(preferred,float).copy();local[0]=lower[0]-offsets[:,0].min()+.003
    local[2]=lower[2]-offsets[:,2].min()+.001
    predicted=offsets+local
    if (np.any(predicted[:,:2]<lower[:2]+.0029) or np.any(predicted[:,:2]>upper[:2]-.0029)
            or np.any(predicted[:,2]<lower[2]) or np.any(predicted[:,2]>upper[2])):
        raise RuntimeError('Measured cargo cannot fit legal original cell waypoint')
    return local,dict(geometry_source='full_native_collision_vertices_current_orientation',vertices=len(vertices),
        predicted_min_local=predicted.min(0).tolist(),predicted_max_local=predicted.max(0).tolist(),
        original_lower=lower.tolist(),original_upper=upper.tolist(),native_placement_verified=False)


def release_height(author,side,original_height):
    """Open above the real tray rim; never spread fingers inside a narrow cell."""
    from types import SimpleNamespace
    from .execution_design_thin_edge import material_collision_points_task
    spec=author.scene.spec
    if not(getattr(author,'_execution_design_reference_authorized',False) and spec.get('id')=='E11'
           and spec.get('execution_design',{}).get('revision')==REVISION_V3):
        raise ValueError('E11 engineering rim release scope required')
    state,_=author.c.snapshot();tray=state['tray']
    policy=SimpleNamespace(a=author,frame=lambda ref:(np.asarray(tray['pos']),np.asarray(tray['mat'])))
    vertices=material_collision_points_task(policy,dict(actor='tray'))
    geometry=author.finger_geometry(side)
    height,proof=rim_release_height(vertices,geometry,author.tip(side),original_height)
    if hasattr(author,'out'):
        import json
        with (author.out/'e11-rim-release.private.jsonl').open('a')as f:
            f.write(json.dumps(dict(side=side,step=author.c.steps,**proof))+'\n')
    return height


def rim_release_height(tray_vertices,finger_geometry,tip,original_height):
    vertices=np.asarray(tray_vertices,float);tip=np.asarray(tip,float)
    if vertices.ndim!=2 or vertices.shape[1]!=3 or len(vertices)<4 or not np.isfinite(vertices).all():
        raise ValueError('Actual tray collision cloud required')
    if finger_geometry.get('source')!='actual_collision_mesh_current_body_pose' or len(finger_geometry.get('fingers',[]))!=2:
        raise ValueError('Both actual finger collision meshes required')
    lowest=min(float(f['aabb_min_task_m'][2])for f in finger_geometry['fingers'])
    rim=float(vertices[:,2].max());height=max(float(original_height),float(tip[2])+rim+.008-lowest)
    if not np.isfinite([lowest,rim,height]).all():raise ValueError('Finite actual rim and fingers required')
    return height,dict(actual_rim_top_task_m=rim,actual_lowest_finger_task_m=lowest,
        target_tcp_z=height,predicted_finger_clearance_m=lowest+height-tip[2]-rim,
        drop_inside_original_xy=True,native_release_verified=False)
