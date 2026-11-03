"""E04/E07/E16/E25 engineering-only physical relay placements. No world/goal/score writes."""
import copy,itertools,json
import numpy as np
from .execution_design import REVISION_V3


def _scope(author):
    if not(getattr(author,'_execution_design_reference_authorized',False)
           and author.scene.spec['id'] in ('E04','E07','E16','E25')
           and author.scene.spec.get('execution_design',{}).get('revision')==REVISION_V3):
        raise ValueError('E07 relay requires explicit v3 engineering reference')


def _numpy(value):
    if hasattr(value,'detach'):value=value.detach()
    if hasattr(value,'cpu'):value=value.cpu()
    return np.asarray(value,float)


def staging_target(author,payload_goals=None):
    """Find an empty, on-table task-frame site from actual object poses."""
    _scope(author);scene=author.scene;spec=scene.spec;state,_=author.c.snapshot()
    table=scene.layout.config['table'];origin=np.asarray(getattr(scene,'origin',(0,0,0)),float)
    center=np.asarray(table['position'],float)+origin;half=np.asarray(table['size'],float)/2
    corners=np.array([scene.world_to_task(center+half*np.array(sign))for sign in itertools.product((-1,1),repeat=3)])
    low,high=corners.min(axis=0),corners.max(axis=0)
    # E16 has a large receiving tray; only the transferred pieces determine
    # relay footprint. The tray remains a measured obstacle below.
    # A resumed E25 queue has already placed its prefix. Keep every actual
    # object as an obstacle below, but size the moving payload footprint from
    # the remaining private queue rather than the completed spoon's rotation.
    payloads={g['object'] for g in (spec['goals']if payload_goals is None else payload_goals)}
    if not payloads or not payloads<={g['object']for g in spec['goals']}:
        raise ValueError('Relay payloads must be original task goals')
    extent=(max(float(np.linalg.norm(o['size'][:2])) for o in spec['objects'] if o['id'] in payloads)+.025
            if spec['id'] in ('E16','E25') else max(max(o['size'][:2])for o in spec['objects'])+.025)
    footprint=np.array([extent,extent],float)
    if spec['id']=='E25':
        # The relay preserves each utensil's measured source orientation; its
        # final rotation is deferred to the receiving arm. A square with the
        # long-axis radius falsely excluded the real narrow tabletop corridor.
        # Retain the full measured rotated bounds and the original 25mm margin.
        measured=[]
        for obj in spec['objects']:
            if obj['id']not in payloads:continue
            rotation=np.asarray(state[obj['id']]['mat'],float)
            half=np.asarray(obj.get('bounds_half_extent',obj['size']),float)
            center=np.asarray(obj.get('local_bounds_center',[0,0,0]),float)
            measured.append((np.abs(rotation@center)+np.abs(rotation)@half)[:2])
        footprint=np.max(measured,axis=0)+.025
    bases=[np.asarray(scene.world_to_task(_numpy(r.data.root_pos_w[0])),float)for r in scene.robots.values()]
    middle=np.mean(bases,axis=0);candidate0=np.array([middle[0]+.45,middle[1]])
    obstacles=[]
    for obj in spec['objects']:
        body=state[obj['id']];rotation=np.asarray(body['mat'],float)
        pos=np.asarray(body['pos'],float)+rotation@np.asarray(obj.get('local_bounds_center',[0,0,0]),float)
        size=np.abs(rotation)@np.asarray(obj.get('bounds_half_extent',obj['size']),float)
        obstacles.append((pos[:2],size[:2]))
    # Reserve all final targets too, so future completed placements remain safe.
    obstacles.extend((np.asarray(z['xy'],float),np.asarray(z['half_size'],float))for z in spec['zones'])
    offsets=(((0.,-.02,-.04,-.08,-.16,.02,.04,.08),(0.,-.03,.03,-.06,.06,-.09,.09))
             if spec['id']=='E25' else ((0.,-.08,-.16,.08),(0.,-.06,.06)))
    for dx,dy in itertools.product(*offsets):
        xy=candidate0+[dx,dy]
        if np.any(xy-footprint<low[:2])or np.any(xy+footprint>high[:2]):continue
        if any(np.all(np.abs(xy-pos)<size+footprint)for pos,size in obstacles):continue
        return dict(id='engineering-relay-table',xy=xy.tolist(),half_size=footprint.tolist(),surface_z=float(high[2]),support='table',
                    footprint_source=('measured_orientation_preserved_payload_bounds_plus_25mm'if spec['id']=='E25'else'conservative_payload_radius'))
    raise RuntimeError('No measured empty on-table E07 relay site')


