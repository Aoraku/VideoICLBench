"""Front25 local segments use the shared engineering checkpoint gate."""
import importlib

MODULES={
    'E15':'execution_design_segments_e15',
    'E18':'execution_design_segments_e18',
    'E17':'execution_design_segments_e17_e20','E20':'execution_design_segments_e17_e20',
    'E19':'execution_design_segments_e19_e25','E25':'execution_design_segments_e19_e25',
    'E23':'execution_design_segments_e23_e24','E24':'execution_design_segments_e23_e24',
}


E20_ENTRIES={'e20_grasp_blue','e20_grasp_and_lift_blue','e20_b_grasp_and_lift_blue1','e20_liftoff_red','e20_c_place_next_blue_from423'}
E20_ENTRIES.add('e20_b_reseat_lift_blue_from2')
E20_ENTRIES.add('e20_a_grasp_lift_blue_from268')
E20_ENTRIES.add('e20_c_finish_blue_transfer_from321')
E20_ENTRIES.add('e20_c_reacquire_supported_blue_from1')
E20_ENTRIES.add('e20_a_lift_red_from543')
E20_ENTRIES.add('e20_a_finish_after_red_lift7')
E20_ENTRIES.add('e20_b_pickup_blue_left_from424')
E20_ENTRIES.add('e20_b_lift_and_finish_from_left98')
E20_ENTRIES.add('e20_c_direct_remaining_from423')

E17_EXTRA_MODULES={
    'e17_a_edge_grip_floor_after1':'execution_design_segments_e17_a_remaining',
    'e17_c_edge_grip_remaining90':'execution_design_e17_two_blue_remaining',
    'e17_c_low_ingress_from_held100':'execution_design_e17_two_blue_remaining',
    'e17_c_low_ingress_from_held2':'execution_design_e17_two_blue_remaining',
    'e17_b_handover_recycle_from_held187':'execution_design_e17_recycle_delivery',
}

