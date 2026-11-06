"""NativeA223: release wrong box, minimal divider-clear nudge, real green grip."""
from copy import deepcopy
import numpy as np
from .execution_design import REVISION_V3,source_sha256
from .execution_design_expert import ExecutionDesignAuthor
from .execution_design_segments_e17 import STAND_ROTATION_MATRIX_LIMIT,TRIANGLE_SHA
from .realworld_tool_expert import ToolExecutionError

NAME='green_triangle'
CORNERS=np.array([[x,y,z]for x in(-1,1)for y in(-1,1)for z in(-1,1)],float)
TRIANGLE=np.array([[x,y,z]for x,y in[(-.02,-.017320508),(.02,-.017320508),(0.,.017320508)]for z in(-.003,.003)])


def _tray(policy):
    obj=policy.objects['packing_box'];shapes=obj.get('collision_shapes',[])
    if obj.get('kind')!='tray'or len(shapes)!=9 or shapes[0].get('type')!='box':raise ToolExecutionError('Original nine-part packing tray required')
    rails=[r for r in shapes if r.get('type')=='box'and np.allclose(r['size'],[.003,.014,.006],atol=1e-9,rtol=0)]
    if len(rails)!=4:raise ToolExecutionError('Actual source divider geometry required')
    return obj,sorted(rails,key=lambda r:r['pos'][1]),float(shapes[0]['pos'][2]+shapes[0]['size'][2])


def _frame(policy):
    base,rotation=policy.frame({'actor':'packing_box'})
    if rotation[2,2]<.99:raise ToolExecutionError('Packing box is not upright for physical regrasp')
    return base,rotation


def _bounds(policy):
    base,box=_frame(policy);pos,rotation=policy.frame({'actor':NAME})
    points=(TRIANGLE@rotation.T+pos-base)@box
    return points.min(0),points.max(0),(pos-base)@box


def _finger_offsets(policy):
    base,box=_frame(policy);tip=policy.tip('right');cloud=[];geometry=policy.a.finger_geometry('right')
    if geometry.get('source')!='actual_collision_mesh_current_body_pose':raise ToolExecutionError('Actual finger collision mesh readback required')
    for finger in geometry['fingers']:
        lo=np.asarray(finger['aabb_min_task_m']);hi=np.asarray(finger['aabb_max_task_m'])
        cloud.extend((((lo+hi)/2+CORNERS*(hi-lo)/2)-tip)@box)
    cloud=np.asarray(cloud)
    return cloud.min(0),cloud.max(0)


def _bay(policy):
    obj,rails,floor=_tray(policy);_,_,center=_bounds(policy)
    index=min(range(len(rails)),key=lambda i:abs(rails[i]['pos'][1]-center[1]))
    if index==0:raise ToolExecutionError('No reviewed inward divider-free bay')
    lower=rails[index-1]['pos'][1]+rails[index-1]['size'][1]
    upper=rails[index]['pos'][1]-rails[index]['size'][1]
    if upper-lower<.045:raise ToolExecutionError('Source divider-free bay is too narrow')
    return obj,rails,floor,float(lower),float(upper)


def _fit_xy(point,lo,hi,xlow,xhigh,ylow,yhigh):
    # Plan a TCP target inside real walls. This never clips a measured pose/q.
    before=np.asarray(point,float);target=before.copy()
    limits=[(xlow-lo[0]+.0025,xhigh-hi[0]-.0025),(ylow-lo[1]+.0025,yhigh-hi[1]-.0025)]
    if any(a>=b for a,b in limits):raise ToolExecutionError('Actual open fingers do not fit the source bay')
    for i,(low,high)in enumerate(limits):target[i]=max(low,min(high,target[i]))
    if np.linalg.norm(target[:2]-before[:2])>.008:raise ToolExecutionError('Real gripper clearance would leave the reviewed triangle grasp area')
    return target


