"""Validate a small engineering cohort before restoring individual rooms."""
import hashlib
from pathlib import Path

SCHEMA='engineering-checkpoint-cohort-v1'


def selected_requests(request,cases,controllers,request_path,control):
    if request.get('schema')!=SCHEMA or request.get('diagnostic_only')is not True or control!='positive':
        raise ValueError('Explicit positive engineering checkpoint cohort required')
    if not 1<=len(cases)<=3 or len(controllers)!=len(cases):
        raise ValueError('Engineering cohort supports at most3 existing rooms')
    lookup={}
    for case in cases:
        if case['task']not in{f'E{i}'for i in range(44,51)}:raise ValueError('Cohort task scope E44-E50 only')
        key=(case['task'],case['variant'],case['seed'])
        if key in lookup or case['episode_id']not in controllers:raise ValueError('Ambiguous cohort case identity')
        lookup[key]=case
    singles=request.get('requests')
    if not isinstance(singles,list)or not 1<=len(singles)<=len(cases):raise ValueError('Nonempty explicit cohort requests required')
    selected=[];seen=set();base=Path(request_path).parent
    for single in singles:
        if not isinstance(single,dict)or single.get('schema')==SCHEMA:raise ValueError('Nested cohort requests forbidden')
        key=tuple(single.get(k)for k in('task','variant','seed'))
        if key not in lookup or key in seen:raise ValueError('Duplicate or unmatched cohort request')
        if not isinstance(single.get('entry'),str):raise ValueError('Explicit suffix entry required')
        path=Path(single['checkpoint']);path=path if path.is_absolute()else base/path
        raw=path.read_bytes()
        if hashlib.sha256(raw).hexdigest()!=single.get('sha256'):raise ValueError('Cohort checkpoint file SHA mismatch')
        seen.add(key);case=lookup[key];selected.append((case['episode_id'],case,single))
    # Rooms absent from this list keep their independently fresh initial state.
    return selected
