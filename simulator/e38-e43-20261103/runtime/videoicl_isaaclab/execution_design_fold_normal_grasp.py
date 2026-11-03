"""Continue a real raised E44 leaf through normal pinch and public folding."""
import json,math
import numpy as np
from .realworld_tool_expert import ToolExecutionError,_axis_rotation


def complete(p,clearance_target_z=None,grasp_side='left',face_normal_only=False):
    from .execution_design_native_finger_mesh import measured_mesh
    from .execution_design_e33_grasp import actual_mesh
    from .execution_design_clip_grasp import solve_finger_placement,convex_meshes_clear
    from .execution_design_thin_edge import table_bounds_task,mechanism_collision_points_task
    from .execution_design_thin_motion import checked_move
    from .execution_design_cutlery_grasp import orient
    from .execution_design_local_pose_path import inspect_local_pose_path
    from .engineering_thin_suffix import save_stage
    if grasp_side not in('left','right'):raise ValueError('Named physical folding hand required')
    a=p.a;s=p.s['crease'];g=s['expert'];base=dict(mechanism=s['mechanism'],**g['base_press']);fold=dict(mechanism=s['mechanism'],**g['fold_grasp']);side=grasp_side;support='right'if side=='left'else'left';floor=table_bounds_task(a.scene)['top']
    def angle():return math.degrees(math.acos(float(np.clip(p.frame(base)[1][:,2]@p.frame(fold)[1][:,2],-1,1))))
    need_press=[False]
    def table_guard():
        guide=p.s.get('execution_design_fold_fixture',{})
        guided=guide.get('single_pusher',False)and any(p.contact(base['contact_body'],n)for n in guide.get('base_guide_contact_ids',[]))
        if not p.contact(base['contact_body'],'table')and not guided:
            raise ToolExecutionError('Normal fold lost real base table/guide support')
    def guard():
        table_guard()
        if not need_press[0]:return
        if any(p.contact(base['contact_body'],f'{support}_finger{i}')for i in(1,2)):return
        previous=a.stage
        p.stage('E44-normal-fold-reseat-base')
        bp,br=p.frame(base);point=bp+br@np.array([-.025,.075 if support=='left'else-.075,.0006])
        fingers=np.concatenate([actual_mesh(a,support,n)for n in a.scene.embodiment.fingers]);low=fingers[fingers[:,2]<=fingers[:,2].min()+.0001].mean(0)
        target=p.tip(support)+point-low;target[2]-=.0001
        checked_move(p,support,target,table_guard,tolerance=.002)
        for _ in range(8):
            if any(p.contact(base['contact_body'],f'{support}_finger{i}')for i in(1,2)):
                p.stage(previous);return
            p.act(support,'DOWN',mm=.5)
            if not p.contact(base['contact_body'],'table'):
                raise ToolExecutionError('Normal fold base reseating lost real table support')
            if any(p.contact(base['contact_body'],f'{support}_finger{i}')for i in(1,2)):
                p.stage(previous);return
        raise ToolExecutionError('Normal fold could not re-seat actual base pressing contact')
    def log(phase,**values):
        with(a.out/'fold-normal-pinch.private.jsonl').open('a')as f:f.write(json.dumps(dict(phase=phase,step=p.c.steps,fold_angle_deg=angle(),**values))+'\n')
    if angle()<30. or p.point(fold)[2]<floor+.045:
        raise ToolExecutionError('Normal fold requires the actually raised source leaf')
    def geometry():
        tcp=p.tip(side);rotation=np.asarray(a.tcp_rotation_task(side));names=('panda_hand',*a.scene.embodiment.fingers)
        meshes=[measured_mesh(a,side,name)-tcp for name in names]
        source=[actual_mesh(a,side,name)-tcp for name in a.scene.embodiment.fingers]
        jaw=rotation[:,1].copy()
        if jaw@(meshes[1].mean(0)-meshes[2].mean(0))<0:jaw=-jaw
        return tcp,rotation,meshes,source,jaw
    # Release the trailing edge horizontally, then leave through the side
    # lane before lifting into the other forearm. A table-supported base and
    # passive rail suffice during EMPTY staging; re-seat press before loading.
    p.stage('E44-normal-pinch-empty-side-clear')
    if any(p.contact(base['contact_body'],f'{side}_finger{i}')for i in(1,2)):
        p.act(side,'BACK',mm=8.);table_guard()
    checked_move(p,side,[float(p.tip(side)[0]),.15 if side=='left'else-.15,float(p.tip(side)[2])],guard,tolerance=.004)
    checked_move(p,side,[*p.tip(side)[:2],.92],guard,tolerance=.006);p.act(side,'RELEASE')
    need_press[0]=True;guard()
    fp,fr=p.frame(fold);grasp=dict(fold,local=[.1,.05 if side=='left'else-.05,0.]);point=p.point(grasp);normal=fr[:,2];tangent=fr[:,0]
    tcp,rotation,meshes,source,jaw=geometry();local=[m@rotation for m in meshes];source_local=[m@rotation for m in source]
    choices=[]
    # A face-normal wrist points the palm outside Panda reach. Screen the
    # table-clear oblique public wrist first; actual bilateral grip remains
    # mandatory after the achieved-pose placement is recomputed below.
    rotations=[]
    for pitch in (() if face_normal_only else (-40.,-20.)):
        turn=_axis_rotation(np.array([0.,1.,0.]),math.radians(pitch))
        along=turn@np.array([0.,0.,-1.]);closing=turn@np.array([1.,0.,0.])
        rotations.append(np.column_stack((np.cross(closing,along),closing,along)))
    for sign in(-1.,1.):
        along=-tangent;rotations.append(np.column_stack((np.cross(sign*normal,along),sign*normal,along)))
    for target in rotations:
        mapped=[m@target.T for m in local];ss=[m@target.T for m in source_local];axis=target@rotation.T@jaw
        points=np.array([point-normal*.0006,point+normal*.0006])
        for plan in solve_finger_placement(points,mapped[0],mapped[1:],axis,floor,maximum_closure=.04,margin=.0001,pad_depth_m=.0015,preferred_translation=point):
            goal=np.asarray(plan['tcp_translation']);closure=plan['closure_m']
            if not all(min((m+goal)[:,2].min(),(m+goal+sgn*closure*axis)[:,2].min())>=floor+.0001-1e-9 for m,sgn in zip(ss,(-1.,1.))):continue
            h=float(tcp[2]);near=goal+np.array([-.025,0.,.025]);high=max(float(near[2]),.86)
            retreat=np.array([-.1,.15 if side=='left'else-.15,.85])
            poses=[dict(position=retreat.tolist(),rotation=rotation.tolist()),dict(position=retreat.tolist(),rotation=target.tolist()),dict(position=[*near[:2],high],rotation=target.tolist()),dict(position=near.tolist(),rotation=target.tolist()),dict(position=goal.tolist(),rotation=target.tolist())]
            path=inspect_local_pose_path(a,p.c,side,poses,minimum_joint_margin_rad=.015,max_rotation_step_rad=math.radians(2))
            log('normal-pinch-candidate',point=point.tolist(),rotation=target.tolist(),plan=plan,native_ik=path)
            if path['feasible']:choices.append((target,plan,near,h,high,retreat));break
        if choices:break
    if not choices:raise ToolExecutionError('Raised source leaf has no table-clear native normal-pinch route')
    target,plan,near,h,high,retreat=choices[0]
    p.stage('E44-normal-pinch-empty-orient');checked_move(p,side,retreat,guard,tolerance=.004);orient(a,side,target);guard()
    checked_move(p,side,[*near[:2],high],guard,tolerance=.004);checked_move(p,side,near,guard,tolerance=.002)
    # Recompute against achieved R and live leaf, rather than trusting a
    # candidate at a nearby desired pose. Source+native floor sweep retained.
    tcp,rotation,meshes,source,jaw=geometry();fp,fr=p.frame(fold);point=p.point(grasp);normal=fr[:,2];points=np.array([point-normal*.0006,point+normal*.0006])
    candidates=solve_finger_placement(points,meshes[0],meshes[1:],jaw,floor,maximum_closure=.04,margin=.0001,pad_depth_m=.0015,preferred_translation=tcp)
    if not candidates:raise ToolExecutionError('Actual wrist no longer fits both real paper faces')
    goal=np.asarray(candidates[0]['tcp_translation']);closure=candidates[0]['closure_m']
    if not all(min((m+goal)[:,2].min(),(m+goal+sgn*closure*jaw)[:,2].min())>=floor+.0001-1e-9 for m,sgn in zip(source,(-1.,1.))):raise ToolExecutionError('Actual normal-pinch source sweep crosses table')
    p.stage('E44-normal-pinch-actual-approach');checked_move(p,side,goal,guard,tolerance=.0003)
    for _ in range(4):
        p.stage('E44-normal-pinch-real-grasp');p.act(side,'GRASP');guard()
        if p.held(fold,side):break
    else:raise ToolExecutionError('Actual paper normal pinch lacks two real opposite-finger contacts')
    save_stage(a,'actual-leaf-normal-grip',dict(angle_deg=angle()))
    initial=a.tcp_rotation_task(side).copy();bp,br=p.frame(base);hinge=bp+br@np.asarray(g['hinge_point_local']);axis=br@np.asarray(g['axis_local']);vector=p.point(grasp)-hinge;start=angle();desired=(90.,60.,115.)[p.index]
    def loaded():p.require_held(fold,side);guard()
    p.stage('E44-real-normal-grip-fold')
    for goal_angle in np.arange(start+1.,desired+1.,1.):
        loaded();turn=_axis_rotation(axis,math.radians(min(goal_angle,desired)-start)*float(g['direction']))
        p.move_point(side,grasp,hinge+turn@vector,loaded,tolerance=.0007);loaded();orient(a,side,turn@initial);loaded()
        log('actual-contact-fold-step',requested_angle_deg=min(float(goal_angle),desired),actual_bilateral=p.held(fold,side))
    if abs(angle()-desired)>4.:raise ToolExecutionError('Actual normal-gripped paper missed source target angle')
    p.release(fold,side);p.move(side,p.tip(side)+tangent*.06)
    p.move(support,p.tip(support)+[0,0,.07]);p.wait(2)
    _,contacts=p.snapshot();fixture=p.s['execution_design_fold_fixture']['fixture_contact_ids']
    if any(fold['contact_body']in pair and any(n in pair for n in fixture)for pair in contacts):raise ToolExecutionError('Final folded leaf still depends on rail support')
    log('released-source-target',released_angle_deg=angle(),base_table=p.contact(base['contact_body'],'table'))
    return dict(physical_fold_route_finished=True,measured_angle_deg=angle(),native_whole_task_success_not_asserted=True)
