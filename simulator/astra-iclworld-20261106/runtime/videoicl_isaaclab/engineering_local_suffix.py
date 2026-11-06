"""Fixed, engineering-only suffixes for the E26-E37 repair work.

Native startup restoration and readback are handled by engineering_checkpoint;
this module dispatches only a named stage, never a whole-source acceptance.
"""
import importlib

ENTRIES={
    'E28':{'e28_insert':('execution_design_tools_debug','run_e28')},
    'E31':{'e31_release':('execution_design_e31_debug','run'),
           'e31_flip':('execution_design_e31_debug','run_flip'),
           'e31_source_tail':('execution_design_e31_source_tail','run'),
           'e31_source_clear':('execution_design_e31_source_tail','run_clear')},
    'E34':{'e34_acquire':('execution_design_e34_debug','run'),
           'e34_narrow':('execution_design_e34_acquire','run_debug'),
           'e34_place':('execution_design_e34b_place','run')},
    'E37':{'e37_orient':('execution_design_tools_debug','run_e37'),
           'e37_source_tail':('execution_design_e37_source_tail','run')},
}


def solve(author,checkpoint,context):
    task=author.scene.spec['id'];entry=context.get('entry')
    if task not in ENTRIES or entry not in ENTRIES[task]:
        raise ValueError('Explicit supported local engineering segment required')
    if not getattr(author.c,'_engineering_diagnostic_only',False):
        raise ValueError('Local suffix requires admitted native checkpoint restoration')
    if not author.control_report.get('engineering_reference_only'):
        raise ValueError('Local suffix requires engineering author')
    if checkpoint.get('diagnostic_only') is not True:
        raise ValueError('Checkpoint must remain diagnostic-only')
    parameters=dict(context.get('parameters',{}))
    signs=context.get('generated_axis_signs')
    if not isinstance(signs,dict) or set(signs)!=set(author.scene.robots):
        raise ValueError('Recovered calibrated public-axis signs required')
    normalized={side:{int(k):v for k,v in axes.items()}for side,axes in signs.items()}
    if any(set(axes)!={0,1,2}or any(v not in(-1,1)for v in axes.values())for axes in normalized.values()):
        raise ValueError('Invalid recovered public-axis signs')
    author.generated_axis_signs=normalized
    if context.get('carried_payload') is not None:
        name,side=context['carried_payload']
        if name not in author.scene.objects or side not in author.scene.robots:
            raise ValueError('Invalid reconstructed carried actor')
        author.carried_payload=(name,side)
    module_name,function=ENTRIES[task][entry]
    module=importlib.import_module('.'+module_name,__package__)
    before=author.c.steps
    old=getattr(author,'_execution_design_reference_authorized',False)
    author._execution_design_reference_authorized=True
    try:
        payload=(dict(checkpoint,context={**checkpoint.get('context',{}),**parameters})
                 if task in ('E28','E37') else parameters)
        result=getattr(module,function)(author,payload)
    finally:
        author._execution_design_reference_authorized=old
    if not isinstance(result,dict):raise ValueError('Local engineering segment must return measured result')
    return dict(result,task=task,entry=entry,local_debug_only=True,
        source_initial_episode=False,native_task_acceptance=False,
        local_public_actions=author.c.steps-before,
        source_checkpoint_actions=checkpoint['source']['steps'])
