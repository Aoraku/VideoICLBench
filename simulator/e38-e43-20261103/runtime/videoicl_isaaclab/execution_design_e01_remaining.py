"""Continue the uncompleted physical E01 workflow without repeating its prefix."""
import numpy as np
from .realworld_tool_expert import ToolExecutionError


def _inside(p,name,container,extra=.02):
    state,_=p.snapshot();base,r=p.frame({'actor':container})
    local=r.T@(np.asarray(state[name]['pos'])-base)
    return bool(np.all(abs(local[:2])<=np.asarray(p.objects[container]['size'])[:2]+extra))


def _extract_if_needed(p,entry):
    base=p.frame({'actor':'tray'})[0]
    held=any(p.snapshot()[0]['tray']['grasp'])
    if p.contact('tray','meal_box')and _inside(p,'tray','meal_box'):return
    if entry!='extract_tray'and all(p.contact(name,'tray')or p.contact(name,'meal_box')for name in p.d['target_members']):return
    # A native restore has poses/FK before it has fresh solver contacts.  The
    # explicit food entry follows the measured source tray release; do not
    # reacquire an already prepared tray merely because cold contacts are empty.
    if entry!='extract_tray'and base[0]<-.22 and .79<float(base[2])<.85 and not held:return
    if base[0]<-.22 and(p.contact('tray','table')and not held or held and entry!='extract_tray'):return
    hands=[s for i,s in enumerate(('left','right'))if p.snapshot()[0]['tray']['grasp'][i]]
    if not hands:
        p.stage_on_table('tray');return
    if len(hands)!=1:raise ToolExecutionError('E01 extraction has an ambiguous actual tray hold')
    side=hands[0];stale=0;p.stage('functional-continue-original-tray-extraction')
    while float(p.frame({'actor':'tray'})[0][0])>-.33:
        p.require_held({'actor':'tray'},side);before=float(p.frame({'actor':'tray'})[0][0])
        p.act(side,'BACK',mm=25.)
        stale=stale+1 if before-float(p.frame({'actor':'tray'})[0][0])<.001 else 0
        if stale>=3:raise ToolExecutionError('E01 tray extraction has no actual progress')
    p.act(side,'RELEASE');p.move(side,p.tip(side)+[0,0,.06],tolerance=.008)
    if any(p.snapshot()[0]['tray']['grasp'])or not p.contact('tray','table'):
        raise ToolExecutionError('E01 extracted tray has not physically released onto its table')


def _finish_food(p):
    from .execution_design_e01_food import pickup_food,park_empty_other
    selected=(['burger','fries'],['burger','drink'],['fries','drink'])[p.index]
    if set(p.identity[label]for label in selected)!=set(p.d['target_members']):
        raise ToolExecutionError('E01 original variant selection differs from its source')
    state=getattr(p,'_e01_food_progress',dict(selected=selected,completed=[],current=None))
    p._e01_food_progress=state
    if state['selected']!=selected:raise ToolExecutionError('E01 saved food selection differs')
    container=p.s['containers']['plate'];tray=container['ref']['actor']
    for label in selected:
        name=p.identity[label];snapshot,_=p.snapshot()
        placed=not any(snapshot[name]['grasp'])and(
            p.contact(name,tray)and _inside(p,name,tray)
            or p.contact(name,'meal_box')and _inside(p,name,'meal_box'))
        if label in state['completed']and not any(snapshot[name]['grasp'])and _inside(p,name,tray):
            local=p.frame({'actor':tray})[1].T@(np.asarray(snapshot[name]['pos'])-p.frame({'actor':tray})[0])
            placed=placed or bool(-.03<float(local[2])<.14)
        if placed:
            if label not in state['completed']:state['completed'].append(label)
            continue
        if label in state['completed']:
            raise ToolExecutionError('E01 previously placed selected food actually left its container: '+name)
        hands=[s for i,s in enumerate(('left','right'))if snapshot[name]['grasp'][i]]
        if len(hands)>1:raise ToolExecutionError('E01 selected food needs one actual held hand')
        side=hands[0]if hands else p.hand_for(name);ref=p.ref(name)
        park_empty_other(p,side,state,ref if hands else None)
        state['current']=label;p.stage('functional-continue-selected-food-'+label)
        if not hands:ref,side=pickup_food(p,name,side)
        guard=lambda:p.require_held(ref,side)
        control=dict(actor=name,local=p.bottom_local(name).tolist())
        target=p.body_point(container['ref'],p.geometry['plate_positions'][name]);point=p.point(control)
        if max(abs(point[:2]-target[:2]))>.02:
            high=max(.98,float(point[2]),float(target[2])+.07)
            p.move_point(side,control,[*point[:2],high],guard,tolerance=.008)
            p.move_point(side,control,[*target[:2],high],guard,tolerance=.008)
        p.move_point(side,control,target+[0,0,.004],guard,tolerance=.006)
        p.act(side,'RELEASE');p.move(side,p.tip(side)+[0,0,.06],tolerance=.008)
        if any(p.snapshot()[0][name]['grasp'])or not p.contact(name,tray)or not _inside(p,name,tray):
            raise ToolExecutionError('E01 selected food did not actually land on its tray: '+name)
        state['completed'].append(label);state['current']=None


def complete_remaining(p,params):
    from .execution_design_e01_balance import _coarse
    from .execution_design_e01_package import _state,stage_meal_box_for_loading,load_meal_tray
    from .execution_design_e01_functional import close_lid,deliver,_lid_angle,prestage_open_carton
    if p.task!='E01'or not _coarse(p)or params.get('functional_mode')is not True:
        raise ToolExecutionError('Explicit E01 functional engineering continuation required')
    if p.spec['seed']!=4201 or p.variant not in 'ABC':raise ToolExecutionError('E01 source identity differs')
    p.max_mm=min(25.,float(p.a.scene.embodiment.config['control']['step_mm'][1]))
    if params.get('resume_entry')not in('extract_tray','food','stage_carton','load_tray','shipment','delivery'):
        raise ToolExecutionError('Explicit measured E01 resume entry required')
    p.a.control_report['e01_functional_resume']=dict(source_cumulative_steps=p.c.steps,
        entry=params['resume_entry'],variant=p.variant,selected_actors=list(p.d['target_members']),
        repeated_source_prefix=False,native_history_restored=False)
    _extract_if_needed(p,params['resume_entry']);_finish_food(p)
    state=_state(p)
    if p.contact('tray','meal_box')and _inside(p,'tray','meal_box')and not any(p.snapshot()[0]['tray']['grasp']):
        state['phase']='loaded'
    if state['phase']=='stage_box':stage_meal_box_for_loading(p)
    if state['phase']=='load_tray':load_meal_tray(p)
    package=next(q for q in p.d['packages']if q['container']=='meal_box')
    if abs(_lid_angle(p,package))>.35:prestage_open_carton(p);close_lid(p)
    return deliver(p)
