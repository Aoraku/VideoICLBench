"""Editable music collections and shared activity messages; no learned rules."""
from copy import deepcopy
import json
from vic import business
from .domain import initialize

TASKS={18,28,32}


def fixture(task_id,seed,spec):
    state=business.generate(task_id,seed);items=[];activities=[]
    names=['春日市集','图书馆夜读','社区开放日'] if task_id!=28 else ['周末音乐会']
    for index,name in enumerate(names):
        group=business.generate(32 if task_id==32 else 28,seed+137*index)['items']
        count=12 if task_id==28 else 9 if task_id==32 else 8
        activity=dict(id=f'event-{index+1}',name=name,group_id=20+index,
            group_name=name+'筹备组',artist=['Mira Chen','Northbound','Paper Moon'][index],date=f'2026-02-{10+index*5:02d}')
        activities.append(activity)
        for n in range(count):
            item=deepcopy(group[n%6]);item.update(id=f'{index}-{n}',activity=activity['id'],
                record_code=f'M{index+1}-{n+1:03d}',edition='录音室版' if n<6 else '现场版',available=True)
            if task_id==18:item['artist']=activity['artist']
            if n>=6:
                item['year']+=1;item['duration']+=17;item['name_length']=len(item['name'])
            if task_id==28 and n in (4,9):item['available']=False
            if task_id==32 and n==8:item.update(name='活动序曲',edition='保留曲目')
            items.append(item)
    extra=deepcopy(items[0]);extra.update(id='personal',activity='personal',record_code='P-001',name='午后私藏',edition='私人收藏')
    items.append(extra);state['items']=items;state=initialize(state)
    sources=[];playlists={}
    for index,activity in enumerate(activities):
        tracks=[x['id'] for x in state['items'] if x['activity']==activity['id']]
        slices=[tracks[0:5],tracks[3:8],tracks[7:12]] if task_id==28 else [tracks[0:4],tracks[3:8]] if task_id==32 else [tracks[0:3],tracks[2:5]]
        activity['sources']=[]
        for n,members in enumerate(slices):
            key=f'source-{index+1}-{n+1}';activity['sources'].append(key)
            sources.append(dict(id=key,name=activity['name']+(' · 专辑' if task_id==32 else ' · 来源歌单')+str(n+1),activity=activity['id'],members=list(members)))
        activity.update(additions=tracks[5:6+index] if task_id==18 else [],exclusions=[tracks[1]] if task_id==18 else [],
            playlist_name=activity['name']+(' · 列表甲' if task_id==32 else ' · 活动歌单'),baseline=tracks[:1]+tracks[8:9] if task_id==32 else [])
        if task_id==32:
            key=f'list-{index+1:03d}'
            playlists[key]=dict(id=key,activity=activity['id'],name=activity['playlist_name'],members=list(activity['baseline']),saved=dict(name=activity['playlist_name'],members=list(activity['baseline'])))
    own=state['items'][-1]['id']
    playlists['personal']=dict(id='personal',activity='personal',name='我的午后收藏',members=[own],saved=dict(name='我的午后收藏',members=[own]))
    state.update(workflow='music_projects',linked_apps=['music','im'],
        execution=dict(assignment=spec['assignment'],instructions=spec['inference']['instructions'],delivery=spec['delivery']),
        world=dict(activities=activities,sources=sources,playlists=playlists,shares=[],messages=[],
            groups=[dict(id=a['group_id'],name=a['group_name'],activity=a['id']) for a in activities]+[dict(id=50,name='自由交流',activity='personal')],
            brief={18:'为三个活动整理歌单：合并活动单列出的来源歌单，按歌曲编号去重，再执行明确的增删要求。使用最终歌曲数量与活动单的歌手署名、日期，按视频次序组成歌单名称；三个字段以下划线连接，日期为 YYYY-MM-DD。保存歌单并分享到对应活动群。',
                   28:'为周末音乐会合并三个来源歌单，按歌曲编号去重，排除标记为不可用的版本，再按视频标准排序。并列保持歌曲首次出现在来源歌单中的顺序；来源次序以活动单为准。保存完整歌单，并分享到对应活动群。',
                   32:f'维护三个活动各自的列表甲。只检查活动单列出的专辑，按视频条件添加合格且尚未入列的歌曲，保留全部原成员。评分阈值为 {state["source"]["threshold"]}/100，时长以整数秒计；同名但不同编号的版本是不同歌曲。保存后把歌单和本次实际新增清单分享到对应活动群。'}[task_id]))
    return state


