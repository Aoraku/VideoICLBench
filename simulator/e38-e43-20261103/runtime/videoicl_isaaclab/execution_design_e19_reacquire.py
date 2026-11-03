"""E19C red/water terminal continuation through real public robot actions."""
from copy import deepcopy
import json
import math
import numpy as np
from .author_orientation import _axis_angle
from .realworld_structural_expert import StructuralAuthor
from .realworld_tool_expert import ToolExecutionError
from .execution_design_e19_reference import gravity_seat_red_water,_scope

CAP_SHA='a8d1a023e305cc173e0bda92a4c52f7f2f20731a32894b4fbab2a2669f840c4a'
WATER_SHA='a1063067fb4ff0db03ba5436820756f9149f6eb45b5c9c5973ef5d6274eff71f'
HIGH_GRASP_Z=.0055


def higher_red_cap_ref(tool,ref):
    """Same absolute source point for full C pickup and terminal reacquisition."""
    _scope(tool)
    if tool.spec.get('variant')!='C'or ref.get('actor')!='cap_red':
        raise ValueError('Reviewed C red cap required')
    obj=next(o for o in tool.spec['objects']if o['id']=='cap_red')
    if obj.get('source_asset',{}).get('sha256')!=CAP_SHA:raise ValueError('Original reviewed red-cap source required')
    original=np.asarray(tool.s['structural_grasps']['cap_red']['local'],float)
    local=np.asarray(ref['local'],float);jaw=np.asarray(ref['jaw_axis_local'],float)
    if (not np.allclose(original,[0,0,.003],atol=1e-10,rtol=0)or not np.array_equal(jaw,[0,1,0])
            or not np.allclose(local[:2],original[:2],atol=1e-10,rtol=0)
            or not any(abs(float(local[2])-z)<1e-10 for z in (.003,HIGH_GRASP_Z))):
        raise ValueError('Original reviewed cap grasp and jaw axis required')
    if float(obj['size'][2])<=HIGH_GRASP_Z:raise ValueError('Higher grasp must lie inside the original cap height')
    result=deepcopy(ref);result['local']=[float(original[0]),float(original[1]),HIGH_GRASP_Z]
    return result


def _pose_near(body,expected,label):
    p=np.asarray(expected['pos'],float);r=np.asarray(expected['mat'],float)
    if p.shape!=(3,)or r.shape!=(3,3)or not np.isfinite(np.r_[p,r.ravel()]).all():raise ValueError('Finite terminal '+label+' pose required')
    if np.linalg.norm(np.asarray(body['pos'])-p)>.005 or _axis_angle(r@np.asarray(body['mat']).T)[1]>math.radians(5):
        raise ToolExecutionError('Actual '+label+' differs from terminal fixture')


