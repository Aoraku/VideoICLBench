"""Private E27/E34 engineering routes using real table release and regrasp.

Only a copied reference queue changes. Scene goals, public controls and native
success criteria remain unchanged; geometry proposals are not reachability proof.
"""
import copy
import json
import math
import numpy as np
from .execution_design import REVISION_V3


def _scope(a):
    if not (getattr(a,'_execution_design_reference_authorized',False)
            and a.scene.spec['id'] in ('E27','E34')
            and a.scene.spec.get('execution_design',{}).get('revision')==REVISION_V3):
        raise ValueError('Explicit E27/E34 v3 engineering transfer required')


def choose_stage(lower,upper,half,obstacles,base_x):
    """Reject overlap with actual bodies and every reserved final target."""
    lower,upper,half=map(lambda v:np.asarray(v,float),(lower,upper,half))
    if not np.isfinite(np.r_[lower,upper,half,base_x]).all()or np.any(half<=0):
        raise ValueError('Finite measured staging geometry required')
    for dx in (.35,.29,.45,.53,.65):
        for y in (0.,-.24,.24,-.32,.32):
            xy=np.array([base_x+dx,y])
            if np.any(xy-half<lower)or np.any(xy+half>upper):continue
            if any(np.all(np.abs(xy-np.asarray(center))<=np.asarray(extent)+half)for center,extent in obstacles):continue
            return xy
    raise RuntimeError('No measured empty cutlery handoff site')


def initial_pickup_hand(a):
    """Park the correct peer once, using the first relay leg's pickup rule."""
    _scope(a);spec=a.scene.spec;goals=list(spec['goals'])
    zones={z['id']:z for z in spec['zones']}
    if not spec.get('expert_preserve_goal_order'):
        goals.sort(key=lambda g:float(zones[g['target']]['xy'][0]),reverse=spec.get('variant')=='A')
    if not goals:raise ValueError('Cutlery pickup requires an actual goal')
    name=goals[0]['object'];obj=next(o for o in spec['objects']if o['id']==name)
    state,_=a.c.snapshot();body=state[name]
    source=np.asarray(body['pos'])+np.asarray(body['mat'])@np.asarray(obj['grasp_point_local'])
    distances={}
    for side,robot in a.scene.robots.items():
        value=robot.data.root_pos_w[0]
        if hasattr(value,'detach'):value=value.detach()
        if hasattr(value,'cpu'):value=value.cpu()
        base=np.asarray(a.scene.world_to_task(np.asarray(value,float)))
        distances[side]=float(np.linalg.norm(source[:2]-base[:2]))
        if spec['id']=='E34':
            # The closest source hand need not cover the receiving tray.
            # Choose one hand for both endpoints, rather than accepting a
            # low destination pose with only milliradians of joint margin.
            target=np.asarray(zones[goals[0]['target']]['xy'],float)+(
                np.asarray(body['mat'])@np.asarray(obj['grasp_point_local']))[:2]
            distances[side]=max(distances[side],float(np.linalg.norm(target-base[:2])))
    return min(distances,key=distances.get)


def released_return_clearance(a,side,clearance):
    """Keep a released wrist high until it has returned to its home XY."""
    _scope(a);state,_=a.c.snapshot()
    if a.carried_payload is not None or any(any(row.get('grasp',[]))for row in state.values()):
        raise RuntimeError('Cutlery return requires actual release before switching hands')
    height=max(float(clearance),float(a.tip(side)[2]))
    if not np.isfinite(height):raise ValueError('Finite measured return clearance required')
    return height


