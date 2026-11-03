"""One coarse public yaw escape after measured left q7-limited transport."""
from .realworld_tool_expert import ToolExecutionError


def run(author,context):
    from .execution_design_e08_branch import _policy
    from .execution_design_e08_shape_guard import SourceShoeGeometry
    from .execution_design_branch_geometry import install_public_guard
    from .execution_design_branch_rotation import finish_accepted_public_rotation
    if context.get('actor')not in('left_shoe','right_shoe')or context.get('side')not in('left','right')or context.get('midfoot_grasp_strategy')!='sourceinitial_upper_com_pair_v1':raise ValueError('Measured source COM acquisition context required')
    p=_policy(author,context)
    if context.get('branch_params',{}).get('resume_com_lift_from_measured')is True:
        from .execution_design_e08_midfoot import SoleAcquisitionGeometry
        from .execution_design_thin_edge import material_collision_points_task
        from .execution_design_branch_geometry import collision_parts_task
        actor=context['actor'];side=context['side'];p.require_held(dict(actor=actor),side)
        guard=SoleAcquisitionGeometry(p,actor,side,mode='held',allow_table_departure=True);install_public_guard(p,guard)
        while True:
            guard();low=float(material_collision_points_task(p,dict(actor=actor))[:,2].min());rim=max(float(a[:,2].max())for a in collision_parts_task(p,'box'))
            if low>rim+.050:break
            p.act(side,'UP',mm=12.)
        from .execution_design_e08_source_pair import solve
        return solve(author,resume_context=context)
    if context.get('branch_params',{}).get('resume_com_transport_measured')is True:
        p.require_held(dict(actor=context['actor']),context['side']);context.update(coarse_continue_transport=True,coarse_keep_escape_yaw=True)
        from .execution_design_e08_source_pair import solve
        return solve(author,resume_context=context)
    if context.get('actor')!='left_shoe'or context.get('side')!='left':raise ValueError('Measured left-specific escape context required')
    if context.get('branch_params',{}).get('resume_after_left_release')is True:
        from .execution_design_e08_source_pair import functional_shoe_readback,solve
        from .execution_design_e08_midfoot import SoleAcquisitionGeometry
        history=context.get('source_actor_rotation_history',{})
        if not history.get('left_shoe',{}).get('functional',{}).get('functional_pass'):raise ToolExecutionError('Measured left release history required')
        guard=SoleAcquisitionGeometry(p,'left_shoe','left');install_public_guard(p,guard)
        # Native forces are empty immediately after restore; one actual public
        # action rebuilds contact before checking the already released shoe.
        p.act('left','STILL')
        if not functional_shoe_readback(p,'left_shoe')['functional_pass']:raise ToolExecutionError('Measured released left shoe must remain functionally in box')
        context['coarse_released_empty_turn_commands']=int(context.get('coarse_released_empty_turn_commands',0))+1
        p.act('left','ROTATE_CW',degrees=20.);finish_accepted_public_rotation(p,'left',guard)
        import numpy as np
        guard.move(np.array([p.tip('left')[0],.48,p.tip('left')[2]]))
        context['coarse_skip_completed_left']=True
        return solve(author,resume_context=context)
    p.require_held(dict(actor='left_shoe'),'left');guard=SourceShoeGeometry(p,'left_shoe','left');install_public_guard(p,guard)
    if context.get('branch_params',{}).get('lower_from_measured375')is True:
        from .execution_design_thin_edge import material_collision_points_task
        from .execution_design_branch_geometry import collision_parts_task
        while True:
            low=float(material_collision_points_task(p,dict(actor='left_shoe'))[:,2].min());rim=max(float(a[:,2].max())for a in collision_parts_task(p,'box'))
            if low<=rim+.040:break
            p.act('left','DOWN',mm=min(12.,max(2.,(low-rim-.035)*1000)))
        context.update(coarse_keep_escape_yaw=True,coarse_continue_transport=True,source_functional_chain=True,coarse_transport_height='measured payload lowest = actualrim+40mm; remove unnecessary1.12m materialheight that reached Panda extension')
        from .execution_design_e08_source_pair import solve
        return solve(author,resume_context=context)
    used=int(context.get('rotation_commands_used',0))
    if used>=120:raise ToolExecutionError('Original120 shoe rotation bound exhausted')
    context['rotation_commands_used']=used+1;p.act('left','ROTATE_CW',degrees=10.);finish_accepted_public_rotation(p,'left',guard)
    context.update(coarse_keep_escape_yaw=True,coarse_escape='Actual left joint7lowerlimit: publicCW10 frees wrist; X transport before Y, natural Boxwalls may guide final toe pose',source_functional_chain=True)
    from .execution_design_e08_source_pair import solve
    return solve(author,resume_context=context)
