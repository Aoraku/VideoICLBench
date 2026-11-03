"""E31 engineering suffix after validated fresh-world native reconstruction."""
import json
from .execution_design_e31_release import lower_for_release


def run(author,parameters):
    if author.scene.spec['id']!='E31'or not getattr(author.c,'_engineering_diagnostic_only',False):
        raise ValueError('E31 debug phase requires the validated diagnostic restore')
    semantic=author.scene.spec['semantic'];plate=semantic['plate'];side=parameters.get('side','right')
    goal=parameters.get('goal')or next(g for g in author.scene.spec['goals']if g['object']==plate)
    original=getattr(author,'_execution_design_reference_authorized',False)
    author._execution_design_reference_authorized=True;author.carried_payload=(plate,side)
    author.stage='checkpoint-e31-material-release';start=author.c.steps
    try:
        stop=lower_for_release(author,plate,side,goal)
        author.carried_payload=None;author.release_generated(side)
        author.stage='checkpoint-e31-physx-settle'
        for _ in range(2):author.act()
        result=author.c.evaluator.result();state,contacts=author.c.snapshot()
        required={'released','stable','container_relation','bowl_up','plate_face_orientation','containment_or_rim_coverage','real_bowl_plate_contact'}
        conditions={c['type']:bool(c['passed'])for c in result.get('conditions',[])}
        contact=frozenset((plate,semantic['bowl']))in contacts
        no_grasp=not any(state[plate]['grasp'])
        segment_passed=bool(required<=set(conditions)and all(conditions.values())and contact and no_grasp)
        report=dict(diagnostic_only=True,source_initial_state_full_positive=False,
            segment_passed=segment_passed,actual_plate_bowl_contact=contact,
            local_actions=author.c.steps-start,author_release_stop=stop,
            actual_native_result=result,actual_plate_grasps=author.c.snapshot()[0][plate]['grasp'])
        (author.out/'e31-local-release-result.private.json').write_text(json.dumps(report,default=lambda x:x.tolist(),indent=2)+'\n')
        if not segment_passed:
            raise RuntimeError('E31 local real release did not satisfy native physics: '+json.dumps(result.get('failed_checks',result.get('conditions',[]))))
        return report
    finally:author._execution_design_reference_authorized=original


def solve(author,checkpoint,context):
    return run(author,context.get('parameters',context.get('context',{})))


