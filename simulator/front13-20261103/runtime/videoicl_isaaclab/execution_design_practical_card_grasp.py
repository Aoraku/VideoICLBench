"""Public-action pickup for explicitly labelled 1mm engineering cards."""
import math
import numpy as np
from .realworld_tool_expert import ToolExecutionError,_axis_rotation


def acquire(p,ref,side):
    from .author_clearance import prepare_single_hand
    from .execution_design_cutlery_grasp import orient
    from .execution_design_e33_grasp import actual_mesh
    from .execution_design_card_direct import plan_open_target,prove_bilateral_lift
    from .execution_design_thin_edge import material_collision_points_task,table_bounds_task
    from .execution_design_thin_motion import checked_move
    from .engineering_thin_suffix import save_stage
    obj=next(o for o in p.spec['objects']if o['id']==ref['actor'])
    if not np.isclose(obj['size'][2],.0005):raise ValueError('Explicit 1mm practical card required')
    p.stage('practical-card-open-approach');prepare_single_hand(p.a,side,.98);p.act(side,'RELEASE')
    position,rotation=p.frame(ref);short=rotation[:,1].copy();short[2]=0.;short/=np.linalg.norm(short)
    down=np.array([0.,0.,-1.]);current=p.a.tcp_rotation_task(side)
    if short@current[:,1]<0:short=-short
    orient(p.a,side,np.column_stack((np.cross(short,down),short,down)))
    tcp=p.tip(side);fingers=[actual_mesh(p.a,side,n)for n in p.a.scene.embodiment.fingers]
    obstacles={n:material_collision_points_task(p,dict(actor=n))for n in p.a.scene.objects if n!=ref['actor']}
    floor=table_bounds_task(p.a.scene)['top']
    plan=plan_open_target(position,rotation,tcp,fingers,actual_mesh(p.a,side,'panda_hand'),floor,obstacles)
    target=plan['position'];height=plan['approach_height']
    checked_move(p,side,[*p.tip(side)[:2],height],tolerance=.004)
    checked_move(p,side,[*target[:2],height],tolerance=.004)
    checked_move(p,side,target,tolerance=.0006)
    # Enter the actual 1mm edge band. Do not require a special micrometre toe
    # setpoint: true bilateral contact and 25mm payload lift decide success.
    for _ in range(4):
        lowest=float(p.a.finger_geometry(side)['lowest_z_task_m'])
        top=float(material_collision_points_task(p,ref)[:,2].max())
        if lowest<top-.0001:break
        p.act(side,'DOWN',mm=.5)
    else:raise ToolExecutionError('Practical card edge remains above physical fingers')
    p.stage('practical-card-close');p.act(side,'GRASP')
    for _ in range(100):
        if p.held(ref,side):break
        q=p.a.scene.robots[side].data.joint_pos[:,p.c.ids[side][1]].cpu().numpy()
        if np.max(q)<.001:raise ToolExecutionError('Practical card close missed actual sides')
        p.act()
    else:raise ToolExecutionError('Practical card physical close exceeded bounded travel')
    save_stage(p.a,'practical-card-bilateral',dict(side=side))
    p.stage('practical-card-actual-lift');raised=prove_bilateral_lift(p,ref,side,initial_lift_step_mm=.5)
    save_stage(p.a,'practical-card-lift',dict(side=side,raised_m=raised))
    return raised
