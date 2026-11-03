"""B98: lift the real two-receipt pinch, then continue the physical workflow."""
from .execution_design import REVISION_V3
from .realworld_tool_expert import ToolExecutionError


def run_segment(a,segment,parameters):
    s=a.scene.spec;cp=getattr(a,'_engineering_resume_checkpoint',{});source=cp.get('source',{})
    if (segment!='e20_b_lift_and_finish_from_left98'or parameters!={}or s.get('id')!='E20'
            or s.get('variant')!='B'or s.get('seed')!=4201
            or s.get('execution_design',{}).get('revision')!=REVISION_V3
            or s['execution_design'].get('condition')!='I'
            or not a.control_report.get('engineering_reference_only')or cp.get('diagnostic_only')is not True
            or source.get('steps')!=98 or source.get('physics_ticks')!=9802
            or not getattr(a.c,'_engineering_diagnostic_only',False)
            or not getattr(a.c,'_engineering_checkpoint_readback_passed',False)):
        raise ToolExecutionError('Registered E20 B98 actual held-blue fixture required')
    from .execution_design_expert import ExecutionDesignAuthor
    from .execution_design_segments_e17_e20 import _held_with_contacts,_source,DISK_SHA
    from .execution_design_e20_reference import verify_grip_during_small_liftoff,remember_freed_source_rail
    from .execution_design_e20_c_transfer import finish_left_placement
    p=ExecutionDesignAuthor(a);name='blue_supply_1';_source(p,name,DISK_SHA,[.016,.01603,.000988])
    # Real cold-restored bilateral grip can lift the 2mm chip 1.5mm away from
    # its rail during the mandatory native-FK hold. Preserve the exact source
    # geometry, but do not require pressing an already-held chip back onto it.
    import numpy as np
    fixtures=p.spec.get('fixtures',[])
    if (p.d.get('initial_storage',{}).get(name)!='fixture3'or len(fixtures)<=3
            or fixtures[3].get('type')!='box'or not np.allclose(fixtures[3]['size'],[.003,.012,.014])):
        raise ToolExecutionError('B98 original source-rail3 geometry required')
    _held_with_contacts(p,name,'left');p.stage('local-E20-B98-real-lift-before-third-squeeze')
    verify_grip_during_small_liftoff(p,p.ref(name),'left',initial_measured_grips=1)
    _held_with_contacts(p,name,'left');region=next(r for r in p.d['local_regions']if r['id']=='triangle')
    finish_left_placement(p,region,acquire=False)
    remember_freed_source_rail(p,'blue_supply_3')
    p._engineering_skip_actual_completed_regions=True
    p.local_stage();p.package_stage();p.deliver()
    from .execution_design_e20_slots import _inside
    state,contacts=p.snapshot()
    if any(any(v['grasp'])for v in state.values()):raise ToolExecutionError('Remaining E20 workflow still physically holds an object')
    for r in p.d['local_regions']:
        actual=[n for n in r['candidates']if _inside(p,r,n)and p.contact(n,r['actor'])]
        if len(actual)!=r['count']:raise ToolExecutionError('Actual E20 final supported region count differs: '+r['id'])
    return dict(local_completed=True,operations=p.operations,actions=p.c.steps-p.start)
