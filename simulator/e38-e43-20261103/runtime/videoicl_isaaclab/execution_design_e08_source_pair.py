"""Source-initial E08: actual upper-COM pinches and two physical box corridors."""
import math
import numpy as np
from .realworld_tool_expert import ToolExecutionError,_axis_rotation
from .execution_design_e08_reference import MeasuredShoeAuthor


def nearest_down_jaw(current,shoe_rotation):
    """Equivalent jaw assignments use the closest reachable hand orientation."""
    from .author_orientation import _axis_angle
    y=np.asarray(shoe_rotation,float)[:,1].copy();y[2]=0.;y/=np.linalg.norm(y);z=np.array([0.,0.,-1.])
    choices=[np.column_stack((np.cross(sign*y,z),sign*y,z))for sign in(1.,-1.)]
    return min(choices,key=lambda r:_axis_angle(r@np.asarray(current).T)[1])


def first_cooked_contact_height(pieces,xy,obstacles):
    """First physical contact when lowering the entire actual nonconvex shoe."""
    from scipy.spatial import ConvexHull
    xy=np.asarray(xy,float);heights=[]
    for a in pieces:
        for b in obstacles:
            if np.any(np.asarray(a).min(0)[:2]+xy>np.asarray(b).max(0)[:2])or np.any(np.asarray(a).max(0)[:2]+xy<np.asarray(b).min(0)[:2]):continue
            eq=ConvexHull((np.asarray(b)[:,None,:]-np.asarray(a)[None,:,:]).reshape(-1,3)).equations;low=-float('inf');high=float('inf');valid=True
            for nx,ny,nz,offset in eq:
                rhs=-float(np.array([nx,ny])@xy+offset)
                if abs(nz)<1e-10:
                    if rhs< -1e-8:valid=False;break
                elif nz>0:high=min(high,rhs/nz)
                else:low=max(low,rhs/nz)
            if valid and low<=high+1e-8 and np.isfinite(high):heights.append(float(high))
    if not heights:raise ToolExecutionError('No physical cooked support below the complete shoe')
    return max(heights)


