"""E12 engineering grasp candidate for the reviewed lying charger source."""
from copy import deepcopy
import math


def horizontal_charger_grasps(spec,grasps):
    if spec.get('id')!='E12' or spec.get('execution_design',{}).get('revision')!='embodied50-execution-v3-20261102':
        raise ValueError('E12 v3 engineering contract required')
    objects={o['id']:o for o in spec['objects']};result=deepcopy(grasps)
    for name in spec['semantic']['groups']['chargers']:
        obj=objects[name];source=obj.get('source_asset',{})
        if source.get('sha256')!='e5843b3b6f1829b5a251030b7204eb5988b412a4f648138e7eb0a870f703b043' or source.get('source_rotation')!=[1,0,0,0]:
            raise ValueError('E12 candidate requires the reviewed charger collision source')
        if len(obj['size'])!=3 or any(not math.isclose(a,b,rel_tol=1e-7)for a,b in zip(obj['size'],[.022500229104381986,.023750007838586176,.030000168595459287])):
            raise ValueError('E12 candidate requires reviewed charger dimensions')
        g=result[name]
        if g['jaw_axis_local']!=[0,1,0] or not math.isclose(g['local'][2],.01100016859545929,abs_tol=1e-9):
            raise ValueError('E12 candidate refuses to overwrite a different grasp revision')
        # The original local-Y jaw becomes vertical when the charger lies at
        # Rx90 on the table. Local-X pinches its real 45mm-wide body from the
        # sides. Raise the working point within that body so actual finger
        # toes clear the support; native contacts/holding remain decisive.
        g['jaw_axis_local']=[1,0,0]
        g['local'][1]=.012
    return result


def pin_aperture_diagnostics(author,name,slot_id):
    """Measure both real pin cross sections in the matching real hole frames."""
    import numpy as np
    from .realworld_structural_evidence import _basis
    slot=author.s['slots'][str(slot_id)];pins=author.s['pins'][name]
    if len(pins)!=2 or len(slot['holes'])!=2:raise ValueError('E12 requires exactly two measured pins and holes')
    _,body_rotation=author.frame({'actor':name});_,socket_rotation=author.frame(slot['ref'])
    rows=[]
    for pin,hole in zip(pins,slot['holes']):
        ha,hu,hv=_basis(hole['axis_local'],hole['u_local']);ha,hu,hv=(socket_rotation@x for x in(ha,hu,hv))
        pa,pu,pv=_basis(pin['axis_local'],pin['u_local']);pa,pu,pv=(body_rotation@x for x in(pa,pu,pv))
        tip=author.body_point({'actor':name},pin['tip_local']);center=author.body_point(slot['ref'],hole['center_local']);delta=tip-center
        pin_half=np.asarray(pin['half_size']);hole_half=np.asarray(hole['half_size'])
        projection=np.array([abs(hu@pu)*pin_half[0]+abs(hu@pv)*pin_half[1],abs(hv@pu)*pin_half[0]+abs(hv@pv)*pin_half[1]])
        lateral=np.array([hu@delta,hv@delta]);axial=float(ha@delta)
        # Cross section swept through full requested insertion must also fit,
        # not only the tip rectangle when an angled pin first meets the mouth.
        depth=min(float(pin['length'])*.85,float(hole['depth'])-.001)
        tangent=np.array([hu@pa,hv@pa]);normal=max(1e-9,abs(float(ha@pa)))
        skew=np.abs(tangent)*depth/normal
        margins=hole_half-projection-np.abs(lateral)-skew
        rows.append(dict(lateral_m=lateral.tolist(),axial_m=axial,margin_m=margins.tolist(),axis_dot=float(pa@ha),fits=bool(np.all(margins>=.00005)and pa@ha<-.999)))
    return rows


