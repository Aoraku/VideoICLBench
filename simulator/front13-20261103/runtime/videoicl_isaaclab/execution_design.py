"""Versioned execution specifications; never mutate an existing assignment.

The source catalog is private: only public_task_assignment / public_metadata
may be exposed to the policy. Exporting a contract is not physical acceptance.
"""
from copy import deepcopy
from functools import lru_cache
import hashlib
import json
from pathlib import Path

REVISION_V2 = 'embodied50-execution-v2-20261102'
REVISION_V3 = 'embodied50-execution-v3-20261102'
REVISION = REVISION_V3
SUPPORTED_REVISIONS = (REVISION_V2, REVISION_V3)
ROOTS = {REVISION_V2:Path(__file__).resolve().parents[1]/'execution-design-v2',
         REVISION_V3:Path(__file__).resolve().parents[1]/'execution-design-v3'}
ROOT = ROOTS[REVISION]
WORKFLOW_TASKS = frozenset(('E01', 'E09', 'E17', 'E20', 'E39'))


@lru_cache(maxsize=2)
def _catalog(revision=REVISION):
    if revision not in SUPPORTED_REVISIONS:raise ValueError('Unsupported execution-design revision: '+str(revision))
    root=ROOTS[revision]
    value = json.loads((root / 'catalog.private.json').read_bytes())
    if hashlib.sha256((root / 'source.md').read_bytes()).hexdigest() != value['source_sha256']:
        raise ValueError('Execution-design source checksum mismatch')
    if value['revision'] != revision or len(value['tasks']) != 50:
        raise ValueError('Execution-design revision mismatch')
    return value


def metadata(task,revision=None):
    """Private authoring/evaluation metadata, including local rule evidence."""
    for item in _catalog(REVISION if revision is None else revision)['tasks']:
        if item['id'] == task:
            return deepcopy(item)
    raise ValueError('Unknown execution-design task: ' + str(task))


def source_sha256(revision=None):
    return _catalog(REVISION if revision is None else revision)['source_sha256']


def public_task_assignment(task,revision=None):
    """The complete public goal; identical for ABC, with no private rule answer."""
    return metadata(task,revision)['public_goal']


def public_metadata(task,revision=None):
    item = metadata(task,revision)
    keys=('id', 'title', 'difficulty', 'support_mask', 'main_condition', 'public_goal')
    if 'environment_base' in item:keys+=('environment_base',)
    return {k: deepcopy(item[k]) for k in keys}


def build_task_contract(task, variant, seed, condition=None,revision=None):
    """Produce a fresh private contract for a supported R/I/E condition.

    Identity is revision-specific. I and E share semantic_input_identity while
    E has a distinct environment identity. Physical adapters must implement the
    declared input changes and pass acceptance before a model may be admitted.
    """
    revision=REVISION if revision is None else revision
    item = metadata(task,revision)
    if variant not in ('A', 'B', 'C') or type(seed) is not int or seed < 0:
        raise ValueError('Invalid variant or seed')
    condition = item['main_condition'] if condition is None else condition
    if condition not in item['support_mask']:
        raise ValueError(f'{task} does not support {condition}; supports {item["support_mask"]}')
    def digest(value):
        return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':')).encode()).hexdigest()
    # R has no new semantic seed: seed affects rendering only. No G0/G1/G2 alias.
    base=item.get('environment_base','I')
    reproduce=condition=='R' or (condition=='E' and base=='R')
    semantic_input = dict(revision=revision, task=task, family='R' if reproduce else 'IE', input_seed=None if reproduce else seed)
    assignment = dict(revision=revision, task=task, variant=variant, seed=seed, condition=condition,
                      source_sha256=_catalog(revision)['source_sha256'])
    identity = digest(assignment)
    contract=dict(task=task, variant=variant, seed=seed, title=item['title'], instruction=item['public_goal'],
                execution_design=dict(**assignment, difficulty=item['difficulty'], support_mask=item['support_mask'],
                    assignment_identity_sha256=identity, semantic_input_identity=digest(semantic_input),
                    environment_identity=digest(dict(semantic_input, environment='paired_alternative' if condition == 'E' else 'demonstration_environment')),
                    input_change_description=item['input_change_description'],
                    physics_acceptance_required=True, physics_acceptance_status='pending'),
                local_demo=deepcopy(next(v for v in item['local_demo_variants'] if v['variant'] == variant)),
                rule_qa=dict(local_rule_unchanged=True, question_bank='embodied-rule-qa-v1',
                    assignment_identity_sha256=identity, fresh_first_answer_required=True, reuse_previous_assignment_answer=False),
                workflow=deepcopy(item['workflow']), acceptance=deepcopy(_catalog(revision)['acceptance']),
                demo_quality=deepcopy(item['demo_quality']))
    if revision==REVISION_V3:
        contract['execution_design'].update(environment_base=base,
            paired_input_identity=digest(dict(semantic_input,variant=variant)),
            pairing_invariants=deepcopy(item['environment_pairing']['invariants']),
            allowed_environment_changes=deepcopy(item['environment_pairing']['allowed_changes']),
            environment_changes=[],pairing_verification='pending_native_adapter_measurement')
    return contract


def export_task_packages(destination, tasks=None, seeds=(0, 1, 2), conditions=None,revision=None):
    """Export new versioned packages exclusively; never overwrite old tasks.

    This is authoring only, with no deployment, process start, or model admission.
    ``conditions=None`` uses each task's designated main condition.
    """
    destination = Path(destination)
    revision=REVISION if revision is None else revision
    tasks = list(tasks) if tasks is not None else [t['id'] for t in _catalog(revision)['tasks']]
    seeds = list(seeds)
    contracts = []
    for task in tasks:
        selected = [metadata(task,revision)['main_condition']] if conditions is None else list(conditions)
        for condition in selected:
            for seed in seeds:
                for variant in 'ABC':
                    contracts.append(build_task_contract(task, variant, seed, condition,revision=revision))
    if len({c['execution_design']['assignment_identity_sha256'] for c in contracts}) != len(contracts):
        raise ValueError('Duplicate exported assignments')
    if destination.exists():
        raise FileExistsError('A new export directory is required')
    destination.mkdir(parents=True)
    records = []
    for c in contracts:
        d = c['execution_design']; name = f'{c["task"]}-{c["variant"]}-{d["condition"]}-seed{c["seed"]}'
        room = destination / name; room.mkdir()
        public = dict(revision=revision, task=c['task'], title=c['title'], instruction=c['instruction'],
                      assignment_identity_sha256=d['assignment_identity_sha256'])
        (room / 'task.public.json').write_text(json.dumps(public, ensure_ascii=False, indent=2) + '\n')
        private = room / 'execution.private.json'
        private.write_text(json.dumps(c, ensure_ascii=False, indent=2) + '\n'); private.chmod(0o600)
        records.append(dict(path=name, task=c['task'], variant=c['variant'], seed=c['seed'], condition=d['condition'],
                            assignment_identity_sha256=d['assignment_identity_sha256'], contract_sha256=hashlib.sha256(private.read_bytes()).hexdigest()))
        if revision==REVISION_V3:records[-1].update({k:deepcopy(d[k]) for k in ('environment_base','paired_input_identity','pairing_invariants','allowed_environment_changes','environment_changes','pairing_verification')})
    manifest = dict(revision=revision, source_sha256=_catalog(revision)['source_sha256'], model_launch_enabled=False,
                    physics_acceptance_status='pending', assignments=records)
    (destination / 'manifest.json').write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + '\n')
    return manifest
