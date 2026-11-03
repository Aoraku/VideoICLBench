"""Actual high-clearance E50 flip; original native clip/delivery goals remain."""
import numpy as np
from .realworld_tool_expert import ToolExecutionError,_axis_rotation


def flip_then_clip(p,name,clip,ref):
    from .engineering_thin_suffix import save_stage
    from .execution_design_e33_grasp import actual_mesh
    from .execution_design_thin_edge import table_bounds_task
    if p.task!='E50'or not p.spec['semantic'].get('engineering_card_approximation'):
        raise ValueError('Explicit practical E50 engineering flip required')
    guard=lambda:p.require_held(ref,'left')
    guard();initial=p.frame(ref)[1].copy()
    p.stage('e50-flip-clear-space')
    # The full Panda hand must rotate around the held card without sweeping
    # through the tabletop. Move closer to its base before reversing the wrist.
    p.move_point('left',ref,[-.22,.08,1.04],guard,tolerance=.004)
    save_stage(p.a,'e50-card-before-high-flip',dict(card=name))
    p.stage('e50-actual-high-card-flip');p.rotate_actor(name,'left',_axis_rotation([1.,0.,0.],np.pi)@initial)
    guard()
    if float(p.frame(ref)[1][2,2])<.9:raise ToolExecutionError('Actual E50 card did not turn face up')
    save_stage(p.a,'e50-card-flipped-high',dict(card=name))
    target=np.asarray(p.s['tool_expert']['card_flip_place_task'],float).copy()
    floor=table_bounds_task(p.a.scene)['top']
    low=min(float(actual_mesh(p.a,'left',n)[:,2].min())for n in ['panda_hand',*p.a.scene.embodiment.fingers])
    target[2]=max(1.,float(p.frame(ref)[0][2])+floor+.015-low)
    p.stage('e50-high-card-ready-for-clip');p.move_point('left',ref,target,guard,tolerance=.004)
    return p.clip_card_after_flip(name,clip,ref)
