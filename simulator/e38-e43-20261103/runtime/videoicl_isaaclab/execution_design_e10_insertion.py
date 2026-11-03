"""Engineering-only E10 measured multi-hole/post insertion with public actions."""
import math
import numpy as np
from .realworld_tool_expert import ToolExecutionError
from .execution_design_e10_reference import post_transport_height


def planned_post_rotation(rotation):
    """Use a reachable six-degree lean inside the original physical bore rule."""
    r=np.asarray(rotation,float)
    if r.shape!=(3,3)or not np.isfinite(r).all()or not np.allclose(r.T@r,np.eye(3),atol=1e-5):
        raise ToolExecutionError('Proper original post placement rotation required')
    if np.allclose(r[2],[0,0,1],atol=1e-5):
        from .realworld_tool_expert import _axis_rotation
        return _axis_rotation([0,1,0],math.radians(-6.))@r
    return r


def post_rotation_for_object(author,name,rotation):
    holes=author.s['holes'][name]
    if len(holes)==1 and np.linalg.norm(np.asarray(holes[0]['center_local'])[:2])<1e-6:
        # A centered circular bore has no task yaw requirement. Keep its
        # current yaw instead of spending wrist actions turning it90degrees.
        from .realworld_tool_expert import _axis_rotation
        _,current=author.frame({'actor':name})
        rotation=_axis_rotation([0,0,1],math.atan2(current[1,0],current[0,0]))
    return planned_post_rotation(rotation)


def turn_to_post_rotation(author,name,side,rotation):
    """Finish accepted public rotations before another increment, above posts."""
    from .execution_design_branch_geometry import HeldGeometry,install_public_guard
    from .execution_design_branch_rotation import turn_to_fixed_goal
    _,current=author.frame({'actor':name})
    target=np.asarray(rotation)@np.asarray(current).T@np.asarray(author.a.tcp_rotation_task(side))
    geometry=HeldGeometry(author,name,side);original=author.act
    had_original=hasattr(author,'_branch_public_original_act')
    install_public_guard(author,geometry)
    try:return turn_to_fixed_goal(author,side,target,geometry,1.,lambda:author.require_held({'actor':name},side))
    finally:
        author.act=original
        if not had_original:del author._branch_public_original_act


def post_clearances(author,name,indices):
    holes=author.s['holes'][name]
    if len(holes)!=len(indices)or len(set(indices))!=len(indices):
        raise ToolExecutionError('E10 every physical hole needs its own actual post')
    _,rotation=author.frame({'actor':name});rows=[]
    for hole,index in zip(holes,indices):
        post=author.s['posts'][index]
        base=author.body_point(post['ref'],post['base_local']);tip=author.body_point(post['ref'],post['tip_local'])
        axis=tip-base;axis=axis/np.linalg.norm(axis)
        center=author.body_point({'actor':name},hole['center_local'])
        normal=rotation@np.asarray(hole['axis_local']);normal=normal/np.linalg.norm(normal)
        cosine=abs(float(normal@axis));lateral=center-base-axis*float((center-base)@axis)
        # Bound the projected cylinder and the whole six-mm bore, not only
        # one center point that can look aligned while the other holes jam.
        skew=float(hole['half_depth'])*math.sqrt(max(0.,1-cosine*cosine))/max(cosine,1e-9)
        margin=float(hole['radius'])-float(post['radius'])/max(cosine,1e-9)-float(np.linalg.norm(lateral))-skew
        signed=float(normal@axis);length=float(np.linalg.norm(tip-base))
        along=float((center-base)@normal/signed)if abs(signed)>1e-9 else math.inf
        offset=float(np.linalg.norm(base+along*axis-center))
        native_margin=float(hole['radius'])+.0005-float(post['radius'])-offset
        rows.append(dict(margin_m=margin,gap_above_tip_m=float((center-tip)@axis),axis_dot=cosine,
            height_above_base_m=float((center-base)@axis),post_length_m=length,
            native_radial_margin_m=native_margin,native_along_m=along,
            native_threaded=bool(cosine>=.98 and 0<along<length-float(hole['half_depth'])-.001 and native_margin>=0.),
            coarse_shaft_crosses_bore=bool(cosine>=.90 and 0<along<length-float(hole['half_depth'])-.001 and native_margin>=0.)))
    return rows


