"""Public instruction selector for explicitly opted-in inference bindings."""

def public_instruction(binding, fallback):
    metadata=binding.get('inference_generalization')
    if metadata is None:return fallback
    if (not isinstance(metadata,dict) or metadata.get('schema')!='videoicl-inference-task-v1'
        or metadata.get('group') not in ('G1','G2') or metadata.get('demo_unchanged') is not True):
        raise ValueError('Invalid inference generalization contract')
    instruction=metadata.get('instruction')
    if not isinstance(instruction,str) or not instruction.strip():raise ValueError('Inference prompt required')
    if any(x in instruction for x in ('**A：','**B：','**C：','验收边界')):raise ValueError('Private answer table in public instruction')
    return instruction


def e24_yarn_rule(spec):
    """Select only the explicitly compiled E24 G1 schema, never by object name."""
    metadata=spec.get('inference_generalization',{})
    return (spec.get('id')=='E24' and metadata.get('schema')=='videoicl-inference-task-v1'
            and metadata.get('group')=='G1' and metadata.get('demo_unchanged') is True
            and metadata.get('rule_profile')=='e24-yarn-insertion-v1')
