"""Native C209: clear actual finger/tray interference, release onto old table goal."""
import math
import numpy as np
from .execution_design_segments_e19_e25 import _scope
from .execution_design_e25_reference import TAIL_GRASPS
from .realworld_tool_expert import _axis_rotation


def release_height_for_knife(a,goal,zone,proposed_z):
    """Future full C route: clear the measured tray before gravity release."""
    _scope(a,'E25','C')
    if goal.get('object')!='knife'or zone.get('id')!='knife_target':
        raise ValueError('Original C final knife table goal required')
    state,contacts=a.c.snapshot()
    if (not state['knife']['grasp'][0]or not all(frozenset(('knife','left_finger'+str(i)))in contacts for i in(1,2))):
        raise RuntimeError('C knife release height needs the real bilateral hold')
    geometry=a.finger_geometry('left')
    if geometry.get('source')!='actual_collision_mesh_current_body_pose':
        raise RuntimeError('Actual C finger collision meshes required')
    obj=next(o for o in a.scene.spec['objects']if o['id']=='tray');tray=state['tray']
    rotation=np.asarray(tray['mat']);center=np.asarray(tray['pos'])+rotation@np.asarray(obj.get('local_bounds_center',[0,0,0]))
    half=np.abs(rotation)@np.asarray(obj.get('bounds_half_extent',obj['size']))
    overlaps=any(np.all(np.asarray(f['aabb_max_task_m'])[:2]>=center[:2]-half[:2])
        and np.all(np.asarray(f['aabb_min_task_m'])[:2]<=center[:2]+half[:2])for f in geometry['fingers'])
    height=float(proposed_z)
    if overlaps:
        height=max(height,float(a.floor_clear_tcp('left',floor=float(center[2]+half[2])+.005)))
    a.control_report['e25_c_final_knife_release_height']=dict(original_tcp_z_m=float(proposed_z),
        selected_tcp_z_m=height,actual_finger_tray_xy_overlap=bool(overlaps),
        tray_top_z_m=float(center[2]+half[2]),native_goal_unchanged=True)
    return height


def run(a,parameters):
    _scope(a,'E25','C');checkpoint=getattr(a,'_engineering_resume_checkpoint',{});source=checkpoint.get('source',{})
    if (parameters!={}or a.scene.spec.get('seed')!=4201 or checkpoint.get('diagnostic_only')is not True
            or source.get('steps')!=209 or source.get('physics_ticks')!=20911
            or not getattr(a.c,'_engineering_diagnostic_only',False)
            or not getattr(a.c,'_engineering_checkpoint_readback_passed',False)):
        raise ValueError('Registered C209 admitted native checkpoint required')
    obj=next(o for o in a.scene.spec['objects']if o['id']=='knife')
    if obj.get('source_asset',{}).get('sha256')!=TAIL_GRASPS['knife']['sha256']:
        raise ValueError('Original C source knife mesh required')
    goal=next(g for g in a.scene.spec['goals']if g['object']=='knife')
    zone=next(z for z in a.scene.spec['zones']if z['id']==goal['target'])
    if zone.get('anchor_object')or goal.get('required_support',zone.get('support','table'))!='table':
        raise ValueError('Original C knife table goal required')
    xy=np.asarray(goal.get('placement_xy',zone['xy']),float);half=np.asarray(zone['half_size'],float)
    floor=float(zone.get('surface_z',.8))
    target=(_axis_rotation([0,0,1],float(goal.get('yaw',0)))@
            _axis_rotation([0,1,0],float(goal.get('pitch',0)))@
            _axis_rotation([1,0,0],float(goal.get('roll',0))))
    def region_and_orientation(*,before_release=True):
        state,_=a.c.snapshot();body=state['knife'];r=np.asarray(body['mat'],float)
        angle=math.acos(float(np.clip((np.trace(target@r.T)-1)/2,-1,1)))
        if np.any(abs(np.asarray(body['pos'])[:2]-xy)>half)or(before_release and angle>math.radians(6)):
            raise RuntimeError('C209 actual knife is outside original release region/orientation')
        if not floor<float(body['pos'][2])<floor+.09:
            raise RuntimeError('C209 actual knife is outside short gravity release height')
    def held():
        state,contacts=a.c.snapshot()
        if (not state['knife']['grasp'][0]or not all(frozenset(('knife','left_finger'+str(i)))in contacts for i in(1,2))
                or any(body['grasp'][1]or(name!='knife'and body['grasp'][0])for name,body in state.items())):
            raise RuntimeError('C209 requires actual bilateral knife grip and empty peer')
    held();region_and_orientation();old_act=a.act;before=a.c.steps;holding=True
    a.carried_payload=('knife','left');a.stage='grasped-knife'
    def act(*args,**kwargs):
        if a.c.steps-before>=30:raise RuntimeError('C209 bounded release tail exhausted')
        if holding:held()
        result=old_act(*args,**kwargs)
        if holding:held()
        return result
    a.act=act
    try:
        # Actual upward extraction removes the measured finger1/tray load;
        # do not continue driving the already flat knife farther downward.
        tip=np.asarray(a.tip('left'),float)
        a.move_generated({'left':[*tip[:2],tip[2]+.020]})
        _,contacts=a.c.snapshot()
        if any('left_finger'+str(i)in pair and 'knife'not in pair for pair in contacts for i in(1,2)):
            raise RuntimeError('C209 finger still touches scene geometry after upward extraction')
        region_and_orientation();holding=False;a.release_generated('left');a.carried_payload=None
        state,contacts=a.c.snapshot()
        if any(state['knife']['grasp'])or frozenset(('knife','table'))not in contacts:
            raise RuntimeError('C209 actual gravity release lacks original table support')
        region_and_orientation(before_release=False)
        a.stage='released-knife';tip=np.asarray(a.tip('left'),float)
        a.move_generated({'left':[*tip[:2],tip[2]+.040]})
        state,contacts=a.c.snapshot();region_and_orientation(before_release=False)
        if any(state['knife']['grasp'])or frozenset(('knife','table'))not in contacts:
            raise RuntimeError('C209 final original table support lost')
        return [dict(operation='actual_finger_tray_upward_clearance',side='left',requested_lift_m=.020),
                dict(operation='original_C_knife_table_gravity_release',side='left')]
    finally:a.act=old_act
