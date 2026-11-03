"""E34 private reference: real pad capture, handle placement and short withdrawal."""
import json,math
import numpy as np
from .execution_design import REVISION_V3


def scope(a):
    if not (getattr(a,'_execution_design_reference_authorized',False)
            and a.scene.spec['id']=='E34'
            and a.scene.spec.get('execution_design',{}).get('revision')==REVISION_V3):
        raise ValueError('Explicit E34 v3 engineering reference required')


def pad_capture(point,meshes,floor):
    """An attempted pinch requires real material between both open pad sections."""
    from .execution_design_cutlery_grasp import plane_section
    point=np.asarray(point,float);meshes=[np.asarray(m,float)for m in meshes]
    if len(meshes)!=2 or not np.isfinite(point).all():raise ValueError('Two actual pad meshes required')
    if any(m[:,2].min()<floor-.0003 or point[2]<m[:,2].min()+.001 or point[2]>m[:,2].max()-.001 for m in meshes):return False
    try:sections=[plane_section(m,point[2])for m in meshes]
    except ValueError:return False
    centers=[(s.min(0)+s.max(0))/2 for s in sections]
    jaw=centers[1][:2]-centers[0][:2];length=float(np.linalg.norm(jaw))
    if length<.005:return False
    jaw/=length;across=np.array([-jaw[1],jaw[0]])
    if not all((s[:,:2]@across).min()+.0005<=point[:2]@across<=(s[:,:2]@across).max()-.0005 for s in sections):return False
    return bool((sections[0][:,:2]@jaw).max()+.0005<point[:2]@jaw<(sections[1][:,:2]@jaw).min()-.0005)


def approach(a,side,obj,target):
    scope(a)
    from .execution_design_e33_grasp import actual_mesh
    from .execution_design_thin_edge import table_bounds_task
    floor=table_bounds_task(a.scene)['top'];target=np.asarray(target,float);history=[]
    labels=(('FWD','BACK'),('LEFT','RIGHT'),('UP','DOWN'))
    signs=getattr(a,'generated_axis_signs',{}).get(side,{})
    for _ in range(160):
        state,_=a.c.snapshot();body=state[obj['id']]
        point=np.asarray(body['pos'])+np.asarray(body['mat'])@np.asarray(obj['grasp_point_local'])
        meshes=[actual_mesh(a,side,n)for n in a.scene.embodiment.fingers]
        if pad_capture(point,meshes,floor):
            with (a.out/'e34-material-approach.private.jsonl').open('a')as f:
                f.write(json.dumps(dict(step=a.c.steps,object=obj['id'],point=point.tolist(),tcp=a.tip(side).tolist(),actual_open_pad_capture=True,native_grasp_verified=False))+'\n')
            return
        error=target-np.asarray(a.tip(side));axis=int(np.argmax(abs(error)))
        history.append(float(np.linalg.norm(error)))
        if max(abs(error))<.0005 or len(history)>=32 and min(history[-32:-24])-min(history[-8:])<.0005:
            raise RuntimeError('E34 actual material did not enter opposing pad sections')
        positive=1 if error[axis]>0 else -1
        token=labels[axis][0 if positive==signs.get(axis,1) else 1]
        a.act(token if side=='left'else'STILL',token if side=='right'else'STILL',min(20.,max(.5,abs(error[axis])*1000)))
    raise RuntimeError('E34 material approach action bound exhausted')


def level_handle(a,name,side):
    scope(a)
    handle=np.asarray(a.scene.spec['semantic']['handle_points'][name]);labels=(('ROLL_LEFT','ROLL_RIGHT'),('PITCH_UP','PITCH_DOWN'),('ROTATE_CCW','ROTATE_CW'))
    errors=[]
    for _ in range(70):
        state,_=a.c.snapshot();body=state[name]
        if a.carried_payload!=(name,side) or not body['grasp'][0 if side=='left'else 1]:raise RuntimeError('E34 leveling requires true cutlery grasp')
        vector=np.asarray(body['mat'])@handle;wanted=vector.copy();wanted[2]=0
        if np.linalg.norm(wanted)<.001:raise RuntimeError('E34 handle has no planar direction')
        if abs(vector[2])<=.003:return
        u=vector/np.linalg.norm(vector);v=wanted/np.linalg.norm(wanted);axis=np.cross(u,v);angle=math.acos(np.clip(float(u@v),-1,1));axis/=np.linalg.norm(axis)
        delta=axis*angle;i=int(np.argmax(abs(delta)));token=labels[i][int(delta[i]<0)]
        errors.append(abs(float(vector[2])))
        if len(errors)>=20 and min(errors[-20:-10])-min(errors[-10:])<.0002:raise RuntimeError('E34 actual handle leveling stalled')
        a.act(token if side=='left'else'STILL',token if side=='right'else'STILL',rotation_deg=min(8.,max(4.,abs(math.degrees(delta[i])))))
        # Each physical move remains above the measured table and container.
        state,_=a.c.snapshot();obj=next(o for o in a.scene.spec['objects']if o['id']==name);b=state[name]
        bottom=float(np.asarray(b['pos'])[2]-(np.abs(b['mat'])@np.asarray(obj['size']))[2])
        tops=[.8]
        for obstacle in a.scene.spec['objects']:
            if obstacle['id']==name:continue
            other=state[obstacle['id']]
            center=np.asarray(other['pos'])+np.asarray(other['mat'])@np.asarray(obstacle.get('local_bounds_center',[0,0,0]))
            half=np.abs(other['mat'])@np.asarray(obstacle['size']);tops.append(float(center[2]+half[2]))
        if min(bottom,float(a.finger_geometry(side)['lowest_z_task_m']))<max(tops)+.01:raise RuntimeError('E34 leveling lost measured table clearance')
    raise RuntimeError('E34 handle leveling action bound exhausted')