def plan_transfers(a,goals,prefer_single_hand=False):
    _scope(a)
    if prefer_single_hand:
        side=initial_pickup_hand(a)
        planned=copy.deepcopy(goals)
        for goal in planned:goal.update(_cutlery_arm=side,_cutlery_direct=True)
        (a.out/'cutlery-transfer-plan.private.json').write_text(json.dumps(dict(
            records=[dict(object=g['object'],pickup_hand=side,final_hand=side,relay_inserted=False)for g in planned],
            source_goals_unchanged=True,native_reachability_verified=False,
            policy='single initial hand; actual loaded route screened before public translation')))
        return planned
    from .execution_design_thin_edge import table_bounds_task
    state,_=a.c.snapshot();spec=a.scene.spec
    objects={o['id']:o for o in spec['objects']};zones={z['id']:z for z in spec['zones']}
    bases={}
    for side,robot in a.scene.robots.items():
        p=robot.data.root_pos_w[0]
        if hasattr(p,'detach'):p=p.detach()
        if hasattr(p,'cpu'):p=p.cpu()
        bases[side]=np.asarray(a.scene.world_to_task(np.asarray(p,float)))
    def nearest(xy):return min(bases,key=lambda side:np.linalg.norm(np.asarray(xy)-bases[side][:2]))
    bounds=table_bounds_task(a.scene);planned=[];records=[]
    for original in goals:
        goal=copy.deepcopy(original);name=goal['object'];obj=objects[name];body=state[name]
        rotation=np.asarray(body['mat']);offset=rotation@np.asarray(obj['grasp_point_local'])
        source=np.asarray(body['pos'])+offset;target=zones[goal['target']]
        source_hand=nearest(source[:2]);destination_hand=nearest(np.asarray(target['xy'])+offset[:2])
        goal['_cutlery_arm']=destination_hand
        record=dict(object=name,pickup_hand=source_hand,final_hand=destination_hand,relay_inserted=source_hand!=destination_hand)
        if source_hand!=destination_hand:
            half=np.abs(rotation)@np.asarray(obj.get('bounds_half_extent',obj['size']))
            # Final yaw may differ from pickup; reserve both actual and flat
            # cutlery footprint for the real intermediate table placement.
            footprint=np.maximum(half[:2],np.asarray(obj['size'])[:2])+.025
            obstacles=[]
            for key,other in objects.items():
                value=state[key];rot=np.asarray(value['mat']);center=np.asarray(value['pos'])+rot@np.asarray(other.get('local_bounds_center',[0,0,0]))
                extent=np.abs(rot)@np.asarray(other.get('bounds_half_extent',other['size']))
                obstacles.append((center[:2],extent[:2]))
            obstacles.extend((z['xy'],z['half_size'])for z in spec['zones'])
            xy=choose_stage(np.asarray(bounds['lower'])[:2],np.asarray(bounds['upper'])[:2],footprint,obstacles,float(np.mean([b[0]for b in bases.values()])))
            stage=dict(id='engineering-cutlery-table',xy=xy.tolist(),half_size=footprint.tolist(),surface_z=float(bounds['top']),support='table')
            relay=copy.deepcopy(goal);relay['_cutlery_target']=stage;relay['_cutlery_arm']=source_hand
            relay.pop('placement_xy',None);relay.pop('required_support',None)
            for key in ('roll','pitch','yaw'):relay.pop(key,None)
            planned.append(relay);goal['_cutlery_after_relay']=stage;record['stage']=stage
        planned.append(goal);records.append(record)
    (a.out/'cutlery-transfer-plan.private.json').write_text(json.dumps(dict(records=records,source_goals_unchanged=True,native_reachability_verified=False)))
    return planned


def translation_samples(start,target,step=.04):
    start=np.asarray(start,float).copy();target=np.asarray(target,float)
    if start.shape!=(3,)or target.shape!=(3,)or not np.isfinite(np.r_[start,target,step]).all()or step<=0:
        raise ValueError('Finite three-dimensional route required')
    result=[]
    while np.max(np.abs(target-start))>1e-7:
        delta=target-start;i=int(np.argmax(np.abs(delta)))
        start[i]+=np.sign(delta[i])*min(step,abs(delta[i]));result.append(start.copy())
    return result


def screen_direct_translation(a,name,side,target,ik_probe=None):
    """Check measured loaded FK candidates, then retain public action execution."""
    _scope(a);state,_=a.c.snapshot()
    if a.carried_payload!=(name,side)or not state[name]['grasp'][0 if side=='left'else 1]:
        raise RuntimeError('Direct cutlery route requires actual payload grasp')
    points=translation_samples(a.tip(side),target)
    if not points:return
    if ik_probe is None:
        from .execution_design_drawer_ik_probe import inspect
        ik_probe=inspect
    rotation=np.asarray(a.tcp_rotation_task(side),float)
    checked=ik_probe(a,a.c,side,[dict(position=p,rotation=rotation)for p in points])
    valid=len(checked)==len(points)and all(
        x['kinematically_reachable']and x['position_error_m']<.001
        and x['orientation_error_rad']<np.deg2rad(1.5)
        and x['minimum_joint_margin_rad']>=.04 for x in checked)
    if valid and len(checked)>1:
        valid=all(np.max(np.abs(np.asarray(y['candidate_joints_rad'])-x['candidate_joints_rad']))<np.pi
                  for x,y in zip(checked,checked[1:]))
    with (a.out/'cutlery-direct-route.private.jsonl').open('a')as f:
        f.write(json.dumps(dict(step=a.c.steps,object=name,side=side,target=np.asarray(target).tolist(),
            sampled_positions=[p.tolist()for p in points],candidates=checked,
            kinematic_screen_passed=bool(valid),native_route_verified=False,actuation_performed=False))+'\n')
    if not valid:raise RuntimeError('Direct cutlery route lacks measured continuous joint margin')