def packing_plan(p,context):
    from .execution_design_thin_edge import material_collision_points_task
    from .execution_design_branch_geometry import collision_parts_task
    from .e08_packing_recipe import RECIPES,SOURCE_SHA256
    state,_=p.snapshot();name=context['actor'];body=state[name];box=state['box'];r=np.asarray(body['mat']);pos=np.asarray(body['pos']);br=np.asarray(box['mat']);bp=np.asarray(box['pos']);relative=br.T@r
    if p.objects[name]['source_asset']['sha256']!=SOURCE_SHA256[name]:raise ValueError('Original source-bound packing shoe required')
    points=(material_collision_points_task(p,dict(actor=name))-pos)@r;shape=points@relative.T
    pieces=[((a-pos)@r)@relative.T for a in collision_parts_task(p,name)];obstacles=[(a-bp)@br for a in collision_parts_task(p,'box')]
    # The already released source shoe is a real obstacle and legal support.
    other='right_shoe'if name=='left_shoe'else'left_shoe'
    obstacles.extend((a-bp)@br for a in collision_parts_task(p,other))
    xy=np.array(RECIPES[p.variant][name]['origin_box'][:2]);z=first_cooked_contact_height(pieces,xy,obstacles);origin=np.r_[xy,z]
    cavity=p.s['containers']['box'];lo=np.array(cavity['lower'])-[.002,.002,.003];hi=np.array(cavity['upper'])+[.002,.002,.003];posed=shape+origin;margin=np.minimum(posed.min(0)-lo,hi-posed.max(0))
    axes=p.s['shoe_axes'][name];toe=relative@(np.asarray(axes['toe_local'])-axes['heel_local']);label=np.asarray(p.s['label_end']['point_local']);cosine=float(toe@label/np.linalg.norm(toe)/np.linalg.norm(label));wanted=({'left_shoe':1,'right_shoe':1},{'left_shoe':-1,'right_shoe':-1},{'left_shoe':1,'right_shoe':-1})[p.index][name]
    future_joint_clear=True
    if name=='left_shoe':
        from scipy.spatial import ConvexHull
        from scipy.optimize import linprog
        other_body=state[other];other_pos=np.asarray(other_body['pos']);other_r=np.asarray(other_body['mat']);recipe=RECIPES[p.variant][other]
        future=[((a-other_pos)@other_r)@np.asarray(recipe['rotation_box']).T+np.asarray(recipe['origin_box'])for a in collision_parts_task(p,other)]
        for a in pieces:
            aa=a+origin
            for b in future:
                if np.any(aa.max(0)<b.min(0))or np.any(b.max(0)<aa.min(0)):continue
                eq=np.r_[ConvexHull(aa).equations,ConvexHull(b).equations]
                lp=linprog([0.,0.,0.,-1.],A_ub=np.c_[eq[:,:3],np.ones(len(eq))],b_ub=-eq[:,3],bounds=[(None,None)]*4,method='highs')
                if not lp.success:raise ToolExecutionError('Joint original cooked packing separation unresolved')
                if lp.x[3]>.0001:future_joint_clear=False
    result=dict(acceptable=bool(np.all(margin>=0)and cosine*wanted>.9 and future_joint_clear),future_other_source_joint_nonpenetration=future_joint_clear,inside_original_cavity=bool(np.all(margin>=0)),correct_label_direction=cosine*wanted>.9,
        native_toe_label_cosine=cosine,native_cavity_margin_xyz_m=margin.tolist(),first_actual_cooked_contact_origin_z=float(z),
        destination_point_task=(bp+br@(origin+relative@np.asarray(context['control_local']))).tolist(),joint_recipe_source='actual1341_cook22x2_box17_minkowski_joint_terminal',original_native_geometry_unchanged=True)
    context['source_initial_packing_plan']=result;context['destination_point_task']=result['destination_point_task']
    return result


def orient_for_packing(p,context,guard):
    from .execution_design_branch_rotation import turn_to_fixed_goal
    from .author_orientation import _axis_angle
    actor=context['actor'];side=context['side'];state,_=p.snapshot();target=np.asarray(context['target_actor_rotation']);current=np.asarray(state[actor]['mat']);hand=np.asarray(p.a.tcp_rotation_task(side))
    absolute=target@current.T@hand
    def count():
        if int(context['rotation_commands_used'])>=120:raise ToolExecutionError('Original120 rotation bound exhausted')
        context['rotation_commands_used']+=1
    _,angle=_axis_angle(absolute@hand.T)
    if angle>math.radians(170.):
        from .execution_design_branch_rotation import finish_accepted_public_rotation
        robot=p.a.scene.robots[side];ids,_=robot.find_joints(['panda_joint7'],preserve_order=True);q7=float(robot.data.joint_pos[0,ids[0]]);count();p.act(side,'ROTATE_CCW'if q7>=0 else'ROTATE_CW',degrees=10.);finish_accepted_public_rotation(p,side,guard)
    context['coarse_planned_hand_turn']=turn_to_fixed_goal(p,side,absolute,guard,5.,count)
    # Apply the one planned small roll component as a public command. No
    # repeated refinement of native containment or contact margins follows.
    axis,remaining=_axis_angle(absolute@np.asarray(p.a.tcp_rotation_task(side)).T)
    if remaining>math.radians(3.):
        from .execution_design_branch_rotation import finish_accepted_public_rotation
        k=int(np.argmax(abs(axis)));labels=(('ROLL_LEFT','ROLL_RIGHT'),('PITCH_UP','PITCH_DOWN'),('ROTATE_CCW','ROTATE_CW'));count();p.act(side,labels[k][int(axis[k]<0)],degrees=min(10.,max(.5,abs(math.degrees(remaining*axis[k])))));finish_accepted_public_rotation(p,side,guard)
    return None


