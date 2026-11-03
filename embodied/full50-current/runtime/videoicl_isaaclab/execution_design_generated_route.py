"""Measured clearance for isolated v3 engineering placement references.

This chooses reference waypoints only. It changes neither the world, public IK,
input contract nor native success criteria. Native reachability still must pass.
"""
import numpy as np
from .execution_design import REVISION_V3

MEASURED_CLEARANCE_TASKS=frozenset(('E02','E04','E05','E06','E07','E11','E13','E14','E16','E21','E22','E25','E27','E31','E34','E35','E36','E41'))
# New layouts can move a pickup across the two arm workspaces. These tasks
# E32/E33/E38 retain their clearance policy pending geometry review.
BACK25_HAND_TASKS=frozenset(('E27','E31','E32','E33','E34','E35','E36','E38','E41'))
# E06 B failed while genuinely holding its final ball at the fixed 1.10m
# carry plane. Lower only that plane using measured clearance; retain the
# already verified left-arm acquisition instead of adding a second change.
HAND_SELECTION_TASKS=(MEASURED_CLEARANCE_TASKS-{'E06'})|BACK25_HAND_TASKS


def initial_back25_hand(author,preferred):
    """Choose the first actual pickup arm before parking the opposite hand."""
    spec=author.scene.spec
    if (not getattr(author,'_execution_design_reference_authorized',False)
            or spec.get('execution_design',{}).get('revision')!=REVISION_V3
            or spec.get('id')not in BACK25_HAND_TASKS):return preferred
    zones={z['id']:z for z in spec['zones']}
    goals=list(spec['goals'])
    if not spec.get('expert_preserve_goal_order'):
        goals.sort(key=lambda g:float(zones[g['target']]['xy'][0]),reverse=spec.get('variant')=='A')
    if not goals:raise ValueError('Initial hand selection requires a real placement goal')
    goal=goals[0]
    return choose_generated_hand(author,goal['object'],goal,zones[goal['target']],preferred)['chosen']


def measured_generated_clearance(author, margin_m=.025):
    spec=author.scene.spec
    if (not getattr(author,'_execution_design_reference_authorized',False)
            or spec.get('execution_design',{}).get('revision')!=REVISION_V3
            or spec.get('id') not in MEASURED_CLEARANCE_TASKS):
        raise ValueError('Measured route is restricted to reviewed v3 engineering references')
    if not .02<=float(margin_m)<=.05:raise ValueError('Positive collision clearance margin required')
    state,_=author.c.snapshot();tops={};payload_below={};finger_below={}
    goals={g['object'] for g in spec['goals']}
    for obj in spec['objects']:
        name=obj['id'];body=state[name]
        pos=np.asarray(body['pos'],float);rotation=np.asarray(body['mat'],float)
        half=np.asarray(obj.get('bounds_half_extent',obj['size']),float)
        center=np.asarray(obj.get('local_bounds_center',[0,0,0]),float)
        if (pos.shape!=(3,) or rotation.shape!=(3,3) or half.shape!=(3,)
                or not np.isfinite(np.r_[pos,rotation.ravel(),half,center]).all() or np.any(half<=0)):
            raise ValueError('Finite measured body transform and authored physical bounds required: '+name)
        midpoint=pos+rotation@center;extent=np.abs(rotation)@half
        tops[name]=float(midpoint[2]+extent[2])
        if name in goals:
            if spec['id']=='E25':
                from .execution_design_e25_reference import grasp_spec
                obj=grasp_spec(author,obj)
            elif spec['id']=='E02':
                from .execution_design_e02_reference import grasp_spec
                obj=grasp_spec(author,obj)
            elif spec['id']=='E21':
                from .execution_design_e21_reference import grasp_spec
                obj=grasp_spec(author,obj)
            grasp=pos+rotation@np.asarray(obj.get('grasp_point_local',[0,0,0]),float)
            if not np.isfinite(grasp).all():raise ValueError('Nonfinite authored grasp point')
            payload_below[name]=max(0.,float(grasp[2]-(midpoint[2]-extent[2])))
    for side in ('left','right'):
        tip=np.asarray(author.tip(side),float)
        geometry=author.finger_geometry(side)
        if geometry.get('source')!='actual_collision_mesh_current_body_pose':
            raise ValueError('Actual finger collision geometry required')
        lowest=float(geometry['lowest_z_task_m'])
        if not np.isfinite(tip).all() or not np.isfinite(lowest):
            raise ValueError('Finite actual finger geometry and TCP required')
        finger_below[side]=max(0.,float(tip[2])-lowest)
    # A fingertip can have to grasp above the object's authored point to clear
    # the source support. Include this vertical adjustment in the carried depth.
    payload_depth=max(payload_below.values(),default=0.)+max(finger_below.values())
    surface=max([.8]+[float(z.get('surface_z',.8))for z in spec.get('zones',[])])
    obstacle_top=max([surface]+list(tops.values()))
    clearance=obstacle_top+max(payload_depth,max(finger_below.values()))+float(margin_m)
    if not np.isfinite(clearance):raise ValueError('Nonfinite reference clearance')
    return dict(source='actual_body_pose_authored_physical_bounds_and_actual_finger_mesh',
                coordinate_frame='room_task',task=spec['id'],clearance_z_m=float(clearance),
                obstacle_top_z_m=obstacle_top,object_tops_task_m=tops,
                payload_grasp_to_bottom_m=payload_below,finger_below_tcp_m=finger_below,
                payload_depth_allowance_m=payload_depth,margin_m=float(margin_m),
                native_reachability_verified=False)