def apply(state,op,target='',value='',ids=None):
    state=deepcopy(state);w=state['world']
    try:data=json.loads(value) if value else {}
    except (ValueError,TypeError) as exc:raise ValueError('操作内容需要有效 JSON') from exc
    if not isinstance(data,dict):raise ValueError('操作字段无效')
    if op=='playlist.create':
        if set(data)!={'activity','name'} or data['activity'] not in {a['id'] for a in w['activities']} or not isinstance(data['name'],str) or not data['name'].strip() or len(data['name'])>160:
            raise ValueError('请选择活动并填写歌单名称')
        number=state.get('next_playlist',1)
        while f'list-{number:03d}' in w['playlists']:number+=1
        key=f'list-{number:03d}';state['next_playlist']=number+1
        w['playlists'][key]=dict(id=key,activity=data['activity'],name=data['name'].strip(),members=[],saved=None)
        return state
    if op=='group.message':
        if set(data)!={'text'} or not isinstance(data['text'],str) or not data['text'].strip() or len(data['text'])>4000 or target not in {str(g['id']) for g in w['groups']}:
            raise ValueError('请选择有效群聊并填写消息')
        w['messages'].append(dict(id=len(w['messages'])+1,group=int(target),body=data['text'].strip()))
        return state
    playlist=w['playlists'].get(target)
    if not playlist:raise ValueError('歌单不存在')
    if op=='playlist.delete':
        if any(s['playlist']==target for s in w['shares']):raise ValueError('请先撤回此歌单的分享')
        del w['playlists'][target];return state
    if op=='playlist.rename':
        if set(data)!={'name'} or not isinstance(data['name'],str) or not data['name'].strip() or len(data['name'])>160:raise ValueError('请填写歌单名称，最多 160 字')
        playlist['name']=data['name'].strip()
    elif op in ('playlist.add','playlist.remove'):
        selected=data.get('songs')
        if set(data)!={'songs'} or not isinstance(selected,list) or not all(isinstance(x,str) for x in selected) or not set(selected)<={x['id'] for x in state['items']}:raise ValueError('请选择资料库中的歌曲')
        if op=='playlist.add':playlist['members']=list(dict.fromkeys(playlist['members']+selected))
        else:playlist['members']=[x for x in playlist['members'] if x not in selected]
    elif op=='playlist.import':
        source=next((s for s in w['sources'] if s['id']==data.get('source')),None)
        if set(data)!={'source'} or not source:raise ValueError('请选择来源歌单或专辑')
        playlist['members']=list(dict.fromkeys(playlist['members']+source['members']))
    elif op=='playlist.order':
        order=data.get('songs')
        if set(data)!={'songs'} or not isinstance(order,list) or len(order)!=len(playlist['members']) or set(order)!=set(playlist['members']):raise ValueError('排序须包含全部歌单成员且不重复')
        playlist['members']=list(order)
    elif op=='playlist.save':
        if not playlist['members']:raise ValueError('请先为歌单添加歌曲')
        playlist['saved']=dict(name=playlist['name'],members=list(playlist['members']))
        return state
    elif op=='playlist.share':
        if set(data)!={'group'} or data['group'] not in {g['id'] for g in w['groups']}:raise ValueError('请选择活动群')
        if playlist['saved']!=dict(name=playlist['name'],members=playlist['members']):raise ValueError('请先保存歌单中的更改')
        activity=next((a for a in w['activities'] if a['id']==playlist['activity']),None)
        baseline=activity['baseline'] if activity else []
        w['shares'].append(dict(id=f'share-{state.get("next_share",1)}',group=data['group'],playlist=target,name=playlist['name'],members=list(playlist['members']),
            added=[x for x in playlist['members'] if x not in baseline],link=f'playlists/{target}/'))
        state['next_share']=state.get('next_share',1)+1
        return state
    elif op=='playlist.unshare':
        if set(data)!={'share'} or not any(s['id']==data['share'] and s['playlist']==target for s in w['shares']):raise ValueError('分享记录不存在')
        w['shares']=[s for s in w['shares'] if s['id']!=data['share']]
        return state
    else:raise ValueError('未知歌单操作')
    # Save snapshots are retained to expose unsaved changes and stale shares.
    return state