def functional_shoe_readback(p,actor):
    from .execution_design_thin_edge import material_collision_points_task
    from .execution_design_e08_branch import _native_landing_conditions
    state,_=p.snapshot();box=state['box'];body=state[actor];points=material_collision_points_task(p,dict(actor=actor));local=(points-np.asarray(box['pos']))@np.asarray(box['mat']);c=p.s['containers']['box'];lo=np.asarray(c['lower']);hi=np.asarray(c['upper']);native=_native_landing_conditions(p,dict(actor=actor,midfoot_grasp_strategy='sourceinitial_upper_com_pair_v1'))
    xy=np.all((local[:,:2]>=lo[:2]-.020)&(local[:,:2]<=hi[:2]+.020),axis=1);span=float(np.ptp(local[:,2]));below=max(0.,min(float(local[:,2].max()),float(hi[2])+.010)-float(local[:,2].min()))/span
    wanted=({'left_shoe':1,'right_shoe':1},{'left_shoe':-1,'right_shoe':-1},{'left_shoe':1,'right_shoe':-1})[p.index][actor]
    other='right_shoe'if actor=='left_shoe'else'left_shoe';supported=p.contact(actor,'box')or p.contact(actor,other);unheld=not any(body['grasp'])and native['hand_force_n']<.05
    passed=bool(float(xy.mean())>=.75 and float(local[:,2].max())<=float(hi[2])+.012 and native['toe_label_cosine']*wanted>.1 and supported and unheld and float(points[:,2].min())>=.797)
    return dict(functional_pass=passed,actual_support_contact=supported,unheld=unheld,inside_box20mm_XY_fraction=float(xy.mean()),vertical_envelope_below_rim10mm_fraction=below,actual_protrusion_above_original_rim_m=max(0.,float(local[:,2].max())-float(hi[2])),toe_correct_halfspace=native['toe_label_cosine']*wanted>.1,native_conditions=native,native_score_not_modified=True)


def functional_release(p,context):
    from .execution_design_e13_release import actual_opening_bodies
    from .execution_design_branch_geometry import swept_pose_clearance,collision_parts_task,install_public_guard
    from .execution_design_e08_shape_guard import SourceShoeGeometry
    from .execution_design_thin_edge import table_bounds_task
    actor=context['actor'];side=context['side'];p.require_held(dict(actor=actor),side);state,_=p.snapshot();tip=p.tip(side)
    # Exact physical sweep, without an extra1mm wall/neighbor proximity promise.
    swept_pose_clearance(actual_opening_bodies(p,side),tip,tip,np.eye(3),{n:collision_parts_task(p,n)for n in state if n!=actor},table_bounds_task(p.a.scene)['top'],margin=0.)
    p.act(side,'RELEASE');g=SourceShoeGeometry(p,actor,side,require_hold=False);install_public_guard(p,g);g.move(p.tip(side)+[0,0,.060]);row=functional_shoe_readback(p,actor)
    return dict(native_landing_conditions=row['native_conditions'],functional=row)