def solve(author,checkpoint,request):
    task=author.scene.spec['id'];entry=request['entry']
    if task not in MODULES or not entry.startswith(task.lower()+'_'):
        raise ValueError('Explicit registered front25 local segment required')
    if task=='E20' and entry not in E20_ENTRIES:
        raise ValueError('Explicit registered E20 local segment required')
    if task=='E17' and entry in E17_EXTRA_MODULES and (checkpoint.get('diagnostic_only')is not True or not author.control_report.get('engineering_reference_only')or not getattr(author.c,'_engineering_diagnostic_only',False)or not getattr(author.c,'_engineering_checkpoint_readback_passed',False)):
        raise ValueError('Short segment requires admitted native checkpoint restoration/readback')
    if entry in('e17_a_floor_regrasp_green_99','e17_a_floor_regrasp_after_close7','e17_a_continue_actual_push22','e17_a_box_axis_grasp_floor33') and (checkpoint.get('diagnostic_only')is not True or not author.control_report.get('engineering_reference_only')or not getattr(author.c,'_engineering_diagnostic_only',False)or not getattr(author.c,'_engineering_checkpoint_readback_passed',False)):
        raise ValueError('Short segment requires admitted native checkpoint restoration/readback')
    if entry in('e17_b_recycle_low_from_held999','e17_b_recycle_deliver_after_release16','e17_c_release_in_region_blue_117','e17_c_resume_after_two_blues_1','e17_c_resume_before_sweep11') and (checkpoint.get('diagnostic_only')is not True or not author.control_report.get('engineering_reference_only')or not getattr(author.c,'_engineering_diagnostic_only',False)or not getattr(author.c,'_engineering_checkpoint_readback_passed',False)):
        raise ValueError('Short segment requires admitted native checkpoint restoration/readback')
    if entry in ('e17_a_finish_from_actual_held40','e17_b_release_actual_upper_green_492','e17_c_place_actual_held_blue_336','e17_a_regrasp_after_lost_green_1','e17_c_resume_remaining_above_rail_121','e20_grasp_and_lift_blue','e20_b_grasp_and_lift_blue1','e20_c_place_next_blue_from423','e17_b_resume_held_upper_triangle_848','e17_b_place_held_upper_from_hover_722','e17_a_release_box_nudge_regrasp_223','e17_c_confirm_released_upper_blue_222','e17_a_grasp_green_floor_edge_57','e17_a_grasp_green_base_18','e17_c_resume_remaining_after_blue_release_1','e17_c_resume_remaining_after_relevel_93','e17_a_resume_held_green_and_remaining_37','e17_b_resume_remaining_after_upper_213'):
        if (checkpoint.get('diagnostic_only')is not True
                or not author.control_report.get('engineering_reference_only')
                or not getattr(author.c,'_engineering_diagnostic_only',False)
                or not getattr(author.c,'_engineering_checkpoint_readback_passed',False)):
            raise ValueError('Short segment requires admitted native checkpoint restoration/readback')
    module_name=MODULES[task]
    if task=='E17' and entry in E17_EXTRA_MODULES:
        module_name=E17_EXTRA_MODULES[entry]
    elif task=='E20' and entry=='e20_c_place_next_blue_from423':
        module_name='execution_design_e20_slots'
    elif task=='E18' and entry in ('e18_grasp_lift_ball_from616','e18_grasp_lift_ball_from_open483'):
        module_name='execution_design_e18_ball'
    elif task=='E18' and entry=='e18_contact_offsets_from102':
        module_name='execution_design_e18_contact_read'
    elif task=='E18' and entry=='e18_closed_cap_from3':
        module_name='execution_design_e18_closed_cap'
    elif task=='E18' and entry in ('e18_roll_selected_ball_from160','e18_roll_selected_ball_from_closed3','e18_roll_selected_ball_from_tilted40'):
        module_name='execution_design_e18_ball_roll'
    elif task=='E20' and entry=='e20_b_reseat_lift_blue_from2':
        module_name='execution_design_e20_b_reseat'
    elif task=='E20' and entry=='e20_b_pickup_blue_left_from424':
        module_name='execution_design_e20_b_direct_left'
    elif task=='E20' and entry=='e20_b_lift_and_finish_from_left98':
        module_name='execution_design_e20_b_held98'
    elif task=='E20' and entry=='e20_c_direct_remaining_from423':
        module_name='execution_design_e20_c_direct_remaining'
    elif task=='E20' and entry=='e20_a_grasp_lift_blue_from268':
        module_name='execution_design_e20_a_grip'
    elif task=='E20' and entry in('e20_a_lift_red_from543','e20_a_finish_after_red_lift7'):
        module_name='execution_design_e20_a_red'
    elif task=='E20' and entry in('e20_c_finish_blue_transfer_from321','e20_c_reacquire_supported_blue_from1'):
        module_name='execution_design_e20_c_transfer'
    elif task=='E25' and entry=='e25_c_empty_return_from591':
        module_name='execution_design_e25_c_return'
    elif task=='E25' and entry=='e25_a_release_spoon_from600':
        module_name='execution_design_e25_a_spoon_release'
    elif task=='E25' and entry in('e25_b_empty_return_from792','e25_b_empty_return_from636'):
        module_name='execution_design_e25_b_return'
    elif task=='E25' and entry in('e25_a_finish_remaining_from586','e25_a_finish_after_knife_relay186','e25_b_finish_remaining_from636','e25_b_finish_after_return'):
        module_name='execution_design_e25_remaining'
    elif task=='E17' and entry in ('e17_a_resume_after_lower_first','e17_b_resume_after_lower_first'):
        module_name='execution_design_segments_e17'
    elif task=='E17' and entry=='e17_a_release_box_nudge_regrasp_223':
        module_name='execution_design_segments_e17_regrasp'
    elif task=='E17' and entry in('e17_a_grasp_green_floor_edge_57','e17_a_grasp_green_base_18'):
        module_name='execution_design_segments_e17_regrasp_edge'
    elif task=='E17' and entry in('e17_a_floor_regrasp_green_99','e17_a_floor_regrasp_after_close7','e17_a_continue_actual_push22','e17_a_box_axis_grasp_floor33'):
        module_name='execution_design_e17_a_floor_regrasp'
    elif task=='E17' and entry=='e17_b_recycle_deliver_after_release16':
        module_name='execution_design_e17_complete_layers'
    elif task=='E17' and entry=='e17_b_recycle_low_from_held999':
        module_name='execution_design_e17_recycle_delivery'
    elif task=='E17' and entry=='e17_c_release_in_region_blue_117':
        module_name='execution_design_e17_release_current'
    elif task=='E17' and entry in('e17_c_resume_after_two_blues_1','e17_c_resume_before_sweep11'):
        module_name='execution_design_e17_two_blue_remaining'
    elif task=='E17' and entry in('e17_b_release_actual_upper_green_492','e17_c_place_actual_held_blue_336'):
        module_name='execution_design_e17_actual_upper'
    elif task=='E17' and entry=='e17_b_resume_remaining_after_upper_213':
        module_name='execution_design_segments_e17_b_remaining'
    elif task=='E17' and entry in('e17_a_resume_held_green_and_remaining_37','e17_a_regrasp_after_lost_green_1','e17_a_finish_from_actual_held40'):
        module_name='execution_design_segments_e17_a_remaining'
    elif task=='E17' and entry in('e17_b_resume_held_upper_triangle_848','e17_b_place_held_upper_from_hover_722'):
        module_name='execution_design_segments_e17_held_upper'
    elif task=='E17' and entry=='e17_c_place_held_blue_upper_south':
        module_name='execution_design_segments_e17_upper'
    elif task=='E17' and entry=='e17_c_confirm_released_upper_blue_222':
        module_name='execution_design_segments_e17_completion'
    elif task=='E17' and entry in('e17_c_resume_remaining_after_blue_release_1','e17_c_resume_remaining_after_relevel_93','e17_c_resume_remaining_above_rail_121'):
        module_name='execution_design_segments_e17_remaining'
    module=importlib.import_module('.'+module_name,__package__)
    previous=getattr(author,'_execution_design_reference_authorized',False)
    author._execution_design_reference_authorized=True
    try:result=module.run_segment(author,entry,request['parameters'])
    finally:author._execution_design_reference_authorized=previous
    if any(k in result for k in ('success','strict_success','task_score_100')):
        raise ValueError('Local segment must not supply a full-task grade')
    return dict(result,segment_passed=result.get('local_completed')is True,
                full_task_acceptance=False)
