"""A543: actual supported red pinch, then original measured public liftoff."""
from .execution_design import REVISION_V3
from .realworld_tool_expert import ToolExecutionError


def run_segment(a,segment,parameters):
    s=a.scene.spec;cp=getattr(a,'_engineering_resume_checkpoint',{});source=cp.get('source',{})
    continue_held=(segment=='e20_a_finish_after_red_lift7'and source.get('steps')==7
        and source.get('physics_ticks')==702 and cp.get('stage')=='checkpoint-suffix-completed'
        and cp.get('context',{}).get('entry')=='e20_a_lift_red_from543')
    lift_boundary=segment=='e20_a_lift_red_from543'and source.get('steps')==543 and source.get('physics_ticks')==55140
    if (not(continue_held or lift_boundary)or parameters!={}or s.get('id')!='E20'
            or s.get('variant')!='A'or s.get('seed')!=4201
            or s.get('execution_design',{}).get('revision')!=REVISION_V3
            or s['execution_design'].get('condition')!='I'
            or not a.control_report.get('engineering_reference_only')or cp.get('diagnostic_only')is not True
            or not getattr(a.c,'_engineering_diagnostic_only',False)
            or not getattr(a.c,'_engineering_checkpoint_readback_passed',False)):
        raise ToolExecutionError('Registered E20 A543 supported red native boundary required')
    from .execution_design_expert import ExecutionDesignAuthor
    from .execution_design_e20_reference import verify_grip_during_small_liftoff
    from .execution_design_segments_e17_e20 import _held_with_contacts,_source,_source_rail,DISK_SHA
    p=ExecutionDesignAuthor(a);name='red_supply_1';side='right'
    _source(p,name,DISK_SHA,[.016,.01603,.000988]);_held_with_contacts(p,name,side)
    if continue_held:
        if p.contact(name,'fixture7'):raise ToolExecutionError('A7 red lift must already clear original source rail')
        from .execution_design_e20_slots import _inside
        from .execution_design_e20_reference import remember_freed_source_rail
        region=next(r for r in p.d['local_regions']if name in r['candidates'])
        p.stage('local-E20-A7-finish-real-held-red')
        p.place(name,region['actor'],p.free_chip_slot(region,name),actual_held_side=side)
        remember_freed_source_rail(p,'blue_supply_3')
        p._engineering_skip_actual_completed_regions=True
        p.local_stage();p.package_stage();p.deliver()
        state,contacts=p.snapshot()
        if any(any(v['grasp'])for v in state.values()):raise ToolExecutionError('A7 remaining workflow still holds actual cargo')
        for r in p.d['local_regions']:
            actual=[n for n in r['candidates']if _inside(p,r,n)and p.contact(n,r['actor'])]
            if len(actual)!=r['count']:raise ToolExecutionError('A7 actual final supported region count differs: '+r['id'])
        return dict(local_completed=True,operations=p.operations,actions=p.c.steps-p.start)
    _source_rail(p,name,7)
    p.stage('local-E20-A543-real-red-liftoff')
    verify_grip_during_small_liftoff(p,p.ref(name),side,initial_measured_grips=2)
    _held_with_contacts(p,name,side)
    return dict(local_completed=True,operations=p.operations,actions=p.c.steps-p.start)
