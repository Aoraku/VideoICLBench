"""Coarse engineering phone handling; native score remains unchanged and separate."""
import math
import numpy as np
from .realworld_tool_expert import ToolExecutionError,_axis_rotation
from .execution_design_e13_edge import PhoneMoves


def rough_orientation(p):
    state,_=p.snapshot();r=np.asarray(state['phone']['mat']);camera=r@np.asarray(p.s['camera_end_points']['phone']);camera/=np.linalg.norm(camera);back=r@np.asarray(p.s['back_normals']['phone']);component=float(camera[2]if p.variant=='A'else-camera[1]if p.variant=='B'else camera[1])
    return dict(camera_direction=camera.tolist(),back_direction=back.tolist(),camera_correct_halfspace=component>.1,back_operator_halfspace=bool(back[0]<-.1),correct=bool(component>.1 and back[0]<-.1))


def leading_section(p):
    from scipy.spatial import ConvexHull
    from scipy.optimize import linprog
    from .execution_design_e13_camera import closed_phone_obstacle
    state,_=p.snapshot();cloud=closed_phone_obstacle(p)[0];center=np.asarray(state['phone']['pos']);h=ConvexHull(cloud)
    z=float((cloud[:,2].min()+cloud[:,2].max())/2);solve=linprog([1.,0.,0.],A_ub=h.equations[:,:3],b_ub=-h.equations[:,3],A_eq=[[0,1,0],[0,0,1]],b_eq=[center[1],z],bounds=[(None,None)]*3,method='highs')
    if not solve.success:raise ToolExecutionError('Actual leading phone section unavailable')
    point=solve.x.copy();point[0]+=.020 if getattr(p,'_functional_source_initial',False)else.006
    return point


def _turn(p,ctx,g,target,held=False):
    from .execution_design_branch_rotation import turn_to_fixed_goal
    if held:
        state,_=p.snapshot();target=np.asarray(target)@np.asarray(state['phone']['mat']).T@np.asarray(p.a.tcp_rotation_task(g.side))
        def count():
            old=int(ctx.get('camera_end_legacy_held_commands_before_empty',0));used=int(ctx.get('functional_held_rotation_commands',0))
            if old+used>=80:raise ToolExecutionError('Original80 held rotation budget exhausted')
            ctx['functional_held_rotation_commands']=used+1
    else:
        def count():ctx['functional_empty_rotation_commands']=int(ctx.get('functional_empty_rotation_commands',0))+1
    return turn_to_fixed_goal(p,g.side,target,g,15. if held else 1.,count)


def solve(author):
    spec=author.scene.spec
    if spec.get('id')!='E13'or not author.control_report.get('engineering_reference_only'):raise ValueError('E13 engineering route required')
    goal=spec['goals'][0];zone=next(z for z in spec['zones']if z['id']==goal['target'])
    from .execution_design_e13_branch import prepare_context
    ctx=prepare_context(author,goal,zone,.98,spec.get('expert_action_budget',3000),author.c.steps);ctx.update(functional_phase='empty_stage',functional_side='left',functional_source_initial=True)
    return run(author,ctx)


