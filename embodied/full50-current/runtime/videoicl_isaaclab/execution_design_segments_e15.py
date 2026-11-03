"""E15B/C local red-piece suffixes after original 118/716-action boundaries.

Uses the original empty-wrist preparation and generated public transfer tail.
No completed blue-piece route, calibration prefix, pose or score is replayed.
"""
from copy import deepcopy
import math
import numpy as np
from .execution_design import REVISION_V3, source_sha256
from .realworld_semantic_checks import POSITION_TOLERANCE_M, ANGLE_TOLERANCE_DEG


def _finite(value, shape):
    value = np.asarray(value, float)
    if value.shape != shape or not np.isfinite(value).all():
        raise ValueError('Finite measured E15 segment context required')
    return value


def _goal(spec, name, target):
    goals = [g for g in spec.get('goals', []) if g.get('object') == name and g.get('target') == target]
    if len(goals) != 1 or goals[0].get('type') != 'place' or set(goals[0]) - {'type','object','target','yaw'}:
        raise ValueError('Original unique E15 yaw-placement goal required')
    goal = goals[0]
    if type(goal.get('yaw')) not in (int,float) or not math.isfinite(goal['yaw']):
        raise ValueError('Original finite E15 goal yaw required')
    return goal


def _blue_preserved(author, goal, original=None, *, require_goal=True):
    state, contacts = author.c.snapshot(); body = state['blue_t']
    zone = next(z for z in author.scene.spec['zones'] if z['id'] == goal['target'])
    position = _finite(body['pos'], (3,)); rotation = _finite(body['mat'], (3,3))
    yaw = math.atan2(rotation[1,0],rotation[0,0])
    error = math.atan2(math.sin(yaw-goal['yaw']),math.cos(yaw-goal['yaw']))
    if any(body['grasp']) or frozenset(('blue_t','table')) not in contacts:
        raise RuntimeError('Protected blue T must remain released and supported')
    if require_goal and (np.linalg.norm(position[:2]-zone['xy']) > POSITION_TOLERANCE_M
                         or abs(error) > math.radians(ANGLE_TOLERANCE_DEG)):
        raise RuntimeError('Previously completed blue T must remain correctly placed')
    if original is not None and (np.linalg.norm(position-original[0]) > .002
            or np.linalg.norm(rotation-original[1]) > .02):
        raise RuntimeError('Protected blue T moved during local red suffix')
    return position.copy(), rotation.copy()


