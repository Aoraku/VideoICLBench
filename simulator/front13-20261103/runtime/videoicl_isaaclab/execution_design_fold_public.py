"""E44 engineering route: real base sliding, side pinch, contact-driven fold.

Only existing public translations/rotations/gripper actions; no pose, joint,
constraint, attachment, evaluator or initial-layout writes.
"""
import json,math
from pathlib import Path
import numpy as np
from .execution_design import REVISION_V3,source_sha256
from .execution_design_thin_edge import table_bounds_task,edge_slide_target,check_under_table_clearance,trailing_edge_push_pose,mechanism_collision_points_task,actual_finger_points_task,seek_actual_contact
from .realworld_tool_expert import ToolExecutionError,_axis_rotation,_unit


def fold_public(p):
    a=p.a;spec=p.spec;design=spec.get('execution_design',{})
    if spec['id']!='E44'or design.get('revision')!=REVISION_V3 or design.get('source_sha256')!=source_sha256(REVISION_V3)or not a.control_report.get('engineering_reference_only'):
        raise ValueError('Isolated source-checked E44 engineering required')
    if p.s.get('execution_design_fold_fixture'):
        from .execution_design_e44_fixture import verify_native_initial
        verify_native_initial(p)
        import os
        if p.s['execution_design_fold_fixture'].get('schema')in('e44-passive-folding-rails-v2','e44-passive-folding-rails-v3','e44-passive-folding-rails-v4'):
            from .execution_design_fold_contact_push import complete_passive_guide
            return complete_passive_guide(p)
        if os.environ.get('VIC_E44_FIXTURE_INITIAL_ONLY')=='1':
            raise ToolExecutionError('Initial fixture validation only; zero physical actions requested')
        if os.environ.get('VIC_E44_RAIL_RAISE_ONLY')=='1':
            from .execution_design_fold_rails import raise_onto_rails
            raise_onto_rails(p)
            raise ToolExecutionError('Passive-rail edge preparation diagnostic only; whole task not accepted')
    s=p.s['crease'];g=s['expert'];mech=next(m for m in spec['mechanisms']if m['id']==s['mechanism'])
    if mech['mechanical_asset'].get('free_base')is not True:raise ValueError('Actual free-base sheet required')
    fold=dict(mechanism=s['mechanism'],**g['fold_grasp']);base=dict(mechanism=s['mechanism'],**g['base_press'])
    bounds=table_bounds_task(a.scene)
    def log(phase,**kwargs):
        row=dict(phase=phase,step=p.c.steps,fold_point=p.point(fold).tolist(),base_point=p.point(base).tolist(),**kwargs)
        p.operations.append(row)
        with (Path(a.out)/'fold-public-geometry.private.jsonl').open('a')as f:f.write(json.dumps(row)+'\n')
    def contact_base():return any(p.contact(base['contact_body'],f'left_finger{i}')for i in (1,2))
    def base_supported():return p.contact(base['contact_body'],'table')
    def press_base():
        p.stage('E44-public-base-contact');p.act('left','GRASP')
        point=p.point(base);height=max(p.clearance,float(p.tip('left')[2]))
        p.move('left',[*p.tip('left')[:2],height]);p.move('left',[*point[:2],height])
        geom=a.finger_geometry('left');lowest=geom['lowest_z_task_m'];target=p.tip('left').copy()
        target[2]+=point[2]+.0006-lowest+.006
        p.move('left',target)
        sought=seek_actual_contact(lambda:contact_base()and base_supported(),lambda:p.act('left','DOWN',mm=.5),32)
        if sought is not None:return
        raise ToolExecutionError('No actual supported base-panel pressing contact')
    # Free-base articulation is translated by real surface friction. The
    # source Crease connects BasePanel to FoldPanel, never the world.
    bp,br=p.frame(base);fp=p.point(fold);hinge=bp+br@np.asarray(g['hinge_point_local'],float)
    outward=_unit(fp-hinge);outward[2]=0.;outward=_unit(outward)
    plan=edge_slide_target(fp,p.point(base),outward,bounds)
    log('planned-slide',table_lower=bounds['lower'].tolist(),table_upper=bounds['upper'].tolist(),
        table_edge=plan['table_edge'],distance=plan['distance'],target_grasp=plan['target_grasp'].tolist())
    # Read the same native world's right-arm state before committing to a long
    # push. A reachable pushing wrist does not imply the final pinch is reachable.
    from .execution_design_drawer_ik_probe import inspect,physical_grasp_targets
    pinch_candidates=[]
    for candidate_rotation in physical_grasp_targets(a,p.c,'right',outward,pinch_axis=[0.,0.,1.]):
        target=np.asarray(plan['target_grasp'],float)
        outside=target+outward*.08;outside[2]=max(p.clearance,float(p.tip('right')[2]))
        candidates=inspect(a,p.c,'right',[
            dict(position=target.tolist(),rotation=candidate_rotation.tolist()),
            dict(position=outside.tolist(),rotation=candidate_rotation.tolist())])
        log('native-final-pinch-precheck',rotation=candidate_rotation.tolist(),ik=candidates)
        if all(row['kinematically_reachable']for row in candidates):
            pinch_candidates.append(candidate_rotation)
    if not pinch_candidates:
        from .execution_design_fold_compress import compress_fold
        return compress_fold(p)
    final_pinch_rotation=pinch_candidates[0]
    # Contact the actual trailing edge rather than sliding over the top.
    # The archived surface-friction attempt moved the hand70mm but sheet5mm.
    p.stage('E44-public-trailing-edge-approach');p.act('left','GRASP')
    def seat_trailing_edge():
        material=mechanism_collision_points_task(p,base)
        start,receipt=trailing_edge_push_pose(material,actual_finger_points_task(a,'left'),p.tip('left'),outward,bounds['top'])
        log('measured-trailing-edge',**receipt)
        # Reacquire from behind the measured edge; never chase contact by
        # driving forwards over the top of the 1.2mm panel.
        height=max(float(p.tip('left')[2])+.008,float(start[2])+.012)
        p.move('left',[*p.tip('left')[:2],height]);p.move('left',[*start[:2],height]);p.move('left',start,tolerance=.0003)
        sought=seek_actual_contact(contact_base,lambda:p.act('left',token,mm=.5),12)
        if sought is not None:
            log('actual-trailing-contact',seek_actions=sought)
            return
        raise ToolExecutionError('No actual trailing-edge finger contact')
    # Native v3 climbs the strongly sloped toe and repeatedly loses contact.
    # A measured 10-degree forward wrist candidate reduces toe-front sweep
    # across the 1.2mm material band; verify real IK before issuing rotation.
    from .execution_design_e33_grasp import actual_mesh
    from .execution_design_drawer_ik_probe import inspect
    from .execution_design_cutlery_grasp import orient as orient_empty
    rotation=a.tcp_rotation_task('left');tip=p.tip('left')
    candidate=_axis_rotation(np.cross([0.,0.,1.],outward),math.radians(10.))@rotation
    fingers=actual_finger_points_task(a,'left')
    transformed=(fingers-tip)@rotation@candidate.T+tip
    candidate_start,_=trailing_edge_push_pose(mechanism_collision_points_task(p,base),transformed,tip,outward,bounds['top'])
    palm=(actual_mesh(a,'left','panda_hand')-tip)@rotation@candidate.T+candidate_start
    if float(palm[:,2].min())<bounds['top']+.0002-1e-6:
        raise ToolExecutionError('Forward push candidate palm would cross actual tabletop')
    targets=[dict(position=tip.tolist(),rotation=candidate.tolist()),dict(position=candidate_start.tolist(),rotation=candidate.tolist())]
    ik=inspect(a,p.c,'left',targets)
    log('forward-toe-candidate',rotation=candidate.tolist(),contact_start=candidate_start.tolist(),ik=ik)
    if not all(row['kinematically_reachable']for row in ik):
        raise ToolExecutionError('Measured forward toe candidate is outside actual joint workspace')
    orient_empty(a,'left',candidate)
    history=[];component=plan['component'];sign=plan['sign']
    token=(('FWD','BACK'),('LEFT','RIGHT'))[component][int(sign<0)]
    # First approach retains high clearance until directly behind the edge.
    p.move('left',[*p.tip('left')[:2],max(p.clearance,float(p.tip('left')[2]))])
    seat_trailing_edge();reseats=0
    # The v3 native trace advances the sheet about 0.5mm per 2mm
    # public push. 800 bounded pushes cover the measured 280mm route
    # with margin; the author still enforces its 3000-action total budget.
    for _ in range(800):
        actual=p.point(fold);remaining=float((plan['target_grasp']-actual)@outward)
        if remaining<=.002:break
        if not base_supported():raise ToolExecutionError('Free base lost actual tabletop support during edge pushing')
        # Real contact can persist after a toe climbs onto the panel top.
        # The v12 trace then gives only44um downward motion for a1mm request;
        # continuing to push just slides across the top rather than the edge.
        material_top=float(mechanism_collision_points_task(p,base)[:,2].max())
        actual_toe=float(a.finger_geometry('left')['lowest_z_task_m'])
        on_top=actual_toe>=material_top-.00015
        if not contact_base()or on_top:
            reseats+=1
            if reseats>100:raise ToolExecutionError('Bounded trailing-edge reseat count exceeded')
            log('trailing-edge-reacquisition',reason='toe_at_panel_top'if on_top else'contact_absent',
                actual_toe_z=actual_toe,actual_material_top_z=material_top)
            seat_trailing_edge()
        # Horizontal servo actions reset their vertical target to achieved
        # height. Correct measured toe climbing before the next short push.
        low=float(a.finger_geometry('left')['lowest_z_task_m'])
        if low>bounds['top']+.0004:
            p.act('left','DOWN',mm=min(1.,(low-bounds['top']-.0002)*1000))
        p.stage('E44-public-push-free-base-edge')
        p.act('left',token,mm=min(2.,remaining*1000))
        after=p.point(fold);history.append(float(after@outward))
        log('edge-push-step',actual_displacement_m=float((after-fp)@outward),base_contact=contact_base(),base_supported=base_supported())
        if len(history)>=12 and max(history[-12:])-min(history[-12:])<.001:
            raise ToolExecutionError('Actual sheet did not translate under public trailing-edge contact')
    else:raise ToolExecutionError('Bounded physical sheet push did not expose edge')
    p.act('left','UP',mm=8.)
    # Re-seat the holding hand on the measured translated base.
    press_base()
    def base_guard():
        if not contact_base()or not base_supported():raise ToolExecutionError('Fold requires actual held base and tabletop contact')
    p.stage('E44-public-outside-edge-orient');p.act('right','RELEASE')
    point=p.point(fold);outside=point+outward*.08;outside[2]=max(p.clearance,float(p.tip('right')[2]))
    p.move('right',[*p.tip('right')[:2],outside[2]],base_guard);p.move('right',outside,base_guard)
    target_rotation=final_pinch_rotation
    def orient(target,guard):
        from .author_orientation import _axis_angle
        for _ in range(240):
            guard();axis,angle=_axis_angle(target@a.tcp_rotation_task('right').T)
            if angle<math.radians(1.):return
            k=int(np.argmax(abs(axis)));token=(('ROLL_LEFT','ROLL_RIGHT'),('PITCH_UP','PITCH_DOWN'),('ROTATE_CCW','ROTATE_CW'))[k][int(axis[k]<0)]
            p.act('right',token,degrees=min(3.,max(.5,abs(math.degrees(angle*axis[k])))))
        raise ToolExecutionError('Public side-pinch wrist orientation did not converge')
    orient(target_rotation,base_guard)
    target=p.point(fold)
    check_under_table_clearance(target,p.tip('right'),a.finger_geometry('right'),bounds,component,sign)
    near=target+outward*.06;near[2]=target[2]
    p.move('right',near,base_guard)
    p.stage('E44-public-side-edge-pinch');p.move('right',target,base_guard,tolerance=.001)
    stable=0
    for _ in range(5):
        p.act('right','GRASP');stable=stable+1 if p.held(fold,'right')else 0
        if stable>=3:break
    else:raise ToolExecutionError('Actual side-pinch lacks stable two-finger panel contact')
    initial=a.tcp_rotation_task('right').copy();bp,br=p.frame(base);hinge=bp+br@np.asarray(g['hinge_point_local'],float);axis=br@_unit(g['axis_local']);vector=p.point(fold)-hinge
    desired=180.-(90.,120.,45.)[p.index];direction=float(g['direction'])
    def guarded():base_guard();p.require_held(fold,'right')
    def measured():
        bn=p.frame(base)[1]@_unit(s['base']['normal_local']);fn=p.frame(fold)[1]@_unit(s['fold']['normal_local'])
        return math.degrees(math.acos(float(np.clip(bn@fn,-1.,1.))))
    p.stage('E44-public-contact-driven-fold')
    for degrees in np.arange(1.,desired+1.,1.):
        guarded();turn=_axis_rotation(axis,math.radians(min(degrees,desired))*direction)
        orient(turn@initial,base_guard)
        p.move_point('right',fold,hinge+turn@vector,guarded,tolerance=.0015)
        log('fold-step',target_fold_deg=float(degrees),measured_fold_deg=measured(),actual_bilateral_grip=p.held(fold,'right'))
    if abs(measured()-desired)>3.:raise ToolExecutionError('Actual panel did not reach source fold angle')
    p.release(fold,'right');p.move('right',p.tip('right')+outward*.07)
    p.move('left',p.tip('left')+[0,0,.07]);p.wait(8)
    log('released-final',measured_fold_deg=measured(),base_supported=base_supported())