def choose_generated_hand(author, name, goal, target, preferred):
    """Choose the shorter worst endpoint reach, never claim IK feasibility."""
    spec=author.scene.spec
    if (not getattr(author,'_execution_design_reference_authorized',False)
            or spec.get('execution_design',{}).get('revision')!=REVISION_V3
            or spec['id'] not in HAND_SELECTION_TASKS):
        raise ValueError('Engineering hand selection requires reviewed v3 route')
    state,_=author.c.snapshot();obj=next(o for o in spec['objects']if o['id']==name)
    if spec['id']=='E25':
        from .execution_design_e25_reference import grasp_spec
        obj=grasp_spec(author,obj)
    elif spec['id']=='E02':
        from .execution_design_e02_reference import grasp_spec
        obj=grasp_spec(author,obj)
    elif spec['id']=='E21':
        from .execution_design_e21_reference import grasp_spec
        obj=grasp_spec(author,obj)
    body=state[name];offset=np.asarray(body['mat'],float)@np.asarray(obj.get('grasp_point_local',[0,0,0]),float)
    source=np.asarray(body['pos'],float)+offset
    destination_offset=offset
    if spec['id']=='E25' and any(k in goal for k in ('roll','pitch','yaw')):
        # Cutlery has off-centre handles. Match rotate_held's absolute RzRyRx
        # target for endpoint selection; current pickup offset can face away.
        roll,pitch,yaw=[float(goal.get(k,0.))for k in ('roll','pitch','yaw')]
        cx,sx=np.cos(roll),np.sin(roll);cy,sy=np.cos(pitch),np.sin(pitch);cz,sz=np.cos(yaw),np.sin(yaw)
        desired=np.array([[cz,-sz,0],[sz,cz,0],[0,0,1.]])@np.array([[cy,0,sy],[0,1,0],[-sy,0,cy]])@np.array([[1,0,0],[0,cx,-sx],[0,sx,cx]])
        destination_offset=desired@np.asarray(obj.get('grasp_point_local',[0,0,0]),float)
    destination=np.asarray(goal.get('placement_xy',target['xy']),float)+destination_offset[:2]
    if target.get('anchor_object'):
        anchor=state[target['anchor_object']]
        destination=(np.asarray(anchor['pos'])+np.asarray(anchor['mat'])@np.asarray(target.get('anchor_local_center',[0,0,0])))[:2]+destination_offset[:2]
    costs={};bases={}
    for side in ('left','right'):
        value=author.scene.robots[side].data.root_pos_w[0]
        if hasattr(value,'detach'):value=value.detach()
        if hasattr(value,'cpu'):value=value.cpu()
        base=np.asarray(author.scene.world_to_task(np.asarray(value,float)),float)
        if not np.isfinite(np.r_[base,source,destination]).all():raise ValueError('Finite actual base/source/destination required')
        bases[side]=base.tolist()
        costs[side]=max(float(np.linalg.norm(source[:2]-base[:2])),float(np.linalg.norm(destination-base[:2])))
    if preferred not in costs:raise ValueError('Invalid preferred hand')
    if spec['id'] in BACK25_HAND_TASKS:
        # Symmetric cross-table transfers have near-equal endpoint reach (1 mm).
        # Prefer the arm local to the pickup in that tie; empty-hand acquisition
        # should not cross the table merely because a legacy arm was pinned.
        near_ties=[side for side in costs if costs[side]<=min(costs.values())+.001]
        chosen=min(near_ties,key=lambda side:(float(np.linalg.norm(source[:2]-np.asarray(bases[side])[:2])),side!=preferred))
    else:
        chosen=min(costs,key=lambda side:(costs[side],side!=preferred))
    return dict(chosen=chosen,preferred=preferred,object=name,source_grasp_task_m=source.tolist(),
                destination_grasp_task_xy_m=destination.tolist(),actual_robot_bases_task_m=bases,
                max_endpoint_horizontal_reach_m=costs,native_reachability_verified=False)


def park_before_hand_switch(author, previous, chosen, home_xy, clearance):
    """Return a released hand at measured clearance before its normal high park."""
    if chosen==previous:return
    if author.carried_payload is not None:raise RuntimeError('Reference switch while carrying is forbidden')
    state,_=author.c.snapshot()
    if any(any(bool(x)for x in row.get('grasp',[]))for row in state.values()):
        raise RuntimeError('Reference hand switch requires actual payload release')
    if (getattr(getattr(author,'scene',None),'spec',{}).get('id')=='E25'
            and getattr(author,'_execution_design_reference_authorized',False)):
        from .execution_design_e25_functional import withdraw_released
        withdraw_released(author,previous)
        return
    author.stage='switch-return-home-'+previous
    author.move_generated({previous:[*author.tip(previous)[:2],clearance]})
    author.move_generated({previous:[*home_xy[previous],clearance]})
    if (getattr(getattr(author,'scene',None),'spec',{}).get('id')=='E16'
            and getattr(author,'_execution_design_reference_authorized',False)):
        from .execution_design_e16_parking import restore_released_wrist
        restore_released_wrist(author,previous,clearance)
