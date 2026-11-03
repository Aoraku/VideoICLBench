"""E20 engineering slot search completion and pinned C423 next-piece segment."""
import itertools
import numpy as np
from .execution_design import REVISION_V3
from .realworld_tool_expert import ToolExecutionError

DISK_SHA='0a52a9c5b908277e7e408155316a3fc55f889405d6ab0331f0922e8bb4047120'


def _scope(policy):
    if (policy.task!='E20'or policy.d.get('revision')!=REVISION_V3
            or not policy.a.control_report.get('engineering_reference_only')):
        raise ToolExecutionError('Explicit E20 v3 engineering slot search required')


def boundary_slot(policy,region,name):
    """Only after the old four cells fail, try four original-boundary corners.

    The original rotated AABBs, all candidate occupancies and 2mm separation
    remain unchanged. No source poses, region bounds or acceptance rules change.
    """
    _scope(policy)
    if region not in policy.d['local_regions']or name not in region['candidates']:
        raise ToolExecutionError('Original E20 region and candidate inventory required')
    for actor in region['candidates']:
        obj=policy.objects[actor]
        if (obj.get('source_asset',{}).get('sha256')!=DISK_SHA
                or not np.allclose(obj['size'],[.016,.01603,.000988],atol=1e-8,rtol=0)):
            raise ToolExecutionError('Original E20 chip meshes/bounds required')
    base,rotation=policy.frame(dict(actor=region['actor']));state=policy.snapshot()[0]
    lower=np.asarray(region['lower'],float);upper=np.asarray(region['upper'],float)
    half=np.abs(rotation.T@state[name]['mat'])@np.asarray(policy.objects[name]['size'])
    low=lower[:2]+half[:2]+.002;high=upper[:2]-half[:2]-.002
    available=[]
    if np.all(low<high):
        for x,y in itertools.product((0,1),repeat=2):
            xy=np.array([high[0]if x else low[0],high[1]if y else low[1]])
            occupied=False
            for other in region['candidates']:
                if other==name:continue
                center=rotation.T@(state[other]['pos']-base)
                extent=np.abs(rotation.T@state[other]['mat'])@np.asarray(policy.objects[other]['size'])
                if center[2]+extent[2]<lower[2]or center[2]-extent[2]>upper[2]:continue
                if np.all(np.abs(center[:2]-xy)<extent[:2]+half[:2]+.002):
                    occupied=True;break
            if not occupied:available.append([*xy,float(lower[2])])
    if not available:raise ToolExecutionError('No measured free chip slot: '+region['id'])
    from .execution_design_e20_reference import robot_bases
    bases=robot_bases(policy)
    target=min(available,key=lambda p:min(float(np.linalg.norm((base+rotation@p)[:2]-b[:2]))for b in bases.values()))
    policy.a.control_report.setdefault('e20_boundary_slot_search',[]).append(dict(
        actor=name,region=region['id'],target_local=target,original_four_cells_exhausted=True,
        original_rotated_AABB_occupancy=True,wall_margin_m=.002,chip_separation_margin_m=.002))
    return target


def _inside(policy,region,name):
    base,rotation=policy.frame(dict(actor=region['actor']));state=policy.snapshot()[0]
    center=rotation.T@(state[name]['pos']-base)
    extent=np.abs(rotation.T@state[name]['mat'])@np.asarray(policy.objects[name]['size'])
    # The actual support separately verifies the vertical placement. The native
    # chip's contact resting offset can differ from the nominal floor by microns.
    return bool(np.all(center[:2]-extent[:2]>=np.asarray(region['lower'])[:2])
        and np.all(center[:2]+extent[:2]<=np.asarray(region['upper'])[:2]))


def run_segment(author,segment,parameters):
    if segment!='e20_c_place_next_blue_from423'or parameters!={}:
        raise ToolExecutionError('Registered C423 next-blue entry with empty parameters required')
    spec=author.scene.spec;checkpoint=getattr(author,'_engineering_resume_checkpoint',{});source=checkpoint.get('source',{})
    if (spec.get('id')!='E20'or spec.get('variant')!='C'or spec.get('seed')!=4201
            or spec.get('execution_design',{}).get('revision')!=REVISION_V3
            or spec.get('execution_design',{}).get('condition')!='I'
            or not author.control_report.get('engineering_reference_only')
            or checkpoint.get('diagnostic_only')is not True
            or source.get('steps')!=423 or source.get('physics_ticks')!=43140
            or not getattr(author.c,'_engineering_diagnostic_only',False)
            or not getattr(author.c,'_engineering_checkpoint_readback_passed',False)):
        raise ToolExecutionError('Registered E20 C423 admitted native checkpoint required')
    from .execution_design_expert import ExecutionDesignAuthor
    from .execution_design_e20_reference import replenishment_candidates,remember_freed_source_rail
    policy=ExecutionDesignAuthor(author);_scope(policy);state,contacts=policy.snapshot()
    if any(any(body['grasp'])for body in state.values()):
        raise ToolExecutionError('C423 next-piece segment requires actual empty hands')
    region=next(r for r in policy.d['local_regions']if r['id']=='triangle')
    if region['required_color']!='blue'or region['actor']!='compartment_tray':
        raise ToolExecutionError('Original C triangle blue assignment required')
    if (not _inside(policy,region,'blue_supply_3')
            or frozenset(('blue_supply_3',region['actor']))not in contacts):
        raise ToolExecutionError('C423 previous blue3 must remain actually released and supported in its cell')
    completed=[name for name in region['candidates']if _inside(policy,region,name)]
    if len(completed)!=2 or set(completed)!={'blue_supply_3','blue_supply_4'}:
        raise ToolExecutionError('C423 actual completed blue inventory differs from original boundary')
    remaining=[n for n in replenishment_candidates(policy,region)if n not in completed]
    if not remaining:raise ToolExecutionError('C423 original next blue source is unavailable')
    name=remaining[0];target=policy.free_chip_slot(region,name)
    source_support=policy.d['initial_storage'].get(name)
    if not source_support or not policy.contact(name,source_support):
        raise ToolExecutionError('C423 next blue lacks actual original source support')
    remember_freed_source_rail(policy,'blue_supply_3')
    policy.place(name,region['actor'],target)
    state,contacts=policy.snapshot()
    if (any(state[name]['grasp'])or frozenset((name,region['actor']))not in contacts
            or not all(_inside(policy,region,n)for n in [*completed,name])):
        raise ToolExecutionError('C423 next blue lacks actual original cell support/containment')
    return dict(local_completed=True,operations=policy.operations,placed_actor=name,
                original_region=region['id'],actions=policy.c.steps-policy.start)
