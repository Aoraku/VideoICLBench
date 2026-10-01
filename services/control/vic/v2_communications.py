"""Private outcome checks for project requests, handovers and group delivery."""
from copy import deepcopy
import json
from . import business
from vic_apps.communications import file_record, handover_text, message_link


def selected_file(initial, request, variant):
    items=[x for x in initial['items'] if x['project']==request['project'] and x['file_type']==request['file_type'] and x['version']==request['version']]
    return min(items,key=lambda x: x['size'] if variant=='A' else -x['size'] if variant=='B' else len(x['name']))['id']


def selected_members(initial, project, variant):
    items=[x for x in initial['items'] if x['project']==project['id']]
    return business.expected_effect(15,variant,{**initial,'items':items})['members']


def evaluate(initial, final, variant, events):
    checks=[]
    def check(name,value):checks.append(dict(id=name,passed=bool(value)))
    t=initial['task_id'];w=final['world'];d=final['domain'];start=initial['world']
    for key in initial.keys()-{'world','domain','next_group'}:check('input:'+key,final.get(key)==initial[key])
    for key in start.keys()-{'handover','documents','groups'}:check('input:world:'+key,w.get(key)==start[key])
    expected=deepcopy(initial['domain']);messages=[]
    def sent(recipient,body,reference,attachment=None):
        messages.append(dict(sender='self',recipient=str(recipient),body=body,reference=reference,attachment=attachment))
    if t==11:
        for request in start['requests']:
            sent(request['requester'],'资料回复 · '+request['id'],request['id'],selected_file(initial,request,variant))
        for key in ('handover','documents','groups'):check('unchanged:'+key,w.get(key)==start[key])
    elif t==13:
        projects={p['id'] for p in start['projects']};rows={}
        for item in initial['items']:
            if item['project'] not in projects or item['batch']!='晚班-0115' or '紧急' not in item['text']:continue
            key=item['id'];status={'A':'已转发','B':'已收藏','C':'已归档'}[variant]
            rows[key]=dict(message=key,task_number=item['record_code'],project=item['project'],link=message_link(item),status=status)
            if variant=='A':sent(2,item['text'],key)
            elif variant=='B':
                expected['objects'][key]['starred']=True;expected['collections']['favorites'].append(key)
            else:expected['objects'][key]['archived']=True
        check('handover:rows',w['handover'].get('rows')==rows)
        check('handover:title',w['handover'].get('title')==start['handover']['title'])
        check('handover:sent',w['handover'].get('sent') is True)
        check('handover:document_count',set(w['documents'])=={'handover-001'})
        document=w['documents'].get('handover-001',{})
        check('handover:document_rows',document.get('rows')==rows)
        check('handover:recipient',document.get('recipient')==2)
        check('handover:document_title',document.get('title')==start['handover']['title'])
        body=handover_text(dict(title=start['handover']['title'],rows=document.get('rows',{})))
        check('handover:document_body',document.get('body')==body)
        expected['files']['handover-001']=file_record(start['handover']['title']+'.md',body)
        sent(2,start['handover']['title'],'handover-001','handover-001')
        check('unchanged:groups',w['groups']==start['groups'])
    else:
        groups=list(w['groups'].values());check('groups:count',len(groups)==len(start['projects']))
        for project in start['projects']:
            candidates=[g for g in groups if g['name']==project['group_name']]
            check(project['id']+':one_group',len(candidates)==1)
            if len(candidates)!=1:continue
            group=candidates[0]
            check(project['id']+':members',len(group['members'])==3 and set(group['members'])==set(selected_members(initial,project,variant)))
            check(project['id']+':announcement',group['announcement']==project['announcement'])
            check(project['id']+':material',[m['body'] for m in group['messages']]==[project['material_link']])
        for key in ('handover','documents'):check('unchanged:'+key,w.get(key)==start[key])
    # IDs and send order do not define success; duplicate or misrouted sends do.
    normalize=lambda rows:sorted(json.dumps({k:v for k,v in m.items() if k!='id'},sort_keys=True,ensure_ascii=False) for m in rows)
    check('delivery:messages',normalize(d['messages'])==normalize(messages))
    for key in expected.keys()-{'messages'}:
        if key=='collections':check('business:'+key,{k:sorted(v) for k,v in d[key].items()}=={k:sorted(v) for k,v in expected[key].items()})
        else:check('business:'+key,d.get(key)==expected[key])
    check('activity',bool(events))
    return dict(success=all(c['passed'] for c in checks),completion=sum(c['passed'] for c in checks)/len(checks),checks=checks,violations=[c['id'] for c in checks if not c['passed']])