def occupied_pin_channel_diagnostics(author,name,slot_id):
    """Exact pin material inside the actual entrance/bottom planes only."""
    import numpy as np
    from .realworld_structural_evidence import _basis
    slot=author.s['slots'][str(slot_id)];position,rotation=author.frame(dict(actor=name))
    base,matrix=author.frame(slot['ref']);rows=[]
    for pin,hole in zip(author.s['pins'][name],slot['holes']):
        pa,pu,pv=(rotation@axis for axis in _basis(pin['axis_local'],pin['u_local']))
        ha,hu,hv=(matrix@axis for axis in _basis(hole['axis_local'],hole['u_local']))
        tip=position+rotation@np.asarray(pin['tip_local']);center=base+matrix@np.asarray(hole['center_local'])
        ru,rv=pin['half_size'];points=np.array([tip-pa*t+pu*su*ru+pv*sv*rv
            for t in(0.,float(pin['length']))for su in(-1,1)for sv in(-1,1)])
        heights=(points-center)@ha;depth=float(hole['depth'])
        clipped=[point for point,z in zip(points,heights)if-depth<=z<=0.]
        for i in range(8):
            for j in range(i+1,8):
                if (i^j).bit_count()!=1 or abs(heights[j]-heights[i])<1e-14:continue
                for plane in(-depth,0.):
                    fraction=(plane-heights[i])/(heights[j]-heights[i])
                    if 0.<=fraction<=1.:clipped.append(points[i]+fraction*(points[j]-points[i]))
        margins=None
        if clipped:
            delta=np.asarray(clipped)-center
            extent=np.array([max(abs(delta@hu)),max(abs(delta@hv))])
            margins=(np.asarray(hole['half_size'])-extent).tolist()
        rows.append(dict(actual_depth_m=-float((tip-center)@ha),
            occupied_channel_margin_m=margins,occupied_vertices=len(clipped),
            fits_actual_channel=bool(margins is not None and min(margins)>=0.),
            virtual_full_recipe_segment_required=False))
    return rows


def insertion_channel_diagnostics(author,name,slot_id):
    """Gate only actual pin material between the original channel planes."""
    rows=pin_aperture_diagnostics(author,name,slot_id)
    for row,occupied in zip(rows,occupied_pin_channel_diagnostics(author,name,slot_id)):
        row['virtual_full_recipe_margin_m']=row['margin_m']
        row.update(occupied)
        row['margin_m']=occupied['occupied_channel_margin_m']
        row['fits']=bool(row['axis_dot']<-.999 and (row['margin_m']is None
            or min(row['margin_m'])>=.00005))
    return rows


