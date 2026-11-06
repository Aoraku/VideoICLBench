"""Exhaustive E01-E50 native-adapter selection; registration is not scene proof."""
from .realworld_native_evidence import NativeTaskEvaluator, SUPPORTED as RIGID
from .realworld_mechanism_evidence import MechanismTaskEvaluator, SUPPORTED as MECHANISM
from .realworld_tool_evidence import ToolTaskEvaluator, SUPPORTED as TOOL
from .realworld_structural_evidence import StructuralTaskEvaluator, SUPPORTED as STRUCTURAL
from .realworld_observation import RealWorldEvaluator
from .realworld_tool_expert import solve_tool
from .realworld_structural_expert import solve_structural
from .realworld_mechanism_expert import solve_mechanism

ADAPTERS={}
for tasks,implementation in ((RIGID,NativeTaskEvaluator),(MECHANISM,MechanismTaskEvaluator),(TOOL,ToolTaskEvaluator),(STRUCTURAL,StructuralTaskEvaluator)):
    for task in tasks:
        if task in ADAPTERS:raise RuntimeError('Ambiguous native task adapter: '+task)
        ADAPTERS[task]=implementation
if set(ADAPTERS)!={f'E{i:02}' for i in range(1,51)}:
    raise RuntimeError('Native adapter registry does not cover the frozen E01-E50 panel')


def adapter_class(task,*,has_semantic=True):
    if task not in ADAPTERS:raise NotImplementedError(str(task)+': outside frozen E01-E50 native panel')
    if task in ('E05','E32') and not has_semantic:return RealWorldEvaluator
    return ADAPTERS[task]


def create_evaluator(spec):
    if spec.get('execution_design'):
        from .execution_design import SUPPORTED_REVISIONS, WORKFLOW_TASKS
        if spec['execution_design'].get('revision') not in SUPPORTED_REVISIONS:
            raise ValueError('Unknown execution-design revision')
        if spec['id'] in WORKFLOW_TASKS:
            from .execution_design_evidence import ExecutionDesignEvaluator
            return ExecutionDesignEvaluator(spec)
    return adapter_class(spec['id'],has_semantic=bool(spec.get('semantic')))(spec)

# Expert policies are deliberately narrower than the native evaluator panel:
# an adapter can validate a user episode without pretending that a private
# demonstration controller exists. Missing policies fail explicitly.
EXPERTS={task:solve_structural for task in STRUCTURAL}
EXPERTS.update({task:solve_tool for task in TOOL})
EXPERTS.update({task:solve_mechanism for task in MECHANISM})

def expert_policy(task):
    try:return EXPERTS[task]
    except KeyError as exc:raise NotImplementedError(f'{task}: no private public-action expert policy') from exc


__all__=['ADAPTERS','EXPERTS','adapter_class','create_evaluator','expert_policy']