def run_flip(author,parameters):
    """Mechanical C suffix on a measured B fixture; never relabel its identity."""
    if (author.scene.spec['id']!='E31' or author.scene.spec['variant']!='B'
            or not getattr(author.c,'_engineering_diagnostic_only',False)):
        raise ValueError('E31 flip diagnostic requires the original B checkpoint identity')
    from .execution_design_e31_orientation import align_face
    from .realworld_semantic_checks import check_task
    semantic=author.scene.spec['semantic'];plate=semantic['plate'];side=parameters.get('side','right')
    goal=dict(next(g for g in author.scene.spec['goals']if g['object']==plate),pitch=3.141592653589793,roll=0.)
    original=getattr(author,'_execution_design_reference_authorized',False)
    author._execution_design_reference_authorized=True;author.carried_payload=(plate,side)
    start=author.c.steps;contact_reader=None
    try:
        author.stage='checkpoint-e31-mechanical-inversion'
        if parameters.get('palm_readback') is True:
            from .execution_design_e31_hand_contacts import install
            contact_reader=install(author,all_robot_links=parameters.get('all_robot_contacts') is True)
            if parameters.get('palm_probe_hold') is True:
                author.act();contact_reader['flush']()
        if parameters.get('resume_narrow_release') is True:
            pass
        elif parameters.get('release_only') is True:
            pass
        elif parameters.get('material_yaw') is True:
            from .execution_design_e31_flip import yaw_for_material_release
            yaw_for_material_release(author,plate,side)
        elif parameters.get('resume_actual_finish') is True:
            from .execution_design_e31_flip import finish_from_actual_plate
            finish_from_actual_plate(author,plate,side,only_return=parameters.get('return_only') is True)
        elif parameters.get('safe_site') is True:
            from .execution_design_e31_flip import invert_at_clear_site
            invert_at_clear_site(author,plate,side)
        else:align_face(author,plate,side,goal)
        author.stage='checkpoint-e31-inverted-material-release'
        if parameters.get('anchored_open_finish')is True:
            from .execution_design_e31_open_finish import run as finish_open
            stop=finish_open(author,parameters)
        elif parameters.get('settle_only')is True:
            author.carried_payload=None;stop=dict(already_physically_released=True)
        elif parameters.get('left_handover') is True:
            handover_parameters=parameters.get('handover_parameters',{'pinch_mode':'tangent'})
            # A saved close-approach state already places the other hand next
            # to the actual plate. Preserve that measured relative geometry.
            if handover_parameters.get('resume_stage')or handover_parameters.get('pinch_mode')=='axial':
                stop=dict(restored_handover_stage=handover_parameters.get('resume_stage','axial_empty_staging'))
            else:stop=lower_for_release(author,plate,side,goal)
            from .execution_design_e31_left_handoff import handover
            original_act=author.act;grip_probe=[False]
            def observed_act(*args,**kwargs):
                if (parameters.get('left_grip_readback') is True and not grip_probe[0]
                        and author.stage=='e31-left-handoff-real-left-grasp'):
                    from .execution_design_grip_readback import install as install_grip
                    install_grip(author,plate,'left',max_samples=2500,stem='e31-left-native-grip')
                    grip_probe[0]=True
                return original_act(*args,**kwargs)
            author.act=observed_act
            try:handover(author,handover_parameters)
            finally:author.act=original_act
            side='left';author.stage='checkpoint-e31-left-held-lower'
            if handover_parameters.get('pinch_mode')=='axial':
                align_face(author,plate,side,goal)
            stop=lower_for_release(author,plate,side,goal,maximum_drop_gap_m=.030,
                require_bowl_contact=parameters.get('require_bowl_contact')is True)
            author.carried_payload=None;author.release_generated(side)
            author.stage='checkpoint-e31-left-empty-clear'
            for _ in range(3):author.act('UP','STILL',8.)
        elif parameters.get('supported_short_separation')is True:
            from .execution_design_e31_supported_separate import run as separate
            stop=separate(author,parameters)
        elif parameters.get('supported_narrow_release')is True:
            if frozenset((plate,semantic['bowl']))not in author.c.snapshot()[1]:
                raise RuntimeError('E31 supported narrow release requires real bowl contact')
            from .execution_design_e31_narrow_release import release_inverted
            stop=release_inverted(author,plate,side,preferred_axis=parameters.get('withdrawal_axis'))
        elif parameters.get('direct_right_planned_placement')is True:
            from .execution_design_e31_planned_place import run as planned_place
            stop=planned_place(author,parameters.get('direct_right_parameters'))
        elif parameters.get('direct_right_normal_spin')is True:
            from .execution_design_e31_right_direct import run as direct_right
            stop=direct_right(author,parameters.get('direct_right_parameters'))
        elif parameters.get('press_support') is True:
            from .execution_design_e31_press import support_and_release
            stop=support_and_release(author,parameters.get('press_parameters'))
            if parameters.get('press_parameters',{}).get('stop_after_top_contact')is True:return stop
        elif parameters.get('resume_narrow_release') is True:
            stop=dict(restored_already_released=True)
            from .execution_design_e31_narrow_release import release_inverted
            release_inverted(author,plate,side,already_released=True)
        elif parameters.get('narrow_release') is True:
            stop=lower_for_release(author,plate,side,goal)
            from .execution_design_e31_narrow_release import release_inverted
            release_inverted(author,plate,side)
        else:
            stop=lower_for_release(author,plate,side,goal)
            author.carried_payload=None;author.release_generated(side)
        author.stage='checkpoint-e31-inverted-physx-settle'
        for _ in range(2):author.act()
        native=author.c.evaluator.result();state,contacts=author.c.snapshot()
        alternate=check_task('E31','C',native['observation'])
        contact=frozenset((plate,semantic['bowl']))in contacts
        no_grasp=not any(state[plate]['grasp'])
        down_z=float(state[plate]['mat'][2][2])
        strict=bool(alternate['success']and contact and no_grasp and down_z<-.85)
        approximate=False
        if parameters.get('allow_approximate_demo')is True:
            forces=getattr(author,'_e31_native_contact_reader',{}).get('current_forces_n',{})
            values=[v for k,v in forces.items()if k.startswith(plate+'/')]
            approximate=bool(contact and no_grasp and down_z<0 and values
                and all(v is not None and v<=.001 for v in values)
                and float(state[plate]['pos'][2])>float(state[semantic['bowl']]['pos'][2]))
        passed=strict or approximate
        report=dict(diagnostic_only=True,source_initial_state_full_positive=False,
            segment_passed=passed,source_variant='B',mechanical_target_variant='C',
            strict_C_checks_passed=strict,approximate_demo_ready=approximate,
            source_identity_preserved=True,local_actions=author.c.steps-start,
            author_release_stop=stop,actual_native_B_result=native,
            actual_C_rule_observation_check=alternate,actual_plate_bowl_contact=contact,
            actual_plate_grasps=state[plate]['grasp'],actual_down_normal_z=down_z)
        (author.out/'e31-local-flip-result.private.json').write_text(json.dumps(report,default=lambda x:x.tolist(),indent=2)+'\n')
        if not passed:raise RuntimeError('E31 mechanical inversion suffix failed original C physical conditions: '+json.dumps(alternate))
        return report
    finally:
        if contact_reader is not None:contact_reader['flush']()
        author._execution_design_reference_authorized=original
