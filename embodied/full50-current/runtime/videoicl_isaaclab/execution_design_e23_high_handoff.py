"""One real high-air handoff from the measured right-held256 boundary."""
import math
import json
import numpy as np
from .realworld_tool_expert import ToolExecutionError,_axis_rotation


def run_segment(a,segment,parameters):
    from .execution_design_segments_e23_e24 import (_scope,_air_move,_air_rotate_empty,
        _air_check,_air_release_after_receiver_grip)
    from .realworld_structural_expert import StructuralAuthor
    _scope(a,'E23');spec=a.scene.spec;cp=getattr(a,'_engineering_resume_checkpoint',{})
    grasp_current=segment=='e23_grasp_current_lowwall_from12'
    continuing=segment=='e23_finish_high_handoff_from132'
    admitted=(12,1202)if grasp_current else(132,13202)if continuing else(256,25602)
    if(segment not in('e23_high_handoff_from256','e23_finish_high_handoff_from132','e23_grasp_current_lowwall_from12')or parameters!={}or spec.get('variant')!='A'
            or spec.get('seed')!=4201 or spec['execution_design'].get('condition')!='I'
            or(cp.get('source',{}).get('steps'),cp.get('source',{}).get('physics_ticks'))!=admitted
            or cp.get('diagnostic_only')is not True or not getattr(a.c,'_engineering_checkpoint_readback_passed',False)):
        raise ValueError('Admitted actual E23A right-held handoff checkpoint required')
    policy=StructuralAuthor(a);policy._engineering_air_joint_reserve=.02
    policy._engineering_coarse_free_space=True
    policy._engineering_conservative_tree_components=True
    name=policy.identity['red'];ref=dict(actor=name);right=((ref,'right'),)
    policy.require_held(ref,'right');state,_=policy.snapshot()
    if any(body['grasp'][0]for body in state.values()):raise ToolExecutionError('Actual E23 high receiver must be empty')
    if policy.objects[name].get('source_asset',{}).get('sha256')!='c9d82475379f3bc83666d97222a3c55a39f3334f97eb9ed02df4efab84183b5b':
        raise ValueError('Original E23 hollow cup mesh required')
    if grasp_current:
        # The source12 palms already cleared the real cup. Try its actual
        # low-wall pad coverage rather than pushing4mm toward the handle.
        policy.stage('local-E23-native12-real-current-pads-grasp')
        _air_check(policy,'left',target=name,allow_target_finger_contact=True)
    elif continuing:
        # The real132 receiver is already beneath the raised cup. Finish XY
        # first; lifting while7mm outside the final axis met the cup handle.
        goal=policy.point(dict(actor=name,local=[0,0,-.0405]))
        policy.stage('local-E23-native132-actual-low-wall-grasp')
        current=policy.tip('left').copy()
        for waypoint in([goal[0],current[1],current[2]],
                         [goal[0],goal[1],current[2]],goal):
            _air_move(policy,'left',waypoint,held_guards=right,target=name,
                      tolerance=.002,maximum_step=.002)
    else:
        policy.stage('local-E23-real-held-cup-up100-clear-tree')
        _air_move(policy,'right',policy.tip('right')+[0,0,.100],held_guards=right,payload=name,tolerance=.005,maximum_step=.005)
        cup=np.asarray(policy.snapshot()[0][name]['mat']);base=np.array([[0.,-1,0],[-1,0,0],[0,0,-1.]])
        rotation=cup@_axis_rotation([0,0,1],-math.pi/2)@_axis_rotation([1,0,0],-math.pi/2)@base
        policy.stage('local-E23-receiver-high-azimuth')
        _air_rotate_empty(policy,'left',rotation,held_guards=right,target=name,tolerance_degrees=6.,maximum_degrees=10.)
        goal=policy.point(dict(actor=name,local=[0,0,-.0305]));staging=goal-cup[:,2]*.040
        policy.stage('local-E23-empty-receiver-up-before-XY')
        _air_move(policy,'left',[*policy.tip('left')[:2],staging[2]],held_guards=right,target=name,tolerance=.005,maximum_step=.005)
        _air_move(policy,'left',[staging[0],policy.tip('left')[1],staging[2]],held_guards=right,target=name,tolerance=.005,maximum_step=.005)
        _air_move(policy,'left',staging,held_guards=right,target=name,tolerance=.003,maximum_step=.005)
        policy.stage('local-E23-high-real-cup-low-grasp')
        _air_move(policy,'left',goal,held_guards=right,target=name)
    for _ in range(3):
        policy.act('left','GRASP');policy.require_held(ref,'right')
        if policy.snapshot()[0][name]['grasp'][0]:break
    policy.require_held(ref,'left')
    _air_check(policy,'left',target=name,allow_target_finger_contact=True)
    result=_air_release_after_receiver_grip(policy,single_real_observation=True,retreat_up=.04,retreat_y=.06)
    result.update(segment=segment,private_joint_reserve_rad=.02,real_high_handoff=True,
                  extra_long_settle_required=False)
    (a.out/'e23-real-high-handoff.private.json').write_text(json.dumps(result)+'\n')
    _hang_current_red(policy)
    result.update(actions=policy.c.steps-policy.start,operations=policy.operations,
                  red_released_on_original_top_branch=True)
    return result


