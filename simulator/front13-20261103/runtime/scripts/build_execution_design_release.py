#!/usr/bin/env python3
"""Build an isolated, model-disabled execution-v2 release and verify native gates."""
from pathlib import Path
import argparse
import hashlib
import json
import shutil
import sys
import xml.etree.ElementTree as ET

RUNTIME = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RUNTIME))
from videoicl_isaaclab.execution_design import REVISION, REVISION_V2, REVISION_V3, SUPPORTED_REVISIONS, WORKFLOW_TASKS, build_task_contract, metadata, source_sha256
from videoicl_isaaclab.realworld_scenes import load as load_scene

CONTROLS = ('positive', 'wrong_members', 'wrong_destination', 'wrong_rule', 'not_released')
SOURCE_PATTERNS = ('videoicl_isaaclab/*.py', 'execution-design-v2/*','execution-design-v3/*',
                   'configs/realworld50_catalog.json', 'configs/tasks.json',
                   'configs/embodiments/*.json', 'scripts/build_execution_design_release.py',
                   'sdk-overlays/execution-design-v2/vic_sdk/*.py',
                   'sdk-overlays/execution-design-v3/vic_sdk/*.py',
                   'tests/test_execution_design_qa_integration.py',
                   'scripts/prepare_execution_design_qa.py',
                   'scripts/probe_realworld_room_pool.py', 'scripts/serve_realworld_room_pool.py')


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def write(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n')


def source_hashes(runtime=RUNTIME):
    return {str(p.relative_to(runtime)): sha(p) for pattern in SOURCE_PATTERNS for p in sorted(runtime.glob(pattern)) if p.is_file()}


def build_release(destination, *, bindings=None, seeds=(4201, 4202, 4203),qa_preparation=None,tasks=None,revision=None):
    revision=REVISION if revision is None else revision
    if revision not in SUPPORTED_REVISIONS:raise ValueError('Unsupported release revision')
    all_tasks=[f'E{i:02}'for i in range(1,51)]
    selected=sorted((all_tasks if revision==REVISION_V3 else WORKFLOW_TASKS) if tasks is None else list(tasks))
    if not selected or len(set(selected))!=len(selected) or not set(selected)<=set(all_tasks):raise ValueError('Unique known release tasks required')
    dest = Path(destination)
    if dest.exists():raise FileExistsError('New release directory required; existing campaigns are immutable')
    if len(set(seeds)) < 3 or any(type(s) is not int or s < 0 for s in seeds):raise ValueError('At least three distinct nonnegative seeds required')
    binding_path = Path(bindings) if bindings else RUNTIME/'configs/realworld_full50_bindings.json'
    original = json.loads(binding_path.read_bytes())
    if original.get('execution_design') or any(original['tasks'][t].get('inference_generalization') for t in WORKFLOW_TASKS):
        raise ValueError('Canonical source bindings required')
    dest.mkdir(parents=True)
    from videoicl_isaaclab.execution_design_qa import export_sdk
    sdk_receipt=export_sdk(dest/'sdk',revision=revision)
    # Bundle only source/config files; reviewed asset binaries remain separately
    # hash-verified by the source resolver and native preflight.
    hashes = source_hashes()
    for rel in hashes:
        target=dest/'runtime'/rel;target.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(RUNTIME/rel,target)
    qa_root=RUNTIME.parent/'evaluation'/'rule_qa'
    if not qa_root.is_dir():qa_root=RUNTIME.parent/'qa'
    qa_hashes={}
    for name in ('questions.json','answer_key.private.json'):
        target=dest/'qa'/name;target.parent.mkdir(parents=True,exist_ok=True)
        shutil.copyfile(qa_root/name,target);qa_hashes[name]=sha(target)
    qa_bank=json.loads((dest/'qa/questions.json').read_bytes())
    qa_keys=json.loads((dest/'qa/answer_key.private.json').read_bytes())
    if qa_bank['bank_version']!=qa_keys['bank_version']:raise ValueError('QA bank/key mismatch')
    questions={q['task_id']:q for q in qa_bank['questions']}
    answers={q['task_id']:q for q in qa_keys['questions']}
    loader = dest/'load_case.py'
    loader.write_text("""from pathlib import Path
import argparse,json,sys
root=Path(__file__).resolve().parent
sys.path.insert(0,str(root/'runtime'))
from videoicl_isaaclab.realworld_scenes import load
p=argparse.ArgumentParser();p.add_argument('case_id');p.add_argument('--offline',action='store_true');a=p.parse_args()
m=json.loads((root/'manifest.private.json').read_text());c=next(c for c in m['cases'] if c['case_id']==a.case_id)
s=load(c['task'],c['variant'],c['seed'],root/c['binding_file'],verify_files=not a.offline)
print(json.dumps(dict(case_id=c['case_id'],objects=len(s['objects']),revision=s['execution_design']['revision'],source_files_verified=s['source_files_verified'],release_ready=s['release_ready'])))
""")
    cases=[]
    for condition in ('R','I','E'):
        binding=json.loads(json.dumps(original));binding['execution_design']={'revision':revision,'condition':condition}
        bp=dest/'bindings'/f'{condition}.private.json';write(bp,binding)
        for task in selected:
            if condition not in metadata(task,revision)['support_mask']:continue
            for variant in 'ABC':
                for seed in seeds:
                    contract=build_task_contract(task,variant,seed,condition,revision=revision)
                    key=f'{task}-{variant}-{condition}-seed{seed}';case_dir=dest/'cases'/key
                    write(case_dir/'execution.private.json',contract)
                    # Persist the exact seed-specific public order used by the
                    # native room. The private rule contract is never a public
                    # task prompt, and a generic prompt omitting the order is
                    # insufficient for selecting the destination or batch.
                    scene=load_scene(task,variant,seed,bp,verify_files=False)
                    public={'task':task,'title':scene['title'],'instruction':scene['instruction'],
                            'revision':revision,'order':dict(scene.get('public_order',{}))}
                    write(case_dir/'task.public.json',public)
                    inputs={};input_hashes={}
                    for mode in ('text','real','sim'):
                        identity=hashlib.sha256((contract['execution_design']['assignment_identity_sha256']+':'+mode).encode()).hexdigest()
                        # Text contains the local rule only. Real/sim remain local
                        # demo input, never a demonstration of the full workflow.
                        question=questions[task];keyrow=answers[task]
                        packet_id='qp_'+hashlib.sha256((qa_bank['bank_version']+'\0'+identity).encode()).hexdigest()[:20]
                        packet=dict(packet_id=packet_id,question_id=question['question_id'],prompt=question['prompt'],
                            options=question['options'],response_instruction='只输出一个大写选项字母：A、B、C或D。')
                        grading=dict(packet_id=packet_id,question_id=question['question_id'],task_id=task,variant=variant,
                            assignment_identity_sha256=identity,condition=condition,input_mode=mode,
                            correct_option=keyrow['answers'][variant],source_demo_sha256=keyrow['sources'][variant]['sha256'])
                        value={'input_condition':mode,'assignment_identity_sha256':identity,'public_task':public,
                               'rule_qa':dict(contract['rule_qa'],assignment_identity_sha256=identity),
                               'qa_public_packet':packet,'qa_grading_private':grading,
                               'local_demo_source':contract['local_demo'],'demo_scope':'local_rule_only',
                               'source_media_rebinding_required':mode=='sim','model_launch_enabled':False}
                        if mode=='text':value['text_rule']=contract['local_demo']['observed_demo']
                        ip=case_dir/f'input-{mode}.private.json'
                        write(ip,value);inputs[mode]=f'cases/{key}/input-{mode}.private.json';input_hashes[mode]=sha(ip)
                    cases.append({'case_id':key,'task':task,'variant':variant,'seed':seed,'condition':condition,
                                  'assignment_identity_sha256':contract['execution_design']['assignment_identity_sha256'],
                                  'binding_file':str(bp.relative_to(dest)),'binding_sha256':sha(bp),
                                  'contract_file':f'cases/{key}/execution.private.json','contract_sha256':sha(case_dir/'execution.private.json'),
                                  'public_task_file':f'cases/{key}/task.public.json','public_task_sha256':sha(case_dir/'task.public.json'),
                                  'input_specs':inputs,'input_spec_hashes':input_hashes,'media_bindings':{'real':None,'sim':None},
                                  'native_controls':{control:None for control in CONTROLS}})
                    if revision==REVISION_V3:
                        cases[-1]['declared_pairing']={k:contract['execution_design'][k] for k in ('environment_base','paired_input_identity','pairing_invariants','allowed_environment_changes')}
                        cases[-1]['native_adapter_pairing']={k:scene['execution_design'].get(k) for k in ('environment_base','paired_input_identity','pairing_invariants','environment_changes','pairing_verification','paired_physical_input_sha256','applied_input_changes')}
    coverage=[dict(task=t,support_mask=metadata(t,revision)['support_mask'],environment_base=metadata(t,revision).get('environment_base'),
                   included=t in selected,native_acceptance='pending',required_cases=len(metadata(t,revision)['support_mask'])*3*len(seeds),
                   required_controls=len(metadata(t,revision)['support_mask'])*3*len(seeds)*len(CONTROLS)) for t in all_tasks]
    manifest={'schema':'videoicl-execution-release-v3' if revision==REVISION_V3 else 'videoicl-execution-v2-release-v1','revision':revision,'model_launch_enabled':False,
              'native_acceptance':'pending','asset_validation':'pending','source_hashes':hashes,
              'canonical_bindings_sha256':sha(binding_path),'qa_hashes':qa_hashes,'qa_runtime_acceptance':None,
              'sdk_files':sdk_receipt['files'],'sdk_overlay_applied':True,'cases':cases,
              'scope':'full50' if selected==all_tasks else 'engineering_subset','selected_tasks':selected,'coverage':coverage,
              'source_document_sha256':source_sha256(revision),'full50_ready':False,
              'required_full50_cases':sum(r['required_cases']for r in coverage),'required_full50_controls':sum(r['required_controls']for r in coverage),
              'asset_note':'Reviewed upstream asset files must resolve and hash-validate on the native worker.'}
    write(dest/'manifest.private.json',manifest)
    if qa_preparation is not None:
        install_prepared_qa(dest,qa_preparation)
        manifest=json.loads((dest/'manifest.private.json').read_bytes())
    for p in dest.rglob('*.private.json'):p.chmod(0o600)
    return manifest


def install_prepared_qa(release,preparation):
    """Bind verified existing local media and executed QA tests into a new release."""
    release=Path(release);preparation=Path(preparation)
    manifest=json.loads((release/'manifest.private.json').read_bytes())
    revision=manifest['revision']
    prepared=json.loads((preparation/'preparation.private.json').read_bytes())
    if manifest.get('model_launch_enabled') is not False:raise ValueError('QA binding requires model-disabled release')
    if prepared.get('revision')!=revision or prepared.get('sdk_files')!=manifest.get('sdk_files'):raise ValueError('Prepared SDK differs from exported SDK')
    test=prepared['integration_test'];testfile=_local(preparation,test['path'])
    if sha(testfile)!=test['sha256'] or test.get('passed') is not True:raise ValueError('QA integration tests not verified')
    test_source='tests/test_execution_design_qa_integration.py'
    if test.get('source_sha256')!=manifest['source_hashes'].get(test_source):raise ValueError('QA test source changed')
    _validate_qa_junit(testfile,revision)
    qa_dir=release/'qa';test_target=qa_dir/'integration-tests.xml';shutil.copyfile(testfile,test_target)
    receipt=dict(schema='videoicl-execution-v2-qa-gate-v1',revision=revision,source_hashes=manifest['source_hashes'],
        qa_hashes=manifest['qa_hashes'],conditions=['R','I','E'] if revision==REVISION_V3 else ['I','E'],input_modes=['text','real','sim'],
        media_delivery_before_question=True,first_answer_immutable=True,action_blocked_before_answer=True,
        no_answer_key_in_public_mount=True,fresh_assignment_resume_checked=True,
        test_artifact=dict(path=str(test_target.relative_to(release)),sha256=sha(test_target),source_sha256=test['source_sha256']))
    rp=qa_dir/'runtime-acceptance.private.json';write(rp,receipt)
    manifest['qa_runtime_acceptance']=dict(path=str(rp.relative_to(release)),sha256=sha(rp))
    by_key={(r['task'],r['variant'],r['mode']):r for r in prepared['media'] if r.get('status')=='ready'}
    from videoicl_isaaclab.execution_design_qa import prepare_assignment,write_assignment,bind_native_spec,export_public_task
    for case in manifest['cases']:
        assignments=[];package_media={}
        for mode in ('text','real','sim'):
            media=by_key.get((case['task'],case['variant'],mode))
            if mode!='text' and media is None:continue
            source_path=None
            if mode!='text':
                source_path=Path(media['path'])
                if sha(source_path)!=media['sha256']:raise ValueError('Prepared media bytes changed')
                relative='media/'+media['sha256']+source_path.suffix
                target=release/relative;target.parent.mkdir(exist_ok=True)
                if not target.exists():shutil.copyfile(source_path,target)
                package_media[mode]=dict(path=str(target))
                case['media_bindings'][mode]=dict(path=relative,sha256=media['sha256'],task=case['task'],variant=case['variant'],
                    scope='local_rule_only',source_sha256=media['source_sha256'],
                    rule_matches_source_reviewed=mode=='sim',rule_preserving_transcode_reviewed=mode=='real')
            source='text_rule' if mode=='text' else mode
            assignment,_=prepare_assignment(case['task'],case['variant'],case['seed'],case['condition'],source,
                bank_dir=release/'qa',media_path=source_path,review=media.get('review') if media else None,revision=revision)
            case_dir=release/'cases'/case['case_id']
            write_assignment(case_dir,assignment);assignments.append(assignment)
        native=bind_native_spec(dict(task_id=case['task'],variant=case['variant'],seed=case['seed']),assignments)
        write(release/'cases'/case['case_id']/'qa-native-binding.private.json',native)
        package_dir=release/'tasks'/case['case_id']
        export_public_task(package_dir,task=case['task'],variant=case['variant'],seed=case['seed'],condition=case['condition'],
            public_task=json.loads((release/case['public_task_file']).read_bytes()),assignments=assignments,media=package_media,revision=revision)
        case['sdk_task_package']=dict(path=str(package_dir.relative_to(release)),
            files={str(p.relative_to(package_dir)):sha(p) for p in package_dir.rglob('*') if p.is_file()})
    write(release/'manifest.private.json',manifest)


def _local(release, relative):
    p=(release/relative).resolve()
    if not p.is_relative_to(release.resolve()):raise ValueError('Evidence path escapes release')
    return p


def _validate_qa_junit(path,revision=REVISION):
    root=ET.parse(path).getroot();cases=root.findall('.//testcase')
    required={'test_exported_sdk_checks_new_identity_and_real_gui_action_gate':6,
              'test_actual_agent_load_inputs_uses_exported_native_binding':2,
              'test_mcp_service_exposes_qa_without_private_answer':1,
              'test_concurrent_first_answer_and_legacy_assignments_unchanged':1,
              'test_revision_and_private_answer_cannot_bypass_assignment_loader':1}
    if revision==REVISION_V3:required['test_all50_v3_legal_conditions_and_explicit_v2_sdk_compatibility']=1
    if any(c.find(tag) is not None for c in cases for tag in ('error','failure','skipped')):
        raise ValueError('QA integration test failures or skips')
    for prefix,count in required.items():
        if len({c.get('name') for c in cases if c.get('name','').split('[')[0]==prefix})!=count:
            raise ValueError('QA integration test matrix incomplete')


def validate_release(release):
    release=Path(release);manifest=json.loads((release/'manifest.private.json').read_bytes());errors=[]
    revision=manifest.get('revision')
    if revision not in SUPPORTED_REVISIONS:return dict(ready=False,full50_ready=False,errors=['revision_mismatch'])
    all_tasks={f'E{i:02}'for i in range(1,51)};selected=set(manifest.get('selected_tasks',WORKFLOW_TASKS))
    if not selected or not selected<=all_tasks:errors.append('invalid_selected_tasks')
    full_scope=selected==all_tasks and manifest.get('scope')=='full50'
    if not full_scope:errors.append('full50_scope_incomplete')
    if manifest.get('source_document_sha256')!=source_sha256(revision):errors.append('source_document_mismatch')
    if manifest.get('sdk_overlay_applied') is not True or not manifest.get('sdk_files'):errors.append('qa_sdk_overlay_missing')
    for rel,expected_sdk in manifest.get('sdk_files',{}).items():
        p=release/'sdk'/rel
        if not p.is_file() or sha(p)!=expected_sdk:errors.append('sdk_hash_mismatch:'+rel)
    hashes=manifest.get('source_hashes',{})
    if not hashes:errors.append('missing_source_hashes')
    for rel,expected in hashes.items():
        p=release/'runtime'/rel
        if not p.is_file() or sha(p)!=expected:errors.append('source_hash_mismatch:'+rel)
    cases=manifest.get('cases',[])
    qa_bank=qa_keys=None
    try:
        for name in ('questions.json','answer_key.private.json'):
            if sha(release/'qa'/name)!=manifest.get('qa_hashes',{}).get(name):raise ValueError('qa_bank_hash_mismatch')
        qa_bank=json.loads((release/'qa/questions.json').read_bytes())
        qa_keys=json.loads((release/'qa/answer_key.private.json').read_bytes())
        if qa_bank['bank_version']!=qa_keys['bank_version']:raise ValueError('qa_bank_version_mismatch')
    except (OSError,KeyError,TypeError,ValueError) as exc:errors.append(str(exc))
    # The old v1 adapter lacks revision/seed/I/E-specific assignment checks.
    # A fresh runtime must demonstrate its delivery/first-answer/action gate;
    # a copied question bank alone does not prove that integration.
    qa_receipt=manifest.get('qa_runtime_acceptance')
    if not qa_receipt:errors.append('qa_runtime_acceptance_pending')
    else:
        try:
            qp=_local(release,qa_receipt['path'])
            if sha(qp)!=qa_receipt['sha256']:raise ValueError('qa_runtime_receipt_hash_mismatch')
            qr=json.loads(qp.read_bytes())
            if qr.get('schema')!='videoicl-execution-v2-qa-gate-v1' or qr.get('revision')!=revision or qr.get('source_hashes')!=hashes or qr.get('qa_hashes')!=manifest.get('qa_hashes'):raise ValueError('qa_runtime_receipt_identity_mismatch')
            expected_conditions={'R','I','E'}if revision==REVISION_V3 else {'I','E'}
            if set(qr.get('conditions',[]))!=expected_conditions or set(qr.get('input_modes',[]))!={'text','real','sim'}:raise ValueError('qa_runtime_coverage_incomplete')
            if not all(qr.get(k) is True for k in ('media_delivery_before_question','first_answer_immutable','action_blocked_before_answer','no_answer_key_in_public_mount','fresh_assignment_resume_checked')):raise ValueError('qa_runtime_gate_unverified')
            ap=_local(release,qr['test_artifact']['path'])
            if not ap.stat().st_size or sha(ap)!=qr['test_artifact']['sha256']:raise ValueError('qa_runtime_test_artifact_invalid')
            if qr['test_artifact'].get('source_sha256')!=hashes.get('tests/test_execution_design_qa_integration.py'):raise ValueError('qa_runtime_test_source_mismatch')
            _validate_qa_junit(ap,revision)
        except (OSError,KeyError,TypeError,ValueError) as exc:errors.append(str(exc))
    expected={(t,v,c) for t in selected for v in 'ABC' for c in metadata(t,revision)['support_mask']}
    coverage=manifest.get('coverage',[])
    if len(coverage)!=50 or {r.get('task')for r in coverage}!=all_tasks:errors.append('full50_coverage_plan_incomplete')
    for row in coverage:
        if row.get('task') not in all_tasks:continue
        item=metadata(row['task'],revision)
        if row.get('support_mask')!=item['support_mask'] or row.get('environment_base')!=item.get('environment_base') or row.get('included') is not (row['task'] in selected):errors.append('coverage_plan_mismatch:'+row['task'])
    observed={}
    for case in cases:
        key=case['case_id'];observed.setdefault((case['task'],case['variant'],case['condition']),set()).add(case['seed'])
        try:
            bp=_local(release,case['binding_file'])
            if sha(bp)!=case['binding_sha256']:raise ValueError('binding_hash_mismatch')
            contract=json.loads(_local(release,case['contract_file']).read_bytes())
            if sha(_local(release,case['contract_file']))!=case.get('contract_sha256'):raise ValueError('contract_hash_mismatch')
            if contract['execution_design']['assignment_identity_sha256']!=case['assignment_identity_sha256']:raise ValueError('assignment_mismatch')
            if contract!=build_task_contract(case['task'],case['variant'],case['seed'],case['condition'],revision=revision):raise ValueError('contract_content_mismatch')
            public=json.loads(_local(release,case['public_task_file']).read_bytes())
            if sha(_local(release,case['public_task_file']))!=case['public_task_sha256']:raise ValueError('public_task_hash_mismatch')
            scene=load_scene(case['task'],case['variant'],case['seed'],bp,verify_files=False)
            expected_public=dict(task=case['task'],title=scene['title'],instruction=scene['instruction'],revision=revision,order=dict(scene.get('public_order',{})))
            if public!=expected_public:raise ValueError('public_task_content_mismatch')
            if revision==REVISION_V3:
                declared={k:contract['execution_design'][k]for k in ('environment_base','paired_input_identity','pairing_invariants','allowed_environment_changes')}
                if case.get('declared_pairing')!=declared:raise ValueError('declared_environment_pairing_mismatch')
                measured={k:scene['execution_design'].get(k)for k in ('environment_base','paired_input_identity','pairing_invariants','environment_changes','pairing_verification','paired_physical_input_sha256','applied_input_changes')}
                if case.get('native_adapter_pairing')!=measured:raise ValueError('native_adapter_pairing_mismatch')
            if set(case['input_specs'])!={'text','real','sim'}:raise ValueError('input_modes_incomplete')
            if qa_receipt:
                package=case.get('sdk_task_package')
                if not package:raise ValueError('sdk_task_package_missing')
                directory=_local(release,package['path'])
                if any(not _local(directory,r).is_file() or sha(_local(directory,r))!=digest for r,digest in package['files'].items()):raise ValueError('sdk_task_package_hash_mismatch')
                ns=json.loads((directory/'environment/native.json').read_bytes())
                if ns.get('task_revision')!=revision or ns.get('generalization_condition')!=case['condition']:raise ValueError('sdk_task_revision_mismatch')
                if (ns.get('task_id'),ns.get('variant'),ns.get('seed'))!=(case['task'],case['variant'],case['seed']):raise ValueError('sdk_task_native_identity_mismatch')
                instruction=public['title']+'\n\n'+public['instruction']+'\n'
                if (directory/'instruction.md').read_text()!=instruction or ns.get('instruction_sha256')!=hashlib.sha256(instruction.encode()).hexdigest():raise ValueError('sdk_task_instruction_mismatch')
                for mode in ('text','real','sim'):
                    source='text_rule' if mode=='text' else mode
                    if mode!='text' and not case['media_bindings'].get(mode):continue
                    assignment=json.loads((directory/'environment/rule-qa'/f'{source}.json').read_bytes())
                    expected_identity=hashlib.sha256((case['assignment_identity_sha256']+':'+mode).encode()).hexdigest()
                    if assignment.get('assignment_identity_sha256')!=expected_identity or ns.get('qa_assignment_identities',{}).get(source)!=expected_identity:raise ValueError('sdk_task_qa_identity_mismatch')
                    from videoicl_isaaclab.execution_design_qa import prepare_assignment
                    expected_assignment,_=prepare_assignment(case['task'],case['variant'],case['seed'],case['condition'],'text_rule',bank_dir=release/'qa',revision=revision)
                    expected_assignment.update(source=source,assignment_identity_sha256=expected_identity)
                    if revision==REVISION_V3:expected_assignment['paired_input_identity']=hashlib.sha256((contract['execution_design']['paired_input_identity']+':'+mode).encode()).hexdigest()
                    if mode!='text':expected_assignment['source_sha256']=case['media_bindings'][mode]['sha256']
                    if assignment!=expected_assignment:raise ValueError('sdk_task_qa_content_mismatch')
                    if mode!='text':
                        dm=ns.get('demo' if mode=='real' else 'demo_sim',{})
                        if dm.get('sha256')!=expected_assignment['source_sha256'] or sha(_local(directory,dm['path']))!=expected_assignment['source_sha256']:raise ValueError('sdk_task_media_mismatch')
            for mode,relative in case['input_specs'].items():
                ip=_local(release,relative);value=json.loads(ip.read_bytes())
                if sha(ip)!=case.get('input_spec_hashes',{}).get(mode):raise ValueError('input_spec_hash_mismatch:'+mode)
                identity=hashlib.sha256((case['assignment_identity_sha256']+':'+mode).encode()).hexdigest()
                if value.get('assignment_identity_sha256')!=identity or value.get('input_condition')!=mode or value.get('public_task')!=public:raise ValueError('input_identity_or_public_mismatch:'+mode)
                if value.get('rule_qa')!=dict(contract['rule_qa'],assignment_identity_sha256=identity) or value.get('demo_scope')!='local_rule_only' or value.get('local_demo_source')!=contract['local_demo']:raise ValueError('qa_or_local_demo_contract_mismatch:'+mode)
                if mode=='text' and value.get('text_rule')!=contract['local_demo']['observed_demo']:raise ValueError('text_rule_mismatch')
                if mode!='text' and 'text_rule' in value:raise ValueError('rule_leaked_into_video_input')
                if qa_bank is not None and qa_keys is not None:
                    question=next(q for q in qa_bank['questions'] if q['task_id']==case['task'])
                    answer=next(q for q in qa_keys['questions'] if q['task_id']==case['task'])
                    packet=value['qa_public_packet'];grading=value['qa_grading_private']
                    packet_id='qp_'+hashlib.sha256((qa_bank['bank_version']+'\0'+identity).encode()).hexdigest()[:20]
                    expected_packet=dict(packet_id=packet_id,question_id=question['question_id'],prompt=question['prompt'],options=question['options'],response_instruction='只输出一个大写选项字母：A、B、C或D。')
                    if packet!=expected_packet or set(packet['options'])!=set('ABCD'):raise ValueError('qa_public_packet_mismatch')
                    if grading!=dict(packet_id=packet_id,question_id=question['question_id'],task_id=case['task'],variant=case['variant'],assignment_identity_sha256=identity,condition=case['condition'],input_mode=mode,correct_option=answer['answers'][case['variant']],source_demo_sha256=answer['sources'][case['variant']]['sha256']):raise ValueError('qa_private_grading_mismatch')
                if mode!='text':
                    media=case.get('media_bindings',{}).get(mode)
                    if not media:errors.append(key+':'+mode+':local_media_pending')
                    else:
                        mp=_local(release,media['path'])
                        if not mp.stat().st_size or sha(mp)!=media['sha256'] or media.get('scope')!='local_rule_only' or media.get('task')!=case['task'] or media.get('variant')!=case['variant'] or media.get('source_sha256')!=value['qa_grading_private']['source_demo_sha256']:raise ValueError('local_media_identity_mismatch:'+mode)
                        if mode=='sim' and media.get('rule_matches_source_reviewed') is not True:raise ValueError('sim_local_rule_review_pending')
                        if mode=='real' and media['sha256']!=media['source_sha256'] and media.get('rule_preserving_transcode_reviewed') is not True:raise ValueError('real_transcode_review_pending')
            for control in CONTROLS:
                receipt_ref=case.get('native_controls',{}).get(control)
                if not receipt_ref:errors.append(key+':'+control+':native_pending');continue
                receipt_path=_local(release,receipt_ref['path'])
                if sha(receipt_path)!=receipt_ref['sha256']:raise ValueError('native_receipt_hash_mismatch')
                r=json.loads(receipt_path.read_bytes())
                # A CPU fixture, author declaration, scripted success or mock
                # cannot satisfy this measured native receipt protocol.
                if r.get('schema')!='videoicl-native-execution-v2-control-v1' or r.get('backend')!='isaaclab_physx' or r.get('evidence_origin')!='native_physx_worker' or r.get('synthetic') is not False:raise ValueError('non_native_evidence')
                if revision==REVISION_V3 and r.get('revision')!=revision:raise ValueError('native_revision_mismatch')
                if revision==REVISION_V3 and case['condition']=='E':
                    if r.get('initial_pairing_verified') is not True or r.get('environment_base')!=case['declared_pairing']['environment_base'] or r.get('paired_input_identity')!=case['declared_pairing']['paired_input_identity']:raise ValueError('native_initial_environment_pairing_unverified')
                if r.get('case_id')!=key or r.get('control')!=control or r.get('assignment_identity_sha256')!=case['assignment_identity_sha256'] or r.get('source_hashes')!=hashes or r.get('binding_sha256')!=case['binding_sha256']:raise ValueError('native_identity_or_source_mismatch')
                owner=r.get('native_process',{})
                if not all(owner.get(k) for k in ('pid','start_ticks','gpu_uuid','run_id')):raise ValueError('missing_native_process_identity')
                if not all(r.get(k) is True for k in ('history_valid','asset_hashes_verified','no_teleport','robot_actuation_only','stable_state_verified','evidence_complete')):raise ValueError('native_evidence_incomplete')
                if r.get('strict_success') is not (control=='positive'):raise ValueError('control_wrong_outcome')
                process=r.get('process_score')
                if type(process) not in (int,float) or not 0<=process<=100 or (control=='positive' and process!=100) or (control!='positive' and process>=100):raise ValueError('control_process_score_invalid')
                if control!='positive' and r.get('negative_condition_observed') is not True:raise ValueError('negative_control_not_exercised')
                if not r.get('physics_steps',0)>0 or r.get('native_action_count',0)<=0:raise ValueError('no_native_execution')
                artifacts=r.get('artifacts',{})
                for kind in ('trajectory','contacts','final_snapshot','final_rgb','final_rgb_left_wrist','final_rgb_right_wrist','native_actions'):
                    a=artifacts.get(kind,{})
                    if not a.get('path') or not a.get('sha256'):raise ValueError('missing_artifact:'+kind)
                    ap=_local(release,a['path'])
                    if not ap.is_file() or ap.stat().st_size==0 or sha(ap)!=a['sha256']:raise ValueError('artifact_hash_mismatch:'+kind)
        except (OSError,KeyError,TypeError,ValueError) as exc:errors.append(key+':'+str(exc))
    if set(observed)!=expected or any(len(s)<3 for s in observed.values()):errors.append('missing_task_variant_condition_seed_coverage')
    if len({c['case_id']for c in cases})!=len(cases):errors.append('duplicate_cases')
    return {'ready':not errors,'full50_ready':not errors and full_scope,'native_acceptance':'passed' if not errors else 'pending_or_failed','case_count':len(cases),'errors':errors}


def set_model_launch_enabled(release, enabled):
    """Opt-in gate only: this does not launch or deploy any process."""
    if type(enabled) is not bool:raise TypeError('Boolean enabled required')
    release=Path(release)
    if enabled:
        result=validate_release(release)
        if not result['ready']:raise RuntimeError('Native acceptance incomplete; model admission denied')
    path=release/'manifest.private.json';manifest=json.loads(path.read_bytes())
    manifest['model_launch_enabled']=enabled
    if enabled:manifest['native_acceptance']='passed'
    write(path,manifest)


def main():
    p=argparse.ArgumentParser();p.add_argument('destination');p.add_argument('--bindings');p.add_argument('--qa-preparation');p.add_argument('--tasks',nargs='+');p.add_argument('--revision',choices=SUPPORTED_REVISIONS,default=REVISION);p.add_argument('--validate',action='store_true');args=p.parse_args()
    if args.validate:
        result=validate_release(args.destination);print(json.dumps(result));return 0 if result['ready'] else 2
    m=build_release(args.destination,bindings=args.bindings,qa_preparation=args.qa_preparation,tasks=args.tasks,revision=args.revision)
    print(json.dumps({'cases':len(m['cases']),'model_launch_enabled':False,'native_acceptance':'pending'}));return 0

if __name__=='__main__':raise SystemExit(main())