def insert_charger_precisely(author,name,ref,side,slot_id,rotation,depth,*,resume=False):
    """Bounded public-action insertion; never push misaligned pins into a face."""
    import numpy as np
    from .realworld_structural_evidence import _basis
    from .realworld_tool_expert import ToolExecutionError
    if author.task!='E12' or not getattr(author.a,'control_report',{}).get('engineering_reference_only'):
        raise ToolExecutionError('E12 independent engineering control required')
    if getattr(author,'_e12_functional_workflow',False):
        from .execution_design_e12_functional import insert
        return insert(author,name,ref,side,slot_id,rotation,depth,resume=resume)
    slot=author.s['slots'][str(slot_id)];pin=author.s['pins'][name][0];hole=slot['holes'][0]
    ha,_,_=_basis(hole['axis_local'],hole['u_local']);_,matrix=author.frame(slot['ref']);ha=matrix@ha
    center=author.body_point(slot['ref'],hole['center_local']);control=dict(actor=name,local=pin['tip_local']);guard=lambda:author.require_held(ref,side)
    resume_precision=resume=='precision'
    channel=bool(getattr(author,'_e12_toe_preparation',{}).get('replanned_source_toe28'))
    insertion_rows=insertion_channel_diagnostics if channel else pin_aperture_diagnostics
    if resume:
        current_rows=insertion_rows(author,name,slot_id)
        if resume_precision and not all(row['fits']for row in current_rows):
            raise ToolExecutionError('E12 precision continuation requires currently fitted actual pins')
        if not resume_precision and min(row['axial_m']for row in current_rows)<.003:
            raise ToolExecutionError('E12 resumed free-air alignment requires actual pin clearance above socket')
        approach=center+ha*float(np.mean([row['axial_m']for row in current_rows]))
    else:
        height=max(author.clearance,float(center[2])+.10)
        author.move_point(side,control,[*author.point(control)[:2],height],guard)
        if author.a.control_report.get('e12_pin_alignment'):
            rotate_charger_with_public_holds(author,name,side,rotation)
        else:author.rotate_actor(name,side,rotation)
        author.move_point(side,control,[*center[:2],height],guard)
        approach=center+ha*.025
        author.move_point(side,control,approach,guard)
    from .execution_design_e12_feedback import PinResponse
    servo=PinResponse(author,name,slot_id,side)
    # Measure half-mm public actions above the holes, before precision alignment.
    # The aperture geometry and contact gate are never weakened for calibration.
    author.stage('measure-public-responses-slot-'+str(slot_id))
    if resume:
        report=author.a.control_report;model=report.get('e12_active_pin_response',{})
        if model.get('actor')==name and model.get('slot')==slot_id:
            origin='captured_actual_rolling_samples'
        else:
            model=next((row for row in reversed(report.get('e12_public_response_calibration',[]))if row.get('actor')==name and row.get('slot')==slot_id),None)
            if model is None:raise ToolExecutionError('E12 resume lacks actual response samples')
            origin='original_actual_calibration_prior; missing rolling context explicitly reconstructed'
        servo.samples={key:[np.asarray(row,float)for row in rows]for key,rows in model['samples'].items()}
        if any(value.shape!=(6,)or not np.isfinite(value).all()for values in servo.samples.values()for value in values):
            raise ToolExecutionError('E12 resume response samples must be finite measured six-vectors')
        servo.last_token='STILL' # the explicit native held reconstruction was a public STILL
        report['e12_response_resume_model']=dict(actor=name,slot=slot_id,source=origin)
    for token in (()if resume else('FWD','STILL','BACK','STILL','LEFT','STILL','RIGHT','STILL','DOWN','STILL')*2):
        guard();calibration=pin_aperture_diagnostics(author,name,slot_id)
        support=slot['ref'].get('actor',slot['ref'].get('contact_body'))
        if min(row.get('axial_m',-1.)for row in calibration)<.015 or author.contact(name,support):
            raise ToolExecutionError('E12 response calibration requires clear free air')
        servo.act(token)
    if not resume:author.a.control_report.setdefault('e12_public_response_calibration',[]).append(dict(actor=name,slot=slot_id,still_context='one_public_STILL_after_the_same_measured_translation',samples={token:[sample.tolist()for sample in values]for token,values in servo.samples.items()}))
    author.stage('precision-align-both-pins-slot-'+str(slot_id))
    diagnostics=[]
    # The public action lower bound is retained. If actual .5mm/.5deg actions
    # cannot achieve the real ~.3mm aperture clearance, fail above the socket.
    for _ in range(160):
        if resume_precision:rows=current_rows;break
        guard();_,current=author.frame({'actor':name});delta=np.asarray(rotation)@current.T
        angle=float(np.arccos(np.clip((np.trace(delta)-1)/2,-1,1)))
        toe=getattr(author,'_e12_toe_preparation',{})
        tilt_rows=pin_aperture_diagnostics(author,name,slot_id)if resume else []
        tilt=max((math.acos(float(np.clip(-row['axis_dot'],-1,1)))for row in tilt_rows),default=0.)
        if resume and tilt>math.radians(.2)and not toe.get('resume_tilt_correction_used'):
            axis=np.array([delta[2,1]-delta[1,2],delta[0,2]-delta[2,0],delta[1,0]-delta[0,1]])/(2*math.sin(angle))
            i=int(np.argmax(abs(axis)));token=(('ROLL_LEFT','ROLL_RIGHT'),('PITCH_UP','PITCH_DOWN'),('ROTATE_CCW','ROTATE_CW'))[i][int(axis[i]<0)]
            toe['resume_tilt_correction_used']=True
            author.act(side,token,degrees=.5);author.act(side,'STILL')
            continue
        if angle>math.radians(.35):
            axis=np.array([delta[2,1]-delta[1,2],delta[0,2]-delta[2,0],delta[1,0]-delta[0,1]])/(2*math.sin(angle))
            i=int(np.argmax(abs(axis)));token=(('ROLL_LEFT','ROLL_RIGHT'),('PITCH_UP','PITCH_DOWN'),('ROTATE_CCW','ROTATE_CW'))[i][int(axis[i]<0)]
            author.act(side,token,degrees=min(1.,abs(math.degrees(angle*axis[i]))));continue
        rows=pin_aperture_diagnostics(author,name,slot_id);diagnostics.append(rows)
        error=approach-author.point(control)
        if all(r['fits']for r in rows)and abs(float(error@ha))<.001:break
        i=int(np.argmax(abs(error)))
        if abs(error[i])<.00005:raise ToolExecutionError('E12 real dual-pin geometry cannot fit at centered pose')
        token=(('FWD','BACK'),('LEFT','RIGHT'),('UP','DOWN'))[i][int(error[i]<0)]
        author.act(side,token,mm=min(1.,abs(float(error[i]))*1000))
    else:raise ToolExecutionError('E12 actual dual-pin alignment cannot meet source aperture margins')
    author.a.control_report.setdefault('e12_pin_alignment',[]).append(dict(actor=name,slot=slot_id,alignment=rows))
    author.stage('precision-insert-both-pins-slot-'+str(slot_id))
    target=center-ha*depth
    correction_count=0
    for _ in range(240):
        guard();rows=insertion_rows(author,name,slot_id)
        if not all(r['fits']for r in rows):
            # The measured 486-action failure drifted 0.14mm sideways during
            # one DOWN while both pin tips were still 23mm above the holes.
            # Recenter only in free air; any possible socket contact keeps the
            # original stop guard. Never push or rotate a misaligned inserted pin.
            support=slot['ref'].get('actor',slot['ref'].get('contact_body'))
            if (not rows or min(r.get('axial_m',-1.)for r in rows)<.003
                    or author.contact(name,support) or correction_count>=60):
                raise ToolExecutionError('E12 real pin clearance lost; refusing further insertion')
            error=center-author.point(control);error-=ha*float(error@ha)
            i=int(np.argmax(abs(error)))
            if abs(float(error[i]))<.00005:
                raise ToolExecutionError('E12 free-air pin rotation cannot fit; refusing insertion')
            token=(('FWD','BACK'),('LEFT','RIGHT'),('UP','DOWN'))[i][int(error[i]<0)]
            author.act(side,token,mm=min(.5,abs(float(error[i]))*1000))
            correction_count+=1
            continue
        remaining=float((target-author.point(control))@(-ha))
        if remaining<=.0005:break
        # Source slots are upright. Reject future tilted source rather than
        # silently turning one-axis DOWN into an unreviewed diagonal plunge.
        if float(ha[2])<.999:raise ToolExecutionError('E12 reviewed insertion requires upright socket')
        try:
            token=servo.choose()
        except ToolExecutionError:
            # A just-fitting corner pose may have no safe next discrete action.
            # Recenter freely only while still well above the socket. Never
            # permit this recovery once the pins approach or contact the holes.
            support=slot['ref'].get('actor',slot['ref'].get('contact_body'))
            if (min(row.get('axial_m',-1.)for row in rows)<.003
                    or author.contact(name,support) or correction_count>=60):raise
            error=center-author.point(control);error-=ha*float(error@ha)
            i=int(np.argmax(abs(error)))
            if abs(float(error[i]))<.00005:raise
            token=(('FWD','BACK'),('LEFT','RIGHT'),('UP','DOWN'))[i][int(error[i]<0)]
            correction_count+=1
        servo.act(token)
    else:raise ToolExecutionError('E12 measured insertion did not advance to physical depth')
    if name=='charger_2'and hasattr(author,'_e12_toe_preparation'):
        release_toe_charger(author,name,ref,side,slot_id)
    else:
        author.release(ref,side);author.move(side,author.tip(side)+[0,0,.06]);author.wait(3)
    support=slot['ref'].get('actor',slot['ref'].get('contact_body'))
    if not author.contact(name,support):raise ToolExecutionError('E12 inserted charger lacks actual socket support')


