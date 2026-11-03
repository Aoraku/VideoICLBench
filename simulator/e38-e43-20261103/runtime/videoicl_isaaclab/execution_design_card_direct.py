"""Engineering-only direct thin-card edge pinch using actual near-table toes."""
import json,math
import numpy as np
from .realworld_tool_expert import ToolExecutionError,_axis_rotation
from .execution_design import REVISION_V3,source_sha256
from .execution_design_thin_edge import table_bounds_task,material_collision_points_task


def plan_open_target(position,rotation,tcp,fingers,palm,floor,obstacles):
    """Choose a real long-axis grasp section clearing nearby props vertically."""
    from .execution_design_clip_grasp import convex_meshes_clear
    low=min(float(m[:,2].min())for m in fingers)
    tips=[m[m[:,2]<=float(m[:,2].min())+.0004].mean(0)for m in fingers]
    offset=np.mean(tips,axis=0)-tcp
    target=np.asarray(position,float).copy();target[:2]-=offset[:2]
    target[2]=tcp[2]+floor+.00002-low
    long=np.asarray(rotation,float)[:,0].copy();long[2]=0.;long/=np.linalg.norm(long)
    height=max(floor+.14,float(tcp[2]));rows=[]
    for displacement in(0.,.015,-.015,.025,-.025,.030,-.030):
        candidate=target+long*displacement;delta=candidate-tcp
        future=[np.asarray(m)+delta for m in [palm,*fingers]]
        dz=np.array([0.,0.,max(0.,height-candidate[2])])
        sweep=[np.vstack((m,m+dz))for m in future]
        blocked=[name for name,points in obstacles.items()if any(not convex_meshes_clear(m,points,clearance=.0005)for m in sweep)]
        rows.append(dict(long_axis_offset_m=displacement,target_tcp=candidate.tolist(),blocked_by=blocked))
        if not blocked:return dict(position=candidate,approach_height=height,candidates=rows,native_grasp_verified=False)
    raise ToolExecutionError('No actual open-finger card section clears nearby prop geometry')


def acquire_direct_card(p,ref,side):
    a=p.a;design=p.spec.get('execution_design',{})
    if p.task!='E50'or design.get('revision')!=REVISION_V3 or design.get('source_sha256')!=source_sha256(REVISION_V3)or not a.control_report.get('engineering_reference_only'):
        raise ValueError('Source-checked independent E50 engineering direct pinch required')
    if a.scene.embodiment.name!='franka':raise ValueError('Measured Panda direct pinch required')
    from .execution_design_e33_grasp import actual_mesh
    from .execution_design_cutlery_grasp import orient
    from .execution_design_thin_motion import checked_move
    def log(phase,**values):
        state,contacts=p.snapshot();geometry=a.finger_geometry(side)
        with (a.out/'card-direct-public.private.jsonl').open('a')as stream:
            stream.write(json.dumps(dict(phase=phase,step=p.c.steps,tcp=p.tip(side).tolist(),
                card_position=state[ref['actor']]['pos'].tolist(),card_rotation=state[ref['actor']]['mat'].tolist(),
                finger_geometry=geometry,actual_contacts=[sorted(pair)for pair in contacts if ref['actor']in pair],
                actual_contact_forces=[dict(pair=sorted(pair),force_n=float(force))for pair,force in p.c.contact_forces.items()if ref['actor']in pair],**values))+'\n')
    bounds=table_bounds_task(a.scene);position,rotation=p.frame(ref);material=material_collision_points_task(p,ref)
    short_axis=rotation[:,1].copy();short_axis[2]=0.;short_axis/=np.linalg.norm(short_axis)
    meshes=[actual_mesh(a,side,name)for name in a.scene.embodiment.fingers]
    jaw=meshes[0].mean(0)-meshes[1].mean(0);jaw[2]=0.;jaw/=np.linalg.norm(jaw)
    if jaw@short_axis<0:short_axis=-short_axis
    yaw=math.atan2(float(np.cross(jaw,short_axis)[2]),float(jaw@short_axis))
    p.stage('card-direct-open-align');p.act(side,'RELEASE');orient(a,side,_axis_rotation([0,0,1],yaw)@a.tcp_rotation_task(side))
    meshes=[actual_mesh(a,side,name)for name in a.scene.embodiment.fingers]
    obstacles={name:material_collision_points_task(p,dict(actor=name))for name in a.scene.objects if name!=ref['actor']}
    plan=plan_open_target(position,rotation,p.tip(side),meshes,actual_mesh(a,side,'panda_hand'),bounds['top'],obstacles)
    target=plan['position'];height=plan['approach_height']
    log('actual-open-toe-plan',target_tcp=target.tolist(),material_top=float(material[:,2].max()),yaw_rad=yaw,prop_clearance_candidates=plan['candidates'])
    checked_move(p,side,[*p.tip(side)[:2],height]);checked_move(p,side,[*target[:2],height]);checked_move(p,side,target,tolerance=.0003)
    # Public downward actions stop on actual table physics; no penetration
    # teleport or geometry adjustment is used to obtain the thin pinch band.
    # A tilted88mm card's global maximum can be>350um while its central
    # grasp section is only184um high. Global card top prematurely stopped v22
    # at164um toe clearance, above the real vertical inner-pad contact band.
    # Refine against the measured tabletop itself using bounded public actions.
    refine_open_toe_height(p,side,bounds['top'])
    log('open-near-table')
    p.stage('card-direct-bilateral-pinch')
    for _ in range(6):
        p.act(side,'GRASP');held=p.held(ref,side)
        log('close-contact',actual_bilateral_held=held)
        # The v20 first closure made real bilateral contact; repeated closure
        # on the tabletop then squeezed the184um card away. Test the grasp
        # immediately through real upward motion, with both contacts checked
        # before and after every accepted action and25mm actual lift required.
        if held:break
    else:raise ToolExecutionError('Direct thin-card pinch lacks actual bilateral contact')
    p.stage('card-direct-held-lift');raised=prove_bilateral_lift(p,ref,side)
    log('actual-held-lift',raised_m=raised,held=p.held(ref,side))


def prove_bilateral_lift(p,ref,side,initial_lift_step_mm=2.,after_action=None):
    """Contact alone cannot certify grasp: actual material must follow25mm."""
    original=p.frame(ref)[0].copy()
    first=float(initial_lift_step_mm)
    if not .5<=first<=2.:raise ValueError('Initial public lift step must be0.5–2mm')
    increments=([first]*4 if first<2. else[])+[2.]*15
    for index,mm in enumerate(increments):
        p.require_held(ref,side);p.act(side,'UP',mm=mm);p.require_held(ref,side)
        if after_action is not None:after_action(index+1)
        if float(p.frame(ref)[0][2]-original[2])>=.025:break
    raised=float(p.frame(ref)[0][2]-original[2])
    if raised<.025:raise ToolExecutionError('Bilateral card contact did not physically lift card25mm')
    return raised


def refine_open_toe_height(p,side,floor):
    """Bounded native toe/table feedback; never alter collision geometry."""
    for _ in range(5):
        low=float(p.a.finger_geometry(side)['lowest_z_task_m'])
        if low<=float(floor)+.00005:return low
        p.act(side,'DOWN',mm=.5)
    low=float(p.a.finger_geometry(side)['lowest_z_task_m'])
    if low>float(floor)+.00005:
        raise ToolExecutionError('Actual open toe did not reach50um table clearance')
    return low