def thread_piece(author,name,ref,side,target,rotation,indices,support):
    if author.task!='E10' or not getattr(author.a,'control_report',{}).get('engineering_reference_only'):
        raise ToolExecutionError('E10 independent engineering control required')
    record_runtime_shape_count(author,name)
    rotation=post_rotation_for_object(author,name,rotation);target=np.asarray(target,float)
    holes=author.s['holes'][name];control=dict(actor=name,local=holes[0]['center_local'])
    guard=lambda:author.require_held(ref,side)
    author.stage('thread-real-holes-'+name)
    # A restored suffix must use the same measured corridor as a full run.
    # StructuralAuthor's default1.15m stow is outside this far-post workspace.
    height=post_transport_height(author,name,side,holes[0]['center_local'],target,rotation)
    author.move_point(side,control,[*author.point(control)[:2],height],guard)
    turn_to_post_rotation(author,name,side,rotation)
    author.move_point(side,control,[*target[:2],height],guard)
    post=author.s['posts'][indices[0]];top=author.body_point(post['ref'],post['tip_local'])
    approach=np.array([*target[:2],float(top[2])+.020])
    author.move_point(side,control,approach,guard)
    return thread_precision(author,name,ref,side,target,rotation,indices,support)


def thread_precision(author,name,ref,side,target,rotation,indices,support,*,descent_mm=2.,release=True):
    """Resume measured holes at their current pose without a new high approach."""
    if author.task!='E10' or not getattr(author.a,'control_report',{}).get('engineering_reference_only'):
        raise ToolExecutionError('E10 independent engineering control required')
    if not math.isfinite(descent_mm)or not .5<=descent_mm<=3.:
        raise ToolExecutionError('E10 precision branch requires reviewed public descent step')
    record_runtime_shape_count(author,name)
    rotation=post_rotation_for_object(author,name,rotation);target=np.asarray(target,float)
    holes=author.s['holes'][name];control=dict(actor=name,local=holes[0]['center_local'])
    guard=lambda:author.require_held(ref,side)
    author.stage('precision-thread-all-holes-'+name)
    rows=post_clearances(author,name,indices)
    if min(row['gap_above_tip_m']for row in rows)>.010:
        turn_to_post_rotation(author,name,side,rotation)
    history=[]
    for _ in range(650):
        guard();rows=post_clearances(author,name,indices)
        point=author.point(control);_,current=author.frame({'actor':name})
        delta=rotation@current.T;angle=float(np.arccos(np.clip((np.trace(delta)-1)/2,-1,1)))
        fits=min(row['native_radial_margin_m']for row in rows)>=0.
        native_axis=min(row['axis_dot']for row in rows)>=.98
        above_entry=min(row['gap_above_tip_m']for row in rows)>max(float(h['half_depth'])for h in holes)+.0005
        if (not fits or not native_axis)and not above_entry:
            raise ToolExecutionError('E10 actual multi-hole clearance lost near posts')
        if not native_axis:
            # Rotate only with the whole piece still clear of every post tip.
            if min(row['gap_above_tip_m']for row in rows)<.006:
                raise ToolExecutionError('E10 actual piece tilted near insertion posts')
            axis=np.array([delta[2,1]-delta[1,2],delta[0,2]-delta[2,0],delta[1,0]-delta[0,1]])/(2*math.sin(angle))
            i=int(np.argmax(abs(axis)));token=(('ROLL_LEFT','ROLL_RIGHT'),('PITCH_UP','PITCH_DOWN'),('ROTATE_CCW','ROTATE_CW'))[i][int(axis[i]<0)]
            author.act(side,token,degrees=min(1.,abs(math.degrees(angle*axis[i]))));continue
        error=target-point
        if not fits:
            i=int(np.argmax(abs(error[:2])));token=(('FWD','BACK'),('LEFT','RIGHT'))[i][int(error[i]<0)]
            author.act(side,token,mm=1.)
        elif all(row['native_threaded']for row in rows):
            # All original posts now pass through their complete real bores.
            # The remaining descent is physically guided by those same posts;
            # board/stack support and the original native geometry are checked
            # after release. A private basal seating coordinate is not a task
            # condition and need not be pushed to with hundreds of tiny steps.
            break
        else:
            if min(row['native_radial_margin_m']for row in rows)<0.:
                raise ToolExecutionError('E10 actual hole centers cannot fit all posts')
            author.act(side,'DOWN',mm=min(descent_mm,max(.5,float(point[2]-target[2]-.0005)*1000)))
        history.append(author.point(control).copy())
        if len(history)>=20 and max(np.linalg.norm(p-history[-1])for p in history[-20:])<.0001:
            raise ToolExecutionError('E10 precision threading actual motion stalled')
    else:raise ToolExecutionError('E10 precision threading exceeded public action bound')
    guard();rows=post_clearances(author,name,indices)
    if not all(row['native_threaded']for row in rows):
        raise ToolExecutionError('E10 final physical multi-hole margin missing')
    if not release:
        return dict(local_completed=True,ready_for_release=True,actual_final_holes=rows,
            actual_point=author.point(control).tolist(),whole_task_score=None)
    return release_engaged_piece(author,name,ref,side,target,rotation,indices,support)


