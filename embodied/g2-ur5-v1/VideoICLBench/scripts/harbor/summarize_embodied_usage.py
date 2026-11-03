#!/usr/bin/env python3
"""Read per-episode native cumulative usage without summing cumulative events.

No API access, image token estimates, history rebuilding, or mutation of runs.
"""
from __future__ import annotations
import argparse
from collections import Counter
import hashlib
import json
import re
from pathlib import Path

FIELDS=('total_input_tokens','cached_input_tokens','uncached_input_tokens','output_tokens','reasoning_tokens')
IDENTITY=('run_id','task_id','variant','seed','suite','epoch')


def rows(path):
    with path.open(errors='replace') as stream:
        for number,line in enumerate(stream,1):
            try:value=json.loads(line)
            except ValueError:continue
            if isinstance(value,dict):yield number,value


def nonnegative(value):
    return value if type(value) is int and value>=0 else None


def normalize(value):
    value=value if isinstance(value,dict) else {}
    inp=nonnegative(value.get('input_tokens'))
    cached=nonnegative(value.get('cached_input_tokens',value.get('input_tokens_details',{}).get('cached_tokens')
        if isinstance(value.get('input_tokens_details'),dict) else None))
    reasoning=nonnegative(value.get('reasoning_output_tokens',value.get('output_tokens_details',{}).get('reasoning_tokens')
        if isinstance(value.get('output_tokens_details'),dict) else None))
    return dict(total_input_tokens=inp,cached_input_tokens=cached,
        uncached_input_tokens=inp-cached if inp is not None and cached is not None and cached<=inp else None,
        output_tokens=nonnegative(value.get('output_tokens')),reasoning_tokens=reasoning)


def input_images(value):
    if isinstance(value,dict):
        return int(value.get('type')=='input_image')+sum(input_images(v) for v in value.values() if isinstance(v,(dict,list)))
    if isinstance(value,list):return sum(input_images(v) for v in value)
    return 0