def run_segment(author, segment, parameters):
    if segment=='e15_b_complete_blue_from95':
        from .execution_design_e15_b_reference import run_segment as blue
        return blue(author,segment,parameters)
    if segment=='e15_b_rotate_place_red_from14':
        from .execution_design_e15_held_red import run_segment as held_red
        return held_red(author,segment,parameters)
    if segment in('e15_b_grasp_red_hover118','e15_b_close_lift_from56'):
        from .execution_design_e15_red_acquire import run_segment as acquire
        return acquire(author,segment,parameters)
    if segment in('e15_b_recover214_and_approach_red','e15_b_continue_recovered1_to_red','e15_b_continue11_with_small_wrist_steps'):
        from .execution_design_segments_e15_recover import run_segment as recover
        return recover(author,segment,parameters)
    entries={'e15_resume_empty_wrist_then_place':('C',716,72440,True),
             'e15_b_resume_red_from_empty_boundary':('B',118,12640,False)}
    if segment not in entries or not isinstance(parameters,dict):
        raise ValueError('Explicit E15 empty-wrist local suffix required')
    variant,source_steps,source_tick,blue_completed=entries[segment]
    if set(parameters) - {'object','side','clearance'}:
        raise ValueError('Unknown E15 suffix parameters; source goals cannot be overridden')
    a = author; spec = a.scene.spec; design = spec.get('execution_design',{})
    checkpoint = getattr(a,'_engineering_resume_checkpoint',{})
    source = checkpoint.get('source',{})
    if (spec.get('id') != 'E15' or spec.get('variant') != variant or spec.get('seed') != 4201
            or design.get('condition') != 'I' or design.get('revision') != REVISION_V3
            or design.get('source_sha256') != source_sha256(REVISION_V3)
            or not getattr(a,'_execution_design_reference_authorized',False)
            or not a.control_report.get('engineering_reference_only') or a.smooth
            or a.scene.embodiment.name != 'franka' or checkpoint.get('diagnostic_only') is not True
            or source.get('steps') != source_steps or source.get('physics_ticks') != source_tick):
        raise ValueError('Pinned E15 variant/I/4201 diagnostic boundary required')
    if parameters.get('object','red_t') != 'red_t' or parameters.get('side','right') != 'right':
        raise ValueError('Local E15 suffix is only the original right-hand red T')
    recording = a.scene.embodiment.config.get('author_recording',{})
    clearance = float(recording.get('transfer_clearance_z',1.10))
    if not math.isfinite(clearance) or not math.isclose(float(parameters.get('clearance',clearance)),clearance,abs_tol=1e-10,rel_tol=0):
        raise ValueError('Original profile transfer clearance cannot be overridden')
    if any(recording.get(k) is not None for k in ('pre_grasp_opening_m','release_opening_m')):
        raise ValueError('E15 suffix requires the original public gripper route')
    if getattr(a,'carried_payload',None) is not None or getattr(a,'_e15_wrist_branch',None):
        raise RuntimeError('E15 suffix starts empty without a fabricated prepared branch')
    state, contacts = a.c.snapshot()
    if any(any(body.get('grasp',[])) for body in state.values()) or frozenset(('red_t','table')) not in contacts:
        raise RuntimeError('Both hands empty and real red source table support required')
    goal = _goal(spec,'red_t','red_t_target'); blue_goal = _goal(spec,'blue_t','blue_t_target')
    obj = next(o for o in spec['objects'] if o['id'] == 'red_t')
    if (obj.get('source_asset',{}).get('sha256') != '98bae9ae3dddf67e58004695930c09f3d36f715dfa2bf5d65d1ed2b7179fa493'
            or not spec.get('task_adapter','').startswith(('realworld','full50'))):
        raise ValueError('Original source T geometry and generated tabletop adapter required')
    target = next(z for z in spec['zones'] if z['id'] == goal['target'])
    preserved_blue = _blue_preserved(a,blue_goal,require_goal=blue_completed)
    before = a.c.steps; operations = []; old_act = a.act
    had_local_act = 'act' in a.__dict__; previous_local_act = a.__dict__.get('act')
    def guarded_act(*args,**kwargs):
        _blue_preserved(a,blue_goal,preserved_blue,require_goal=blue_completed)
        def held_red():
            if getattr(a,'carried_payload',None) is not None:
                actual,pairs=a.c.snapshot()
                if (a.carried_payload!=('red_t','right') or not actual['red_t']['grasp'][1]
                        or not all(frozenset(('red_t','right_finger'+str(i)))in pairs for i in (1,2))):
                    raise RuntimeError('Local red T lost actual bilateral carrying contact')
        held_red()
        result = old_act(*args,**kwargs)
        held_red()
        _blue_preserved(a,blue_goal,preserved_blue,require_goal=blue_completed)
        return result
    a.act = guarded_act
    try:
        from .execution_design_e15_wrist import prepare_empty,prepared_empty_height
        a.stage = 'segment-e15-resume-empty-wrist-red_t'
        prepare_empty(a,'right','red_t',goal,clearance)
        operations.append(dict(operation='original_measured_empty_wrist_preparation',actor='red_t'))
        # Identical E15-only remainder of Demonstration.solve_generated after
        # prepare_empty: recompute current physical offset; no prefix replay.
        state,_ = a.c.snapshot()
        point = _finite(state['red_t']['pos'],(3,)) + _finite(state['red_t']['mat'],(3,3)) @ np.asarray(obj.get('grasp_point_local',[0,0,0]),float)
        xy = point[:2]; center_z = max(float(point[2]),float(a.floor_clear_tcp('right')))
        a.stage = 'approach-red_t-local-suffix'
        empty_height=prepared_empty_height(a,'right','red_t',goal,clearance)
        a.move_generated({'right':[*a.tip('right')[:2],empty_height]})
        a.move_generated({'right':[*xy,empty_height]})
        a.move_generated({'right':[*xy,center_z+.045]})
        a.prepare_generated_gripper('right')
        tolerance = min(.0035,max(.0008,min(obj['size'])*.2))
        a.move_generated({'right':[*xy,center_z]},tolerance=tolerance)
        for _ in range(3):a.act('STILL','GRASP')
        state,contacts = a.c.snapshot()
        if not state['red_t']['grasp'][1] or not all(frozenset(('red_t','right_finger'+str(i)))in contacts for i in (1,2)):
            raise RuntimeError('Local red T was not physically bilaterally grasped')
        a.carried_payload = ('red_t','right'); a.stage = 'grasped-red_t-local-suffix'
        a.act('STILL','STILL',20.)
        a.move_generated({'right':[*a.tip('right')[:2],clearance]})
        a.rotate_held('red_t','right',goal)
        state,_ = a.c.snapshot()
        if not state['red_t']['grasp'][1]:raise RuntimeError('Local red T lost actual grip during transfer')
        offset = a.tip('right') - state['red_t']['pos']
        half_height = float((np.abs(state['red_t']['mat'])@np.asarray(obj['size']))[2])
        tcp_xy = np.asarray(target['xy'],float) + offset[:2]
        a.move_generated({'right':[*tcp_xy,clearance]})
        release_z = float(target.get('surface_z',.8)) + half_height + float(offset[2]) + .004
        a.move_generated({'right':[*tcp_xy,release_z]})
        a.carried_payload = None; a.release_generated('right')
        a.stage = 'released-red_t-local-suffix'
        a.move_generated({'right':[*a.tip('right')[:2],clearance]})
        for _ in range(4):a.act()
        state,contacts = a.c.snapshot()
        if any(state['red_t']['grasp']) or frozenset(('red_t','table')) not in contacts:
            raise RuntimeError('Local red T release lacks real table support')
        red=state['red_t'];yaw=math.atan2(red['mat'][1,0],red['mat'][0,0])
        angle=math.atan2(math.sin(yaw-goal['yaw']),math.cos(yaw-goal['yaw']))
        if np.linalg.norm(np.asarray(red['pos'])[:2]-target['xy'])>POSITION_TOLERANCE_M or abs(angle)>math.radians(ANGLE_TOLERANCE_DEG):
            raise RuntimeError('Local red T did not reach its original position/orientation tolerance')
        _blue_preserved(a,blue_goal,preserved_blue,require_goal=blue_completed)
        operations.append(dict(operation='original_public_red_acquire_rotate_place_release',actor='red_t'))
    finally:
        if had_local_act:a.act = previous_local_act
        else:del a.act
    return dict(local_completed=True,operations=operations,active_actions=a.c.steps-before)
