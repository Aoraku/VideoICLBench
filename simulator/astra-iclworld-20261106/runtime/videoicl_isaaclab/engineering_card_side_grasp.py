"""Real side-band card grip planned from cooked fingers and source floor bounds."""
import json,math
import numpy as np
from scipy.optimize import linprog
from scipy.spatial import ConvexHull
from .realworld_tool_expert import ToolExecutionError,_axis_rotation


def side_placement(points,fingers,floor_fingers,palm,jaw,floor,margin=.00002,preferred_translation=None,fixed_translation=None,independent_closures=False,maximum_closure_difference_m=.039):
    plans=[]
    for ordered in(points,points[::-1]):
        a=[];b=[];width=6 if independent_closures else 4
        def row(position,coefficient=0.,finger=0):
            values=[*map(float,position)]+[0.]*(width-3);values[3+finger if independent_closures else 3]=float(coefficient);return values
        for index,(point,mesh,floor_mesh,sign)in enumerate(zip(ordered,fingers,floor_fingers,(-1.,1.))):
            planes=ConvexHull(mesh).equations
            inward=sign*np.asarray(jaw)
            pad=max(planes,key=lambda plane:float(plane[:3]@inward))
            if float(pad[:3]@inward)<.9 or abs(float(pad[2]))>.2:break
            for nx,ny,nz,d in planes:
                n=np.array([nx,ny,nz]);a.append(row(-n,-sign*float(n@jaw),index));b.append(-d-float(n@point)-margin)
            # The point must lie just inside the real inward-facing pad,
            # rather than somewhere inside the toe/back of the whole hull.
            # This distinguishes side entry from pressing onto the card top.
            n=pad[:3];maximum_penetration=margin+.00003
            a.append(row(n,sign*float(n@jaw),index));b.append(float(n@point+pad[3])+maximum_penetration)
            a.append(row([0,0,-1],-sign*jaw[2],index));b.append(float(floor_mesh[:,2].min())-floor-margin)
            # Approach is made with the fingers still open. Constraining only
            # their closed endpoints can put one open toe below the table;
            # both endpoints also bound this linear closing sweep.
            a.append(row([0,0,-1]));b.append(float(floor_mesh[:,2].min())-floor-margin)
        else:
            a.append(row([0,0,-1]));b.append(float(palm[:,2].min())-floor-margin)
            objective=[0,0,1,.005,.005,.05]if independent_closures else[0,0,1,.01]
            bounds=[(None,None)]*3+([(0,.039)]*2+[(0,float(maximum_closure_difference_m))]if independent_closures else[(0,.039)])
            if independent_closures:
                a.extend(([0,0,0,1,-1,-1],[0,0,0,-1,1,-1]));b.extend((0.,0.))
            if fixed_translation is not None:bounds[:3]=[(float(v),float(v))for v in fixed_translation]
            if preferred_translation is not None:
                # Keep the floor-supported thin band, then minimize horizontal
                # correction rather than choosing an arbitrary pad-hull corner.
                a=[values+[0.,0.]for values in a]
                for axis in(0,1):
                    for sign in(-1.,1.):
                        values=[0.]*(width+2);values[axis]=sign;values[width+axis]=-1.;a.append(values);b.append(sign*float(preferred_translation[axis]))
                objective[2]=1000.;objective += [1.,1.];bounds += [(0,None)]*2
            r=linprog(objective,A_ub=a,b_ub=b,bounds=bounds,method='highs')
            if r.success:
                closures=r.x[3:5]if independent_closures else np.repeat(r.x[3],2)
                plans.append(dict(position=r.x[:3],closure_m=float(np.mean(closures)),closures_m=closures.tolist(),closure_difference_m=float(abs(closures[0]-closures[1]))))
    return plans


def com_side_points(vertices,position,rotation,com_local,jaw,half_thickness,fraction,long_offset_m=0.):
    from .engineering_native_convex_rays import line_entry
    normal=np.asarray(rotation)[:,2];direction=np.asarray(jaw)-normal*float(normal@jaw)
    direction/=np.linalg.norm(direction)
    center=np.asarray(position)+np.asarray(rotation)@np.asarray(com_local)
    if not np.isfinite(long_offset_m)or abs(long_offset_m)>.0005:
        raise ValueError('COM-section longitudinal offset is limited to half a millimeter')
    center+=np.asarray(rotation)[:,0]*float(long_offset_m)
    center+=normal*(float(half_thickness)*float(fraction)*np.sign(normal[2])-float(np.asarray(com_local)[2]))
    radius=float(np.linalg.norm(np.ptp(vertices,axis=0)))+.01
    points=[line_entry(vertices,center+sign*radius*direction,-sign*direction)for sign in(-1.,1.)]
    if any(point is None for point in points):raise ToolExecutionError('Real cooked card has no opposed COM-line side section')
    return np.asarray(points)