def release_toe_charger(author,name,ref,side,slot_id):
    """Clear the first body during full opening while pins remain engaged."""
    import numpy as np
    from .execution_design_e13_release import actual_opening_bodies,plan_opening_height
    from .execution_design_branch_geometry import collision_parts_task
    from .execution_design_branch_geometry import swept_pose_clearance
    from .execution_design_thin_edge import table_bounds_task
    from .realworld_tool_expert import ToolExecutionError
    tip=author.tip(side);initial_z=float(tip[2]);top=table_bounds_task(author.a.scene)['top']
    state,_=author.snapshot();obstacles={actor:collision_parts_task(author,actor)for actor in state if actor!=name}
    toe28=getattr(author,'_e12_toe_preparation',{}).get('replanned_source_toe28')
    def opening_plan(bodies,tip,z,max_z):
        if not toe28:return plan_opening_height(bodies,tip,z,obstacles,top,max_z=max_z)
        for height in [*np.arange(z,max_z,.002),max_z]:
            shifted={body:points+[0,0,height-tip[2]]for body,points in bodies.items()}
            at=np.array([*tip[:2],height])
            try:guard=swept_pose_clearance(shifted,at,at,np.eye(3),obstacles,top,
                    margin=0. if getattr(author,'_e12_functional_workflow',False)else .0003)
            except ToolExecutionError:continue
            return dict(tcp_z=float(height),extra_release_height_m=float(height-z),opening_sweep_guard=guard)
        raise ToolExecutionError('E12 actual opening sweep has no clear guided release height')
    plan=opening_plan(actual_opening_bodies(author,side),tip,initial_z,initial_z+.004)
    for _ in range(3):
        author.require_held(ref,side)
        occupied=occupied_pin_channel_diagnostics(author,name,slot_id)
        if not author.contact('charger_1','strip')or (not getattr(author,'_e12_functional_workflow',False)and not all(row['fits_actual_channel']for row in occupied)):
            raise ToolExecutionError('E12 opening clearance requires original supported first and fitted second pins')
        tip=author.tip(side)
        try:
            actual=opening_plan(actual_opening_bodies(author,side),tip,float(tip[2]),float(tip[2]))
            break
        except ToolExecutionError:
            if float(tip[2])-initial_z>=.0045:raise
            amount=min(2.,max(.5,(plan['tcp_z']-float(tip[2]))*1000))
            if getattr(author,'_e12_toe_preparation',{}).get('replanned_source_toe28'):
                measured=pin_aperture_diagnostics(author,name,slot_id)
                if min(-float(row['axial_m'])for row in measured)-amount/1000<=0.:
                    raise ToolExecutionError('E12 opening lift would lose the real two-pin guide')
            author.act(side,'UP',mm=amount)
    else:raise ToolExecutionError('E12 actual full-opening sweep still intersects neighboring source')
    author.a.control_report['e12_actual_toe_release_opening']=dict(plan=plan,actual=actual,
        actual_lift_m=float(author.tip(side)[2])-initial_z,occupied_pin_channels=occupied,
        original_50um_is_engineering_prediction_buffer_not_native_score=True)
    if getattr(author,'_e12_toe_preparation',{}).get('replanned_source_toe28'):
        if min(-float(row['axial_m'])for row in pin_aperture_diagnostics(author,name,slot_id))<=0.:
            raise ToolExecutionError('E12 physical release requires two real guided pin tips')
        if not getattr(author,'_e12_functional_workflow',False):
            from .execution_design_e12_triangle import require_actual_strip_clearance
            require_actual_strip_clearance(author,name)
    author.act(side,'RELEASE')
    if hasattr(author,'_branch_public_original_act'):author.act=author._branch_public_original_act
    if author.held(ref,side):raise ToolExecutionError('E12 second charger did not actually release')
    author.move(side,author.tip(side)+[0,0,.06])


