"""Native Music views for editable event playlists and source collections."""
from copy import deepcopy


def project_context(context,state,songs,route,query):
    world=state['world'];by_id={s.id:s for s in songs}
    playlists=list(world['playlists'].values())
    context.update(music_projects=True,project_world=world,project_playlists=playlists)
    if route=='activities/':
        activities=[]
        for activity in world['activities']:
            a=deepcopy(activity)
            a.update(source_rows=[s for key in a['sources'] for s in world['sources'] if s['id']==key],
                addition_songs=[by_id[k] for k in a['additions']],exclusion_songs=[by_id[k] for k in a['exclusions']],
                playlists=[p for p in playlists if p['activity']==a['id']])
            activities.append(a)
        context['activities']=activities
        return 'blog/music_activities.html'
    if route=='playlists/':return 'blog/music_project_playlists.html'
    if route=='library/' or route.startswith('sources/'):
        source=next((s for s in world['sources'] if route==f'sources/{s["id"]}/'),None)
        if route!='library/' and not source:raise ValueError('Source collection not found')
        context.update(source_collection=source,collection_title=source['name'] if source else '资料库 · 所有歌曲',
            songs=[by_id[k] for k in source['members']] if source else songs)
        return 'blog/music_project_source.html'
    if route.startswith('playlists/'):
        playlist=world['playlists'].get(route.strip('/').split('/')[-1])
        if not playlist:raise ValueError('Playlist not found')
        saved=playlist['saved']==dict(name=playlist['name'],members=playlist['members'])
        context.update(playlist=playlist,songs=[by_id[k] for k in playlist['members']],playlist_saved=saved,
            playlist_shares=[dict(s,group_name=next(g['name'] for g in world['groups'] if g['id']==s['group'])) for s in world['shares'] if s['playlist']==playlist['id']])
        return 'blog/music_project_detail.html'
    return None
