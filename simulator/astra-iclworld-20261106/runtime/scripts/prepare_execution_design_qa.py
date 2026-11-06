#!/usr/bin/env python3
"""Prepare reviewed local-rule inputs and exercise the exported SDK, offline.

No model/API/SSH/native simulator calls. Existing source media are read only;
missing semantic review remains pending rather than inferred from native score.
"""
import argparse
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime,timezone
import json
import os
from pathlib import Path
import subprocess
import sys

RUNTIME=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(RUNTIME))
from videoicl_isaaclab.execution_design import REVISION,SUPPORTED_REVISIONS,WORKFLOW_TASKS,metadata
from videoicl_isaaclab.execution_design_qa import export_sdk,prepare_assignment,sha


def dump(path,value):
    Path(path).write_text(json.dumps(value,ensure_ascii=False,indent=2)+'\n');Path(path).chmod(0o600)


def prepare(destination,*,python=sys.executable,ffmpeg='/opt/homebrew/bin/ffmpeg',sim_reviews=None,tasks=None,revision=None):
    revision=REVISION if revision is None else revision
    tasks=[f'E{i:02}'for i in range(1,51)] if tasks is None else list(tasks)
    if len(set(tasks))!=len(tasks):raise ValueError('Unique tasks required')
    for task in tasks:metadata(task,revision)
    dest=Path(destination).resolve();dest.mkdir(parents=True,exist_ok=False)
    root=RUNTIME.parent;bank=root/'evaluation/rule_qa'
    sdk=export_sdk(dest/'sdk',revision=revision)
    tests=RUNTIME/'tests/test_execution_design_qa_integration.py'
    junit=dest/'integration-tests.xml';log=dest/'integration-tests.log'
    environment=dict(os.environ,PYTHONPATH=str(RUNTIME),PYTHONDONTWRITEBYTECODE='1')
    command=[str(python),'-m','pytest','-q',str(tests),'--junitxml='+str(junit),'-p','no:cacheprovider']
    with log.open('wb') as output:
        result=subprocess.run(command,env=environment,stdout=output,stderr=subprocess.STDOUT,timeout=120)
    if result.returncode:raise RuntimeError('Offline SDK QA integration failed; see '+str(log))
    from build_execution_design_release import _validate_qa_junit
    _validate_qa_junit(junit,revision)
    real_reviews=json.loads((bank/'real-transcode-bindings.private.json').read_bytes())['source_bindings']
    explicit_sim_reviews=json.loads(Path(sim_reviews).read_bytes())['source_bindings'] if sim_reviews else []
    simroot=root/'materials/sim150-20261030'
    sim=json.loads((simroot/'manifest.private.json').read_bytes())['records']
    sourcekeys={q['task_id']:q for q in json.loads((bank/'answer_key.private.json').read_bytes())['questions']}
    jobs=[(task,variant,mode) for task in sorted(tasks) for variant in 'ABC' for mode in ('real','sim')]
    def check(job):
        task,variant,mode=job;record=dict(task=task,variant=variant,mode=mode,status='pending')
        try:
            source_sha=sourcekeys[task]['sources'][variant]['sha256'];record['source_sha256']=source_sha
            if mode=='real':
                provenance_path=root/'materials/real-text300-20261030'/task/variant/'media.private.json'
                provenance=json.loads(provenance_path.read_bytes());path=Path(provenance['path'])
                if sha(provenance['source_path'])!=source_sha or provenance['source_sha256']!=source_sha:raise ValueError('Original source hash mismatch')
                expected=provenance['sha256']
                review=next(r for r in real_reviews if r['task_id']==task and r['variant']==variant and r['sha256']==expected)
                record.update(provenance_path=str(provenance_path),provenance_sha256=sha(provenance_path),review=review)
            else:
                provenance=next(r for r in sim if r['task']==task and r['variant']==variant)
                if not provenance.get('file') or not provenance.get('sha256'):
                    raise ValueError('Complete source sim demo unavailable; incomplete clips cannot substitute for the local-rule demonstration')
                path=simroot/provenance['file'];expected=provenance['sha256']
                if provenance['source_video_sha256']!=source_sha:raise ValueError('Sim source rule identity mismatch')
                independent=provenance.get('independent_review');reviewed={}
                if independent:
                    independent_path=Path(independent['path'])
                    if sha(independent_path)!=independent['sha256']:raise ValueError('Sim review file hash mismatch')
                    reviewed=json.loads(independent_path.read_bytes())
                record.update(independent_review=independent,
                    native_history_valid=provenance.get('native_history_valid'),
                    source_endpoint_review=reviewed.get('source_endpoint_review'),
                    source_visual_final_acceptance=provenance.get('source_visual_final_acceptance'),
                    formal_accepted=provenance.get('formal_accepted'))
                review=next((r for r in explicit_sim_reviews if r.get('task_id')==task and r.get('variant')==variant),None)
            if sha(path)!=expected:raise ValueError('Media bytes changed')
            record.update(path=str(path.resolve()),sha256=expected,bytes=path.stat().st_size,bytes_verified=True)
            decode_log=dest/(task+'-'+variant+'-'+mode+'-decode.log')
            with decode_log.open('wb') as output:
                decoded=subprocess.run([ffmpeg,'-nostdin','-hide_banner','-loglevel','error','-xerror','-threads','1','-i',str(path),
                    '-map','0:v:0','-an','-f','null','-'],stdout=output,stderr=subprocess.STDOUT,timeout=180)
            record['full_decode_verified']=decoded.returncode==0
            if decoded.returncode:raise ValueError('Full decode failed')
            if mode=='sim' and review is None:
                endpoint=record.get('source_endpoint_review') or {}
                record['blocker']=('Existing review accepts visible initial/final relation only; full-episode local-rule semantic review is not accepted.'
                    if endpoint.get('visible_initial_final_task_relation_accepted') is True else
                    'Existing evidence contains native physics conditions but no explicit source/video visual semantic review.')
                return record
            if mode=='sim':
                if review.get('source_sha256')!=source_sha or review.get('full_episode_visual_acceptance') is not True:
                    raise ValueError('Explicit sim review must bind original source and full local-rule video')
                record['review']=review
            prepare_assignment(task,variant,4201,metadata(task,revision)['main_condition'],mode,bank_dir=bank,media_path=path,review=review,revision=revision)
            record['status']='ready'
        except (OSError,ValueError,KeyError,TypeError,StopIteration,subprocess.TimeoutExpired) as exc:
            record['blocker']=type(exc).__name__+': '+str(exc)
        finally:
            dump(dest/(task+'-'+variant+'-'+mode+'.private.json'),record)
        return record
    with ThreadPoolExecutor(max_workers=3) as pool:media=list(pool.map(check,jobs))
    prepared=dict(schema='videoicl-execution-v2-qa-preparation-v1',revision=revision,tasks=tasks,
        checked_utc=datetime.now(timezone.utc).isoformat(),sdk_files=sdk['files'],
        integration_test=dict(path=junit.name,sha256=sha(junit),source_sha256=sha(tests),passed=True,command=command),
        media=media,model_launch_enabled=False,model_calls=0,simulation_starts=0,
        note='SDK and input readiness only. Native scene acceptance is independent and still required.')
    dump(dest/'preparation.private.json',prepared)
    print(json.dumps(dict(output=str(dest),integration_tests='passed',media_ready=sum(r['status']=='ready'for r in media),
        media_pending=sum(r['status']!='ready'for r in media),model_launch_enabled=False)))
    return prepared


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('destination',type=Path)
    p.add_argument('--python',default=sys.executable);p.add_argument('--ffmpeg',default='/opt/homebrew/bin/ffmpeg')
    p.add_argument('--sim-reviews',type=Path,help='Explicit reviewed local-rule videos; never infer this from native score')
    p.add_argument('--tasks',nargs='+');p.add_argument('--revision',choices=SUPPORTED_REVISIONS,default=REVISION)
    args=p.parse_args();prepare(args.destination,python=args.python,ffmpeg=args.ffmpeg,sim_reviews=args.sim_reviews,tasks=args.tasks,revision=args.revision)
