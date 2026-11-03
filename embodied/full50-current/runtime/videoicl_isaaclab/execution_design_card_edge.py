"""Private E50 thin-card acquire through actual public edge pushing/pinching."""
import json
import math
import numpy as np
from .execution_design import REVISION_V3,source_sha256
from .execution_design_thin_edge import (table_bounds_task,material_collision_points_task,
    actual_finger_points_task,trailing_edge_push_pose,card_side_pinch_plan,check_under_table_clearance,seek_actual_contact)
from .realworld_tool_expert import ToolExecutionError,_axis_rotation


def acquire_card(p,ref,side):
    import os
    if os.environ.get('VIC_E50_PUSH_ONLY')=='1':return acquire_card_by_edge(p,ref,side)
    from .execution_design_card_direct import acquire_direct_card
    return acquire_direct_card(p,ref,side)


def acquire_card_by_edge(p,ref,side):
    a=p.a;design=p.spec.get('execution_design',{})
    if p.task!='E50' or design.get('revision')!=REVISION_V3 or design.get('source_sha256')!=source_sha256(REVISION_V3) or not a.control_report.get('engineering_reference_only'):
        raise ValueError('Explicit E50 v3 engineering reference required')
    if a.scene.embodiment.name!='franka':raise ValueError('Measured Panda side pinch required')
    from .execution_design_e33_grasp import actual_mesh
    from .execution_design_cutlery_grasp import orient
    bounds=table_bounds_task(a.scene);up=np.array([0.,0.,1.])
    material=material_collision_points_task(p,ref);position,rotation=p.frame(ref)
    current=a.tcp_rotation_task(side);tcp=p.tip(side)
    local_meshes=[(actual_mesh(a,side,name)-tcp)@current for name in a.scene.embodiment.fingers]
    path=a.out/'card-edge-public.private.jsonl'
    def log(phase,**values):
        with path.open('a')as f:f.write(json.dumps(dict(phase=phase,step=p.c.steps,actor=ref['actor'],**values))+'\n')
    from .execution_design_drawer_ik_probe import inspect
    candidates=[]
    for sign in (1.,-1.):
        outward=np.array([sign,0.,0.])
        for jaw_sign in (1.,-1.):
            jaw=up*jaw_sign;target_rotation=np.column_stack((-np.cross(jaw,outward),jaw,-outward))
            try:plan=card_side_pinch_plan(material,position,[m@target_rotation.T for m in local_meshes],bounds,outward=outward)
            except ValueError as exc:
                log('rejected-edge-geometry',outward=outward.tolist(),jaw_sign=jaw_sign,error=str(exc));continue
            reach=inspect(a,p.c,side,[dict(position=plan['target_grasp'].tolist(),rotation=target_rotation.tolist())])[0]
            log('side-pinch-kinematic-precheck',outward=outward.tolist(),jaw_sign=jaw_sign,result=reach)
            if reach['kinematically_reachable']:candidates.append((float(np.linalg.norm(plan['translation'])),outward,target_rotation,plan))
    if not candidates:raise ToolExecutionError('No measured supported table-edge card pinch in actual joint workspace')
    _,outward,target_rotation,plan=min(candidates,key=lambda row:row[0])
    token='FWD'if outward[0]>0 else'BACK'
    local_grasp=rotation.T@(plan['grasp']-position);grasp=dict(ref,local=local_grasp.tolist())
    log('plan',outward=outward.tolist(),**{k:v.tolist()if isinstance(v,np.ndarray)else v for k,v in plan.items()})
    def contact_geometry(phase):
        from pxr import Usd,UsdPhysics
        import omni.usd
        stage=omni.usd.get_context().get_stage();body=stage.GetPrimAtPath(f"{a.scene.root_path}/Props/{ref['actor']}")
        colliders=[]
        bodies=[body]+[stage.GetPrimAtPath(f'{a.scene.root_path}/{side}_robot/{name}')for name in a.scene.embodiment.fingers]
        for rigid in bodies:
            for prim in Usd.PrimRange(rigid,Usd.TraverseInstanceProxies()):
                if prim.HasAPI(UsdPhysics.CollisionAPI):
                    attrs={key:prim.GetAttribute(key).Get()for key in ('physics:collisionEnabled','physics:approximation','physxCollision:contactOffset','physxCollision:restOffset')}
                    colliders.append(dict(path=str(prim.GetPath()),type=prim.GetTypeName(),attributes=attrs))
        state,contacts=p.snapshot()
        log(phase,colliders=colliders,material_vertices=material_collision_points_task(p,ref).tolist(),
            fingers=[actual_mesh(a,side,name).tolist()for name in a.scene.embodiment.fingers],
            finger_geometry=a.finger_geometry(side),tcp=p.tip(side).tolist(),
            actor_position=state[ref['actor']]['pos'].tolist(),actor_rotation=state[ref['actor']]['mat'].tolist(),
            actual_contacts=[list(pair)for pair in contacts if ref['actor']in pair],
            actual_contact_forces=[dict(pair=sorted(pair),force_n=float(force))for pair,force in p.c.contact_forces.items()if ref['actor']in pair],
            contact_adapter=a.scene.contact_diagnostics())
    def contact():return any(p.contact(ref['actor'],f'{side}_finger{i}')for i in(1,2))
    def supported():return p.contact(ref['actor'],'table')
    p.stage('card-edge-trailing-push');p.act(side,'GRASP')
    # Put one actual leading toe on the card centreline. The parallel-to-edge
    # v13/v17 pair touched with one off-centre finger and yawed the card.
    current_push=a.tcp_rotation_task(side);push_tip=p.tip(side)
    raw_fingers=actual_finger_points_task(a,side);push_candidates=[]
    from .execution_design_card_push_surface import leading_surface
    for yaw,roll in ((math.pi/2,math.radians(20)),(-math.pi/2,math.radians(30)),(-math.pi/2,math.radians(40))):
        direction_turn=_axis_rotation([0,0,1],0. if outward[0]>0 else math.pi)
        proposed=direction_turn@_axis_rotation([1.,0.,0.],roll)@_axis_rotation([0.,0.,1.],yaw)@current_push
        transformed=(raw_fingers-push_tip)@current_push@proposed.T+push_tip
        start,receipt=trailing_edge_push_pose(material_collision_points_task(p,ref),transformed,push_tip,outward,bounds['top'],clearance=.00002,center_leading_toe=True)
        shifted=(transformed-push_tip)+start
        try:face=leading_surface([shifted[:len(shifted)//2],shifted[len(shifted)//2:]],bounds['top']+.000175,outward)
        except ValueError as exc:
            log('pusher-face-rejected',yaw_rad=yaw,roll_rad=roll,error=str(exc));continue
        palm=(actual_mesh(a,side,'panda_hand')-push_tip)@current_push@proposed.T+start
        if float(palm[:,2].min())<bounds['top']+.00002:
            log('pusher-palm-rejected',yaw_rad=yaw,roll_rad=roll,lowest_palm_z=float(palm[:,2].min()));continue
        reach=[inspect(a,p.c,side,[dict(position=point,rotation=proposed.tolist())])[0]for point in(push_tip.tolist(),start.tolist())]
        log('centred-horizontal-face-ik',yaw_rad=yaw,roll_rad=roll,contact_start=start.tolist(),actual_leading_face=face,receipt=receipt,ik=reach)
        if all(row['kinematically_reachable']and row['minimum_joint_margin_rad']>.05 for row in reach):
            from .execution_design_clip_handover import public_route_poses
            from .execution_design_local_pose_path import inspect_local_pose_path
            route=dict(rotation=proposed.tolist(),pregrasp=start.tolist(),position=start.tolist(),height=max(bounds['top']+.14,float(push_tip[2]))+.008)
            continuous=inspect_local_pose_path(a,p.c,side,public_route_poses(push_tip,current_push,route),minimum_joint_margin_rad=.05)
            log('centred-horizontal-face-continuous-route',yaw_rad=yaw,roll_rad=roll,continuous_path=continuous)
            if continuous['feasible']:push_candidates.append(proposed)
    if not push_candidates:raise ToolExecutionError('No measured centred-leading-toe push pose in actual joint workspace')
    orient(a,side,push_candidates[0])
    def seat():
        points=material_collision_points_task(p,ref)
        start,receipt=trailing_edge_push_pose(points,actual_finger_points_task(a,side),p.tip(side),outward,bounds['top'],clearance=.00002,center_leading_toe=True)
        log('seat',**receipt)
        z=max(float(p.tip(side)[2])+.008,float(start[2])+.012)
        p.move(side,[*p.tip(side)[:2],z]);p.move(side,[*start[:2],z]);p.move(side,start,tolerance=.0003)
        contact_geometry('seated-contact-geometry')
        sought=seek_actual_contact(contact,lambda:p.act(side,token,mm=.5),12)
        if sought is not None:
            log('actual-trailing-contact',seek_actions=sought)
            return
        contact_geometry('missing-contact-geometry')
        raise ToolExecutionError('Actual card trailing-edge contact absent')
    p.move(side,[*tcp[:2],max(bounds['top']+.14,float(tcp[2]))]);seat()
    push_initial=p.point(grasp).copy()
    history=[];reseats=0
    for _ in range(900):
        remaining=float((plan['target_grasp']-p.point(grasp))@outward)
        if __import__('os').environ.get('VIC_E50_PUSH_ONLY')=='1'and float((p.point(grasp)-push_initial)@outward)>=.030:
            contact_geometry('actual30mm-horizontal-push')
            raise ToolExecutionError('Actual30mm card push diagnostic only; not whole task acceptance')
        if remaining<=.001:break
        if not supported():raise ToolExecutionError('Card lost real table support while exposing edge')
        if not contact():
            reseats+=1
            if reseats>120:raise ToolExecutionError('Bounded card contact reacquisition exhausted')
            seat()
        low=float(a.finger_geometry(side)['lowest_z_task_m'])
        if low>bounds['top']+.00008:p.act(side,'DOWN',mm=min(.5,(low-bounds['top']-.00002)*1000))
        p.act(side,token,mm=min(2.,remaining*1000))
        progress=float(p.point(grasp)@outward);history.append(progress)
        log('push',actual_grasp=p.point(grasp).tolist(),support=supported(),finger_contact=contact())
        if len(history)>=16 and max(history[-16:])-min(history[-16:])<.0005:
            raise ToolExecutionError('Card fails to advance under real trailing-edge contact')
    else:raise ToolExecutionError('Bounded real card edge slide exhausted')
    p.act(side,'UP',mm=12.);p.act(side,'RELEASE')
    point=p.point(grasp);outside=point+outward*.09;outside[2]=max(p.clearance,float(p.tip(side)[2]))
    p.move(side,[*p.tip(side)[:2],outside[2]]);p.move(side,outside)
    orient(a,side,target_rotation)
    point=p.point(grasp)
    check_under_table_clearance(point,p.tip(side),a.finger_geometry(side),bounds,0,float(outward[0]))
    near=point+outward*.06;p.move(side,near);p.move(side,point,tolerance=.0008)
    stable=0
    for _ in range(5):
        p.act(side,'GRASP');stable=stable+1 if p.held(ref,side)else 0
        if stable>=3:break
    else:raise ToolExecutionError('Card lacks stable actual bilateral finger contact')
    log('actual-side-pinch',held=True,actual_grasp=p.point(grasp).tolist())