def acquire(p,ref,side,empty_clear_completed=False,card_face_fraction=.85,precision_full_down=False,initial_lift_step_mm=2.,centered_com_grasp=False,resume_side_trim=False):
    from .engineering_cooked_geometry_audit import native_cooked_meshes
    from .execution_design_e33_grasp import actual_mesh
    from .execution_design_thin_edge import material_collision_points_task,table_bounds_task
    from .execution_design_clip_grasp import convex_meshes_clear
    from .execution_design_thin_motion import checked_move
    from .execution_design_card_direct import prove_bilateral_lift
    a=p.a;floor=table_bounds_task(a.scene)['top'];obj=next(o for o in p.spec['objects']if o['id']==ref['actor'])
    def log(phase,**values):
        sensor,labels=a.scene.contacts[ref['actor']]
        q=a.scene.robots[side].data.joint_pos[:,p.c.ids[side][1]].cpu().tolist()
        row=dict(phase=phase,step=p.c.steps,actual_grasp=p.held(ref,side),finger_joints=q,
            card_position=p.frame(ref)[0].tolist(),force_labels=labels,force_matrix_world=sensor.data.force_matrix_w.cpu().tolist(),**values)
        with(a.out/'card-side-band.private.jsonl').open('a')as f:f.write(json.dumps(row)+'\n')
    if resume_side_trim and (p.held(ref,side) or not centered_com_grasp):
        raise ToolExecutionError('Side trim resume requires the empty COM-line checkpoint')
    if resume_side_trim:pass
    elif not empty_clear_completed:
        p.stage('card-side-band-empty-clear');p.act(side,'UP',mm=10.);p.act(side,'RELEASE')
    elif float(a.finger_geometry(side)['lowest_z_task_m'])<floor+.003:
        # A near-table checkpoint can have an unladen toe supported by the
        # table. Plan from a freely held wrist, not its contact-deflected pose.
        p.stage('card-side-band-unload-table-contact');p.act(side,'UP',mm=10.)
    if precision_full_down:
        from .execution_design_public_precision_orientation import orient
        short=np.asarray(p.frame(ref)[1])[:,1].copy();short[2]=0.;short/=np.linalg.norm(short)
        if short@np.asarray(a.tcp_rotation_task(side))[:,1]<0:short=-short
        down=np.array([0.,0.,-1.]);target=np.column_stack((np.cross(short,down),short,down))
        p.stage('card-side-band-complete-full-down');orient(a,side,target)
    # After an actual closed-finger pusher, RELEASE changes the logical goal
    # immediately while its rolling physical opening may still be in flight.
    # The placement model uses the physical open stop as its closure origin.
    if float(p.c.grips[side])>=.039:
        for _ in range(128):
            q=a.scene.robots[side].data.joint_pos[:,p.c.ids[side][1]].cpu().numpy()
            if float(np.min(q))>=.0395:break
            p.stage('card-side-band-actual-open-stop');p.act()
        else:raise ToolExecutionError('Actual card gripper did not reach its physical open stop')
    labels=(('ROLL_LEFT','ROLL_RIGHT'),('PITCH_UP','PITCH_DOWN'),('ROTATE_CCW','ROTATE_CW'))
    chosen={}if resume_side_trim else None;chosen_offset=0.
    for attempt in range(0 if resume_side_trim else 8):
        native=native_cooked_meshes(a,p,ref,side)
        (a.out/f'card-side-cooked-{p.c.steps}.private.json').write_text(json.dumps(native))
        tcp=p.tip(side);source=[actual_mesh(a,side,n)-tcp for n in a.scene.embodiment.fingers]
        fingers=[]
        for name in a.scene.embodiment.fingers:
            received=[np.asarray(m['vertices_task'])-tcp for r in native['meshes']if r['name']==name for m in r['cooked_meshes']]
            if not received:raise ToolExecutionError('Actual cooked finger representation missing: '+name)
            fingers.append(np.concatenate(received))
        palm=actual_mesh(a,side,'panda_hand')-tcp
        jaw=np.asarray(a.tcp_rotation_task(side))[:,1].copy()
        if jaw@(fingers[0].mean(0)-fingers[1].mean(0))<0:jaw=-jaw
        position,rotation=p.frame(ref);top_local=float(obj['size'][2])*float(card_face_fraction)*np.sign(rotation[2,2])
        obstacles={n:material_collision_points_task(p,dict(actor=n))for n in a.scene.objects if n!=ref['actor']}
        if centered_com_grasp:
            required=max([floor+.003]+[float(m[:,2].max())+.002 for m in obstacles.values()])
            if float(a.finger_geometry(side)['lowest_z_task_m'])<required:
                p.stage('card-com-grasp-clear-actual-obstacles');p.act(side,'UP',mm=min(p.max_mm,max(p.min_mm,(required-float(a.finger_geometry(side)['lowest_z_task_m']))*1000.)));continue
        card_vertices=np.concatenate([np.asarray(m['vertices_task'])for row in native['meshes']if row['name']==ref['actor']for m in row['cooked_meshes']])
        com=a.scene.objects[ref['actor']].root_physx_view.get_coms()[0,:3].cpu().numpy()
        candidates=([(0.,0,1.)]+[(degrees,2,sign)for degrees in(10.,15.,20.,25.,30.)for sign in(-1.,1.)])if centered_com_grasp else[(0.,0,1.)]+[(degrees,axis,sign)for degrees in(.5,1.,1.5,2.,3.,5.,7.,10.,15.,20.,30.)for axis in(0,1)for sign in(-1.,1.)]
        plans=[]
        for degrees,axis,sign in candidates:
            turn=_axis_rotation(np.eye(3)[axis],math.radians(degrees*sign))
            cooked=[m@turn.T for m in fingers];floors=[np.vstack((s,c))@turn.T for s,c in zip(source,fingers)]
            for offset in((0.,)if centered_com_grasp else(.025,0.,.015,-.015,-.025,.030,-.030)):
                points=com_side_points(card_vertices,position,rotation,com,turn@jaw,obj['size'][2],card_face_fraction)if centered_com_grasp else np.asarray([position+rotation@np.array([offset,y,top_local])for y in(-obj['size'][1],obj['size'][1])])
                for plan in side_placement(points,cooked,floors,palm@turn.T,turn@jaw,floor,preferred_translation=tcp,independent_closures=True):
                    target=plan['position'];dz=np.array([0,0,max(0.,float(tcp[2])-target[2])])
                    shapes=[np.vstack((m+target,m+target+dz))for m in [palm@turn.T,*cooked]]
                    for mesh,sign_close,closure in zip(cooked,(-1.,1.),plan['closures_m']):shapes.append(np.vstack((mesh+target,mesh+target+sign_close*closure*(turn@jaw))))
                    if any(not convex_meshes_clear(m,obstacle,clearance=.0005)for m in shapes for obstacle in obstacles.values()):continue
                    plans.append((degrees,axis,sign,offset,plan));break
                if plans:break
            if plans:break
        if not plans:
            log('no-clear-side-plan',tcp=tcp.tolist(),jaw=jaw.tolist(),source_fingers=[m.tolist()for m in source],native_fingers=[m.tolist()for m in fingers],palm=palm.tolist(),obstacles={k:m.tolist()for k,m in obstacles.items()})
            raise ToolExecutionError('No cooked-finger two-side card band with source-table clearance')
        degrees,axis,sign,offset,plan=plans[0]
        log('cooked-side-plan',degrees=degrees,axis=axis,sign=sign,long_offset_m=offset,closure_m=plan['closure_m'],closures_m=plan['closures_m'],target=plan['position'].tolist())
        if degrees:
            if float(a.finger_geometry(side)['lowest_z_task_m'])<floor+.003:
                p.stage('card-side-band-clear-before-turn');p.act(side,'UP',mm=10.);continue
            from .execution_design_local_pose_path import inspect_local_pose_path
            commanded=min(float(p.max_deg),degrees)
            rotation=a.tcp_rotation_task(side)
            turn=_axis_rotation(np.eye(3)[axis],math.radians(commanded*sign))
            path=inspect_local_pose_path(a,p.c,side,[dict(position=tcp.tolist(),rotation=(turn@rotation).tolist())],minimum_joint_margin_rad=.02)
            if not path['feasible']:raise ToolExecutionError('Side-band wrist turn lacks continuous native IK')
            p.stage('card-side-band-public-orient');p.act(side,labels[axis][int(sign<0)],degrees=commanded);continue
        chosen=plan;chosen_offset=offset;break
    if chosen is None:raise ToolExecutionError('Bounded public turns did not realize a cooked-finger side grip')
    def table_support():
        if not p.contact(ref['actor'],'table'):raise ToolExecutionError('Card lost table support before side grip')
    if not resume_side_trim:
        p.stage('card-side-band-approach');checked_move(p,side,chosen['position'],table_support,tolerance=.0003)
    # Nearby free-placement feasibility is not a certificate at the achieved
    # pose. Re-read current native meshes/R and fix the TCP before any closure.
    idle_ready=3;trim_gain={};pending_trim=None
    for _ in range(12):
        native=native_cooked_meshes(a,p,ref,side);tcp=p.tip(side)
        finger=[np.concatenate([np.asarray(m['vertices_task'])for r in native['meshes']if r['name']==name for m in r['cooked_meshes']])-tcp for name in a.scene.embodiment.fingers]
        source=[actual_mesh(a,side,name)-tcp for name in a.scene.embodiment.fingers]
        floors=[np.vstack((s,c))for s,c in zip(source,finger)];palm=actual_mesh(a,side,'panda_hand')-tcp
        jaw=np.asarray(a.tcp_rotation_task(side))[:,1].copy()
        if jaw@(finger[0].mean(0)-finger[1].mean(0))<0:jaw=-jaw
        pos,rot=p.frame(ref);alternatives=[];valid=[]
        com=a.scene.objects[ref['actor']].root_physx_view.get_coms()[0,:3].cpu().numpy()
        if pending_trim is not None:
            axis0,sign0,start0,command0=pending_trim
            observed=float((tcp[axis0]-start0[axis0])*sign0)
            if observed>command0*.1:trim_gain[(axis0,sign0)]=float(np.clip(observed/command0,.5,1.1))
        card_vertices=np.concatenate([np.asarray(m['vertices_task'])for row in native['meshes']if row['name']==ref['actor']for m in row['cooked_meshes']])
        # Any interior point on the actual 350um side is a valid grip.
        # Restricting the certificate to .5/.65 made a harmless 50um TCP
        # residual force repeated away/return moves before any real closure.
        for fraction in dict.fromkeys((float(card_face_fraction),.5,.65,.85,.95,.75,.35,.15,.05,-.15,-.35,-.5,-.65,-.85)):
            z=float(obj['size'][2])*fraction*np.sign(rot[2,2])
            points=com_side_points(card_vertices,pos,rot,com,jaw,obj['size'][2],fraction)if centered_com_grasp else np.asarray([pos+rot@np.array([chosen_offset,y,z])for y in(-obj['size'][1],obj['size'][1])])
            valid=side_placement(points,finger,floors,palm,jaw,floor,fixed_translation=tcp,independent_closures=True)
            if valid:card_face_fraction=fraction;break
            for candidate in side_placement(points,finger,floors,palm,jaw,floor,preferred_translation=tcp,independent_closures=True):
                if centered_com_grasp:
                    # The task does not demand a mathematically exact COM
                    # line. Re-intersect the actual cooked boundary within
                    # 0.5mm of COM, instead of repeated public moves solely
                    # to eliminate a harmless tens-of-microns X residual.
                    offset=float(np.clip((tcp-candidate['position'])@rot[:,0],-.0005,.0005))
                    actual_points=com_side_points(card_vertices,pos,rot,com,jaw,obj['size'][2],fraction,long_offset_m=offset)
                    achieved=side_placement(actual_points,finger,floors,palm,jaw,floor,fixed_translation=tcp,independent_closures=True)
                    if achieved:
                        points=actual_points;valid=achieved;card_face_fraction=fraction
                        log('near-com-real-boundary-valid',long_offset_m=offset,card_points_task=points.tolist());break
                alternatives.append((float(np.linalg.norm(candidate['position']-tcp)),fraction,candidate))
            if valid:break
        if valid:chosen=valid[0];log('fixed-native-side-pose-valid',closure_m=chosen['closure_m'],closures_m=chosen['closures_m'],closure_difference_m=chosen['closure_difference_m'],card_face_fraction=card_face_fraction);break
        if not alternatives:
            log('actual-pose-no-side-band',tcp=tcp.tolist(),rotation_task=np.asarray(a.tcp_rotation_task(side)).tolist(),native_fingers=[m.tolist()for m in finger],source_fingers=[m.tolist()for m in source],palm=palm.tolist(),jaw=jaw.tolist(),card_rotation=rot.tolist())
            raise ToolExecutionError('Current native wrist has no middle-side-band placement')
        _,card_face_fraction,nearest=min(alternatives,key=lambda row:row[0])
        error=nearest['position']-tcp;axis=int(np.argmax(abs(error)));minimum=float(p.min_mm)/1000.
        log('fixed-native-side-pose-correction',tcp=tcp.tolist(),target=nearest['position'].tolist(),error_m=error.tolist(),trim_gain={str(k):v for k,v in trim_gain.items()})
        if idle_ready:
            p.stage('card-side-band-retained-goal-settle');p.act();idle_ready-=1;continue
        if abs(error[axis])<minimum:
            # Two legal away legs ensure the subsequent return to a SAFE LP
            # target is above the public minimum; never issue a hidden100um step.
            direction=1. if axis==2 else(-1. if error[axis]>0 else 1.)
            token=(('FWD','BACK'),('LEFT','RIGHT'),('UP','DOWN'))[axis][int(direction<0)]
            p.stage('card-side-band-legal-trim-away')
            for _ in range(2):p.act(side,token,mm=p.min_mm);table_support()
            idle_ready=0;pending_trim=None
        else:
            token=(('FWD','BACK'),('LEFT','RIGHT'),('UP','DOWN'))[axis][int(error[axis]<0)]
            sign=1. if error[axis]>0 else -1.
            # Native public moves start at achieved TCP and may stop with a
            # tracking residual. Calibrate only horizontal command distance,
            # using the previous measured move including same-goal STILL.
            # The fixed native LP remains the sole closure certificate.
            gain=trim_gain.get((axis,sign),1.)if axis<2 else 1.
            command=min(float(p.max_mm)/1000.,abs(error[axis])/gain)
            delta=np.eye(3)[axis]*sign*command
            obstacles={n:material_collision_points_task(p,dict(actor=n))for n in a.scene.objects if n!=ref['actor']}
            sweep=[np.vstack((m+tcp,m+tcp+delta))for m in[*floors,palm]]
            if any(float(m[:,2].min())<floor+.00002-1e-8 for m in sweep)or any(not convex_meshes_clear(m,o,clearance=.0005)for m in sweep for o in obstacles.values()):
                raise ToolExecutionError('Calibrated public trim lacks source/native swept clearance')
            pending_trim=(axis,sign,tcp.copy(),command)
            p.stage('card-side-band-actual-pose-trim');p.act(side,token,mm=command*1000);table_support();idle_ready=3
    else:raise ToolExecutionError('Actual fixed side-band pose did not converge within public trim bound')
    expected_q=.04-np.asarray(chosen['closures_m'])
    if getattr(p.c,'_public_gripper_limits',None)is not None:
        from .engineering_thin_grasp_trace import close_current
        return close_current(p,ref,side,expected_q,card_face_fraction=card_face_fraction,initial_lift_step_mm=initial_lift_step_mm,card_points_local=((points-pos)@rot).tolist())
    for _ in range(6):
        p.stage('card-side-band-grasp');p.act(side,'GRASP');log('native-side-closure')
        q=a.scene.robots[side].data.joint_pos[:,p.c.ids[side][1]].cpu().numpy()
        if np.any(q<expected_q-.003):
            raise ToolExecutionError('Fingers closed past the planned card width without bilateral contact')
        if p.held(ref,side):break
    else:raise ToolExecutionError('Cooked-side plan did not establish actual bilateral contact')
    from .engineering_thin_suffix import save_stage
    save_stage(a,'first-side-bilateral',dict(side=side))
    p.stage('card-side-band-held-lift');raised=prove_bilateral_lift(p,ref,side);log('real-card-lift',raised_m=raised)
    save_stage(a,'side-card-lift',dict(raised_m=raised))
    return raised