def release_engaged_piece(author,name,ref,side,target,rotation,indices,support):
    """Open once all original posts guide the complete real bores.

    Also supports an explicit measured-pose release fixture. This entry does
    not claim to reconstruct its historical held/contact dynamics.
    """
    if author.task!='E10' or not getattr(author.a,'control_report',{}).get('engineering_reference_only'):
        raise ToolExecutionError('E10 independent engineering control required')
    record_runtime_shape_count(author,name)
    holes=author.s['holes'][name];control=dict(actor=name,local=holes[0]['center_local'])
    rows=post_clearances(author,name,indices);point=author.point(control);target=np.asarray(target,float)
    _,current=author.frame({'actor':name});delta=np.asarray(rotation,float)@current.T
    angle=float(np.arccos(np.clip((np.trace(delta)-1)/2,-1,1)))
    if not all(row['native_threaded']for row in rows):
        raise ToolExecutionError('E10 actual bores are not engaged along all original posts')
    author.stage('release-engaged-'+name);author.act(side,'RELEASE')
    author.move(side,author.tip(side)+[0,0,.06])
    state,_=author.snapshot()
    supported=physical_post_support(author,state,support)
    if any(state[name]['grasp'])or name not in supported:
        raise ToolExecutionError('E10 inserted piece lacks actual board support or physical release')
    rows=post_clearances(author,name,indices)
    if not all(row['coarse_shaft_crosses_bore']for row in rows):
        raise ToolExecutionError('E10 released piece lost physical multi-hole alignment')
    author.a.control_report.setdefault('e10_precise_threading',[]).append(dict(actor=name,post_indices=indices,actual_final_holes=rows))
    return dict(local_completed=True,functional_pass=True,native_threaded_all=all(row['native_threaded']for row in rows),
        actual_released_board_support=True,actual_post_support_chain=sorted(supported),
        actual_final_holes=rows,actual_point=author.point(control).tolist(),whole_task_score=None)


def finish_functional_remaining(policy):
    """Continue a traced physical checkpoint; never fabricate native history."""
    policy.act()
    policy.post_pieces(skip_functional=True)
    state,_=policy.snapshot();supported=physical_post_support(policy,state,'board');rows=[]
    for name in policy.s['groups']['pieces']:
        label=policy.label(name)
        selected=(label.startswith('red_')if policy.index==0 else label.endswith('_square')if policy.index==1 else label.startswith('red_')or label.endswith('_square'))
        if not selected:continue
        g=policy.geometry['threading_targets'][name];holes=post_clearances(policy,name,g['post_indices'])
        passed=not any(state[name]['grasp'])and name in supported and all(h['coarse_shaft_crosses_bore']for h in holes)
        rows.append(dict(actor=name,functional_pass=passed,native_threaded_all=all(h['native_threaded']for h in holes),holes=holes))
    if not rows or not all(r['functional_pass']for r in rows):raise ToolExecutionError('E10 selected objects did not all complete coarse physical placement')
    return dict(local_completed=True,functional_pass=True,selected_objects=rows,native_score_separate=True,whole_task_score=None)


def physical_post_support(author,state,support):
    """The original native post-support contact graph, including stacked plates."""
    supported={support};pending=set(author.s['groups']['pieces'])&set(state)
    while True:
        more={n for n in pending if not any(state[n]['grasp'])and
              any(author.contact(n,base)for base in supported)}
        if not more:break
        supported.update(more);pending-=more
    return supported


def record_runtime_shape_count(author,name):
    """Refuse an incomplete runtime collision instance before threading it."""
    expected={'square':218,'triangle':166,'circle':32}
    shape=author.objects[name]['shape']
    count=int(author.a.scene.objects[name].root_physx_view.max_shapes)
    if shape not in expected or count!=expected[shape]:
        raise ToolExecutionError('E10 actual runtime collision shape count differs from verified source')
    author.a.control_report.setdefault('e10_actual_runtime_shape_counts',{})[name]=dict(
        shape=shape,actual_max_shapes=count,verified_active_prisms={'square':202,'triangle':150,'circle':16}[shape],
        original_disabled_shape_slots=16)
