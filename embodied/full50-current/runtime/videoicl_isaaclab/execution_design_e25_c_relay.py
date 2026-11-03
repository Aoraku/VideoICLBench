"""C404 native-checkpoint continuation: true relay-knife grasp and placement."""
from copy import deepcopy
import numpy as np
from .execution_design_segments_e19_e25 import _scope,_acquire


def run(a,parameters):
    _scope(a,'E25','C');checkpoint=getattr(a,'_engineering_resume_checkpoint',{});source=checkpoint.get('source',{})
    if (parameters!={}or a.scene.spec.get('seed')!=4201 or checkpoint.get('diagnostic_only')is not True
            or source.get('steps')!=404 or source.get('physics_ticks')!=41240
            or not getattr(a.c,'_engineering_diagnostic_only',False)
            or not getattr(a.c,'_engineering_checkpoint_readback_passed',False)):
        raise ValueError('Registered C404 admitted native checkpoint required')
    from .execution_design_generated_route import measured_generated_clearance
    state,contacts=a.c.snapshot()
    if getattr(a,'carried_payload',None)is not None or any(any(b.get('grasp',[]))for b in state.values())or frozenset(('knife','table'))not in contacts:
        raise RuntimeError('C404 requires actual empty hands and table-supported knife')
    original=next(g for g in a.scene.spec['goals']if g['object']=='knife');goal=deepcopy(original)
    obj=next(o for o in a.scene.spec['objects']if o['id']=='knife');body=state['knife'];r=np.asarray(body['mat']);half=np.asarray(obj.get('bounds_half_extent',obj['size']));center=np.asarray(obj.get('local_bounds_center',[0,0,0]))
    extent=(np.abs(r@center)+np.abs(r)@half)[:2]+.025
    goal['_e07_after_relay']={'id':'measured-existing-relay-support','xy':np.asarray(body['pos'])[:2].tolist(),'half_size':extent.tolist(),'surface_z':.8,'support':'table'}
    p={'side':'left','goal':goal,'expected_source_pose':{k:deepcopy(body[k])for k in('pos','mat')},'approach_z':float(measured_generated_clearance(a)['clearance_z_m'])}
    before=a.c.steps;holding=False;old_act=a.act
    def held():
        state,contacts=a.c.snapshot()
        return bool(state['knife']['grasp'][0]and all(frozenset(('knife','left_finger'+str(i)))in contacts for i in(1,2)))
    def guard():
        state,_=a.c.snapshot()
        if a.c.steps-before>=300:raise RuntimeError('C404 local public knife budget exhausted')
        if any(b.get('grasp',[False,False])[1]or(n!='knife'and b.get('grasp',[False,False])[0])for n,b in state.items()):raise RuntimeError('C404 acquired an unexpected object or peer hold')
        if holding and not held():raise RuntimeError('C404 actual bilateral knife grip lost')
    def act(*args,**kwargs):
        guard();result=old_act(*args,**kwargs);guard();return result
    a.act=act
    try:
        operations=_acquire(a,'C','knife',p);holding=True;guard();a.stage='grasped-knife'
        clearance=float(measured_generated_clearance(a)['clearance_z_m'])
        a.move_generated({'left':[*a.tip('left')[:2],clearance]});a.rotate_held('knife','left',goal)
        state,_=a.c.snapshot();offset=np.asarray(a.tip('left'))-np.asarray(state['knife']['pos']);target=next(z for z in a.scene.spec['zones']if z['id']==original['target']);xy=np.asarray(original.get('placement_xy',target['xy']),float)
        if target.get('anchor_object'):
            anchor=state[target['anchor_object']];xy=(np.asarray(anchor['pos'])+np.asarray(anchor['mat'])@np.asarray(target.get('anchor_local_center',[0,0,0])))[:2]
        height=float((np.abs(state['knife']['mat'])@np.asarray(obj['size']))[2]);tcp_xy=xy+offset[:2]
        a.move_generated({'left':[*tcp_xy,clearance]})
        a.move_generated({'left':[*tcp_xy,float(target.get('surface_z',.8))+height+float(offset[2])+.004]})
        guard();holding=False;a.release_generated('left');state,_=a.c.snapshot()
        if any(state['knife']['grasp']):raise RuntimeError('C404 original knife did not physically release')
        a.carried_payload=None;a.stage='released-knife';a.move_generated({'left':[*a.tip('left')[:2],clearance]})
        state,contacts=a.c.snapshot();support=original.get('required_support',target.get('support','table'))
        if frozenset(('knife',support))not in contacts or np.any(abs(np.asarray(state['knife']['pos'])[:2]-xy)>np.asarray(target['half_size'])):
            raise RuntimeError('C404 original knife goal lacks actual support/region')
        return operations+[{'operation':'original_C_knife_goal_actual_supported_release','side':'left'}]
    finally:a.act=old_act
