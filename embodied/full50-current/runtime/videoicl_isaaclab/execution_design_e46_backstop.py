"""E46 physical scoop with an open, table-side stabilizing finger.

Adapt the unaccepted E28 backstop candidate without changing its owner module.
The food is never grasped or hand-lifted. Actual relative entry precedes a
withdrawal outside its vertical column and a separately verified blade lift.
"""
import json
import numpy as np
from .realworld_tool_expert import ToolExecutionError
from .execution_design_e28_backstop import finger_target


def record(a, row):
    food=row.get('food_actor')or next(iter(a.s['groups']['cargo']))
    try:
        sensor,labels=a.a.scene.contacts[food]
        forces=sensor.data.force_matrix_w[0].sum(dim=0).detach().cpu().numpy()
        rotation=np.asarray(a.a.scene.layout.task_rotation)
        row=dict(row,food_contact_force_vectors_task={label:(rotation.T@vector).tolist()for label,vector in zip(labels,forces)})
    except Exception as exc:
        row=dict(row,force_vector_readback_error=type(exc).__name__+': '+str(exc))
    with (a.a.out/'E46-relative-insertion.private.jsonl').open('a')as f:
        f.write(json.dumps(dict(step=a.c.steps,**row))+'\n')


def insert(a,food,edge,tool_side,direction,height,guard,resume_backstop=False,park_task=None,entry_step_m=.003,entry_tolerance_m=.001):
    if a.task!='E46' or not a.a.control_report.get('engineering_reference_only'):
        raise ToolExecutionError('E46 isolated blade insertion only')
    if a.s.get('auxiliary_loading_hand_allowed')is not True:
        raise ToolExecutionError('Source does not permit a stabilizing hand')
    from .execution_design_drawer_ik_probe import inspect
    if entry_step_m not in (.001,.003)or not 0<entry_tolerance_m<=entry_step_m:raise ToolExecutionError('Bounded actual insertion increments required')
    partials=0
    side='left'if tool_side=='right'else'right';park=a.tip(side).copy()
    if park_task is not None:
        park=np.asarray(park_task,float)
        if park.shape!=(3,)or not np.isfinite(park).all()or not .89<=park[2]<=1.02:
            raise ToolExecutionError('Finite measured safe backstop parking target required')
    if not resume_backstop:
        a.stage('open-finger-backstop-'+food);a.act(side,'RELEASE')
    guard()
    state=a.snapshot()[0];obj=next(o for o in a.spec['objects']if o['id']==food)
    initial=state[food]['pos'].copy();half=np.abs(state[food]['mat'])@np.asarray(obj['size'])
    initial_bottom=float(initial[2]-half[2])
    fingers=a.a.finger_geometry(side)['fingers']
    chosen=min(fingers,key=lambda f:float(np.asarray(f['aabb_center_task_m'])@direction))['name']
    tops=[float(v['pos'][2]+(np.abs(v['mat'])@np.asarray(next(o['size']for o in a.spec['objects']if o['id']==name)))[2])
          for name,v in state.items()if not any(v['grasp'])]
    high=max(.90,max(tops)+.06)
    if resume_backstop:
        if any(state[food]['grasp'])or not any(a.contact(food,side+'_finger'+str(i))for i in(1,2))or a.c.grips[side]<.035:
            raise ToolExecutionError('Resumed source backstop is not a real open-finger food contact')
    else:
        finger=next(f for f in fingers if f['name']==chosen)
        center,target=finger_target(initial,half,direction,finger)
        low=a.tip(side)+target-center
        sites=[np.r_[park[:2],high],np.r_[low[:2],high],low]
        rotation=np.asarray(a.a.tcp_rotation_task(side))
        rows=inspect(a.a,a.c,side,[dict(position=p.tolist(),rotation=rotation.tolist())for p in sites])
        record(a,dict(phase='backstop-route-IK',candidates=rows,public_actions_only=True))
        if not all(r['kinematically_reachable']and r['minimum_joint_margin_rad']>=.06 for r in rows):
            raise ToolExecutionError('Open backstop route lacks measured IK margin')
        for point in sites:a.move(side,point,guard,tolerance=.0015)
        for _ in range(6):
            guard();st=a.snapshot()[0][food]
            if any(st['grasp']):raise ToolExecutionError('Backstop grasped food')
            finger=next(f for f in a.a.finger_geometry(side)['fingers']if f['name']==chosen)
            center,target=finger_target(st['pos'],np.abs(st['mat'])@np.asarray(obj['size']),direction,finger)
            error=target-center
            if max(abs(error))<=.0015:break
            a.move(side,a.tip(side)+error,guard,tolerance=.0015)
        else:raise ToolExecutionError('Measured open backstop did not reach outside-food target')
    withdrawn=False
    for _ in range(45):
        guard();st=a.snapshot()[0][food]
        if any(st['grasp']):raise ToolExecutionError('Food grasped during blade insertion')
        center=st['pos'];half=np.abs(st['mat'])@np.asarray(obj['size']);point=a.point(edge)
        relative=float((point-center)@direction);extent=float(np.abs(st['mat'].T@direction)@np.asarray(obj['size']))
        record(a,dict(phase='actual-relative-entry',food=center.tolist(),edge=point.tolist(),relative_edge=relative,
                      table_contact=a.contact(food,'table'),tool_contact=a.contact(food,edge['actor']),backstop_withdrawn=withdrawn))
        if not withdrawn and (relative>=-extent+.006 or center[2]-half[2]>initial_bottom+.0015):
            a.stage('withdraw-open-finger-before-independent-lift')
            a.move(side,a.tip(side)+direction*.10,guard)
            for f in a.a.finger_geometry(side)['fingers']:
                lo=np.asarray(f['aabb_min_task_m']);hi=np.asarray(f['aabb_max_task_m'])
                if np.all(hi[:2]>=center[:2]-half[:2]-.02)and np.all(lo[:2]<=center[:2]+half[:2]+.02):
                    raise ToolExecutionError('Withdrawn backstop still obstructs vertical blade lift')
            a.move(side,np.r_[a.tip(side)[:2],high],guard)
            a.move(side,np.r_[park[:2],high],guard);withdrawn=True
        if withdrawn and relative>=.002:return
        if np.linalg.norm(center[:2]-initial[:2])>.035:
            raise ToolExecutionError('Food slid ahead instead of actual blade insertion')
        a.stage('actual-relative-blade-insertion-'+food)
        target=point+direction*entry_step_m;target[2]=height
        try:a.move_point(tool_side,edge,target,guard,tolerance=entry_tolerance_m)
        except ToolExecutionError as exc:
            actual=float((a.point(edge)-point)@direction)
            if ('Actual tool material stalled:'not in str(exc)or actual<.0003 or partials>=5
                    or not a.contact(food,edge['actor'])):raise
            partials+=1
            record(a,dict(phase='bounded-actual-partial-entry',actual_progress_m=actual,partial_count=partials,old_target_not_claimed_reached=True))
    raise ToolExecutionError('E46 bounded relative blade insertion failed')