def _hang_current_red(policy):
    from .execution_design_segments_e23_e24 import _rotate_held_at_station,_air_move
    from .execution_design_e23_reference import branch_entry_geometry
    name=policy.identity['red'];ref=dict(actor=name);cup=policy.s['cups'][name]
    branches=policy.s['branches'];branch=branches[max(branches,key=lambda key:policy.body_point(branches[key]['ref'],branches[key]['tip_local'])[2])]
    g=branch_entry_geometry(policy.body_point(branch['ref'],branch['base_local']),
        policy.body_point(branch['ref'],branch['tip_local']),float(np.linalg.norm(np.asarray(cup['rim_local'])-cup['bottom_local'])))
    current=np.asarray(policy.snapshot()[0][name]['mat']);axis=current@np.asarray(cup['axis_local']);wanted=-g['axis']
    cross=np.cross(axis,wanted);angle=math.acos(float(np.clip(axis@wanted,-1,1)))
    if np.linalg.norm(cross)<1e-7:
        cross=np.cross(axis,[1.,0,0]if abs(axis[0])<.9 else[0,1.,0])
    target=_axis_rotation(cross/np.linalg.norm(cross),angle)@current
    policy._e23_rotation_station=(name,'left',policy.tip('left').copy())
    policy.stage('local-E23-original-top-branch-held-red-orientation')
    _rotate_held_at_station(policy,name,'left',target)
    mouth=dict(actor=name,local=cup['rim_local']);support=branch['ref'].get('actor',branch['ref'].get('contact_body'))
    def free():
        policy.require_held(ref,'left')
        if policy.contact(name,support):raise ToolExecutionError('Premature real cup/tree contact before entry')
    level=max(float(policy.point(mouth)[2]),float(g['exterior'][2])+.025)
    for waypoint in([*policy.point(mouth)[:2],level],[*g['exterior'][:2],level],g['exterior'],g['entry']):
        policy.stage('local-E23-real-top-branch-mouth-approach')
        _air_move(policy,'left',waypoint,material=mouth,held_guards=((ref,'left'),),guards=(free,),
                  payload=name,target=support,tolerance=.005,maximum_step=.006)
    policy.stage('local-E23-real-top-branch-insertion')
    _air_move(policy,'left',g['target'],material=mouth,held_guards=((ref,'left'),),
              payload=name,target=support,tolerance=.004,maximum_step=.004)
    policy.release(ref,'left');policy.move('left',policy.tip('left')+g['axis']*.03+[0,0,.04],tolerance=.006)
    if not policy.contact(name,support):raise ToolExecutionError('Real released red cup lacks original top-branch support')