def summarize_run(folder):
    result_path=folder/'result.json'
    result={};warnings=[]
    if result_path.exists():
        try:result=json.loads(result_path.read_text())
        except ValueError:warnings.append('terminal_result_not_yet_readable')
    if not isinstance(result,dict):raise ValueError('Native result must be an object')
    terminal_result_available=bool(result)
    manifest_path=folder/'manifest.json'
    manifest=json.loads(manifest_path.read_text()) if manifest_path.exists() else {}
    if not isinstance(manifest,dict):raise ValueError('Episode manifest must be an object')
    if result.get('engine',manifest.get('engine'))!='codex' or manifest.get('agent_interaction')!='gui_only':return None
    identity={key:result.get(key,manifest.get(key)) for key in IDENTITY}
    if any(value is None for value in identity.values()):
        raise ValueError('Reliable episode identity is required for usage accounting')
    # Native resume appends stdout-N but keeps one profile/session. Earlier
    # turn.completed usage is historical, never another addend or final proof.
    outputs={}
    for path in folder.glob('stdout-*.jsonl'):
        match=re.fullmatch(r'stdout-([1-9][0-9]*)\.jsonl',path.name)
        if match:outputs[int(match.group(1))]=path
    native_attempts=result.get('native_attempts',[])
    if not isinstance(native_attempts,list):
        warnings.append('invalid_native_attempt_metadata');native_attempts=[]
    metadata={}
    for attempt in native_attempts:
        if (not isinstance(attempt,dict) or type(attempt.get('attempt')) is not int
                or attempt['attempt']<1 or attempt.get('stdout')!=f"stdout-{attempt['attempt']}.jsonl"
                or attempt['attempt'] in metadata):
            warnings.append('invalid_native_attempt_metadata');continue
        metadata[attempt['attempt']]=attempt
    attempt_numbers=sorted(set(outputs)|set(metadata))
    latest_attempt=attempt_numbers[-1] if attempt_numbers else None
    output=outputs.get(latest_attempt)
    stream_events=[];attempt_observations=[];session_ids=set()
    for number in attempt_numbers:
        path=outputs.get(number)
        events=list(rows(path)) if path is not None else []
        ids={event['thread_id'] for _,event in events if event.get('type')=='thread.started'
             and isinstance(event.get('thread_id'),str) and event['thread_id']}
        declared=metadata.get(number,{}).get('session_id')
        if isinstance(declared,str) and declared:ids.add(declared)
        session_ids.update(ids)
        errors=Counter(event.get('type') for _,event in events if event.get('type') in ('error','turn.failed'))
        attempt_observations.append(dict(attempt=number,stdout=path.name if path else f'stdout-{number}.jsonl',
            stdout_available=path is not None,session_ids=sorted(ids),error_event_counts=dict(errors),
            metadata_error_count=len(metadata[number]['errors']) if number in metadata and isinstance(metadata[number].get('errors'),list) else None,
            turn_completed_count=sum(event.get('type')=='turn.completed' for _,event in events),
            exit_code=metadata.get(number,{}).get('exit_code')))
        if number==latest_attempt:stream_events=events
    if isinstance(result.get('session_id'),str) and result['session_id']:session_ids.add(result['session_id'])
    rollout_paths=sorted((folder/'profile/sessions').rglob('*.jsonl'))
    # Inspect identities even when stdout already declared one: a changed
    # session in a supposedly private profile must not be silently stitched in.
    for path in rollout_paths:
        for _,event in rows(path):
            if event.get('type')=='session_meta':
                payload=event.get('payload')
                candidate=payload.get('id') if isinstance(payload,dict) else None
                if isinstance(candidate,str) and candidate:session_ids.add(candidate)
                break
    multi_attempt=bool(latest_attempt and latest_attempt>1)
    result_matches_latest=(not multi_attempt or (bool(metadata) and max(metadata)==latest_attempt))
    if multi_attempt and terminal_result_available and not result_matches_latest:
        warnings.append('terminal_result_not_bound_to_latest_attempt')
    if metadata and sorted(metadata)!=list(range(1,max(metadata)+1)):
        warnings.append('noncontiguous_native_attempt_metadata')
    if latest_attempt is not None and output is None:
        warnings.append('latest_attempt_stdout_missing')
    session=next(iter(session_ids)) if len(session_ids)==1 else None
    if len(session_ids)>1:warnings.append('ambiguous_native_session_identity')
    seen=set();native_files=[]
    if session:
        for path in rollout_paths:
            if session not in path.name:continue
            hasher=hashlib.sha256()
            with path.open('rb') as stream:
                for block in iter(lambda:stream.read(1024*1024),b''):hasher.update(block)
            digest=hasher.hexdigest()
            if digest in seen:continue
            seen.add(digest);native_files.append(path)
    rollout=((str(path.relative_to(folder)),number,value) for path in native_files for number,value in rows(path))
    cumulative=[];compacted=[];boundaries=[];images=0
    for path,number,event in rollout:
        payload=event.get('payload',{})
        if event.get('type')=='event_msg' and isinstance(payload,dict):
            info=payload.get('info')
            if payload.get('type')=='token_count' and isinstance(info,dict) and isinstance(info.get('total_token_usage'),dict):
                cumulative.append((event.get('timestamp') or '',path,number,info['total_token_usage']))
            if payload.get('type')=='context_compacted':boundaries.append((path,number))
        if event.get('type')=='compacted':compacted.append((path,number))
        # Only appended native response items: do not recount replacement_history
        # embedded inside a compacted event, or screenshot files never sent.
        if event.get('type')=='response_item':images+=input_images(payload)
    last_terminal=next((event.get('type') for _,event in reversed(stream_events)
        if event.get('type') in ('turn.completed','turn.failed','error')),None)
    final_events=[(line,event['usage']) for line,event in stream_events
        if event.get('type')=='turn.completed' and isinstance(event.get('usage'),dict)] if last_terminal=='turn.completed' else []
    snapshots=[]
    if cumulative:
        _,path,line,value=max(cumulative,key=lambda row:(row[0],row[1],row[2]))
        snapshots.append(dict(source=dict(kind='last_native_cumulative_token_count',path=path,line=line),usage=normalize(value)))
    if final_events:
        line,value=final_events[-1]
        snapshots.append(dict(source=dict(kind='last_native_turn_completed',path=output.name,line=line),usage=normalize(value)))
    if isinstance(result.get('usage'),dict) and result_matches_latest:
        snapshots.append(dict(source=dict(kind='native_final_result_usage',path=result_path.name),usage=normalize(result['usage'])))
    conflicts=[]
    for field in FIELDS:
        known={row['source']['kind']:row['usage'][field] for row in snapshots if row['usage'][field] is not None}
        if len(set(known.values()))>1:conflicts.append(dict(field=field,sources=known))
    # Keep one source snapshot intact; do not splice stale rollout counters into
    # newer terminal output or silently turn disagreement into an alleged total.
    selected=snapshots[0] if snapshots else dict(source=None,usage=normalize(None))
    if conflicts and final_events:
        selected=next(row for row in snapshots if row['source']['kind']=='last_native_turn_completed')
    if 'ambiguous_native_session_identity' in warnings:
        selected=dict(source=None,usage=normalize(None))
    latest_exit_ok=not metadata or metadata.get(latest_attempt,{}).get('exit_code')==0
    is_final=bool(terminal_result_available and result_matches_latest and latest_exit_ok and not conflicts and not warnings and (final_events or
        (selected['source'] and selected['source']['kind']=='native_final_result_usage' and result.get('exit_code')==0 and not multi_attempt)))
    snapshot_status='conflicting' if conflicts else ('final' if is_final else 'partial')
    return dict(identity=identity,
        input_condition=manifest.get('input_condition'),session_id=session,run_directory=str(folder),
        outcome=result.get('outcome'),scored=result.get('scored'),scientific_evaluation=result.get('scientific_evaluation'),
        benchmark_completed=result.get('benchmark_completed'),evaluation_scope=result.get('evaluation_scope'),
        usage=selected['usage'],usage_source=selected['source'],usage_is_final=is_final,
        snapshot_status=snapshot_status,terminal_result_available=terminal_result_available,
        usage_conflicts=conflicts,usage_source_snapshots=snapshots,warnings=warnings,
        active_process_state=None,native_attempt_observations=attempt_observations,
        latest_native_attempt=latest_attempt,result_matches_latest_attempt=result_matches_latest,
        native_resume_accounting='One persistent same-session cumulative snapshot; prior stdout usage is never summed',
        cumulative_events_observed=len(cumulative),cumulative_events_summed=False,
        compaction_count=(len(compacted) if compacted else len(boundaries)) if native_files else None,
        compaction_count_source='native_compacted_records' if compacted else ('native_context_compacted_events' if native_files else None),
        image_input_occurrences=images if native_files else None,
        image_count_source='native_response_item_input_image_occurrences' if native_files else None,
        image_token_estimate=None,compaction_configuration=manifest.get('compaction'))