def placement(a,name,side,target):
    scope(a);state,_=a.c.snapshot();s=a.scene.spec['semantic'];tray=state[s['container']];body=state[name]
    bounds=s['compartment_bounds_local'];local=(np.asarray(bounds['lower'])+np.asarray(bounds['upper']))/2
    obj=next(o for o in a.scene.spec['objects']if o['id']==name)
    handle=np.asarray(body['pos'])+np.asarray(body['mat'])@np.asarray(s['handle_points'][name]);offset=np.asarray(a.tip(side))-handle
    support_choice=None
    if a.scene.spec.get('variant')in('B','C')and name==s['selected']:
        raw=a.scene.objects[name].root_physx_view.get_coms()
        if hasattr(raw,'detach'):raw=raw.detach().cpu().numpy()
        com_local=np.asarray(raw,float).reshape(-1,7)
        if com_local.shape!=(1,7)or not np.isfinite(com_local).all():raise ValueError('One measured native utensil COM required')
        actual_com=np.asarray(body['pos'])+np.asarray(body['mat'])@com_local[0,:3]
        relative=(actual_com-handle)@np.asarray(tray['mat'])
        local[:2]=supported_handle_xy(bounds['lower'],bounds['upper'],relative[:2])
        support_choice=dict(actual_com_task=actual_com.tolist(),actual_com_to_handle_tray_xy=relative[:2].tolist(),
            chosen_handle_cell_xy=local[:2].tolist(),source_cell_bounds_unchanged=True)
    wanted=np.asarray(tray['pos'])+np.asarray(tray['mat'])@local
    half=float((np.abs(body['mat'])@np.asarray(obj['size']))[2]);handle_offset_z=float(handle[2]-body['pos'][2])
    # Tray's local origin is the measured interior support plane in E34.
    wanted[2]=float(tray['pos'][2])+half+handle_offset_z+.003
    if a.scene.spec.get('variant')=='B'and name=='spoon':
        # The source tray root is at its bounding-box centre, not its inner
        # support surface. Use actual cooked material for both support and
        # payload height; the original handle-cell bounds still apply below.
        from types import SimpleNamespace
        from .execution_design_branch_geometry import collision_parts_task
        from .execution_design_e34b_support import vertical_support_z,supported_handle_z
        def frame(ref):
            value=a.c.snapshot()[0][ref['actor']]
            return np.asarray(value['pos']),np.asarray(value['mat'])
        policy=SimpleNamespace(a=a,frame=frame)
        payload_parts=collision_parts_task(policy,name)
        tray_parts=collision_parts_task(policy,s['container'])
        desired_com=wanted+(actual_com-handle)
        surface=vertical_support_z(tray_parts,desired_com[:2])
        proposed=supported_handle_z(handle,payload_parts,surface)
        support_choice.update(actual_tray_support_z=surface,
            support_ray_com_xy=desired_com[:2].tolist(),
            actual_payload_lowest_z=min(float(p[:,2].min())for p in payload_parts),
            coarse_root_height_proposal_z=float(wanted[2]),
            actual_material_handle_proposal_z=proposed,
            source='actual_enabled_native_convex_material')
        wanted[2]=proposed
    if not bounds['lower'][2]-.003<=wanted[2]-tray['pos'][2]<=bounds['upper'][2]+.003:raise RuntimeError('E34 held handle height cannot fit compartment')
    result=wanted+offset
    with (a.out/'e34-handle-placement.private.jsonl').open('a')as f:f.write(json.dumps(dict(step=a.c.steps,object=name,actual_handle=handle.tolist(),desired_handle=wanted.tolist(),tcp_goal=result.tolist(),support_choice=support_choice,native_placement_verified=False))+'\n')
    return result


def supported_handle_xy(lower,upper,com_to_handle):
    """Choose inside the original cell while keeping mass toward its support."""
    lo,hi,delta=np.asarray(lower,float)[:2],np.asarray(upper,float)[:2],np.asarray(com_to_handle,float)
    if delta.shape!=(2,)or not np.isfinite(np.r_[lo,hi,delta]).all()or np.any(hi-lo<=.012):
        raise ValueError('Measured COM offset and nonempty original cell required')
    return np.clip((lo+hi)/2-delta,lo+.006,hi-.006)


def retreat(a,side):
    scope(a);start=np.asarray(a.tip(side)).copy();sign=1 if side=='left'else -1
    token='LEFT' if sign==getattr(a,'generated_axis_signs',{}).get(side,{}).get(1,1) else 'RIGHT'
    for _ in range(30):
        state,_=a.c.snapshot()
        if any(any(b['grasp'])for b in state.values()):raise RuntimeError('E34 retreat requires actual release')
        if sign*(np.asarray(a.tip(side))[1]-start[1])>=.12:return
        a.act(token if side=='left'else'STILL',token if side=='right'else'STILL',20.)
    raise RuntimeError('E34 empty hand failed actual12cm withdrawal')
