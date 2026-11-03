"""C321: finish the real rail handover using short public translations."""
import numpy as np
from .execution_design import REVISION_V3
from .realworld_tool_expert import ToolExecutionError


def run_segment(a, segment, parameters):
    if segment=='e20_c_reacquire_supported_blue_from1':
        return reacquire_supported(a,parameters)
    cp=getattr(a,'_engineering_resume_checkpoint',{});source=cp.get('source',{});spec=a.scene.spec
    if (segment!='e20_c_finish_blue_transfer_from321'or parameters!={}
            or spec.get('id')!='E20'or spec.get('variant')!='C'or spec.get('seed')!=4201
            or spec.get('execution_design',{}).get('revision')!=REVISION_V3
            or spec['execution_design'].get('condition')!='I'
            or not a.control_report.get('engineering_reference_only')
            or cp.get('diagnostic_only')is not True
            or source.get('steps')!=321 or source.get('physics_ticks')!=32102
            or not getattr(a.c,'_engineering_diagnostic_only',False)
            or not getattr(a.c,'_engineering_checkpoint_readback_passed',False)):
        raise ToolExecutionError('Registered E20 C321 native boundary required')
    from .execution_design_expert import ExecutionDesignAuthor
    from .execution_design_e20_slots import _inside
    from .execution_design_segments_e17_e20 import _source,DISK_SHA,_held_with_contacts
    from .execution_design_e20_far_blue import applies,place
    p=ExecutionDesignAuthor(a);name='blue_supply_1';ref=p.ref(name)
    _source(p,name,DISK_SHA,[.016,.01603,.000988])
    region=next(r for r in p.d['local_regions']if r['id']=='triangle')
    fixture=spec['fixtures'][2]
    if (fixture.get('type')!='box'or not np.allclose(fixture['size'],[.003,.012,.014])
            or p.d['initial_storage'].get('blue_supply_3')!='fixture2'):
        raise ToolExecutionError('Original freed blue3 rail2 required')
    target=np.array([*fixture['xy'],fixture['z']+fixture['size'][2]],float)
    def preserved():
        state,contacts=p.snapshot()
        for n in ('blue_supply_3','blue_supply_4'):
            if (any(state[n]['grasp'])or not _inside(p,region,n)
                    or frozenset((n,region['actor']))not in contacts):
                raise ToolExecutionError('C321 previously placed blue support/containment changed')
    def held():
        preserved();_held_with_contacts(p,name,'right')
        if any(v['grasp'][0]or(n!=name and v['grasp'][1])for n,v in p.snapshot()[0].items()):
            raise ToolExecutionError('C321 requires one real right blue1 grip and empty peer')
    held();control=dict(actor=name,local=p.bottom_local(name));point=p.point(control)
    if np.max(abs(point[:2]-target[:2]))>.020 or not 0<=point[2]-target[2]<=.035:
        raise ToolExecutionError('C321 actual blue1 is outside short rail alignment envelope')
    previous=p.max_mm;p.max_mm=min(previous,2.)
    try:
        p.stage('local-E20-C321-short-rail-alignment')
        p.move_point('right',control,[*target[:2],point[2]],held,tolerance=.001)
        p.move_point('right',control,target+[0,0,.001],held,tolerance=.001)
        held();p.release(ref,'right')
    finally:p.max_mm=previous
    p.move('right',p.tip('right')+[0,0,.06])
    state,contacts=p.snapshot();preserved()
    if (any(state[name]['grasp'])or frozenset((name,'fixture2'))not in contacts
            or np.max(abs(p.point(control)-target))>.006):
        raise ToolExecutionError('C321 actual blue1 lacks released narrow rail support')
    p.operations.append(dict(operation='actual_short_step_supported_blue_handover',support='fixture2',maximum_translation_mm=2.))
    # The source-side pickup already happened. Continue with the real left
    # acquisition, then reuse the unchanged original destination controller.
    return finish_left_placement(p,region)


def finish_left_placement(p,region,acquire=True):
    from .execution_design_segments_e17_e20 import _held_with_contacts
    from .execution_design_e20_slots import _inside
    from .execution_design_e20_far_blue import applies,place
    name='blue_supply_1'
    if acquire:ref,side=p.pickup(name,side_override='left')
    else:ref,side=p.ref(name),'left'
    held_left=lambda:_held_with_contacts(p,name,'left')
    held_left();local=p.free_chip_slot(region,name);actor=region['actor']
    p.stage('local-E20-C321-place-next-blue')
    if applies(p,name,actor,local):place(p,name,ref,side,actor,local)
    else:
        base,rotation=p.frame(dict(actor=actor))
        p.lower_place(name,ref,side,p.bottom_local(name),base+rotation@np.asarray(local),support=actor)
    state,contacts=p.snapshot()
    if (any(state[name]['grasp'])or frozenset((name,actor))not in contacts
            or not all(_inside(p,region,n)and frozenset((n,actor))in contacts
                       and not any(state[n]['grasp'])for n in(name,'blue_supply_3','blue_supply_4'))):
        raise ToolExecutionError('C321 next blue lacks real tray support/containment')
    return dict(local_completed=True,operations=p.operations,placed_actor=name,actions=p.c.steps-p.start)


def reacquire_supported(a,parameters):
    cp=getattr(a,'_engineering_resume_checkpoint',{});source=cp.get('source',{});spec=a.scene.spec
    if (parameters!={}or spec.get('id')!='E20'or spec.get('variant')!='C'or spec.get('seed')!=4201
            or spec.get('execution_design',{}).get('revision')!=REVISION_V3
            or spec['execution_design'].get('condition')!='I'
            or not a.control_report.get('engineering_reference_only')or cp.get('diagnostic_only')is not True
            or source.get('steps')!=1 or source.get('physics_ticks')!=110
            or not getattr(a.c,'_engineering_diagnostic_only',False)
            or not getattr(a.c,'_engineering_checkpoint_readback_passed',False)):
        raise ToolExecutionError('Registered E20 C1 actual supported-blue boundary required')
    from .execution_design_expert import ExecutionDesignAuthor
    from .execution_design_segments_e17_e20 import _source,DISK_SHA
    from .execution_design_e20_slots import _inside
    p=ExecutionDesignAuthor(a);name='blue_supply_1';_source(p,name,DISK_SHA,[.016,.01603,.000988])
    region=next(r for r in p.d['local_regions']if r['id']=='triangle');fixture=spec['fixtures'][2]
    if (p.d['initial_storage'].get('blue_supply_3')!='fixture2'
            or fixture.get('type')!='box'or not np.allclose(fixture['size'],[.003,.012,.014])):
        raise ToolExecutionError('C1 original physical rail2 required')
    def supported():
        state,contacts=p.snapshot()
        if any(any(v['grasp'])for v in state.values())or frozenset((name,'fixture2'))not in contacts:
            raise ToolExecutionError('C1 requires actual released blue1 rail support and empty hands')
        for n in('blue_supply_3','blue_supply_4'):
            if not _inside(p,region,n)or frozenset((n,region['actor']))not in contacts:
                raise ToolExecutionError('C1 previous blue support/containment changed')
    supported();p.stage('local-E20-C1-open-empty-right')
    p.act('right','RELEASE');supported()
    p.move('right',p.tip('right')+[0,0,.06],supported)
    supported();p.operations.append(dict(operation='actual_released_supported_blue_left_reacquisition',support='fixture2'))
    return finish_left_placement(p,region)
