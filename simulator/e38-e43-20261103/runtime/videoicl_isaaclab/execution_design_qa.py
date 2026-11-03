"""Offline new-revision QA preparation and immutable SDK export. No API calls."""
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import shutil

from .execution_design import REVISION,REVISION_V2,REVISION_V3,SUPPORTED_REVISIONS,WORKFLOW_TASKS,build_task_contract,metadata

RUNTIME=Path(__file__).parents[1]


def sha(path):
    h=hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda:stream.read(1024*1024),b''):h.update(block)
    return h.hexdigest()


def prepare_assignment(task,variant,seed,condition,mode,*,bank_dir,media_path=None,review=None,revision=None):
    revision=REVISION if revision is None else revision
    if mode not in ('text_rule','real','sim'):raise ValueError('Explicit text_rule/real/sim input required')
    if revision==REVISION_V2 and (task not in WORKFLOW_TASKS or condition not in ('I','E')):
        raise ValueError('Legacy v2 QA export supports workflow I/E only')
    contract=build_task_contract(task,variant,seed,condition,revision=revision)
    quality=contract['demo_quality'].get(task+'-'+variant)
    if revision==REVISION_V3 and quality and mode!='text_rule':
        r=review or {}
        if not (r.get('incomplete_supervision_confirmed') is True and r.get('reviewer') and r.get('evidence')):
            raise ValueError('Incomplete source demo requires explicit supervision confirmation: '+task+'-'+variant)
    bank=json.loads((Path(bank_dir)/'questions.json').read_bytes())
    keys=json.loads((Path(bank_dir)/'answer_key.private.json').read_bytes())
    q=next(q for q in bank['questions'] if q['task_id']==task)
    key=next(q for q in keys['questions'] if q['task_id']==task)
    if bank['bank_version']!=keys['bank_version'] or q['question_id']!=key['question_id'] or set(q['options'])!=set('ABCD'):
        raise ValueError('Invalid reviewed four-option question bank')
    source=key['sources'][variant]
    text=contract['local_demo']['observed_demo']
    digest=hashlib.sha256(text.encode()).hexdigest() if mode=='text_rule' else sha(media_path)
    if mode=='real' and digest!=source['sha256']:
        r=review or {}
        if not (r.get('status')=='reviewed' and r.get('task_id')==task and r.get('variant')==variant and
                r.get('sha256')==digest and r.get('source_sha256')==source['sha256'] and
                r.get('rule_preserving_transcode') is True and r.get('reviewer') and r.get('evidence')):
            raise ValueError('Real media lacks matching reviewed source/transcode provenance')
    if mode=='sim':
        r=review or {}
        if not (r.get('status')=='reviewed' and r.get('task_id')==task and r.get('variant')==variant and
                r.get('sha256')==digest and r.get('rule_matches_source') is True and r.get('reviewer') and r.get('evidence')):
            raise ValueError('Sim local-rule semantic review missing; engineering full workflows forbidden')
    input_mode='text' if mode=='text_rule' else mode
    identity=hashlib.sha256((contract['execution_design']['assignment_identity_sha256']+':'+input_mode).encode()).hexdigest()
    packet={k:deepcopy(q[k]) for k in ('question_id','prompt','options')}
    packet['response_instruction']='只提交一个大写选项字母：A、B、C或D。'
    assignment=dict(schema='rule-qa-execution-assignment-v3' if revision==REVISION_V3 else 'rule-qa-execution-assignment-v2',protocol='qa_then_act',task_id=task,variant=variant,
        seed=seed,revision=revision,generalization_condition=condition,assignment_identity_sha256=identity,
        source=mode,source_sha256=digest,packet=packet,
        provenance=dict(bank_version=bank['bank_version'],bank_sha256=sha(Path(bank_dir)/'questions.json'),
                        source_video_sha256=source['sha256'],demo_scope='local_rule_only'))
    grading=dict(assignment_identity_sha256=identity,question_id=q['question_id'],task_id=task,variant=variant,
        revision=revision,generalization_condition=condition,input_mode=mode,source_sha256=digest,
        correct_option=key['answers'][variant])
    if revision==REVISION_V3:
        assignment.update(environment_base=contract['execution_design']['environment_base'],
            paired_input_identity=hashlib.sha256((contract['execution_design']['paired_input_identity']+':'+input_mode).encode()).hexdigest())
        grading.update(environment_base=assignment['environment_base'],paired_input_identity=assignment['paired_input_identity'])
        if quality:assignment['provenance']['demo_quality']=quality
    return assignment,grading


def write_assignment(task_dir,assignment):
    """Future public task export only; private answer key is not accepted."""
    if set(assignment['packet'])!={'question_id','prompt','options','response_instruction'}:
        raise ValueError('Public packet must not include answers')
    path=Path(task_dir)/'environment'/'rule-qa'/(assignment['source']+'.json')
    path.parent.mkdir(parents=True,exist_ok=True)
    with path.open('x') as stream:json.dump(assignment,stream,ensure_ascii=False,indent=2)
    return path


