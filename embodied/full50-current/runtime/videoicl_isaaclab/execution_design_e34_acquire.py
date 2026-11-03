"""E34 private material approach using a measured narrow, collision-clear jaw.

This only reaches a physical pre-grasp pose. The caller still issues real GRASP
and verifies actual opposing contacts, lift, transport, release and native rule.
"""
import json
from types import SimpleNamespace
import numpy as np
from .execution_design_e34_reference import scope


def check_pickup_neighbors(a,side,selected,baseline):
    """Preserve other cutlery; permit a small real nudge of the movable tray."""
    values,contacts=a.c.snapshot();spec=a.scene.spec;tray=spec['semantic']['container']
    objects={o['id']:o for o in spec['objects']}
    for n,old in baseline.items():
        body=values[n]
        movable_tray=(spec.get('variant')=='B'and n==tray and objects[n].get('role')=='movable')
        translation=.010 if movable_tray else .002
        rotation=.1233742584 if movable_tray else .03
        if any(body['grasp'])or np.linalg.norm(np.asarray(body['pos'])-old['pos'])>translation or np.linalg.norm(np.asarray(body['mat'])-old['mat'])>rotation:
            raise RuntimeError('E34 pickup exceeded original cutlery or movable-container guard: '+n)
        if movable_tray:
            if frozenset((n,'table'))not in contacts:raise RuntimeError('E34 movable tray lost real table support')
        elif any(float(a.c.contact_forces.get(frozenset((n,side+'_finger'+str(i))),0.))>.001 for i in(1,2)):
            raise RuntimeError('E34 pickup touched unselected cutlery: '+n)


