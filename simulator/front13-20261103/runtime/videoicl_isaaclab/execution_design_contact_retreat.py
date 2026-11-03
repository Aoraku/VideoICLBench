"""Monotone public escape from an already-audited gripper contact."""
import math
import numpy as np
from .realworld_tool_expert import ToolExecutionError


def expanded_contact_facets(robot,obstacle,margin=.001):
    from scipy.spatial import ConvexHull,HalfspaceIntersection
    vertices=[]
    for points in(robot,obstacle):
        points=np.asarray(points,float);h=ConvexHull(points);equations=h.equations.copy();equations[:,3]-=margin
        expanded=HalfspaceIntersection(equations,points[h.vertices].mean(0)).intersections;vertices.append(expanded)
    a,b=vertices;difference=(b[:,None,:]-a[None,:,:]).reshape(-1,3)
    return ConvexHull(difference).equations


def convex_exit_certificate(robot,obstacle,axis,margin=.001,facets=None):
    """Exact expanded-convex translation depth and a nonincrease certificate.

    Collision translations form B - A. Inside this convex polytope, distance
    to its boundary is the minimum facet slack. An active outward facet with
    positive axis projection makes that minimum nonincreasing for the entire
    translation, rather than checking only a few sampled points.
    """
    axis=np.asarray(axis,float)
    if axis.shape!=(3,)or not np.isfinite(axis).all()or not np.isclose(np.linalg.norm(axis),1.):raise ValueError('Unit public retreat axis required')
    equations=expanded_contact_facets(robot,obstacle,margin)if facets is None else facets
    slack=-equations[:,3];depth=float(slack.min());active=np.flatnonzero(slack<=depth+1e-8)
    projections=equations[active,:3]@axis;k=int(active[np.argmax(projections)]);projection=float(equations[k,:3]@axis)
    all_proj=equations[:,:3]@axis;positive=all_proj>1e-8
    distance=float(np.min((slack[positive]+.001)/all_proj[positive]))if np.any(positive)else None
    return dict(expanded_translation_penetration_m=depth,active_outward_normal=equations[k,:3].tolist(),
        outward_public_axis_projection=projection,monotone_for_entire_translation=projection>=-1e-9,
        required_exit_distance_m=distance,
        original_expansion_margin_each_body_m=margin,minkowski_facets=len(equations))


class ContactRetreatGeometry:
    def __init__(self,p,side,actor,allowed,obstacle_parts,axis,context,opening_envelope=True):
        self.p=p;self.side=side;self.actor=actor;self.allowed=set(allowed);self.parts=obstacle_parts;self.axis=np.asarray(axis,float);self.context=context;self.previous={};self.last={};self.cache={};self.opening_envelope=opening_envelope
    def check(self,target=None,rotation=None):
        from .execution_design_e33_grasp import actual_mesh
        from .execution_design_thin_edge import table_bounds_task
        from .execution_design_branch_geometry import swept_pose_clearance,collision_parts_task
        p=self.p;tip=p.tip(self.side);target=tip if target is None else np.asarray(target,float)
        if rotation is not None and not np.allclose(rotation,np.eye(3),atol=1e-9):raise ToolExecutionError('Initial contact retreat may not rotate')
        delta=target-tip;distance=float(delta@self.axis)
        if distance<-.000001 or np.linalg.norm(delta-self.axis*distance)>.000001:raise ToolExecutionError('Initial contact retreat requires its certified public axis')
        from .execution_design_e13_release import actual_opening_bodies
        bodies=actual_opening_bodies(p,self.side)if self.opening_envelope else{n:actual_mesh(p.a,self.side,n)for n in('panda_hand',*p.a.scene.embodiment.fingers)}
        state,_=p.snapshot()
        if any(state[self.actor]['grasp'])or not(p.contact(self.actor,'table')or p.contact(self.actor,p.s['stand'])):
            raise ToolExecutionError('Initial finger retreat requires the released phone to retain actual support')
        obstacles={n:collision_parts_task(p,n)for n in state if n!=self.actor}
        other='right'if self.side=='left'else'left';links=('panda_link0','panda_link1','panda_link2','panda_link3','panda_link4','panda_link5','panda_link6','panda_link7','panda_hand',*p.a.scene.embodiment.fingers)
        obstacles.update({other+'_'+n:[actual_mesh(p.a,other,n)]for n in links});table=table_bounds_task(p.a.scene)['top']
        swept_pose_clearance(bodies,tip,target,np.eye(3),obstacles,table)
        phone=self.parts();strict={n:a for n,a in bodies.items()if n not in self.allowed}
        swept_pose_clearance(strict,tip,target,np.eye(3),{self.actor:phone},table)
        rows={}
        for name in self.allowed:
            import hashlib
            cloud=np.concatenate(phone);key=hashlib.sha256(bodies[name].tobytes()+cloud.tobytes()).hexdigest()
            if name not in self.cache or self.cache[name][0]!=key:
                self.cache[name]=(key,expanded_contact_facets(bodies[name],cloud),expanded_contact_facets(bodies[name],cloud,0.))
            cert=convex_exit_certificate(bodies[name],cloud,self.axis,facets=self.cache[name][1])
            actual=convex_exit_certificate(bodies[name],cloud,self.axis,margin=0.,facets=self.cache[name][2])
            depth=max(0.,actual['expanded_translation_penetration_m']);initial=self.previous.setdefault(name,depth)
            # Only the already-contacting released finger gets this numerical
            # contact allowance. Expanded1mm hull overlap is not penetration.
            permitted=initial+.0001
            if depth>permitted:raise ToolExecutionError('Actual initial finger contact penetration clearly increased during retreat')
            cert.update(actual_unexpanded_translation_penetration_m=actual['expanded_translation_penetration_m'],physical_contact_depth_m=depth,
                physical_monotone_for_entire_translation=actual['monotone_for_entire_translation'])
            rows[name]=cert
        self.last=rows;self.context['phone_contact_retreat_last']=rows
        return rows
    def __call__(self):
        result=self.check()
        return result
    def rotate(self,*args):raise ToolExecutionError('Contact retreat cannot rotate before separation')