def plan_transfers(author,goals,ik_probe=None):
    """Preserve final ordering, insert genuine place/regrasp where hands differ.

    IK candidates are reject-only geometry checks, never joint commands or proof
    of collision-free execution. Every placement still uses public controls.
    """
    _scope(author)
    if ik_probe is None:
        from .execution_design_drawer_ik_probe import inspect
        ik_probe=inspect
    state,_=author.c.snapshot();spec=author.scene.spec
    if spec['id']=='E25' and not hasattr(author,'_e25_home_rotations'):
        author._e25_home_rotations={s:np.asarray(author.tcp_rotation_task(s),float).copy()for s in ('left','right')}
    objects={o['id']:o for o in spec['objects']};zones={z['id']:z for z in spec['zones']}
    bases={side:np.asarray(author.scene.world_to_task(_numpy(robot.data.root_pos_w[0])),float)for side,robot in author.scene.robots.items()}
    stage=staging_target(author,goals if spec['id']=='E25'else None);planned=[];checks={side:[]for side in bases};records=[]
    def nearest(xy):return min(bases,key=lambda side:float(np.linalg.norm(np.asarray(xy)-bases[side][:2])))
    for original in goals:
        goal=copy.deepcopy(original);name=goal['object'];obj=objects[name];body=state[name]
        if spec['id']=='E25':
            from .execution_design_e25_reference import grasp_spec
            obj=grasp_spec(author,obj)
        offset=np.asarray(body['mat'],float)@np.asarray(obj.get('grasp_point_local',[0,0,0]),float)
        # B's +60mm receiving pinch shortens the half-turn destination reach.
        # At the original source that bowl-side pinch put the open finger onto
        # the adjacent fork (native 6.07N). Use the original handle at pickup;
        # the genuinely released table relay permits a different real regrasp.
        source_local=objects[name].get('grasp_point_local',[0,0,0]) if spec['id']=='E25'and spec['variant']=='B' else obj.get('grasp_point_local',[0,0,0])
        source_offset=np.asarray(body['mat'],float)@np.asarray(source_local,float)
        source=np.asarray(body['pos'],float)+source_offset;target=zones[goal['target']]
        destination_xy=np.asarray(goal.get('placement_xy',target['xy']),float)
        if target.get('anchor_object'):
            anchor=state[target['anchor_object']]
            destination_xy=(np.asarray(anchor['pos'])+np.asarray(anchor['mat'])@np.asarray(target.get('anchor_local_center',[0,0,0])))[:2]
        destination_offset=offset;desired=None
        if spec['id']=='E25' and any(k in goal for k in ('roll','pitch','yaw')):
            from .realworld_tool_expert import _axis_rotation
            roll,pitch,yaw=[float(goal.get(k,0.))for k in ('roll','pitch','yaw')]
            desired=_axis_rotation([0,0,1],yaw)@_axis_rotation([0,1,0],pitch)@_axis_rotation([1,0,0],roll)
            destination_offset=desired@np.asarray(obj.get('grasp_point_local',[0,0,0]),float)
        source_hand=nearest(source[:2]);destination=nearest(destination_xy+destination_offset[:2])
        source_z=max(float(source[2]),float(author.floor_clear_tcp(source_hand)))
        target_z=max(float(target.get('surface_z',.8))+float(obj['size'][2])+float(destination_offset[2])+.004,float(author.floor_clear_tcp(destination)))
        source_pose=[*source[:2],source_z];target_pose=[*(destination_xy+destination_offset[:2]),target_z]
        target_rotation=np.asarray(author.tcp_rotation_task(destination))
        if desired is not None:target_rotation=desired@np.asarray(body['mat']).T@target_rotation
        checks[source_hand].append(dict(position=source_pose,rotation=author.tcp_rotation_task(source_hand)))
        checks[destination].append(dict(position=target_pose,rotation=target_rotation))
        goal['_e07_engineering_arm']=destination
        if source_hand!=destination:
            relay=copy.deepcopy(goal);relay['target']=stage['id'];relay['_e07_engineering_target']=copy.deepcopy(stage);relay['_e07_engineering_arm']=source_hand;relay['_e07_relay_phase']='place_on_table'
            # These fields describe the final destination, not the temporary
            # physical table release. Only the private copied queue changes.
            relay.pop('placement_xy',None);relay.pop('required_support',None)
            if spec['id']=='E25':
                # Source-side hand only transports to the shared table site.
                # Final absolute orientation is applied by the receiving hand.
                for key in ('roll','pitch','yaw'):relay.pop(key,None)
            planned.append(relay);goal['_e07_after_relay']=copy.deepcopy(stage)
            if spec['id']=='E25'and spec['variant']=='B':relay['_e25_pickup_grasp_local']=list(source_local)
            for side,relay_offset in ((source_hand,source_offset),(destination,offset)):
                z=max(float(stage['surface_z'])+float(obj['size'][2])+float(relay_offset[2])+.004,source_z)
                checks[side].append(dict(position=[*(np.asarray(stage['xy'])+relay_offset[:2]),z],rotation=author.tcp_rotation_task(side)))
        if spec['id']=='E25'and spec['variant']=='B'and source_hand==destination:
            raise RuntimeError('E25 B distinct handle/receiver pinch requires actual table relay')
        planned.append(goal);records.append(dict(object=name,pickup_hand=source_hand,final_hand=destination,relay_inserted=source_hand!=destination,source_grasp_task_m=source.tolist(),source_grasp_local=list(source_local),destination_grasp_task_m=target_pose,private_grasp_local=list(obj.get('grasp_point_local',[0,0,0])),final_absolute_rotation=desired.tolist()if desired is not None else None))
    candidate_results={};failures=[]
    for side,targets in checks.items():
        result=ik_probe(author,author.c,side,targets);candidate_results[side]=dict(original=result)
        reachable=len(result)==len(targets)and all(x.get('kinematically_reachable')for x in result)
        receiver_goals=[g for g in planned if '_e07_after_relay'in g and g['_e07_engineering_arm']==side]
        if (not reachable and spec['id']=='E25' and spec['variant']=='A' and receiver_goals
                and all(r['pickup_hand']!=side and r['final_hand']==side for r in records)):
            from .execution_design_e25_reference import receiver_pitch_candidate
            rotation,proposals=receiver_pitch_candidate(author,side,targets)
            retried=ik_probe(author,author.c,side,proposals);candidate_results[side]['receiver_pitch_8deg']=retried
            reachable=len(retried)==len(proposals)and all(x.get('kinematically_reachable')and x.get('minimum_joint_margin_rad',0)>.01 for x in retried)
            if reachable:
                for g in receiver_goals:g['_e25_receiver_rotation_task']=rotation.tolist()
        if (not reachable and spec['id']=='E25' and spec['variant']=='B' and receiver_goals
                and all(r['pickup_hand']!=side and r['final_hand']==side for r in records)):
            from .execution_design_e25_b_reference import receiver_candidate
            for pitch_deg in (20,24):
                rotation,proposals=receiver_candidate(author,side,targets,pitch_deg)
                retried=ik_probe(author,author.c,side,proposals)
                candidate_results[side]['e25_b_receiver_'+str(pitch_deg)+'deg']=retried
                reachable=len(retried)==len(proposals)and all(x.get('kinematically_reachable')and x.get('minimum_joint_margin_rad',0)>.05 for x in retried)
                if reachable:
                    for g in receiver_goals:g['_e25_receiver_rotation_task']=rotation.tolist()
                    break
        if not reachable:failures.append(side)
    with (author.out/'e07-relay-plan.private.json').open('w')as stream:
        json.dump(dict(records=records,staging=stage,ik_candidates=candidate_results,unreachable_sides=failures,native_passed=False,collision_verified=False,source_goals_unchanged=True),stream)
    if failures:raise RuntimeError('E07 relay contains an unreachable measured endpoint: '+','.join(failures))
    return planned


def verify_relay_release(author,goal):
    """Require genuine supported release before the second hand approaches."""
    if '_e07_after_relay'not in goal:return
    _scope(author);name=goal['object'];target=goal['_e07_after_relay'];state,contacts=author.c.snapshot();body=state[name]
    if any(body.get('grasp',[]))or frozenset((name,'table'))not in contacts:
        raise RuntimeError('E07 relay requires actual release and table support')
    if np.any(np.abs(np.asarray(body['pos'])[:2]-target['xy'])>np.asarray(target['half_size'])):
        raise RuntimeError('E07 relay object is outside its measured temporary site')
