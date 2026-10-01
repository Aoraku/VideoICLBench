"""Private trip validation: source identities, lookahead feasibility and delivery."""
from copy import deepcopy
from datetime import datetime,timedelta
from vic_apps.travel_projects import booking_snapshot,booking_text,itinerary_text
from vic_apps.communications import file_record


def eligible_routes(initial,prefix):
    w=initial['world'];objects=initial['domain']['objects'];index=len(prefix)
    if index==len(w['legs']):return []
    leg=w['legs'][index];ready=datetime.fromisoformat(w['earliest_departure'])
    if prefix:ready=max(datetime.fromisoformat(objects[prefix[-1]]['arrive_at'])+timedelta(minutes=w['connection_minutes']),datetime.fromisoformat(w['legs'][index-1]['meeting_end']))
    result=[]
    for id in leg['candidates']:
        r=objects[id]
        if r['price']<=w['budget'] and r['available'] and datetime.fromisoformat(r['depart_at'])>=ready and r['arrive_at']<=leg['meeting_start']:
            if index+1==len(w['legs']) or eligible_routes(initial,prefix+[id]):result.append(id)
    return result


def route_plan(initial,variant):
    w=initial['world'];objects=initial['domain']['objects']
    if initial['task_id']==44:return {leg['id']:leg['candidates'][0] for leg in w['legs']}
    if initial['task_id']==54:
        return {r['id']:r['route'] for r in w['requests'] if (objects[r['route']]['price']<w['threshold'] if variant=='A' else objects[r['route']]['price']>w['threshold'] if variant=='B' else objects[r['route']]['transfers']%2==0)}
    prefix=[];result={}
    for leg in w['legs']:
        candidates=eligible_routes(initial,prefix)
        if not candidates:raise ValueError('Trip fixture has no feasible completion')
        candidates=sorted(candidates,key=lambda id:objects[id]['record_code'])
        key={'A':lambda id:objects[id]['price'],'B':lambda id:objects[id]['duration'],'C':lambda id:objects[id]['depart_at']}[variant]
        chosen=sorted(candidates,key=key,reverse=variant=='C')[0]
        result[leg['id']]=chosen;prefix.append(chosen)
    return result


def full_name(person,variant):
    name=person['surname']+(' ' if variant!='B' else '-')+person['given_name']
    return name.upper() if variant=='C' else name


def evaluate(initial,final,variant,events):
    checks=[]
    def check(key,value):checks.append(dict(id=key,passed=bool(value)))
    for key in initial.keys()-{'domain','world','next_booking','next_receipt'}:check('input:'+key,initial[key]==final.get(key))
    for key in initial['domain'].keys()-{'files'}:check('input:domain:'+key,initial['domain'][key]==final['domain'].get(key))
    start=initial['world'];w=final['world'];mutable={'profiles','bookings','approvals','receipts','discussion','itinerary'}
    for key in start.keys()-mutable:check('input:world:'+key,start[key]==w.get(key))
    profiles=deepcopy(start['profiles']);people={p['id']:p for p in start['people']}
    if initial['task_id']==44:
        for id in start['legs'][0]['passengers']:profiles[id]['full_name']=full_name(people[id],variant)
    check('traveler_profiles',w['profiles']==profiles)
    plan=route_plan(initial,variant);check('booking_count',len(w['bookings'])==len(plan));check('booking_slots',{b['slot'] for b in w['bookings'].values()}==set(plan))
    expected_bookings={};files=deepcopy(initial['domain']['files']);approvals={}
    for slot,route in plan.items():
        matches=[(id,b) for id,b in w['bookings'].items() if b['slot']==slot];check(slot+':one_booking',len(matches)==1)
        if len(matches)!=1:continue
        id,b=matches[0]
        source=next(r for r in (start['requests'] if initial['task_id']==54 else start['legs']) if r['id']==slot)
        expected_ids=[source['person']] if initial['task_id']==54 else source['passengers']
        actual_ids=[p['id'] for p in b['passengers']];check(slot+':passenger_ids',set(actual_ids)==set(expected_ids) and len(actual_ids)==len(expected_ids))
        ordered=actual_ids if set(actual_ids)==set(expected_ids) and len(actual_ids)==len(expected_ids) else expected_ids
        rows=[dict(id=pid,**profiles[pid]) for pid in ordered]
        expected=dict(id=id,slot=slot,route=route,passengers=rows,cost_center=source['cost_center'],contact=source['contact'],status='draft' if initial['task_id']==44 else 'confirmed',confirmation='' if initial['task_id']==44 else 'SIM-'+id)
        expected['saved']=booking_snapshot(expected);check(slot+':booking',b==expected)
        expected_bookings[id]=expected;files['booking-'+id]=file_record(id+'-行程单.md',booking_text(initial,expected))
        if initial['task_id']==54:
            approvals[slot]=id;receipts=[r for r in w['receipts'] if r['booking']==id];check(slot+':one_notice',len(receipts)==1)
            for receipt in receipts:
                check(slot+':notice',receipt.get('recipient')==source['recipient'] and receipt.get('body')==booking_text(initial,expected) and receipt.get('link')=='bookings/'+id)
    check('approval_links',w['approvals']==approvals)
    check('receipt_count',len(w['receipts'])==(len(plan) if initial['task_id']==54 else 0))
    reference=deepcopy(initial);reference['world']['bookings']=expected_bookings
    ordered=sorted(expected_bookings,key=lambda id:(initial['domain']['objects'][expected_bookings[id]['route']]['depart_at'],id))
    body=itinerary_text(reference,ordered);check('itinerary',w['itinerary']==dict(bookings=ordered,body=body))
    files['travel-itinerary']=file_record('完整出差行程单.md',body);check('real_itinerary_files',final['domain']['files']==files)
    check('activity',bool(events))
    return dict(success=all(c['passed'] for c in checks),completion=sum(c['passed'] for c in checks)/len(checks),checks=checks,violations=[c['id'] for c in checks if not c['passed']])