def solve(author,resume_context=None):
    from .execution_design_e08_branch import prepare_context,prepare_new_source_context,_native_landing_conditions,release_source_left_here
    from .execution_design_e08_midfoot import SoleAcquisitionGeometry,native_local_com,midfoot_section
    from .execution_design_e08_shape_guard import SourceShoeGeometry
    from .execution_design_branch_geometry import install_public_guard,collision_parts_task
    from .execution_design_branch_rotation import turn_to_fixed_goal
    from .execution_design_thin_edge import material_collision_points_task
    from .execution_design_e13_release import actual_opening_bodies
    p=MeasuredShoeAuthor(author);start=p.c.steps;p.max_mm=min(12.,float(author.scene.embodiment.config['control']['step_mm'][1]));history={}
    if p.spec.get('execution_design',{}).get('revision')!='embodied50-execution-v3-20261102'or not author.control_report.get('engineering_reference_only'):raise ValueError('E08 source-initial engineering-only route required')
    context={} if resume_context is None else resume_context
    if resume_context is not None:
        p.start=int(resume_context.get('policy_start_step',0));p.limit=int(resume_context.get('policy_action_budget',3000));history=resume_context.get('source_actor_rotation_history',{})
    original_public_act=p.act
    def record_public_act(*args,**kwargs):
        import json
        result=original_public_act(*args,**kwargs)
        (author.out/'e08-source-pair-policy-context.private.json').write_text(json.dumps(dict(native_action=p.c.steps,context=context)))
        return result
    p.act=record_public_act
    if resume_context is None:
        park=SoleAcquisitionGeometry(p,'left_shoe','left');install_public_guard(p,park);tip=p.tip('left');park.move(np.array([tip[0],.48,max(float(tip[2]),1.04)]))
    actors=('right_shoe',)if resume_context is not None and context.get('coarse_skip_completed_left')else(('left_shoe','right_shoe')if resume_context is None or resume_context['actor']=='left_shoe'else('right_shoe',))
    for actor in actors:
        resumed=resume_context is not None and actor==resume_context['actor']
        if resumed:
            context=resume_context;side=context['side'];history=context.get('source_actor_rotation_history',history);p.require_held(dict(actor=actor),side)
        else:
            state,_=p.snapshot();new_context=prepare_context(author,state,p.c.steps,actor);new_context.update(side='right',midfoot_grasp_strategy='sourceinitial_upper_com_pair_v1',source_initial_physical_route=True,source_actor_rotation_history=history)
            if resume_context is not None:resume_context.clear();resume_context.update(new_context);context=resume_context
            else:context=new_context
            side='right';p.stage('source-com-acquire-'+actor)
            if not getattr(p,'_right_initial_raised',False):
                for _ in range(3):p.act(side,'UP',mm=12.)
                p._right_initial_raised=True
            empty=SoleAcquisitionGeometry(p,actor,side);install_public_guard(p,empty)
            tip=p.tip(side);height=max(float(tip[2]),1.04);empty.move(np.array([tip[0],tip[1],height]));empty.check(closing=False);p.act(side,'RELEASE');empty=SoleAcquisitionGeometry(p,actor,side);install_public_guard(p,empty)
            state,_=p.snapshot();source=np.asarray(state[actor]['pos']);empty.move(np.array([-.2,p.tip(side)[1],height]));empty.move(np.array([-.2,source[1],height]))
            empty.move(np.array([-.2,source[1],.98]));height=.98
            target=nearest_down_jaw(author.tcp_rotation_task(side),state[actor]['mat'])
            def count():
                if context['rotation_commands_used']>=120:raise ToolExecutionError('Original120 rotation bound exhausted')
                context['rotation_commands_used']+=1
            context['source_initial_empty_turn']=turn_to_fixed_goal(p,side,target,empty,1.,count)
            com,mass=native_local_com(p,actor);pos,r=p.frame(dict(actor=actor));section=midfoot_section((material_collision_points_task(p,dict(actor=actor))-pos)@r,com);context.update(midfoot_source_grasp_local=section['grasp_local'],midfoot_actual_com_local=com.tolist(),midfoot_actual_mass_kg=mass)
            point=p.point(dict(actor=actor,local=section['grasp_local']));empty.move(np.array([point[0],p.tip(side)[1],height]));empty.move(np.array([*point[:2],height]));empty.move(point,tolerance=.0008)
            empty.check(closing=True);empty.mode='closing';stable=0
            for _ in range(5):
                p.act(side,'GRASP');stable=stable+1 if p.held(dict(actor=actor),side)else 0
                if stable>=3:break
            else:raise ToolExecutionError('Source-initial COM pinch lacks three actual bilateral receipts')
            empty.mode='held';empty.allow_table_departure=True;history_lift=[]
            while True:
                empty();points=material_collision_points_task(p,dict(actor=actor));low=float(points[:,2].min());rim=max(float(a[:,2].max())for a in collision_parts_task(p,'box'))
                if low>rim+.050:break
                p.act(side,'UP',mm=12.);history_lift.append(low)
                if len(history_lift)>=13 and max(history_lift[-12:])-history_lift[-13]<.0003:raise ToolExecutionError('Source-initial COM lift stalled')
        context.update(prepare_new_source_context(author,context));context.update(midfoot_grasp_strategy='sourceinitial_upper_com_pair_v1',source_initial_physical_route=True)
        from .e08_packing_recipe import RECIPES
        state,_=p.snapshot();context['target_actor_rotation']=(np.asarray(state['box']['mat'])@np.asarray(RECIPES[p.variant][actor]['rotation_box'])).tolist()
        guard=SourceShoeGeometry(p,actor,side);install_public_guard(p,guard);p.stage('source-com-pack-'+actor)
        if not(resumed and context.get('coarse_continue_transport')):
            guard.move(np.array([-.2,p.tip(side)[1],max(float(p.tip(side)[2]),1.04)]))
        if not(resumed and context.get('coarse_keep_escape_yaw')):orient_for_packing(p,context,guard)
        ref=dict(actor=actor,local=context['control_local']);plan=packing_plan(p,context);destination=np.asarray(plan['destination_point_task']);point=p.point(ref)
        rim=max(float(a[:,2].max())for a in collision_parts_task(p,'box'));low=float(material_collision_points_task(p,dict(actor=actor))[:,2].min());high=rim+.040+(float(point[2])-low)
        p.move_point(side,ref,[*point[:2],high],guard,tolerance=.006)
        # Bring the cross-table supply toward this hand's base before reaching
        # forward; X-first at far +Y put right Panda q4 at straight extension.
        if side=='right':p.move_point(side,ref,[p.point(ref)[0],destination[1],high],guard,tolerance=.006)
        else:p.move_point(side,ref,[destination[0],p.point(ref)[1],high],guard,tolerance=.006)
        p.move_point(side,ref,[*destination[:2],high],guard,tolerance=.006)
        # Stop lowering on real support or once above the actual rim; a
        # held material-point promise must not force a supported shoe deeper.
        other='right_shoe'if actor=='left_shoe'else'left_shoe';guard=SourceShoeGeometry(p,actor,side,allowed_payload=('box',other));install_public_guard(p,guard)
        while True:
            low=min(float(material_collision_points_task(p,dict(actor=actor))[:,2].min()),min(float(a[:,2].min())for a in actual_opening_bodies(p,side).values()))
            if p.contact(actor,'box')or p.contact(actor,other)or low<=rim+.018:break
            p.act(side,'DOWN',mm=min(12.,max(2.,(low-rim-.014)*1000)))
        result=functional_release(p,context)
        history[actor]=dict(actual_landing=result['native_landing_conditions'],functional=result['functional'],rotation_commands_used=context['rotation_commands_used'],strategy='sourceinitial_upper_com_pair_v1')
        # End-source hand is empty and clear; its next symmetric jaw assignment
        # is selected from actual orientation instead of an extra180 turn.
        if actor!=actors[-1]:
            empty=SoleAcquisitionGeometry(p,actor,side);install_public_guard(p,empty);tip=p.tip(side)
            empty.move(np.array([tip[0],.48 if side=='left'else-.48,max(float(tip[2]),1.04)]))
    pair={name:_native_landing_conditions(p,dict(actor=name,midfoot_grasp_strategy='sourceinitial_upper_com_pair_v1'))for name in history}
    functional={name:functional_shoe_readback(p,name)for name in history}
    result=dict(task='E08',variant=p.variant,actions=p.c.steps-start,source_initial=resume_context is None,functional_checkpoint_chain=resume_context is not None,operations=p.operations,actual_native_pair_conditions=pair,functional_pass=all(r['functional_pass']for r in functional.values()),functional_observations=functional,native_score_not_modified=True,execution_finished=True,physics_success_not_asserted=True)
    import json
    (author.out/'functional-readback.private.json').write_text(json.dumps(result))
    return result
