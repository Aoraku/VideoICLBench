"""Physically choose equivalent Panda finger assignments before E39 turns."""
import json
import math
import numpy as np
from .realworld_tool_expert import _axis_rotation


def wrap(angle):
    return float((angle+math.pi) % (2*math.pi)-math.pi)


def wrist(author, side):
    robot=author.scene.robots[side]
    ids,_=robot.find_joints('panda_joint7')
    if len(ids)!=1:raise ValueError('E39 requires actual Panda joint7')
    index=ids[0]
    return float(robot.data.joint_pos[0,index]), robot.data.soft_joint_pos_limits[0,index].cpu().numpy()


def choose_turn(delta, q, limits):
    # The hand is palm down: world +Z yaw decreases Panda joint7.
    options=[delta]
    if abs(delta)>math.radians(150):options.extend([delta+2*math.pi,delta-2*math.pi])
    valid=[x for x in options if limits[0]+.08 <= q-x <= limits[1]-.08]
    return min(valid,key=abs) if valid else None


def prepare_empty(author, side, name, goal):
    if 'roll' in goal or 'pitch' in goal or 'yaw' not in goal:
        raise ValueError('E39 wrist assignment requires the declared yaw goal')
    state,_=author.c.snapshot()
    if any(state[name]['grasp']):raise RuntimeError('E39 finger assignment requires an empty hand')
    current=math.atan2(state[name]['mat'][1,0],state[name]['mat'][0,0])
    delta=wrap(float(goal['yaw'])-current)
    q,limits=wrist(author,side)
    if choose_turn(delta,q,limits) is not None:return
    # Swap equivalent opposed fingers while high above the source, before
    # grasping. Neither body nor robot state is reset.
    turn=math.copysign(math.pi,q)
    for _ in range(2):author.rotate_tcp_smooth(side,_axis_rotation([0,0,1],turn/2))
    after,_=wrist(author,side)
    with (author.out/'E39-wrist-assignment.private.jsonl').open('a') as stream:
        stream.write(json.dumps(dict(object=name,before_joint7=q,after_joint7=after,
            actual_empty_turn=turn,goal_delta=delta,limits=limits.tolist()))+'\n')
    if choose_turn(delta,after,limits) is None:
        raise RuntimeError('No original Panda wrist range for E39 yaw after real finger swap')


def rotate_held(author, name, side, goal):
    target=float(goal['yaw']);state,_=author.c.snapshot()
    initial=math.atan2(state[name]['mat'][1,0],state[name]['mat'][0,0])
    q,limits=wrist(author,side)
    turn=choose_turn(wrap(target-initial),q,limits)
    if turn is None:raise RuntimeError('E39 held yaw would exceed original Panda joint7 limits')
    count=max(1,math.ceil(abs(turn)/(math.pi/2)))
    def held():
        value,_=author.c.snapshot()
        if not value[name]['grasp'][0 if side=='left' else 1]:raise RuntimeError('E39 real grip lost during yaw')
    for index in range(1,count+1):
        waypoint=initial+turn*index/count
        def reached():
            values,_=author.c.snapshot();rotation=values[name]['mat']
            return abs(wrap(math.atan2(rotation[1,0],rotation[0,0])-waypoint))<math.radians(3)
        for _ in range(3):
            held()
            if reached():break
            values,_=author.c.snapshot();rotation=values[name]['mat']
            residual=wrap(waypoint-math.atan2(rotation[1,0],rotation[0,0]))
            author.rotate_tcp_smooth(side,_axis_rotation([0,0,1],residual),guard=held,done=reached)
        if not reached():raise RuntimeError('E39 actual material yaw failed to reach waypoint')