def orient_for_rule(a,name,side):
    """Preserve acquired tilt; correct only a native required planar heading."""
    _scope(a)
    if a.scene.spec['id']=='E34' and name in a.scene.spec.get('semantic',{}).get('handle_points',{}):
        # Carry above the destination first. Rotating at the near-source
        # wrist pose can exhaust joint6 despite safe destination geometry.
        # Actual handle leveling runs immediately before placement instead.
        return
    rule=a.scene.spec.get('semantic',{}).get('orientation_targets',{}).get(name)
    if rule is None:
        with (a.out/'cutlery-rule-orientation.private.jsonl').open('a')as f:
            f.write(json.dumps(dict(step=a.c.steps,object=name,side=side,
                constraint='no_native_orientation_target',rotation_requested=False))+'\n')
        return
    axis=np.asarray(rule['working_axis_local'],float);wanted=float(rule['yaw'])
    tolerance=min(.05,float(rule.get('tolerance_rad',.25))*.5)
    errors=[]
    for _ in range(80):
        state,_=a.c.snapshot();body=state[name]
        if a.carried_payload!=(name,side)or not body['grasp'][0 if side=='left'else 1]:
            raise RuntimeError('Cutlery heading correction requires actual grasp')
        direction=np.asarray(body['mat'])@axis
        if np.linalg.norm(direction[:2])<1e-6:raise RuntimeError('Cutlery working axis has no horizontal heading')
        error=math.atan2(math.sin(wanted-math.atan2(direction[1],direction[0])),
                         math.cos(wanted-math.atan2(direction[1],direction[0])))
        with (a.out/'cutlery-rule-orientation.private.jsonl').open('a')as f:
            f.write(json.dumps(dict(step=a.c.steps,object=name,side=side,
                constraint='native_projected_working_axis_yaw',error_rad=error,
                actual_rotation=np.asarray(body['mat']).tolist(),unrequested_tilt_preserved=True))+'\n')
        if abs(error)<tolerance:return
        errors.append(abs(error))
        if len(errors)>=16 and min(errors[-16:-8])-min(errors[-8:])<math.radians(.1):
            raise RuntimeError('Actual cutlery heading correction stalled')
        token='ROTATE_CCW'if error>0 else'ROTATE_CW'
        a.act(token if side=='left'else'STILL',token if side=='right'else'STILL',
              rotation_deg=min(5.,max(.5,abs(math.degrees(error)))))
    raise RuntimeError('Actual cutlery heading correction did not converge')


def verify_relay_release(a,goal):
    if '_cutlery_after_relay'not in goal:return
    _scope(a);state,contacts=a.c.snapshot();name=goal['object'];body=state[name];target=goal['_cutlery_after_relay']
    if any(body.get('grasp',[]))or frozenset((name,'table'))not in contacts:
        raise RuntimeError('Cutlery relay requires actual release and table support')
    if np.any(np.abs(np.asarray(body['pos'])[:2]-target['xy'])>target['half_size']):
        raise RuntimeError('Cutlery relay outside measured table site')


def loaded_clearance(a,name,side,previous):
    """Re-measure after acquisition/orientation, rather than an empty wrist."""
    _scope(a);state,_=a.c.snapshot();spec=a.scene.spec;body=state[name];tcp=np.asarray(a.tip(side))
    if a.carried_payload!=(name,side)or not body['grasp'][0 if side=='left'else 1]:
        raise RuntimeError('Measured cutlery clearance requires actual payload grasp')
    tops=[];bottom=None;rotation_radius=None
    for obj in spec['objects']:
        value=state[obj['id']];rot=np.asarray(value['mat']);center=np.asarray(value['pos'])+rot@np.asarray(obj.get('local_bounds_center',[0,0,0]))
        half=np.abs(rot)@np.asarray(obj.get('bounds_half_extent',obj['size']))
        if obj['id']==name:
            bottom=float(center[2]-half[2])
            # A thin utensil can rotate between genuine opposing contacts.
            # Bound its full source geometry around the ACTUAL measured TCP,
            # not just its currently horizontal lower face. This encloses the
            # long fork tip even if it swings downward during translation.
            local_half=np.asarray(obj.get('bounds_half_extent',obj['size']))
            corners=np.array([[x,y,z]for x in(-1,1)for y in(-1,1)for z in(-1,1)])*local_half
            rotation_radius=float(np.linalg.norm(center+corners@rot.T-tcp,axis=1).max())
        else:tops.append(float(center[2]+half[2]))
    geometry=a.finger_geometry(side)
    if geometry.get('source')!='actual_collision_mesh_current_body_pose':raise ValueError('Actual loaded finger geometry required')
    # Include actual palm as well as fingertips; its clearance can change
    # substantially during the 30-degree thin-handle acquisition.
    from .execution_design_e33_grasp import actual_mesh
    palm_bottom=float(actual_mesh(a,side,'panda_hand')[:,2].min())
    depth=max(rotation_radius,0.,float(tcp[2])-min(bottom,palm_bottom,float(geometry['lowest_z_task_m'])))
    # Clearance is a lower bound, not a command to descend at the source.
    # A successful held rotation may have raised TCP away from a local limit.
    clearance=max(float(previous),float(tcp[2]),max([.8,*tops])+depth+.025)
    if not np.isfinite(clearance):raise ValueError('Finite loaded clearance required')
    with (a.out/'cutlery-loaded-clearance.private.jsonl').open('a')as stream:
        stream.write(json.dumps(dict(step=a.c.steps,object=name,side=side,payload_bottom=bottom,palm_bottom=palm_bottom,rotation_envelope_radius=rotation_radius,loaded_depth=depth,clearance_z=clearance))+'\n')
    return clearance
