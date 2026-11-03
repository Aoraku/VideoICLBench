"""Engineering E43: grip the upper sliding gate, withdraw, then retreat up.

No source-ball actuation. Native bilateral gate contact and no hand/ball contact
are checked throughout. The gate's real prismatic constraint remains unchanged.
"""
import numpy as np
from .realworld_tool_expert import ToolExecutionError


def ball_extent(obj,rotation):
    """Bound the actual analytic sphere, rather than its rotated empty cube."""
    reviewed=obj.get('reviewed_collision_settings',{})
    if reviewed.get('approximation')=='analyticSphere':
        from .execution_design_e43_ball import settings_for
        if reviewed!=settings_for(obj):raise ToolExecutionError('Exact reviewed source sphere required')
        return np.full(3,float(max(obj['size'])))
    return np.abs(np.asarray(rotation))@np.asarray(obj['size'])


def select_gate_hand_frame(tool, ref, side, direction):
    """Check acquisition and the complete physical gate travel, not just IK at grip."""
    import json
    from .execution_design_drawer_ik_probe import physical_grasp_targets
    from .execution_design_cutlery_grasp import orient
    from .execution_design_jacobian_reference import capture
    from .execution_design_local_pose_path import solve_local_pose_path
    from .execution_design_tool_pose_paths import grasp_and_travel_poses
    from .execution_design_clip_handover import rotation_clear, public_rotation_poses
    from .execution_design_clip_grasp import convex_meshes_clear
    from .realworld_tool_expert import _axis_rotation
    from itertools import product
    from .execution_design_e33_grasp import actual_mesh
    from .execution_design_thin_edge import table_bounds_task
    body=tool.snapshot()[0][ref['actor']]
    if any(v['grasp'][0 if side=='left'else 1]for v in tool.snapshot()[0].values()):
        raise ToolExecutionError('Gate hand must be empty before frame selection')
    tool.stage('select-full-gate-travel-hand-frame')
    grip=tool.point(ref)
    height=max(tool.clearance,float(grip[2])+.07,float(tool.tip(side)[2]))
    tool.move(side,np.r_[tool.tip(side)[:2],height])
    bases=physical_grasp_targets(tool.a,tool.c,side,body['mat']@np.array([0.,0.,1.]),
        pinch_axis=body['mat']@np.array([1.,0.,0.]))
    jaw=body['mat']@np.array([1.,0.,0.]);tilts=(0.,-15.,-30.,-45.,15.,30.,45.)
    rotations=[_axis_rotation(jaw,np.deg2rad(tilt))@base for base in bases for tilt in tilts]
    measured=capture(tool.a,tool.c,side);current=np.asarray(measured['position']);current_rotation=np.asarray(measured['rotation_task'])
    names=('panda_hand',*tool.a.scene.embodiment.fingers)
    local=[(actual_mesh(tool.a,side,n)-current)@current_rotation for n in names]
    other='right'if side=='left'else'left';obstacles=[actual_mesh(tool.a,other,n)for n in names]
    floor=table_bounds_task(tool.a.scene)['top'];rows=[];valid=[]
    ball=tool.snapshot()[0]['ball'];ball_object=next(o for o in tool.spec['objects']if o['id']=='ball')
    extent=ball_extent(ball_object,ball['mat']);ball_bounds=np.asarray(list(product((-1.,1.),repeat=3)))*extent+ball['pos']
    for i,r in enumerate(rotations):
        turn=public_rotation_poses(current,current_rotation,r)
        clear=rotation_clear(local,current,current_rotation,turn,obstacles,floor)
        clear=clear and min((m@r.T+grip)[:,2].min()for m in local)>=floor+.0002
        clear=clear and all(convex_meshes_clear(m@r.T+grip,ball_bounds)for m in local)
        poses,_=grasp_and_travel_poses(current,current_rotation,r,grip,height,
            [grip+direction*f for f in(.025,.05,.065)],tool.max_mm/1000.)
        path=solve_local_pose_path(measured['position'],measured['rotation_task'],measured['jacobian'],
            measured['q'],measured['limits'],poses)if clear else None
        rows.append(dict(assignment=i//len(tilts),tilt_degrees=tilts[i%len(tilts)],turn_clear=bool(clear),continuous_path=path))
        if path and path['feasible']:
            valid.append((int(min(x['minimum_joint_margin_rad']for x in path['rows'])/.02),
                          -abs(tilts[i%len(tilts)]),-sum(x['maximum_joint_step_rad']for x in path['rows']),i))
    chosen=max(valid)[3]if valid else None
    (tool.a.out/'gate-full-route-hand-candidates.private.json').write_text(json.dumps(dict(chosen=chosen,candidates=rows,
        native_verified=False,collision_verified=False,gate_travel_m=.065)))
    if chosen is None:raise ToolExecutionError('No physical gate hand assignment clears the complete measured travel')
    orient(tool.a,side,rotations[chosen])


def open_upper_gate(tool,guide_grip,guide_side):
    if tool.task!='E43' or not tool.a.control_report.get('engineering_reference_only'):
        raise ToolExecutionError('E43 isolated reference only')
    trigger=tool.s['launcher']['trigger'];name=trigger['actor'];side='left'if guide_side=='right'else'right'
    objects={o['id']:o for o in tool.spec['objects']};state,_=tool.snapshot();gate=state[name]
    ref=dict(actor=name,local=[0.,0.,float(objects[name]['size'][2])-.005],jaw_axis_local=[1.,0.,0.])
    grasp=tool.point(ref);ball=state['ball'];ball_top=float(ball['pos'][2]+ball_extent(objects['ball'],ball['mat'])[2])
    if grasp[2]-ball_top<.012:
        raise ToolExecutionError('Upper gate grip lacks measured vertical clearance above source ball')
    def guide_guard(*_):
        tool.require_held(guide_grip,guide_side)
        if any(tool.contact('ball',f'{hand}_finger{i}')for hand in('left','right')for i in(1,2)):
            raise ToolExecutionError('Gate hand touched source ball directly')
    hooks=getattr(tool.c,'tick_hooks',None)
    if hooks is not None:hooks.append(guide_guard)
    previous=tool.clearance
    try:
        tool.clearance=min(previous,float(gate['pos'][2]+objects[name]['size'][2]+.06))
        direction=np.asarray(trigger['press_direction_task'],float);direction/=np.linalg.norm(direction)
        select_gate_hand_frame(tool,ref,side,direction)
        tool.stage('grasp-upper-sliding-gate')
        tool.acquire(ref,side);guide_guard();tool.require_held(ref,side)
        start=tool.snapshot()[0][name]['pos'].copy()
        def both_held():guide_guard();tool.require_held(ref,side)
        tool.stage('withdraw-physically-held-gate')
        tool.move(side,tool.tip(side)+direction*min(.065,float(trigger['max_travel'])),both_held,tolerance=.003)
        actual=tool.snapshot()[0][name]['pos']-start
        if float(actual@direction)<.055:
            raise ToolExecutionError('Actual gate did not clear the full source ball width')
        tool.stage('release-gate-retreat-up')
        tool.act(side,'RELEASE');tool.move(side,tool.tip(side)+[0,0,.08],guide_guard)
        tool.wait(10);guide_guard()
    finally:
        tool.clearance=previous
        if hooks is not None:hooks.remove(guide_guard)
