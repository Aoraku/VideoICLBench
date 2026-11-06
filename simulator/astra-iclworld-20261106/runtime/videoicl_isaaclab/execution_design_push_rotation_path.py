"""Source E42 held-tool turn stations screened through the whole public route."""
import json
import math
import time
import numpy as np
from .realworld_tool_expert import _axis_rotation,ToolExecutionError
from .execution_design_tool_pose_paths import append_public_move


def actor_rotation_poses(position,start,target,maximum_degrees=10.):
    from .author_orientation import _axis_angle
    current=np.asarray(start,float).copy();poses=[]
    for _ in range(120):
        axis,angle=_axis_angle(np.asarray(target)@current.T)
        if angle<math.radians(4.):return poses
        i=int(np.argmax(abs(axis)));step=np.sign(axis[i])*min(math.radians(maximum_degrees),abs(angle*axis[i]))
        current=_axis_rotation(np.eye(3)[i],step)@current
        poses.append(dict(position=np.asarray(position).tolist(),rotation=current.tolist()))
    raise ValueError('Bounded actual held-tool public turns did not converge')


def route_poses(position,rotation,target_rotation,station,approach_tcp,maximum_step_m=.025):
    poses=[];position=np.asarray(position,float);station=np.asarray(station,float)
    cursor=append_public_move(poses,position,[*position[:2],station[2]],rotation,maximum_step_m)
    cursor=append_public_move(poses,cursor,station,rotation,maximum_step_m)
    turns=actor_rotation_poses(cursor,rotation,target_rotation)
    poses+=turns;turned=np.asarray(turns[-1]['rotation'])if turns else np.asarray(rotation)
    # Keep the actual existing height when already clear. The ball approach
    # needs55mm over the ball, not another55mm above every turn station.
    above=np.asarray(approach_tcp)+[0,0,.055];height=max(float(cursor[2]),float(above[2]))
    cursor=append_public_move(poses,cursor,[*cursor[:2],height],turned,maximum_step_m)
    cursor=append_public_move(poses,cursor,[*above[:2],height],turned,maximum_step_m)
    append_public_move(poses,cursor,approach_tcp,turned,maximum_step_m)
    return poses,turns