def run(author,ctx):
    import json
    from .execution_design_e13_camera import AcquisitionGeometry,closed_phone_obstacle
    from .execution_design_e13_reedge import EdgeGeometry,sectional_contact_gap,SIDE_ROTATION
    from .execution_design_thin_edge import table_bounds_task,material_collision_points_task,trailing_edge_push_pose,actual_finger_points_task
    from .execution_design_e33_grasp import actual_mesh
    from .execution_design_branch_geometry import install_public_guard,HeldGeometry,collision_parts_task,swept_pose_clearance
    from .execution_design_branch_rotation import finish_accepted_public_rotation
    from .execution_design_tool_tracking import move_material
    from .execution_design_e13_release import actual_opening_bodies,landing_conditions
    from .execution_design_e13_branch import goal_rotation
    p=PhoneMoves(author);p.start=int(ctx.get('policy_start_step',0));p.limit=int(ctx.get('policy_action_budget',3000));side=ctx.get('functional_side','right');start=p.c.steps;ref=dict(actor='phone',local=[0.,0.,0.]);bounds=table_bounds_task(author.scene);p._functional_source_initial=bool(ctx.get('functional_source_initial'))
    ctx.setdefault('functional_phase','push_support');ctx['functional_scope']='coarse physical handling and ABC direction halfspaces; native scores unchanged'
    original=p.act
    def act(*args,**kwargs):
        result=original(*args,**kwargs);(author.out/'e13-functional-policy-context.private.json').write_text(json.dumps(dict(native_action=p.c.steps,context=ctx)));return result
    p.act=act
    if ctx['functional_phase']=='empty_stage':
        g=AcquisitionGeometry(p,side);install_public_guard(p,g);tip=p.tip(side);g.move(np.array([*tip[:2],1.08]));g.check(opening=True);p.act(side,'RELEASE');g=AcquisitionGeometry(p,side);install_public_guard(p,g)
        state,_=p.snapshot();g.move(np.array([-.2,p.tip(side)[1],1.08]));g.move(np.array([-.2,state['phone']['pos'][1],1.08]));_turn(p,ctx,g,np.diag([1.,-1.,-1.]));g.check(closing=True);p.act(side,'GRASP');ctx['functional_phase']='push_support'
    if ctx['functional_phase']=='push_support':
        g=AcquisitionGeometry(p,side,mode='closing');install_public_guard(p,g);axis=np.array([-1.,0.,0.])
        def contact():return any(p.contact('phone',f'{side}_finger{i}')for i in(1,2))
        def search():
            for _ in range(20):
                if contact():return
                gap=sectional_contact_gap(closed_phone_obstacle(p)[0],[actual_mesh(author,side,n)for n in author.scene.embodiment.fingers],axis,bounds['top'])
                if gap<-.002:raise ToolExecutionError('Real push toe overlap without contact')
                p.act(side,'BACK',mm=max(1.,min(4.,(gap+.0005)*1000)))
            raise ToolExecutionError('No real phone push contact')
        def seat():
            cloud=material_collision_points_task(p,ref);point,_=trailing_edge_push_pose(cloud,actual_finger_points_task(author,side),p.tip(side),axis,bounds['top'],clearance=.001,center_leading_toe=True);point[2]+=.001;high=max(float(p.tip(side)[2]),float(point[2])+.025)
            g.move(np.array([*p.tip(side)[:2],high]));g.move(np.array([*point[:2],high]));g.move(point,tolerance=.001);search()
        if not contact():
            if ctx.get('functional_resume_seated'):search()
            else:seat()
        history=[]
        while True:
            point=leading_section(p);remaining=float(point[0]-(bounds['lower'][0]-.020));ctx['functional_push_actual']=dict(actual_leading_point=point.tolist(),remaining_m=remaining)
            if remaining<=.002:break
            if not p.contact('phone','table'):raise ToolExecutionError('Phone lost real Table support during push')
            if not contact():seat()
            low=float(author.finger_geometry(side)['lowest_z_task_m'])
            if low>bounds['top']+.004:p.act(side,'DOWN',mm=min(3.,max(1.,(low-bounds['top']-.002)*1000)))
            p.act(side,'BACK',mm=min(8.,max(2.,remaining*1000)));history.append(float(point[0]))
            if len(history)>=12 and max(history[-12:])-min(history[-12:])<.001:raise ToolExecutionError('No real phone push progress')
        g.move(p.tip(side)+[0,0,.025]);g.check(opening=True);p.act(side,'RELEASE');ctx['functional_phase']='empty_face_turn'
    if ctx['functional_phase']=='empty_face_turn':
        g=AcquisitionGeometry(p,side);install_public_guard(p,g);tip=p.tip(side);g.move(np.array([*tip[:2],1.08]));point=leading_section(p);approach_y=float(point[1])+.15;ctx['functional_approach_y']=approach_y
        g.move(np.array([-.2,p.tip(side)[1],1.08]));g.move(np.array([-.2,approach_y,1.08]));current=np.asarray(author.tcp_rotation_task(side));angle=math.acos(float(np.clip((np.trace(SIDE_ROTATION@current.T)-1)/2,-1,1)))
        if angle>math.radians(170):p.act(side,'ROLL_RIGHT',degrees=10.);finish_accepted_public_rotation(p,side,g)
        _turn(p,ctx,g,SIDE_ROTATION);ctx['functional_phase']='face_entry'
    if ctx['functional_phase']=='face_entry':
        g=EdgeGeometry(p,side);install_public_guard(p,g);point=leading_section(p);ctx['functional_actual_grasp_point']=point.tolist();y=ctx['functional_approach_y']
        # Enter below the table from the unobstructed lateral side; all real
        # Table/phone/stand/passive-arm sweeps are checked per public action.
        if ctx.get('branch_params',{}).get('resume_face_outward_escape')is True:
            p.act(side,'BACK',mm=12.)
            point=point.copy();point[0]-=.006
            ctx['functional_actual_grasp_point']=point.tolist();ctx['functional_entry_escape']='public_BACK12 then actual edge-toe pinch; no route replay'
            g.move(point,tolerance=.004)
        else:
            for target in([p.tip(side)[0],y,.92],[point[0],y,.92],[point[0],y,point[2]],point):g.move(np.asarray(target),tolerance=.002)
        g.check(closing=True);g.mode='closing';stable=0
        for _ in range(5):
            p.act(side,'GRASP');stable=stable+1 if p.held(ref,side)else 0
            if stable>=3:break
        else:raise ToolExecutionError('Phone face grip lacks real bilateral hold')
        ctx['functional_first_hold_action']=p.c.steps;ctx['functional_phase']='lift'
    if ctx['functional_phase']=='lift':
        g=EdgeGeometry(p,side,mode='held');install_public_guard(p,g);history=[]
        while True:
            g();cloud=material_collision_points_task(p,ref);low=float(cloud[:,2].min());top=max(float(a[:,2].max())for a in collision_parts_task(p,p.s['stand']))
            if low>top+.025:break
            p.act(side,'UP',mm=12.);history.append(low)
            if len(history)>=12 and max(history[-12:])-min(history[-12:])<.001:raise ToolExecutionError('Phone did not lift clear')
        ctx['functional_phase']='transport_near_stand'
    if ctx['functional_phase']=='transport_near_stand':
        g=HeldGeometry(p,'phone',side);install_public_guard(p,g);state,_=p.snapshot();stand=state[p.s['stand']];high=max(float(state['phone']['pos'][2]),1.04)
        move_material(p,side,ref,np.array([-.10,float(stand['pos'][1]),high]),guard=g,tolerance=.006);ctx['functional_phase']='rough_ABC_orientation'
    if ctx['functional_phase']=='rough_ABC_orientation':
        g=HeldGeometry(p,'phone',side);install_public_guard(p,g)
        # Rotate near the support, avoiding long transport after a marginal grip.
        if ctx.get('branch_params',{}).get('coarse_orientation_escape1131')is True:
            if p.variant!='A'or not 1131<=p.c.steps<=1133:raise ValueError('Measured1131 A joint5 escape boundary required')
            def held_turn(token):
                used=int(ctx.get('functional_held_rotation_commands',0));legacy=int(ctx.get('camera_end_legacy_held_commands_before_empty',0))
                if legacy+used>=80:raise ToolExecutionError('Original80 held rotation budget exhausted')
                ctx['functional_held_rotation_commands']=used+1;p.act(side,token,degrees=10.);finish_accepted_public_rotation(p,side,g)
            held_turn('ROTATE_CCW')
            point=p.point(ref);move_material(p,side,ref,np.array([-.20,point[1],point[2]]),guard=g,tolerance=.006)
            for _ in range(6):held_turn('ROLL_LEFT')
            for _ in range(6):
                if rough_orientation(p)['correct']:break
                held_turn('PITCH_DOWN')
            if not rough_orientation(p)['correct']:raise ToolExecutionError('Coarse A camera/back halfspaces not reached after measured joint5 escape')
        elif not rough_orientation(p)['correct']:_turn(p,ctx,g,goal_rotation(ctx['goal']),held=True)
        ctx['functional_actual_orientation_before_release']=rough_orientation(p);ctx['functional_phase']='stand_release'
    if ctx['functional_phase']=='stand_release':
        if ctx.get('branch_params',{}).get('coarse_roll_clear1238')is True:
            if p.variant!='A'or not 1238<=p.c.steps<=1240:raise ValueError('Measured1238 joint5 transport escape required')
            g=HeldGeometry(p,'phone',side);install_public_guard(p,g)
            for _ in range(4):
                used=int(ctx.get('functional_held_rotation_commands',0));legacy=int(ctx.get('camera_end_legacy_held_commands_before_empty',0))
                if used+legacy>=80:raise ToolExecutionError('Original80 held rotation budget exhausted')
                ctx['functional_held_rotation_commands']=used+1;p.act(side,'ROLL_LEFT',degrees=10.);finish_accepted_public_rotation(p,side,g)
            if not rough_orientation(p)['correct']:raise ToolExecutionError('Coarse ABC direction lost during joint5 transport escape')
        if ctx.get('branch_params',{}).get('release_measured1221')is True:
            # Actual cameraZ.821/backX−.474 already satisfy coarse task rule.
            # Reanchor away from q5stop before translations; do not retain the
            # failed acceptedCW target or pursue an extra back-angle gate.
            g=HeldGeometry(p,'phone',side);install_public_guard(p,g)
            ctx['functional_held_rotation_commands']=int(ctx.get('functional_held_rotation_commands',0))+1
            p.act(side,'ROTATE_CCW',degrees=2.);finish_accepted_public_rotation(p,side,g)
        if ctx.get('branch_params',{}).get('coarse_back_to_stand1195')is True:
            g=HeldGeometry(p,'phone',side);install_public_guard(p,g)
            for _ in range(12):
                back=np.asarray(rough_orientation(p)['back_direction'])
                if back[0]<-.55:break
                angle=math.atan2(math.sin(-math.pi-math.atan2(back[1],back[0])),math.cos(-math.pi-math.atan2(back[1],back[0])))
                used=int(ctx.get('functional_held_rotation_commands',0));legacy=int(ctx.get('camera_end_legacy_held_commands_before_empty',0))
                if used+legacy>=80:raise ToolExecutionError('Original80 held rotation budget exhausted')
                ctx['functional_held_rotation_commands']=used+1;p.act(side,'ROTATE_CCW'if angle>0 else'ROTATE_CW',degrees=min(10.,max(.5,abs(math.degrees(angle)))));finish_accepted_public_rotation(p,side,g)
            else:raise ToolExecutionError('Phone back still grossly sideways to stand')
        from .execution_design_e13_camera_place import measured_stand_ledge
        g=HeldGeometry(p,'phone',side,allowed_payload=(p.s['stand'],));install_public_guard(p,g);state,_=p.snapshot();phone=state['phone'];points=material_collision_points_task(p,ref);lowband=points[points[:,2]<=points[:,2].min()+.005];front=lowband[lowband[:,0]>=lowband[:,0].max()-.002];point=front.mean(0);local=(point-np.asarray(phone['pos']))@np.asarray(phone['mat']);edge=dict(actor='phone',local=local.tolist());objects={o['id']:o for o in p.spec['objects']};stand=state[p.s['stand']];ledge=measured_stand_ledge(objects[p.s['stand']],p.s,stand['pos'],stand['mat']);top=max(float(a[:,2].max())for a in collision_parts_task(p,p.s['stand']));open_low=min(float(a[:,2].min())for a in actual_opening_bodies(p,side).values());height=max(float(ledge[2])+.012,top+.008-(open_low-point[2]));high=max(float(point[2]),height+.020)
        for target in([*point[:2],high],[*ledge[:2],high],[*ledge[:2],height]):move_material(p,side,edge,np.asarray(target),guard=g,tolerance=.006)
        AcquisitionGeometry(p,side,mode='closing').check(opening=True);p.act(side,'RELEASE');ctx['functional_phase']='withdraw';ctx['functional_release_action']=p.c.steps
    if ctx['functional_phase']=='withdraw':
        from .execution_design_contact_retreat import ContactRetreatGeometry
        from .execution_design_branch_geometry import swept_pose_clearance
        names=('panda_hand',*author.scene.embodiment.fingers)
        def clear():
            now=p.tip(side)
            try:swept_pose_clearance({n:actual_mesh(author,side,n)for n in names},now,now,np.eye(3),{'phone':closed_phone_obstacle(p)},bounds['top']);return True
            except ToolExecutionError:return False
        g=ContactRetreatGeometry(p,side,'phone',author.scene.embodiment.fingers,lambda:closed_phone_obstacle(p),[0,0,1],ctx,opening_envelope=False);install_public_guard(p,g);distance=0.
        while not clear()and distance<.030:p.act(side,'UP',mm=5.);distance+=.005
        if not clear():raise ToolExecutionError('Released phone hand did not separate')
        g=AcquisitionGeometry(p,side);install_public_guard(p,g);g.move(p.tip(side)+[0,0,.040]);ctx['functional_phase']='readback'
    if ctx['functional_phase']=='readback':
        state,_=p.snapshot();orientation=rough_orientation(p);unheld=not any(state['phone']['grasp']);contact=p.contact('phone',p.s['stand']);landing=landing_conditions(p);functional=bool(unheld and contact and orientation['correct'])
        result=dict(task='E13',variant=p.variant,actions=p.c.steps-start,functional_pass=functional,functional_observations=dict(orientation=orientation,actual_stand_contact=contact,unheld=unheld,actual_phone_position=list(map(float,state['phone']['pos']))),native_landing_conditions=landing,native_score_not_modified=True,source_initial=bool(ctx.get('functional_source_initial')),whole_task_score=None)
        (author.out/'functional-readback.private.json').write_text(json.dumps(result));return result
    raise ToolExecutionError('Unknown functional phone phase')