def bind_native_spec(spec,assignments):
    """Bind a future three-input task package without rewriting its physics."""
    result=deepcopy(spec);identities={};paired={};revisions=set()
    if not assignments:raise ValueError('At least one prepared assignment required')
    conditions=set()
    for assignment in assignments:
        if assignment.get('revision') not in SUPPORTED_REVISIONS or any(assignment[k]!=spec[k] for k in ('task_id','variant','seed')):
            raise ValueError('Native package and QA assignment identity mismatch')
        mode=assignment['source']
        if mode in identities:raise ValueError('Duplicate input mode')
        identities[mode]=assignment['assignment_identity_sha256'];conditions.add(assignment['generalization_condition'])
        revisions.add(assignment['revision'])
        if assignment['revision']==REVISION_V3:paired[mode]=assignment['paired_input_identity']
    if len(conditions)!=1:raise ValueError('A native task cannot mix I/E input conditions')
    if len(revisions)!=1:raise ValueError('A native task cannot mix execution revisions')
    revision=revisions.pop()
    result.update(task_revision=revision,generalization_condition=conditions.pop(),qa_assignment_identities=identities)
    if revision==REVISION_V3:
        item=metadata(spec['task_id'],revision)
        result.update(environment_base=item['environment_base'],execution_support_mask=item['support_mask'],qa_paired_input_identities=paired)
    return result


def export_sdk(destination,*,source_sdk=None,revision=None):
    """Actually apply overlay in a new SDK tree; never modify old deployment."""
    revision=REVISION if revision is None else revision
    if revision not in SUPPORTED_REVISIONS:raise ValueError('Unsupported SDK revision')
    dest=Path(destination)
    if dest.exists():raise FileExistsError('New SDK export directory required')
    source=Path(source_sdk) if source_sdk else RUNTIME.parent/'deployment/inference450-remaining300-qa-20261102/VideoICLBench/packages/sdk'
    if not (source/'vic_sdk/embodied_gui_mcp.py').is_file():raise ValueError('Full GUI SDK source required')
    shutil.copytree(source,dest,ignore=shutil.ignore_patterns('__pycache__','*.pyc','.pytest_cache','*.egg-info'))
    overlay=RUNTIME/'sdk-overlays'/('execution-design-v3' if revision==REVISION_V3 else 'execution-design-v2')/'vic_sdk/rule_qa_gate.py'
    shutil.copyfile(overlay,dest/'vic_sdk/rule_qa_gate.py')
    files={str(p.relative_to(dest)):sha(p) for p in sorted(dest.rglob('*')) if p.is_file()}
    receipt=dict(revision=revision,source_sdk=str(source),overlay_applied=True,files=files,
                 model_calls=0,simulation_starts=0,model_launch_enabled=False)
    (dest/'execution-qa-export.private.json').write_text(json.dumps(receipt,indent=2)+'\n')
    return receipt


def export_public_task(destination,*,task,variant,seed,condition,public_task,assignments,media=None,controls_path=None,revision=None):
    """Write the SDK-consumed native.json and QA packets, without private keys.

    This is an offline input package. It provides no controller credentials,
    owner process or model permission. The release native gate remains separate.
    """
    revision=REVISION if revision is None else revision
    dest=Path(destination)
    if dest.exists():raise FileExistsError('Fresh public task directory required')
    item=metadata(task,revision)
    if condition not in item['support_mask']:raise ValueError('Unsupported task condition')
    if public_task.get('task')!=task or public_task.get('revision')!=revision:raise ValueError('Public task revision mismatch')
    controls=Path(controls_path) if controls_path else RUNTIME.parent/'deployment/inference450-remaining300-qa-20261102/tasks/embodied-e09-b/environment/gui-controls.md'
    instruction=public_task['title']+'\n\n'+public_task['instruction']+'\n'
    spec=dict(schema_version=1,kind='embodied',backend='videoicl-native-slurm',task_id=task,variant=variant,seed=seed,
        action_interface='bounded_dual_arm_tokens_v1',agent_interaction='gui_only',agent_protocol='roboprobe_gui_v1',
        instruction_sha256=hashlib.sha256(instruction.encode()).hexdigest(),
        gui_controls=dict(path='gui-controls.md',sha256=sha(controls)),
        native_interaction_validated=False,model_launch_enabled=False,readiness='native_acceptance_pending')
    for a in assignments:
        if a['generalization_condition']!=condition or a['revision']!=revision:raise ValueError('Condition/revision assignment mismatch')
        if a['source']!='text_rule':
            entry=(media or {}).get(a['source'])
            if not entry or sha(entry['path'])!=a['source_sha256']:raise ValueError('Verified assigned media required')
    spec=bind_native_spec(spec,assignments)
    (dest/'environment').mkdir(parents=True)
    (dest/'instruction.md').write_text(instruction)
    shutil.copyfile(controls,dest/'environment/gui-controls.md')
    for a in assignments:
        write_assignment(dest,a)
        if a['source']!='text_rule':
            source=Path(media[a['source']]['path']);relative='environment/media/'+a['source']+source.suffix
            target=dest/relative;target.parent.mkdir(exist_ok=True)
            # Copy bytes rather than symlinking private/shared input trees.
            shutil.copyfile(source,target)
            spec['demo' if a['source']=='real' else 'demo_sim']=dict(path=relative,sha256=a['source_sha256'])
    spec['input_conditions']=[a['source'] for a in assignments]
    (dest/'environment/native.json').write_text(json.dumps(spec,ensure_ascii=False,indent=2)+'\n')
    return spec