def run(author,parameters):
    """Reacquire only red/water; original completed pairs are never replayed."""
    p=parameters;t=StructuralAuthor(author);side='left';name='cap_red';bottle='water_bottle'
    _scope(t)
    if (t.task!='E19'or t.spec.get('variant')!='C'or p.get('side')!=side
            or abs(float(p.get('grasp_local_z_m',HIGH_GRASP_Z))-HIGH_GRASP_Z)>1e-10):
        raise ValueError('Reviewed E19C left red-cap higher grasp required')
    if t.objects[name].get('source_asset',{}).get('sha256')!=CAP_SHA or t.objects[bottle].get('source_asset',{}).get('sha256')!=WATER_SHA:
        raise ValueError('Original reviewed red-cap and water-bottle sources required')
    ref=higher_red_cap_ref(t,t.ref(name));original=np.asarray(t.s['structural_grasps'][name]['local'],float);jaw=np.asarray(ref['jaw_axis_local'],float)
    control={'actor':name,'local':deepcopy(t.s['caps'][name]['center_local'])}
    state,contacts=t.snapshot()
    if getattr(author,'carried_payload',None)is not None or any(any(b.get('grasp',[]))for b in state.values()):
        raise ToolExecutionError('Actual empty hands required before red-cap reacquisition')
    _pose_near(state[name],p['expected_source_pose'],'red cap');_pose_near(state[bottle],p['expected_bottle_pose'],'water bottle')
    if frozenset((name,bottle))not in contacts:raise ToolExecutionError('Actual tilted red cap must remain supported by water bottle at entry')
    mouth=t.s['mouths'][bottle];mouth_ref={'actor':bottle,'local':mouth['center_local']}
    cp=t.point(control);bp=t.point(mouth_ref)
    if np.max(abs(cp[:2]-bp[:2]))>.02 or not -.02<float(cp[2]-bp[2])<.025:
        raise ToolExecutionError('Actual cap is outside supported near-mouth reacquisition')
    t.start=t.c.steps;t.limit=int(p.get('action_limit',300))
    if not 1<=t.limit<=3000:raise ValueError('Bounded public segment action budget required')
    anchors={n:np.asarray(b['pos'],float).copy()for n,b in state.items()if n.endswith('_bottle')}
    hold_required=False;acquiring=True;allow_release=False
    log=author.out/'e19-c-terminal-reacquisition.private.jsonl'
    def record(phase,**extra):
        state,contacts=t.snapshot()
        row=dict(phase=phase,local_actions=t.c.steps-t.start,actual_cap_pose={k:np.asarray(state[name][k]).tolist()for k in ('pos','mat')},
            actual_bottle_pose={k:np.asarray(state[bottle][k]).tolist()for k in ('pos','mat')},actual_cap_grasp=list(state[name]['grasp']),**extra)
        with log.open('a')as stream:stream.write(json.dumps(row)+'\n')
    def held():
        state,contacts=t.snapshot()
        return bool(state[name]['grasp'][0]and all(frozenset((name,'left_finger'+str(i)))in contacts for i in (1,2)))
    def guard():
        state,contacts=t.snapshot()
        if any(np.linalg.norm(np.asarray(state[n]['pos'])-anchor)>.002 for n,anchor in anchors.items()):
            raise ToolExecutionError('E19 reacquisition moved an actual bottle')
        if any(frozenset((n,'left_finger'+str(i)))in contacts for n in anchors for i in (1,2)):
            raise ToolExecutionError('E19 reacquisition fingers contacted an actual bottle')
        if any(b.get('grasp',[False,False])[1]or(n!=name and b.get('grasp',[False,False])[0])for n,b in state.items()):
            raise ToolExecutionError('E19 reacquisition acquired an unexpected object or peer hold')
        if acquiring and not held()and frozenset((name,bottle))not in contacts:
            raise ToolExecutionError('E19 supported cap fell before actual bilateral reacquisition')
        if hold_required and not held():raise ToolExecutionError('E19 actual red-cap bilateral grip lost during lift/alignment')
    original_act=t.act
    def guarded_act(*args,**kwargs):
        nonlocal hold_required
        guard();token=args[1]if len(args)>1 else kwargs.get('token','STILL')
        if token=='RELEASE'and hold_required:
            if not allow_release:raise ToolExecutionError('E19 premature release before measured placement')
            hold_required=False
        result=original_act(*args,**kwargs);guard();return result
    # Scope this first-failure guard to the new ToolAuthor instance. Every
    # inherited public move/release still invokes the original public act.
    t.act=guarded_act
    def move_target(target_fn,tolerance=.0015,near_cap=False):
        history=[]
        for _ in range(100):
            guard();target=np.asarray(target_fn(),float);tip=t.tip(side);delta=target-tip
            if target.shape!=(3,)or not np.isfinite(target).all():raise ValueError('Actual finite reacquisition waypoint required')
            if np.max(abs(delta))<=tolerance:return
            history.append(tip.copy())
            if len(history)>12 and max(np.linalg.norm(x-tip)for x in history[-12:])<.0003:raise ToolExecutionError('E19 actual reacquisition waypoint stalled')
            k=int(np.argmax(abs(delta)));token=(('FWD','BACK'),('LEFT','RIGHT'),('UP','DOWN'))[k][int(delta[k]<0)]
            step=1. if near_cap and float(tip[2]-target[2])<.025 else 4.
            t.act(side,token,mm=min(step,max(.5,abs(delta[k])*1000)))
        raise ToolExecutionError('E19 actual reacquisition waypoint unreachable')
    try:
        record('terminal_entry',original_grasp_local=original.tolist(),higher_grasp_local=ref['local'],source_jaw_axis_local=jaw.tolist())
        t.stage('e19-c-reacquire-open-above-supported-red');t.act(side,'RELEASE')
        height=max(float(t.tip(side)[2]),float(t.point(ref)[2])+.05,float(t.point(mouth_ref)[2])+.07)
        move_target(lambda:np.r_[t.tip(side)[:2],height])
        t.stage('e19-c-reacquire-align-empty-jaw')
        for _ in range(24):
            guard();state,_=t.snapshot();desired=np.asarray(state[name]['mat'])@jaw;desired/=np.linalg.norm(desired)
            geometry=author.finger_geometry(side)
            if geometry.get('source')!='actual_collision_mesh_current_body_pose'or len(geometry.get('fingers',[]))!=2:
                raise ValueError('Actual bilateral finger geometry required for red-cap reacquisition')
            fingers=geometry['fingers'];actual=np.asarray(fingers[0]['body_origin_task_m'])-np.asarray(fingers[1]['body_origin_task_m']);actual/=np.linalg.norm(actual)
            if actual@desired<0:desired=-desired
            angle=math.acos(float(np.clip(actual@desired,-1,1)))
            if angle<math.radians(3):break
            axis=np.cross(actual,desired);axis/=np.linalg.norm(axis);k=int(np.argmax(abs(axis)))
            token=(('ROLL_LEFT','ROLL_RIGHT'),('PITCH_UP','PITCH_DOWN'),('ROTATE_CCW','ROTATE_CW'))[k][int(axis[k]<0)]
            t.act(side,token,degrees=min(5.,max(.5,abs(math.degrees(angle*axis[k])))))
        else:raise ToolExecutionError('E19 actual empty jaw could not align with original source axis')
        t.stage('e19-c-reacquire-higher-source-point')
        move_target(lambda:np.r_[t.point(ref)[:2],height])
        move_target(lambda:t.point(ref),near_cap=True)
        for _ in range(3):
            t.act(side,'GRASP')
            if held():break
        else:raise ToolExecutionError('E19 higher point lacks actual bilateral red-cap grip')
        hold_required=True;acquiring=False;author.carried_payload=(name,side)
        record('actual_higher_point_reacquired')
        t.stage('e19-c-reacquire-lift-clear-of-mouth')
        move_target(lambda:t.tip(side)+np.array([0.,0.,max(0.,float(t.point(mouth_ref)[2])+.035-float(t.point(control)[2]))]))
        guard();geometry=author.finger_geometry(side);cp=t.point(control);bp=t.point(mouth_ref)
        if cp[2]<bp[2]+.025 or geometry['lowest_z_task_m']<bp[2]+.008:
            raise ToolExecutionError('E19 actual reacquired cap lacks lift/rotation clearance')
        record('actual_red_cap_lifted')
        allow_release=True
        gravity_seat_red_water(t,name,ref,side,control,bottle,entry_phase='alignment')
        guard();state,_=t.snapshot()
        if any(state[name]['grasp']):raise ToolExecutionError('E19 actual reacquired cap did not release')
        author.carried_payload=None;record('actual_reacquisition_placement_complete')
        return list(t.operations)
    finally:
        t.act=original_act
