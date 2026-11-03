"""E28 source author: preserve the native-proven v11 insertion prefix.

Provenance: back25-e28a-primary-i4201-v11 frozen backstop SHA256
4ae0805ac823313da28aec9453e230e34145503f26702def8f9a49e7073e7ffc.
The successful original prefix, including its initial empty-hand UP retreat,
is preserved. Once the food actually lifts six millimetres without hand
contact, move that parked hand sideways before further loaded ascent. Actual
scoop history and native support criteria stay in the native evaluator.
This module does not impose an additional COM-inside-5mm author target.
"""
import json
import numpy as np
from .realworld_tool_expert import ToolExecutionError


def finger_target(food_pos, food_half, direction, finger):
    direction=np.asarray(direction,float);direction=direction/np.linalg.norm(direction)
    low=np.asarray(finger['aabb_min_task_m'],float);high=np.asarray(finger['aabb_max_task_m'],float)
    center=(low+high)/2;half=(high-low)/2
    desired=np.asarray(food_pos,float).copy()
    desired[:2]+=direction[:2]*(float(np.abs(direction)@np.asarray(food_half))+float(np.abs(direction)@half)+.002)
    desired[2]=float(food_pos[2]-food_half[2]+.0005+center[2]-low[2])
    return center,desired


def place(a, food, direction, guard):
    if a.s.get('auxiliary_loading_hand_allowed') is not True:
        raise ToolExecutionError('E28 source does not allow an auxiliary stabilizing hand')
    side='left';a._e28_backstop_park=np.asarray(a.tip(side),float).copy()
    a.stage('open-finger-backstop-'+food);a.act(side,'RELEASE')
    guard();state=a.snapshot()[0];obj=next(o for o in a.spec['objects']if o['id']==food)
    half=np.abs(state[food]['mat'])@np.asarray(obj['size'],float)
    fingers=a.a.finger_geometry(side)['fingers']
    projections=[float(np.asarray(f['aabb_center_task_m'])@direction)for f in fingers]
    candidates=[f for f,p in zip(fingers,projections)if p<=min(projections)+.005]
    # Prefer the positive-X finger when equally forward: its other open finger
    # remains away from the adjacent unselected food on the positive-X side.
    selected=max(candidates,key=lambda f:f['aabb_center_task_m'][0])['name']
    a.move(side,[*a.tip(side)[:2],max(1.08,float(a.tip(side)[2]))],guard)
    for index in range(10):
        guard();state=a.snapshot()[0]
        if any(state[food]['grasp']):raise ToolExecutionError('E28 auxiliary hand must not grasp food')
        finger=next(f for f in a.a.finger_geometry(side)['fingers']if f['name']==selected)
        center,target=finger_target(state[food]['pos'],half,direction,finger)
        error=target-center
        if np.max(abs(error))<=.0015:break
        # Keep the empty finger high until its lateral outside-food target is reached.
        if np.max(abs(error[:2]))>.0015:error[2]=0.
        a.move(side,a.tip(side)+error,guard,tolerance=.001)
    else:raise ToolExecutionError('E28 actual open-finger backstop did not converge')
    with (a.a.out/'E28-backstop.private.jsonl').open('a')as f:
        f.write(json.dumps(dict(step=a.c.steps,food=food,finger=selected,actual=finger,target=target.tolist(),grasp_requested=False))+'\n')
    return side


def withdraw(a,food,side,direction,guard):
    from .execution_design_e28_source import _scope
    from .execution_design_e28_backstop import withdraw as clear_loaded_route
    _scope(a)
    previous=getattr(a,'_e28_short_backstop_retreat',None)
    a._e28_short_backstop_retreat=True
    try:return clear_loaded_route(a,food,side,direction,guard)
    finally:
        if previous is None:del a._e28_short_backstop_retreat
        else:a._e28_short_backstop_retreat=previous


def insert(a, food, edge, side, direction, height, guard):
    """Track actual edge relative to food; a pushed food is never entry."""
    backstop=place(a,food,direction,guard);withdrawn=False;history=[]
    obj=next(o for o in a.spec['objects']if o['id']==food)
    initial_state=a.snapshot()[0][food]
    initial=np.asarray(initial_state['pos'],float).copy()
    initial_bottom=float(initial[2]-(np.abs(initial_state['mat'])@np.asarray(obj['size'],float))[2])
    for iteration in range(70):
        guard();state=a.snapshot()[0][food]
        if any(state['grasp']):raise ToolExecutionError('E28 food was grasped during physical insertion')
        center=np.asarray(state['pos']);half=np.abs(state['mat'])@np.asarray(obj['size'],float)
        extent=float(np.abs(np.asarray(state['mat']).T@direction)@np.asarray(obj['size'],float))
        point=a.point(edge);relative=float((point-center)@direction)
        row=dict(step=a.c.steps,food_id=food,relative_edge=relative,food=center.tolist(),blade=point.tolist(),backstop_withdrawn=withdrawn,food_grasp=state['grasp'])
        history.append(row)
        with (a.a.out/'E28-relative-insertion.private.jsonl').open('a')as stream:
            stream.write(json.dumps(row)+'\n')
        if not withdrawn and (relative>=-extent+.006 or center[2]-half[2]>initial_bottom+.0015):
            a.stage('withdraw-open-finger-before-blade-lift-'+food)
            a.move(backstop,a.tip(backstop)+[0,0,.08],guard)
            withdrawn=True
        # The blade surface is behind its leading edge. Once the measured
        # food center is 2mm behind that edge, trying to slide another 25mm
        # makes the already loaded food travel with the blade. Real support
        # and independent hand-free lift remain mandatory in solve().
        if withdrawn and relative>=.002:break
        if np.linalg.norm(center[:2]-initial[:2])>.035:
            raise ToolExecutionError('E28 food slid ahead without actual blade entry')
        a.stage('actual-relative-blade-insertion-'+food)
        # A contact insertion does not need a sub-millimetre point tracker.
        # Issue one ordinary bounded pulse, then reread real edge/food motion.
        # The original table/entry/hand-free lift witnesses remain native.
        axis=int(np.argmax(np.abs(direction[:2])))
        token=(('FWD','BACK'),('LEFT','RIGHT'))[axis][int(direction[axis]<0)]
        a.act(side,token,mm=6.)
    else:raise ToolExecutionError('E28 actual blade entry action bound exhausted')
    if not withdrawn:a.move(backstop,a.tip(backstop)+[0,0,.08],guard)
    with (a.a.out/'E28-relative-insertion.private.jsonl').open('a')as f:
        f.write(json.dumps(dict(food=food,history=history,hand_grasped=False))+'\n')