def run_segment(author,segment,parameters):
    if segment!='e17_a_release_box_nudge_regrasp_223'or not isinstance(parameters,dict)or parameters:
        raise ToolExecutionError('Explicit E17A223 physical regrasp entry with empty parameters required')
    spec=author.scene.spec;d=spec.get('execution_design',{});cp=getattr(author,'_engineering_resume_checkpoint',{});source=cp.get('source',{})
    if (spec.get('id')!='E17'or spec.get('variant')!='A'or spec.get('seed')!=4201
            or d.get('revision')!=REVISION_V3 or d.get('source_sha256')!=source_sha256(REVISION_V3)or d.get('condition')!='I'
            or not author.control_report.get('engineering_reference_only')or not getattr(author,'_execution_design_reference_authorized',False)
            or author.smooth or cp.get('diagnostic_only')is not True or cp.get('state_quality')!='measured_native_state'
            or source.get('steps')!=223 or source.get('physics_ticks')!=22311):
        raise ToolExecutionError('Native E17A223 measured checkpoint required')
    p=ExecutionDesignAuthor(author)
    if p.objects[NAME].get('source_asset',{}).get('sha256')!=TRIANGLE_SHA:raise ToolExecutionError('Original source green triangle required')
    from .execution_design_e17_stand import descriptor,native_readback
    actual=native_readback(author.scene)
    if (p.objects['stand'].get('e17_stand_geometry')!=descriptor()or not actual or actual.get('derived_geometry_sha256')!=descriptor()['derived_geometry_sha256']or actual.get('measured')is not True):raise ToolExecutionError('Original reviewed native stand required')
    state,contacts=p.snapshot()
    if not state['packing_box']['grasp'][1]or any(state[NAME]['grasp']):raise ToolExecutionError('A223 must start from actual wrong-box grip, not an assumed green grip')
    base,rotation=p.frame({'actor':'stand'});base=base.copy();rotation=rotation.copy();saved=state['green_square'];anchor=(rotation.T@(saved['pos']-base),rotation.T@saved['mat'])
    if any(saved['grasp'])or frozenset(('green_square','stand'))not in contacts:raise ToolExecutionError('Previously completed green square must remain supported')
    before=p.c.steps;phase='release_box'
    def guard():
        state,contacts=p.snapshot();pos,rot=p.frame({'actor':'stand'});row=state['green_square']
        if np.linalg.norm(pos-base)>.001 or np.linalg.norm(rot-rotation)>STAND_ROTATION_MATRIX_LIMIT:raise ToolExecutionError('E17 actual stand moved during physical regrasp')
        if (any(row['grasp'])or frozenset(('green_square','stand'))not in contacts or np.linalg.norm(rot.T@(row['pos']-pos)-anchor[0])>.002 or np.linalg.norm(rot.T@row['mat']-anchor[1])>.02):raise ToolExecutionError('E17 completed green square changed during regrasp')
        if any(v['grasp'][0]for v in state.values()):raise ToolExecutionError('E17 idle left hand must remain empty')
        if phase in('push','grasp','lift')and state['packing_box']['grasp'][1]:raise ToolExecutionError('E17 fingers grabbed packing box again, not the green triangle')
    old=author.act;had='act'in author.__dict__;previous=author.__dict__.get('act')
    def guarded(*args,**kwargs):
        if p.c.steps-before>=80:raise ToolExecutionError('E17 physical regrasp exhausted80 public actions')
        guard();result=old(*args,**kwargs);guard();return result
    author.act=guarded
    try:
        p.stage('local-e17a223-release-wrong-box');p.act('right','RELEASE');phase='empty'
        p.move('right',p.tip('right')+[0,0,.040])
        box_base,box_rotation=_frame(p);p.align_empty_chip_axis('right',box_rotation[:,0])
        p.act('right','GRASP');phase='push';guard()
        obj,rails,floor,low,high=_bay(p);lo,hi,center=_bounds(p);offset_lo,offset_hi=_finger_offsets(p)
        inner=np.asarray(obj['inner_size'],float);push=center.copy()
        push[1]=min(float(hi[1]-offset_lo[1]),float(inner[1]-offset_hi[1]-.003))
        push[2]=max(r['pos'][2]+r['size'][2]for r in rails)+.001-offset_lo[2]
        box_base,box_rotation=_frame(p);target=box_base+box_rotation@push
        p.stage('local-e17a223-minimal-divider-clear-push')
        p.move('right',[*target[:2],p.tip('right')[2]]);p.move('right',target)
        for _ in range(10):
            lo,hi,center=_bounds(p)
            if p.held(p.ref(NAME),'right')or(lo[1]>=low+.0005 and hi[1]<=high-.0005):break
            if lo[1]<low-.003:raise ToolExecutionError('Actual triangle nudge overshot its empty bay')
            _,box_rotation=_frame(p);distance=min(.010,max(.003,float(center[1]-(low+high)/2)))
            p.move('right',p.tip('right')-box_rotation[:,1]*distance)
        else:raise ToolExecutionError('Actual triangle did not enter the divider-free bay')
        if not p.held(p.ref(NAME),'right'):
            p.move('right',p.tip('right')+[0,0,.030]);p.act('right','RELEASE');phase='empty'
            obj,_,floor=_tray(p);box_base,box_rotation=_frame(p);pos,rot=p.frame({'actor':NAME})
            # Source E09-proven base pinch; real inner-floor toe clearance is
            # added because this piece has now physically left its raised rail.
            desired=(pos+rot@np.array([0.,-.017320508/3.,0.])-box_base)@box_rotation
            offset_lo,offset_hi=_finger_offsets(p);inner=np.asarray(obj['inner_size'])
            desired=_fit_xy(desired,offset_lo,offset_hi,-inner[0],inner[0],low,high)
            desired[2]=floor+.0025-offset_lo[2];target=box_base+box_rotation@desired
            p.stage('local-e17a223-real-green-grasp');p.move('right',[*target[:2],p.tip('right')[2]]);p.move('right',target)
        phase='grasp'
        from .execution_design_e20_reference import finish_chip_grip
        from .execution_design_segments_e17_e20 import _held_with_contacts
        finish_chip_grip(p,p.ref(NAME),'right');_held_with_contacts(p,NAME,'right');guard()
        initial=np.asarray(p.snapshot()[0][NAME]['pos']).copy();phase='lift';p.stage('local-e17a223-actual-green-short-lift');p.act('right','UP',mm=10.)
        _held_with_contacts(p,NAME,'right');guard();state,_=p.snapshot()
        if float(state[NAME]['pos'][2]-initial[2])<.005 or p.contact(NAME,'packing_box'):raise ToolExecutionError('Green triangle did not actually lift clear of the box')
    finally:
        if had:author.act=previous
        else:del author.act
    return dict(local_completed=True,operations=deepcopy(p.operations),active_actions=p.c.steps-before)