def narrow_material_approach(a,side,obj,unused_target=None):
    scope(a)
    spec=a.scene.spec;name=obj['id'];selected=spec.get('semantic',{}).get('selected')
    if spec.get('variant')not in ('B','C')or name!=selected or name not in ('spoon','fork'):
        raise ValueError('Explicit E34B spoon or E34C fork selected material required')
    from .execution_design_e33_grasp import actual_mesh
    from .execution_design_cutlery_grasp import sectional_target
    from .execution_design_thin_edge import table_bounds_task
    from .execution_design_branch_geometry import collision_parts_task
    from .execution_design_e34_debug import preview_clearance,deep_capture
    required_depth=.001 if spec.get('variant')=='B'else .003
    floor=float(table_bounds_task(a.scene)['top']);objects={o['id']:o for o in spec['objects']}
    state,_=a.c.snapshot()
    if any(any(b['grasp'])for b in state.values()):raise RuntimeError('Narrow material approach requires an actually empty hand')
    baseline={n:dict(pos=np.asarray(b['pos']).copy(),mat=np.asarray(b['mat']).copy())for n,b in state.items()if n!=name}
    fingers=[side+'_finger1',side+'_finger2'];signs=a.generated_axis_signs[side]
    labels=(('FWD','BACK'),('LEFT','RIGHT'),('UP','DOWN'));trace=[];monitored_mode=False
    def force(x,y):return float(getattr(a.c,'contact_forces',{}).get(frozenset((x,y)),0.))
    def guard():
        check_pickup_neighbors(a,side,name,baseline)
    def pulse(token,mm):
        a.act(token if side=='left'else'STILL',token if side=='right'else'STILL',mm);guard()
    def move(target,tolerance=.0015,done=None):
        target=np.asarray(target,float);errors=[]
        for _ in range(100):
            if done is not None and done():return
            error=target-np.asarray(a.tip(side))
            if np.max(abs(error))<=tolerance:return
            errors.append(float(np.linalg.norm(error)))
            if len(errors)>=24 and min(errors[-24:-16])-min(errors[-8:])<.0004:raise RuntimeError('E34 narrow material approach stalled')
            axis=int(np.argmax(abs(error)));positive=1 if error[axis]>0 else-1
            ceiling=3. if monitored_mode else 15.
            minimum=1. if monitored_mode else 3.
            pulse(labels[axis][0 if signs[axis]==positive else 1],min(ceiling,max(minimum,abs(error[axis])*1000)))
        raise RuntimeError('E34 narrow approach action bound exhausted')
    def frame(ref):
        b=a.c.snapshot()[0][ref['actor']];return np.asarray(b['pos']),np.asarray(b['mat'])
    policy=SimpleNamespace(a=a,frame=frame)
    def save(status,**extra):
        record=dict(object=name,side=side,step=a.c.steps,status=status,trace=trace,
            source='native_enabled_collision_pieces_and_actual_low_finger_cross_sections',
            public_grasp_not_yet_attempted=True,native_grasp_verified=False,
            private_pregrasp_depth_m=required_depth,**extra)
        with(a.out/'e34-narrow-material-approach.private.jsonl').open('a')as f:f.write(json.dumps(record,default=lambda v:v.tolist()if hasattr(v,'tolist')else str(v))+'\n')
    try:
        # The B spoon previously achieved a genuine loaded pickup from this
        # material depth. Do not force its broad palm down into the tray merely
        # to meet an extra 3mm author waypoint; real GRASP/lift still must pass.
        if spec.get('variant')=='B':
            body=a.c.snapshot()[0][name]
            point=np.asarray(body['pos'])+np.asarray(body['mat'])@np.asarray(obj['grasp_point_local'])
            pads=[actual_mesh(a,side,n)for n in a.scene.embodiment.fingers]
            if deep_capture(point,pads,floor,depth=required_depth):
                guard();save('actual_existing_material_pregrasp',actual_tcp=a.tip(side),material_point=point)
                return np.asarray(a.tip(side)).copy()
        # If the caller is still low, first clear all unselected actual material.
        meshes=[actual_mesh(a,side,n)for n in ('panda_hand',*a.scene.embodiment.fingers)]
        tip=np.asarray(a.tip(side));parts={n:collision_parts_task(policy,n)for n in state if n!=name}
        top=max([floor,*[float(p[:,2].max())for values in parts.values()for p in values]])
        bottom=min(float(m[:,2].min())for m in meshes)
        if bottom<top+.012:move([*tip[:2],float(tip[2])+top+.015-bottom],tolerance=.003)
        chosen=None;monitored=None
        openings=(.010,.012,.015,.018)if spec.get('variant')=='B'else(.015,.018)
        for opening in openings:
            a.c.grips[side]=opening
            trace.append(dict(step=a.c.steps,per_finger_motor_target_m=opening,joint_state_written=False))
            for _ in range(2):a.act();guard()
            values,_=a.c.snapshot();body=values[name];point=np.asarray(body['pos'])+np.asarray(body['mat'])@np.asarray(obj['grasp_point_local'])
            tip=np.asarray(a.tip(side));rotation=np.asarray(a.tcp_rotation_task(side));palm=actual_mesh(a,side,'panda_hand');pads=[actual_mesh(a,side,n)for n in a.scene.embodiment.fingers]
            goal=sectional_target(point,tip,rotation,rotation,palm,pads,floor)
            obstacles={n:collision_parts_task(policy,n)for n in values if n!=name}
            clear,blocker=preview_clearance([palm,*pads],goal-tip,obstacles)
            trace.append(dict(step=a.c.steps,proposed_tcp=goal,material_point=point,clear=clear,blocker=blocker,native_collision_pieces={n:len(v)for n,v in obstacles.items()}))
            if clear:chosen=goal;break
            if spec.get('variant')=='B'and blocker==spec['semantic']['container']and monitored is None:
                # A convex hull is only a proposal. Retain full actual geometry
                # and allow a bounded, contact-monitored physical approach.
                monitored=(goal.copy(),opening)
                geometry=dict(step=a.c.steps,side=side,proposed_tcp=goal.tolist(),actual_tcp=tip.tolist(),
                    actual_hand_meshes=[m.tolist()for m in[palm,*pads]],
                    actual_obstacle_collision_parts={n:[p.tolist()for p in parts]for n,parts in obstacles.items()},
                    convex_proxy_overlap_only=True,native_clearance_verified=False)
                (a.out/'e34-pregrasp-proxy-overlap.private.json').write_text(json.dumps(geometry)+'\n')
        if chosen is None and monitored is not None:
            monitored_mode=True
            chosen,opening=monitored;a.c.grips[side]=opening
            for _ in range(2):a.act();guard()
            trace.append(dict(step=a.c.steps,convex_proxy_only_overlap_monitored=True,
                per_finger_motor_target_m=opening,actual_unselected_contact_guard_retained=True))
        if chosen is None:raise RuntimeError('No measured narrow jaw clears actual neighboring material')
        def actual_deep_capture():
            values,_=a.c.snapshot();body=values[name]
            point=np.asarray(body['pos'])+np.asarray(body['mat'])@np.asarray(obj['grasp_point_local'])
            return deep_capture(point,[actual_mesh(a,side,n)for n in a.scene.embodiment.fingers],floor,depth=required_depth)
        height=float(a.tip(side)[2]);move([chosen[0],chosen[1],height],tolerance=.002)
        move(chosen,done=actual_deep_capture if spec.get('variant')=='B'else None)
        values,_=a.c.snapshot();body=values[name];point=np.asarray(body['pos'])+np.asarray(body['mat'])@np.asarray(obj['grasp_point_local']);pads=[actual_mesh(a,side,n)for n in a.scene.embodiment.fingers]
        if not deep_capture(point,pads,floor,depth=required_depth):raise RuntimeError('E34 selected material not between both actual pads')
        guard();save('actual_deep_pregrasp',actual_tcp=a.tip(side),material_point=point)
        return np.asarray(a.tip(side)).copy()
    except Exception as exc:
        save('failed',error=type(exc).__name__+': '+str(exc));raise


def run_debug(a,payload):
    """Resume an empty-handed checkpoint at the true material approach only."""
    if not getattr(a.c,'_engineering_diagnostic_only',False):raise ValueError('Admitted diagnostic checkpoint required')
    if a.scene.spec.get('variant')=='B'and payload.get('balanced_grasp'):
        from .execution_design_e34b_balanced_grasp import run_debug as balanced
        return balanced(a,payload)
    spec=a.scene.spec;side=payload.get('side','left');name=spec['semantic']['selected']
    state,_=a.c.snapshot();baseline={n:dict(pos=np.asarray(b['pos']).copy(),mat=np.asarray(b['mat']).copy())for n,b in state.items()if n!=name}
    obj=next(o for o in spec['objects']if o['id']==name);a.carried_payload=None
    narrow_material_approach(a,side,obj)
    a.stage='debug-e34-narrow-real-grasp'
    for _ in range(3):
        a.act('GRASP'if side=='left'else'STILL','GRASP'if side=='right'else'STILL')
        check_pickup_neighbors(a,side,name,baseline)
    state,_=a.c.snapshot()
    if not state[name]['grasp'][0 if side=='left'else 1]:raise RuntimeError('Narrow pregrasp did not produce real selected-object grasp')
    a.carried_payload=(name,side)
    from .execution_design_e34_tail import finish_from_grasp
    report=finish_from_grasp(a,name,side)
    return dict(report,segment_passed=True,local_debug_only=True,fixed36_positive=False)