def summarize_tree(root):
    episodes=[];errors=[]
    folders={path.parent for name in ('result.json','manifest.json') for path in root.rglob(name)}
    for folder in sorted(folders):
        try:row=summarize_run(folder)
        except (ValueError,OSError,TypeError) as exc:
            errors.append(dict(path=str(folder),error_class=type(exc).__name__));continue
        if row is not None:episodes.append(row)
    keys=[tuple(row['identity'][key] for key in IDENTITY) for row in episodes]
    repeated=[list(key) for key,count in Counter(keys).items() if count>1]
    fields={field:dict(known_episodes=sum(row['usage'][field] is not None for row in episodes),
        observed_subtotal=(sum(row['usage'][field] or 0 for row in episodes) if any(row['usage'][field] is not None for row in episodes) else None),
        complete_total=(sum(row['usage'][field] for row in episodes) if episodes and not repeated and not errors
            and all(row['usage'][field] is not None and row['usage_is_final'] for row in episodes) else None)) for field in FIELDS}
    return dict(schema='videoicl-embodied-native-usage-v1',root=str(root),episode_attempt_count=len(episodes),
        duplicate_identities=repeated,errors=errors,totals=fields,episodes=episodes,
        final_episode_count=sum(row['usage_is_final'] for row in episodes),
        partial_episode_count=sum(not row['usage_is_final'] for row in episodes),
        conflicting_episode_count=sum(bool(row['usage_conflicts']) for row in episodes),
        ambiguous_session_episode_count=sum('ambiguous_native_session_identity' in row['warnings'] for row in episodes),
        invalid_attempt_metadata_episode_count=sum('invalid_native_attempt_metadata' in row['warnings']
            or 'noncontiguous_native_attempt_metadata' in row['warnings'] for row in episodes),
        aggregation_scope='discovered native embodied attempts; no claim of complete 300-episode coverage',
        accounting='One native cumulative snapshot per episode; partial and cross-source conflicts remain nonfinal; unknown stays null',
        image_accounting='Count native input-image occurrences, not image tokens; never estimate image tokens')


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--root',type=Path,required=True);p.add_argument('--out',type=Path,required=True)
    args=p.parse_args();root=args.root.resolve(strict=True)
    report=summarize_tree(root)
    args.out.parent.mkdir(parents=True,exist_ok=True)
    with args.out.open('x') as stream:json.dump(report,stream,ensure_ascii=False,indent=2);stream.write('\n')
    print(json.dumps(dict(report=str(args.out),episode_attempt_count=report['episode_attempt_count'],totals=report['totals'])))
    return 0 if (not report['errors'] and not report['duplicate_identities'] and not report['conflicting_episode_count'] and not report['ambiguous_session_episode_count']
        and not report['invalid_attempt_metadata_episode_count']) else 2


if __name__=='__main__':raise SystemExit(main())
