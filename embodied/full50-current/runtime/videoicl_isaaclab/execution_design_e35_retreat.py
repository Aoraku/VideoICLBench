"""Private engineering retreat above the measured completed stack.

The original stack, physical contacts and success evaluator are unchanged.
Only empty-hand public UP motions are issued before the horizontal retreat.
"""
import json
import numpy as np


def align_actual_stack_release(author, name, side, goal, target):
    """Center the held cube on its measured support before public release.

    The narrowest I-condition cube is only 21.84mm wide. A fixed TCP offset
    measured before transit accumulated 9-16mm of payload error in native B.
    Use the present body pose after every public move; never edit body state.
    """
    specs={o['id']:o for o in author.scene.spec['objects']}
    support=goal['required_support'];hand=0 if side=='left' else 1
    history=[]
    def measured():
        state,_=author.c.snapshot();body=state[name]
        if not body['grasp'][hand]:raise RuntimeError('E35 release alignment lost the actual cube grip')
        half=float((np.abs(body['mat'])@np.asarray(specs[name]['size'],float))[2])
        if support=='table':
            xy=np.asarray(target['xy'],float)
            surface=float(target.get('surface_z',.8))
        else:
            lower=state[support]
            if any(lower['grasp']):raise RuntimeError('E35 lower support is still held')
            xy=np.asarray(lower['pos'][:2],float)
            surface=float(lower['pos'][2]+(np.abs(lower['mat'])@np.asarray(specs[support]['size'],float))[2])
        position=np.asarray(body['pos'],float)
        return position,xy,surface,half
    position,xy,surface,half=measured()
    # Clear the measured support before correcting lateral payload error.
    if position[2]-half<surface+.008:
        tip=author.tip(side)
        author.move_generated({side:tip+[0,0,surface+.008+half-position[2]]},tolerance=.001)
    for attempt in range(16):
        position,xy,surface,half=measured()
        error=np.r_[xy-position[:2],surface+.003+half-position[2]]
        history.append(dict(attempt=attempt,position=position.tolist(),support_xy=xy.tolist(),support_top=surface,error=error.tolist()))
        if np.max(np.abs(error[:2]))<=.0015 and abs(error[2])<=.0015:break
        # Horizontal alignment finishes above the support; lower only after it.
        correction=error.copy()
        if np.max(np.abs(error[:2]))>.0015:correction[2]=max(0.,surface+.008+half-position[2])
        author.move_generated({side:author.tip(side)+correction},tolerance=.001)
    else:raise RuntimeError('E35 actual cube/support alignment did not converge')
    with (author.out/'E35-actual-stack-release.private.jsonl').open('a') as stream:
        stream.write(json.dumps(dict(object=name,support=support,history=history,public_actions_only=True))+'\n')


def lift_above_stack(author, side, requested_clearance):
    state, _ = author.c.snapshot()
    top = max(float(s['pos'][2] + (np.abs(s['mat']) @ np.asarray(o['size'], float))[2])
              for o in author.scene.spec['objects']
              if (s := state.get(o['id'])) is not None)
    floor = top + .025
    initial = author.finger_geometry(side)['lowest_z_task_m']
    for attempt in range(8):
        lowest = author.finger_geometry(side)['lowest_z_task_m']
        if lowest >= floor:
            break
        tip = author.tip(side)
        target = max(float(requested_clearance), float(tip[2] + floor - lowest + .003))
        author.move_generated({side: [*tip[:2], target]}, tolerance=.002)
    else:
        raise RuntimeError('E35 empty fingers failed to clear the actual completed stack')
    actual = float(author.tip(side)[2])
    with (author.out/'E35-retreat-clearance.private.json').open('w') as stream:
        json.dump(dict(actual_stack_top_task_m=top, required_finger_bottom_task_m=floor,
                       initial_finger_bottom_task_m=initial,
                       final_finger_bottom_task_m=author.finger_geometry(side)['lowest_z_task_m'],
                       actual_tcp_z_task_m=actual, public_up_only=True), stream, indent=2)
    return max(float(requested_clearance), actual)