def retreat_phone_contact(p,context,parts,opening_envelope=True,audited_boundary_fingers=()):
    from .execution_design_e33_grasp import actual_mesh
    from .execution_design_branch_geometry import swept_pose_clearance,install_public_guard
    from .execution_design_thin_edge import table_bounds_task
    side='right';actor='phone';tip=p.tip(side);table=table_bounds_task(p.a.scene)['top'];names=('panda_hand',*p.a.scene.embodiment.fingers)
    def full_clear():
        bodies={n:actual_mesh(p.a,side,n)for n in names};now=p.tip(side)
        try:swept_pose_clearance(bodies,now,now,np.eye(3),{actor:parts()},table);return True
        except ToolExecutionError:return False
    if full_clear():return dict(public_actions=0,already_separated=True)
    state,contacts=p.snapshot();allowed=[]
    for i,name in enumerate(p.a.scene.embodiment.fingers,1):
        if frozenset((actor,side+'_finger'+str(i)))in contacts:allowed.append(name)
    if not allowed:
        params=context.get('branch_params',{});audited=params.get('audited_initial_phone_contact_fingers',[])
        audited_action=params.get('audited_initial_phone_contact_action',1559)
        if audited==['right_finger1']and audited_action in(1559,1564,1566)and p.c.steps==audited_action:
            allowed=[p.a.scene.embodiment.fingers[0]]
    if audited_boundary_fingers:
        if opening_envelope or p.c.steps!=1786 or tuple(audited_boundary_fingers)!=('right_finger1','right_finger2'):
            raise ValueError('Only exact native1786 previously bilateral closed-phone boundary is audited')
        allowed=list(p.a.scene.embodiment.fingers)
    if not allowed:raise ToolExecutionError('Contact retreat requires an actual or exact audited native boundary finger contact')
    from .execution_design_e13_release import actual_opening_bodies
    actor_points=np.concatenate(parts());current={n:actual_mesh(p.a,side,n)for n in names};bodies=actual_opening_bodies(p,side)if opening_envelope else current;choices=[]
    facets={n:expanded_contact_facets(bodies[n],actor_points)for n in allowed}
    raw_facets={n:expanded_contact_facets(bodies[n],actor_points,0.)for n in allowed}
    for n in allowed:
        current_depth=max(0.,float((-expanded_contact_facets(current[n],actor_points,0.)[:,3]).min()))
        envelope_depth=max(0.,float((-raw_facets[n][:,3]).min()))
        if envelope_depth>current_depth+1e-5:
            raise ToolExecutionError('Remaining public gripper opening would increase initial contact penetration')
    for k in range(3):
        for sign in(1.,-1.):
            axis=np.eye(3)[k]*sign;certs=[convex_exit_certificate(bodies[n],actor_points,axis,facets=facets[n])for n in allowed]
            physical=[convex_exit_certificate(bodies[n],actor_points,axis,margin=0.,facets=raw_facets[n])for n in allowed]
            if not all(c['monotone_for_entire_translation']for c in physical)or not all(c['required_exit_distance_m']is not None for c in certs):continue
            distance=max(c['required_exit_distance_m']for c in certs)
            if not np.isfinite(distance)or distance<=.0001:continue
            g=ContactRetreatGeometry(p,side,actor,allowed,parts,axis,context,opening_envelope=opening_envelope)
            try:g.check(target=tip+axis*distance)
            except ToolExecutionError:continue
            choices.append((distance,k,sign,g,certs))
    if not choices:raise ToolExecutionError('No actual monotone one-axis contact escape with a clear endpoint')
    for distance,k,sign,g,certs in sorted(choices,key=lambda x:x[0]):
        requested=context.get('branch_params',{}).get('phone_contact_retreat_public_axis')
        token=(('FWD','BACK'),('LEFT','RIGHT'),('UP','DOWN'))[k][int(sign<0)]
        if requested is not None and requested!=token:continue
        target=tip+np.eye(3)[k]*sign*distance
        end={n:a+target-tip for n,a in bodies.items()}
        try:swept_pose_clearance(end,target,target,np.eye(3),{actor:parts()},table)
        except ToolExecutionError:continue
        break
    else:raise ToolExecutionError('No certified initial-contact retreat ends fully separated')
    context['phone_contact_retreat_plan']=dict(allowed_initial_finger_bodies=allowed,public_axis=k,sign=sign,distance_m=distance,
        native_steps_at_plan=p.c.steps,certificates=certs,table_and_other_objects_guard_unchanged=True,
        static_shape_exit_distance_m=distance,actual_withdrawal_step_mm=4.,maximum_commanded_withdrawal_mm=30.,initial_contact_numerical_allowance_m=.0001,
        actual_complete_hand_endpoint_requires_original_margin=True)
    import json,hashlib
    proof=dict(native_steps_at_plan=p.c.steps,method='Expanded source convex Minkowski translation facets; minimum translation depth cannot increase along certified axis',
        actual_robot_bodies_task={n:a.tolist()for n,a in current.items()},remaining_full_opening_envelopes_task={n:a.tolist()for n,a in bodies.items()},
        complete_actual_phone_cooked_vertices_task=actor_points.tolist(),plan=context['phone_contact_retreat_plan'])
    raw=json.dumps(proof).encode();path=p.a.out/'phone-initial-contact-retreat-evidence.private.json';path.write_bytes(raw)
    context['phone_contact_retreat_source_evidence']=dict(path=str(path),sha256=hashlib.sha256(raw).hexdigest())
    install_public_guard(p,g);start=p.c.steps;axis=np.eye(3)[k]*sign;token=(('FWD','BACK'),('LEFT','RIGHT'),('UP','DOWN'))[k][int(sign<0)];commanded=0.;force_baseline=None
    while not full_clear():
        g()
        forces=getattr(p.c,'contact_forces',{});force=sum(float(forces.get(frozenset((actor,side+'_finger'+str(i+1))),0.))for i,n in enumerate(p.a.scene.embodiment.fingers)if n in allowed)
        if force_baseline is None and force>0:force_baseline=force
        if force_baseline is not None and force>max(force_baseline*2,force_baseline+1.):raise ToolExecutionError('Released initial finger contact force clearly increased during withdrawal')
        context['phone_contact_retreat_force_readback']=dict(actual_n=force,initial_positive_n=force_baseline)
        if commanded>=30.:raise ToolExecutionError('Actual released finger remains in contact after30mm public withdrawal')
        mm=min(4.,30.-commanded,p.max_mm);p.act(side,token,mm=mm);commanded+=mm
    context['phone_contact_retreat_actual']=dict(public_actions=p.c.steps-start,fully_separated_by_original_guard=True,last_certificates=g.last)
    return context['phone_contact_retreat_actual']