def prepare_next_charger_acquisition(author,ref,side):
    """Return the released hand over the next source before empty yaw rotation."""
    import numpy as np
    from .realworld_tool_expert import ToolExecutionError
    report=getattr(author.a,'control_report',{})
    if author.task!='E12' or not report.get('engineering_reference_only'):
        raise ToolExecutionError('E12 independent engineering control required')
    if not report.get('e12_pin_alignment'):return
    index=0 if side=='left' else 1
    def empty():
        state,contacts=author.snapshot()
        if any(value['grasp'][index]for value in state.values())or any(
                frozenset((name,f'{side}_finger{i}'))in contacts
                for name in state for i in (1,2)):
            raise ToolExecutionError('E12 source retreat requires a released empty hand')
    empty();author.stage('return-empty-hand-over-'+ref['actor'])
    point=author.point(ref);tip=author.tip(side)
    height=max(float(author.clearance),float(point[2])+.10,float(tip[2]))
    author.move(side,np.array([*tip[:2],height]),guard=empty)
    author.move(side,np.array([*point[:2],height]),guard=empty)
    empty()
    restore_first_charger_hand(author,ref,side,empty)


def rotate_charger_with_public_holds(author,name,side,target):
    """Keep each real public angular goal while its measured residual settles."""
    import numpy as np
    from .author_orientation import _axis_angle
    from .realworld_tool_expert import ToolExecutionError
    if author.task!='E12' or not author.a.control_report.get('engineering_reference_only'):
        raise ToolExecutionError('E12 independent engineering control required')
    target=np.asarray(target,float)
    tokens=(('ROLL_LEFT','ROLL_RIGHT'),('PITCH_UP','PITCH_DOWN'),('ROTATE_CCW','ROTATE_CW'))
    def guard():
        author.require_held({'actor':name},side)
        for slot in author.s['slots'].values():
            support=slot['ref'].get('actor',slot['ref'].get('contact_body'))
            if author.contact(name,support):
                raise ToolExecutionError('E12 coarse held rotation requires free air above socket')
    for _ in range(120):
        guard();current=np.asarray(author.frame({'actor':name})[1])
        axis,angle=_axis_angle(target@current.T)
        if angle<math.radians(4.):return
        i=int(np.argmax(abs(axis)));token=tokens[i][int(axis[i]<0)]
        author.act(side,token,degrees=min(10.,max(.5,abs(math.degrees(angle*axis[i])))))
        # Keep the same target through logged public STILL actions. Repeating
        # a relative rotation discarded 4.6deg residual in native v13 slot2.
        for _ in range(6):
            feedback=author.c.action_feedback()['control_feedback'][side]
            if float(feedback['orientation_error_rad'])<=math.radians(.5):break
            guard();author.act(side,'STILL')
            report=author.a.control_report
            report['e12_held_rotation_public_holds']=report.get('e12_held_rotation_public_holds',0)+1
    raise ToolExecutionError('E12 actual held charger rotation did not converge')


