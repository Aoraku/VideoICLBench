"""Private screening evaluation using input collections and actual saved schedule."""
from copy import deepcopy
from vic_apps.screening import timetable,timetable_csv
from vic_apps.communications import file_record


def final_queue(initial,variant):
    w=initial['world'];objects=initial['domain']['objects'];event=w['event']
    base=list(dict.fromkeys(x for f in w['folders'] for x in f['members']))
    excluded={r['video'] for r in event['exclude']};replacements={r['old']:r['new'] for r in event['replacements']}
    base=[replacements.get(x,x) for x in base if x not in excluded]
    first=[x for x in base if (objects[x]['category']=='甲' if variant=='C' else objects[x]['duration']<event['short_below_seconds'])]
    second=[x for x in base if x not in first]
    if variant=='B':first,second=second,first
    result=[]
    for i in range(max(len(first),len(second))):
        if i<len(first):result.append(first[i])
        if i<len(second):result.append(second[i])
    return result


def evaluate(initial,final,variant,events):
    checks=[]
    def check(name,value):checks.append(dict(id=name,passed=bool(value)))
    for key in initial.keys()-{'domain','world'}:check('input:'+key,initial[key]==final.get(key))
    for key in initial['domain'].keys()-{'files'}:check('input:domain:'+key,initial['domain'][key]==final['domain'].get(key))
    start=initial['world'];w=final['world']
    for key in start.keys()-{'queue','timing','schedule'}:check('input:world:'+key,start[key]==w.get(key))
    event=start['event'];queue=dict(name=event['title'],members=final_queue(initial,variant));timing=dict(starts_at=event['starts_at'],turnaround_seconds=event['turnaround_seconds'],breaks={r['after']:r['seconds'] for r in event['breaks']})
    check('queue_name',w['queue']['name']==queue['name']);check('queue_members_and_order',w['queue']['members']==queue['members']);check('queue_saved',w['queue']['saved']==queue)
    check('timing',w['timing']==timing)
    reference=deepcopy(initial);reference['world']['queue'].update(queue);reference['world']['timing']=timing;schedule=timetable(reference)
    check('schedule_rows_and_snapshot',w['schedule']==schedule)
    files={**initial['domain']['files'],'screening-timetable':file_record(event['title']+'-放映时间表.csv',timetable_csv(schedule))}
    check('timetable_file',final['domain']['files']==files);check('activity',bool(events))
    return dict(success=all(c['passed'] for c in checks),completion=sum(c['passed'] for c in checks)/len(checks),checks=checks,violations=[c['id'] for c in checks if not c['passed']])