def align(policy,tool,grip,side,target,ball,direction):
    from .execution_design_jacobian_reference import capture
    from .execution_design_local_pose_path import solve_local_pose_path
    from .execution_design_spatula_clearance import SUPPORT_VERTICES,SOURCE_SHA,HALF_SIZE
    from .execution_design_e33_grasp import actual_mesh
    from .execution_design_tool_route_clearance import swept_route_clear
    from .execution_design_thin_edge import table_bounds_task
    if policy.task!='E42'or not policy.a.control_report.get('engineering_reference_only'):
        raise ToolExecutionError('E42 held source turn reference only')
    actor=tool['actor'];obj=next(o for o in policy.spec['objects']if o['id']==actor)
    if obj['source_asset']['sha256']!=SOURCE_SHA or not np.allclose(obj['size'],HALF_SIZE,atol=1e-9,rtol=0):
        raise ToolExecutionError('Exact source spatula turn support vertices required')
    state,_=policy.snapshot();held=state[actor]
    lowest=float((SUPPORT_VERTICES@held['mat'].T+held['pos'])[:,2].min())
    highest_ball=max(float(state[n]['pos'][2]+max(next(o for o in policy.spec['objects']if o['id']==n)['size']))
        for n in policy.s['groups']['balls'])
    unload=min(.055,max(0.,highest_ball+.025-lowest))
    if unload>.001:
        policy.stage('lift-real-edge-clear-before-turn-probe')
        policy.move(side,policy.tip(side)+[0,0,unload],lambda:policy.require_held(grip,side))
    state,_=policy.snapshot();body=state[actor];position=policy.tip(side);measured=capture(policy.a,policy.c,side)
    current=np.asarray(measured['rotation_task']);relative_hand=body['mat'].T@current;desired=np.asarray(target)@relative_hand
    from .execution_design_e42_edge import central_reference
    offset=body['mat'].T@(position-body['pos'])
    ball_obj=next(o for o in policy.spec['objects']if o['id']==ball);radius=max(ball_obj['size'])
    edge_start=state[ball]['pos']-np.asarray(direction)*(radius+.006)
    # Contact the upper part of the same sphere with the real rim. This
    # raises the broad trailing blade clear of the other source ball. Actual
    # edge/table contact is still required before any driven push is accepted.
    contact_height=min(.003,radius*.25)
    edge_start[2]+=contact_height
    vertices=SUPPORT_VERTICES@body['mat'].T+body['pos']
    local=[(vertices-position)@current]
    names=('panda_hand',*policy.a.scene.embodiment.fingers)
    local +=[(actual_mesh(policy.a,side,name)-position)@current for name in names]
    other='left'if side=='right'else'right';obstacles=[actual_mesh(policy.a,other,name)for name in names]
    floor=table_bounds_task(policy.a.scene)['top'];rows=[];valid=[]
    # The other source ball is a real obstacle even though it is movable. A
    # broad blade sweeping through it can tip the handle and pin a finger on
    # the table before the selected rim reaches its intended ball.
    from itertools import product
    for name in policy.spec['semantic']['groups']['balls']:
        if name==ball:continue
        b=state[name];obj_ball=next(o for o in policy.spec['objects']if o['id']==name)
        extent=np.full(3,max(obj_ball['size']))
        obstacles.append(np.asarray(list(product((-1.,1.),repeat=3)))*extent+b['pos'])
    cpu_started=time.monotonic();cpu_deadline=cpu_started+20.;candidate_limit=24
    def write_plan(chosen=None,budget_reason=None):
        (policy.a.out/('e42-'+ball+'-complete-turn-path.private.json')).write_text(json.dumps(dict(
            chosen=chosen,candidates=rows,native_success_asserted=False,tool_geometry_unchanged=True,
            measured_reference=measured,edge_contact_height_offset_m=contact_height,
            carried_meshes_tcp_local=[m.tolist()for m in local],
            forbidden_obstacles_task=[m.tolist()for m in obstacles],floor_task_m=floor,
            private_cpu_elapsed_seconds=time.monotonic()-cpu_started,private_cpu_limit_seconds=20.,
            candidate_limit=candidate_limit,budget_reason=budget_reason)))
    write_plan()
    for z in(.90,.95):
        for x,y in((position[0],position[1]),(-.12,-.25)):
            for pitch in(7.,4.,0.):
                for yaw_offset in(0.,-6.,6.,-10.,10.):
                    # A source handle pitch within the existing guard raises the gripping
                    # fingers above the table, without changing the real blade.
                    # The four/seven-degree choices stay within the existing eight-degree normal guard.
                    actor_target=(_axis_rotation([0.,0.,1.],math.radians(yaw_offset))@np.asarray(target)
                        @_axis_rotation([0.,1.,0.],math.radians(pitch)))
                    desired=actor_target@relative_hand
                    turns=actor_rotation_poses(position,current,desired)
                    final_hand=np.asarray(turns[-1]['rotation'])if turns else current
                    # The public actor turn stops within4degrees. Plan approach
                    # from that actual stop, not an ideal pose it never executes.
                    effective_actor=final_hand@relative_hand.T
                    outward=np.asarray(tool.get('edge_outward_normal_local',policy.s.get('edge_outward_normal_local')),float)
                    outward-=np.asarray(tool['support_normal_local'])*float(outward@np.asarray(tool['support_normal_local']))
                    front=effective_actor@outward;front[2]=0.;front/=np.linalg.norm(front)
                    if float(front@direction)<math.cos(math.radians(12.)):continue
                    for lateral in(0.,-.010,.010,-.020,.020):
                        if len(rows)>=candidate_limit or time.monotonic()>=cpu_deadline:
                            write_plan(budget_reason='private_cpu_or_candidate_limit')
                            raise ToolExecutionError('E42 private CPU proposal budget exhausted; preserve native checkpoint')
                        edge=central_reference(obj,lateral)
                        approach=edge_start+effective_actor@(offset-edge)
                        station=np.array([x,y,z]);poses,turns=route_poses(position,current,desired,station,approach,policy.max_mm/1000.)
                        try:clear=swept_route_clear(local,position,current,poses,obstacles,floor,deadline_monotonic=cpu_deadline)
                        except TimeoutError:
                            write_plan(budget_reason='private_cpu_collision_limit')
                            raise ToolExecutionError('E42 private CPU collision budget exhausted; preserve native checkpoint')
                        path=solve_local_pose_path(measured['position'],measured['rotation_task'],measured['jacobian'],
                            measured['q'],measured['limits'],poses,max_seconds=max(.000001,cpu_deadline-time.monotonic()))if clear else None
                        index=len(rows);rows.append(dict(station=station.tolist(),edge_local=edge.tolist(),
                            edge_section_lateral_m=lateral,yaw_offset_degrees=yaw_offset,source_handle_pitch_degrees=pitch,
                            target_actor_rotation=actor_target.tolist(),predicted_stopped_actor_rotation=effective_actor.tolist(),
                            whole_turn_clear=bool(clear),whole_route_clear=bool(clear),continuous_path=path))
                        write_plan()
                        if path and path.get('cpu_budget_exhausted'):
                            write_plan(budget_reason='private_cpu_ik_limit')
                            raise ToolExecutionError('E42 private CPU IK budget exhausted; preserve native checkpoint')
                        if path and path['feasible']:
                            valid.append(index);break
                    if valid:break
                if valid:break
            if valid:break
        if valid:break
    chosen=valid[0]if valid else None
    write_plan(chosen)
    if chosen is None:raise ToolExecutionError('No swept-clear continuous source-spatula turn and ball approach')
    station=np.asarray(rows[chosen]['station']);guard=lambda:policy.require_held(grip,side)
    policy.move(side,[*position[:2],station[2]],guard);policy.move(side,station,guard)
    selected_target=np.asarray(rows[chosen]['target_actor_rotation'])
    policy.rotate_actor(actor,side,selected_target);guard()
    return dict(edge_local=rows[chosen]['edge_local'],target_actor_rotation=selected_target.tolist(),
                edge_contact_height_offset_m=contact_height)
