"""Ordinary source-C placement/release continuation; never full-history proof."""
import json
import numpy as np


def run(a,parameters):
    from .execution_design_e31_hand_contacts import install
    from .execution_design_e31_planned_place import run as place
    from .execution_design_e31_press import support_and_release
    from .execution_design_e31_open_finish import run as release
    spec=a.scene.spec;name=spec['semantic']['plate'];bowl=spec['semantic']['bowl']
    if not(spec['id']=='E31'and spec['variant']=='C'and spec['seed']==4201
           and getattr(a.c,'_engineering_diagnostic_only',False)):
        raise ValueError('Explicit original source-C checkpoint continuation required')
    reader=install(a,all_robot_links=True);a.carried_payload=(name,'right');a.act()
    placement=None
    # These are ordinary drop heights, not new task predicates. A planner
    # refusal never issues a physical action or relaxes collision checking.
    for height in(.030,.060):
        try:
            placement=place(a,dict(resume_over_bowl=True,place_only=True,
                placement_offset_xy=[-.018,0.],ordinary_drop_gap_m=height,allow_approximate_demo=True,
                normal_spin_degrees=parameters.get('normal_spin_degrees',0.)))
            break
        except RuntimeError as error:
            if 'path unavailable'not in str(error):raise
    if placement is None:raise RuntimeError('Ordinary source-C release height has no verified whole-world route')
    top=support_and_release(a,dict(stop_after_top_contact=True))
    opened=release(a,dict(allow_gravity_drop=True))
    a.note('final');native=a.c.evaluator.result();state,contacts=a.c.snapshot()
    values={key:value for key,value in reader['current_forces_n'].items()if key.startswith(name+'/')}
    clear=bool(values and all(value is not None and value<=.001 for value in values.values())and not any(state[name]['grasp']))
    ready=bool(clear and frozenset((name,bowl))in contacts
        and float(state[name]['mat'][2,2])<0 and float(state[name]['pos'][2])>float(state[bowl]['pos'][2]))
    report=dict(segment_passed=ready,approximate_demo_ready=ready,diagnostic_only=True,
        source_initial_episode=False,native_initial_history_not_restored=True,
        original_native_result=native,actual_hand_forces_n=values,actual_plate=state[name],
        ordinary_placement=placement,actual_top_support=top,actual_release=opened,
        original_source_root=parameters.get('original_source_root'),native_score_not_modified=True)
    (a.out/'e31-source-C-continuation-result.private.json').write_text(json.dumps(report,indent=2,
        default=lambda value:value.tolist()if hasattr(value,'tolist')else str(value))+'\n')
    if not ready:raise RuntimeError('Source-C continuation has not actually released a down dish on the bowl')
    return report


