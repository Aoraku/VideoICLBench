"""Private evaluation of music assemblies and their actual group deliveries."""
from .business import transform


def desired(initial,activity,variant):
    w=initial['world'];objects=initial['domain']['objects'];t=initial['task_id']
    members=list(dict.fromkeys(x for key in activity['sources'] for x in next(s['members'] for s in w['sources'] if s['id']==key)))
    if t==18:
        members=[x for x in dict.fromkeys(members+activity['additions']) if x not in activity['exclusions']]
        source=dict(artist=activity['artist'],count=len(members),date=activity['date'],text='')
        name=transform(18,'ABC'.index(variant),dict(source=source))
    elif t==28:
        members=[x for x in members if objects[x]['available']]
        key={'A':lambda x:objects[x]['year'],'B':lambda x:objects[x]['duration'],'C':lambda x:objects[x]['artist']}[variant]
        members=sorted(members,key=key,reverse=variant!='A');name=activity['playlist_name']
    else:
        threshold=initial['source']['threshold']
        eligible=[x for x in members if {'A':objects[x]['rating']>threshold,'B':objects[x]['rating']<threshold,'C':objects[x]['duration']%2==0}[variant]]
        members=list(dict.fromkeys(activity['baseline']+eligible));name=activity['playlist_name']
    return dict(name=name,members=members,added=[x for x in members if x not in activity['baseline']])


def evaluate(initial,final,variant,events):
    checks=[]
    def check(name,value):checks.append(dict(id=name,passed=bool(value)))
    for key in initial.keys()-{'world','next_playlist','next_share'}:check('input:'+key,final.get(key)==initial[key])
    start=initial['world'];w=final['world'];t=initial['task_id']
    for key in start.keys()-{'playlists','shares','messages'}:check('input:world:'+key,w.get(key)==start[key])
    check('personal_playlist',w['playlists'].get('personal')==start['playlists']['personal'])
    check('playlist_count',len(w['playlists'])==len(start['activities'])+1)
    compared=(lambda a,b:a==b) if t==28 else (lambda a,b:len(a)==len(set(a)) and set(a)==set(b))
    valid_lists=set()
    for activity in start['activities']:
        expected=desired(initial,activity,variant)
        playlists=[p for p in w['playlists'].values() if p['activity']==activity['id']]
        key=activity['id'];check(key+':one_playlist',len(playlists)==1)
        if len(playlists)!=1:continue
        playlist=playlists[0];valid_lists.add(playlist['id'])
        check(key+':name',playlist['name']==expected['name'])
        check(key+':members',compared(playlist['members'],expected['members']))
        check(key+':saved',playlist['saved']==dict(name=playlist['name'],members=playlist['members']))
        shares=[s for s in w['shares'] if s['playlist']==playlist['id']]
        check(key+':delivered',bool(shares))
        for index,share in enumerate(shares):
            prefix=f'{key}:share:{index}'
            check(prefix+':group',share['group']==activity['group_id'])
            check(prefix+':name',share['name']==expected['name'])
            check(prefix+':members',compared(share['members'],expected['members']))
            check(prefix+':added',len(share['added'])==len(set(share['added'])) and set(share['added'])==set(expected['added']))
            check(prefix+':link',share['link']==f'playlists/{playlist["id"]}/')
    check('no_unrelated_shares',all(s['playlist'] in valid_lists for s in w['shares']))
    check('activity',bool(events))
    return dict(success=all(c['passed'] for c in checks),completion=sum(c['passed'] for c in checks)/len(checks),checks=checks,violations=[c['id'] for c in checks if not c['passed']])
