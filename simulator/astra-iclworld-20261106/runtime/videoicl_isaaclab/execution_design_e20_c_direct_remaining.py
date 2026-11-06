"""C423: actual original-rail destination-hand pickup and remaining workflow."""
from .execution_design import REVISION_V3
from .realworld_tool_expert import ToolExecutionError


def run_segment(a,segment,parameters):
    s=a.scene.spec;cp=getattr(a,'_engineering_resume_checkpoint',{});source=cp.get('source',{})
    if (segment!='e20_c_direct_remaining_from423'or parameters!={}or s.get('id')!='E20'
            or s.get('variant')!='C'or s.get('seed')!=4201
            or s.get('execution_design',{}).get('revision')!=REVISION_V3
            or s['execution_design'].get('condition')!='I'
            or not a.control_report.get('engineering_reference_only')or cp.get('diagnostic_only')is not True
            or (source.get('steps'),source.get('physics_ticks'))!=(423,43140)
            or not getattr(a.c,'_engineering_diagnostic_only',False)
            or not getattr(a.c,'_engineering_checkpoint_readback_passed',False)):
        raise ToolExecutionError('Registered E20 C423 original source-rail suffix required')
    from .execution_design_expert import ExecutionDesignAuthor
    from .execution_design_segments_e17_e20 import _source,_source_rail,DISK_SHA
    from .execution_design_e20_slots import _inside
    from .execution_design_e20_c_transfer import finish_left_placement
    p=ExecutionDesignAuthor(a);name='blue_supply_1';_source(p,name,DISK_SHA,[.016,.01603,.000988]);_source_rail(p,name,3)
    state,contacts=p.snapshot();region=next(r for r in p.d['local_regions']if r['id']=='triangle')
    if any(any(v['grasp'])for v in state.values()):raise ToolExecutionError('C423 direct source entry requires empty actual hands')
    for n in('blue_supply_3','blue_supply_4'):
        if not _inside(p,region,n)or frozenset((n,region['actor']))not in contacts:
            raise ToolExecutionError('C423 original completed blue support/region changed')
    p._engineering_e20_direct_destination=True
    finish_left_placement(p,region)
    p._engineering_skip_actual_completed_regions=True
    p.local_stage();p.package_stage();p.deliver()
    state,contacts=p.snapshot()
    if any(any(v['grasp'])for v in state.values()):raise ToolExecutionError('C423 remaining workflow still physically holds cargo')
    for r in p.d['local_regions']:
        actual=[n for n in r['candidates']if _inside(p,r,n)and p.contact(n,r['actor'])]
        if len(actual)!=r['count']:raise ToolExecutionError('C423 actual supported final count differs: '+r['id'])
    return dict(local_completed=True,operations=p.operations,actions=p.c.steps-p.start)