def remember_acquired_hand(author,ref,side):
    """Save the actual first grasp frame, before any payload rotation."""
    import numpy as np
    author.require_held(ref,side)
    report=author.a.control_report
    hand=np.asarray(author.a.tcp_rotation_task(side),float)
    body=np.asarray(author.frame(ref)[1],float)
    report.setdefault('e12_actual_acquired_hand_frames',[]).append(dict(
        actor=ref['actor'],side=side,hand_rotation_task=hand.tolist(),
        object_rotation_task=body.tolist(),relative_hand_rotation=(body.T@hand).tolist(),
        native_arm_feedback=author.c.public_feedback()['arms'][side]))


def restore_first_charger_hand(author,ref,side,empty):
    """Use public rotations to repeat the first successful finger assignment."""
    import numpy as np
    from .author_orientation import _axis_angle
    from .realworld_tool_expert import ToolExecutionError
    samples=author.a.control_report.get('e12_actual_acquired_hand_frames',[])
    if not samples or samples[0]['side']!=side:
        raise ToolExecutionError('E12 original measured grasp frame unavailable')
    target=np.asarray(author.frame(ref)[1])@np.asarray(samples[0]['relative_hand_rotation'])
    initial=np.asarray(author.tip(side));tokens=(('ROLL_LEFT','ROLL_RIGHT'),('PITCH_UP','PITCH_DOWN'),('ROTATE_CCW','ROTATE_CW'))
    author.stage('restore-first-grasp-hand-over-'+ref['actor'])
    for _ in range(100):
        empty();current=np.asarray(author.a.tcp_rotation_task(side))
        axis,angle=_axis_angle(target@current.T)
        tip=np.asarray(author.tip(side))
        if tip[2]<initial[2]-.02 or np.linalg.norm(tip-initial)>.03:
            raise ToolExecutionError('E12 empty hand rotation departed source clearance')
        if angle<math.radians(1.):return
        i=int(np.argmax(abs(axis)));token=tokens[i][int(axis[i]<0)]
        author.act(side,token,degrees=min(5.,max(.5,abs(math.degrees(angle*axis[i])))))
        # A real public hold completes the existing rotation target instead
        # of discarding its measured residual with another relative command.
        # These are logged STILL actions, never hidden servo ticks or motion.
        for _ in range(2):
            pending=author.c.action_feedback()['control_feedback'][side]['orientation_error_rad']
            if float(pending)<=math.radians(.5):break
            empty();author.act(side,'STILL')
            report=author.a.control_report
            report['e12_empty_restore_public_holds']=report.get('e12_empty_restore_public_holds',0)+1
    raise ToolExecutionError('E12 first-grasp hand orientation did not converge')