def run_clear(a,parameters):
    """Continue only the actually open hand from a bowl-supported source-C CP."""
    from .execution_design_e31_hand_contacts import install
    spec=a.scene.spec;name=spec['semantic']['plate'];bowl=spec['semantic']['bowl']
    if not(spec['id']=='E31'and spec['variant']=='C'and spec['seed']==4201
           and getattr(a.c,'_engineering_diagnostic_only',False)):
        raise ValueError('Explicit original source-C separation continuation required')
    reader=install(a,all_robot_links=True);a.carried_payload=None;trace=[];left_hold=[None];bias=[0.];last_tick=[None]
    def left_pad_force():
        return max(float(a.c.contact_forces.get(frozenset((name,'left_finger'+str(i))),0.))for i in(1,2))
    def forces(side):
        return {k:v for k,v in reader['current_forces_n'].items()if k.startswith(name+'/'+side+'/')}
    def clear(side):
        values=forces(side)
        return bool(values and all(v is not None and v<=.001 for v in values.values()))
    def guard():
        if left_hold[0]is not None and last_tick[0]!=a.c.physics_ticks:
            import torch
            from isaaclab.utils.math import quat_apply_inverse
            from .execution_design_e31_open_finish import support_force_z_bias
            bias[0]=support_force_z_bias(left_pad_force(),bias[0],a.c.dt);last_tick[0]=a.c.physics_ticks
            delta=np.asarray(a.scene.layout.task_rotation)@np.array([0.,0.,bias[0]])
            position,rotation=left_hold[0]
            local=quat_apply_inverse(a.scene.robots['left'].data.root_quat_w,
                torch.as_tensor(delta,device=a.c.device,dtype=position.dtype)[None])
            a.c.targets['left']=(position+local,rotation)
        def refuse(message):
            (a.out/'e31-final-separation-forces.private.json').write_text(json.dumps(
                dict(steps=a.c.steps,forces_n=dict(reader['current_forces_n'])),indent=2)+'\n')
            raise RuntimeError(message)
        for side in('left','right'):
            values={k:v for k,v in reader['current_forces_n'].items()if k.startswith('robot_table/'+side+'/')}
            if not values or any(v is None for v in values.values())or max(values.values())>1.:
                refuse('Actual all-link/table guard refused empty separation')
        if any(v is None or v>1. for k,v in reader['current_forces_n'].items()if k.startswith('bowl/')):
            refuse('Actual hand/bowl guard refused empty separation')
    radial=parameters.get('separation')=='radial'
    a.stage='e31-source-C-final-palm-outward'if radial else'e31-source-C-final-finger-down'
    a.act();guard()
    if parameters.get('anchor_left')is True:
        a.stage='e31-source-C-restore-real-left-top-pressure'
        for _ in range(12):
            if left_pad_force()>.05:break
            a.act(left='DOWN',mm=4.);guard()
        if left_pad_force()<=.05:raise RuntimeError('Actual left top pressure was not established')
        from .engineering_checkpoint import capture
        (a.out/'e31-final-left-pressure.checkpoint.private.json').write_text(json.dumps(
            capture(a.c,a.stage),indent=2)+'\n')
        left_hold[0]=tuple(value.clone()for value in a.c.targets['left'])
        a.stage='e31-source-C-anchored-final-palm-outward'
    if radial:
        from .engineering_native_tick import diagnostic_tick_scope
        start=np.asarray(a.tip('right'),float).copy()
        delta=start[:2]-np.asarray(a.c.snapshot()[0][name]['pos'])[:2]
        if np.linalg.norm(delta)<.01:raise RuntimeError('Actual radial empty-hand direction is ambiguous')
        direction=np.r_[delta/np.linalg.norm(delta),0.]
        for distance in(.020,.040,.060):
            if clear('right'):break
            if any(a.c.snapshot()[0][name]['grasp']):raise RuntimeError('Empty radial withdrawal retained native grasp')
            with diagnostic_tick_scope(a):
                receipt=a.c.author_move({'right':(start+distance*direction).tolist()},
                    max_speed=.025,max_acceleration=.08,guard=guard)
            trace.append(dict(step=a.c.steps,tip=a.tip('right'),right_forces_n=forces('right'),
                plate=a.c.snapshot()[0][name],receipt=receipt))
            (a.out/'e31-empty-withdrawal-progress.private.json').write_text(json.dumps(trace,indent=2,
                default=lambda value:value.tolist()if hasattr(value,'tolist')else str(value))+'\n')
    else:
        for _ in range(16):
            state,contacts=a.c.snapshot()
            if not any(state[name]['grasp'])and clear('right'):break
            if any(state[name]['grasp']):raise RuntimeError('Empty separation unexpectedly retained native grasp')
            a.act(right='DOWN',mm=4.);guard()
            trace.append(dict(step=a.c.steps,tip=a.tip('right'),right_forces_n=forces('right'),plate=a.c.snapshot()[0][name]))
    if not clear('right'):raise RuntimeError('Ordinary downward separation still has actual right contact')
    left_hold[0]=None
    a.stage='e31-source-C-left-empty-up'
    for _ in range(12):
        if clear('left'):break
        a.act(left='UP',mm=4.);guard()
    if not clear('left'):raise RuntimeError('Empty left hand has not actually separated')
    for _ in range(2):a.act();guard()
    a.note('final');state,contacts=a.c.snapshot();native=a.c.evaluator.result()
    ready=bool(clear('left')and clear('right')and not any(state[name]['grasp'])
        and frozenset((name,bowl))in contacts and float(state[name]['mat'][2,2])<0)
    report=dict(segment_passed=ready,approximate_demo_ready=ready,diagnostic_only=True,
        source_initial_episode=False,native_initial_history_not_restored=True,
        original_native_result=native,actual_right_forces_n=forces('right'),actual_left_forces_n=forces('left'),
        actual_plate=state[name],trace=trace,original_source_root=parameters.get('original_source_root'),
        native_score_not_modified=True)
    (a.out/'e31-source-C-continuation-result.private.json').write_text(json.dumps(report,indent=2,
        default=lambda value:value.tolist()if hasattr(value,'tolist')else str(value))+'\n')
    if not ready:raise RuntimeError('Actual source-C dish is not free and supported down on bowl')
    return report
