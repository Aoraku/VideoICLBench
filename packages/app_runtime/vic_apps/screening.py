"""Screening collections, editable playback queue and downloadable timetable."""
from copy import deepcopy
from datetime import datetime,timedelta
import csv
import io
import json
import random
from vic import business
from .domain import initialize
from .communications import file_record

TASKS={35}


def fixture(seed,spec):
    base=business.generate(35,seed);items=[]
    names=['林间清晨','森林里的访客','草地追逐','树下的争执','河岸午后','山谷回声','夜色降临','森林重逢','片尾访谈','导演问答旧版','测试放映片','森林里的访客 · 精简版','夜色降临 · 完整版','往期活动回顾']
    durations=[240,720,480,900,300,840,360,660,750,200,780,420,960,180]
    categories=['乙','乙','甲','甲','乙','甲','甲','乙','甲','甲','乙','甲','乙','甲']
    for i,name in enumerate(names):
        item=deepcopy(base['items'][i%6]);item.update(id=f'film-{i}',record_code=f'FILM-{i+1:03d}',name=name,duration=durations[i],category=categories[i],asset_index=i%6,
            text=f'{name}：社区开放电影放映资料。视频为 Big Buck Bunny 授权片段的循环剪辑，播放时长与资料库显示一致。',edition='本期放映版' if i<11 else '替换版' if i<13 else '往期',batch='2026-02' if i<13 else '2026-01')
        items.append(item)
    base['items']=items;state=initialize(base);ids=[x['id'] for x in state['items']]
    folders=[]
    for i,(name,members) in enumerate([('策展初选',[0,1,2,9]),('社群推荐',[2,3,4,5,10]),('导演补充',[5,6,7,8])]):
        members=[ids[n] for n in members];random.Random(seed+31*i).shuffle(members)
        folders.append(dict(id=f'folder-{i+1}',name=name,members=members))
    state.update(workflow='screening',execution=dict(assignment=spec['assignment'],instructions=spec['inference']['instructions'],delivery=spec['delivery']),
        world=dict(folders=folders,event=dict(title='社区开放电影之夜',starts_at='2026-02-21T19:00:00+08:00',turnaround_seconds=30,short_below_seconds=600,
            exclude=[dict(video=ids[9],reason='导演问答使用现场环节，不播放旧版录像。'),dict(video=ids[10],reason='测试片不进入正式放映。')],
            replacements=[dict(old=ids[1],new=ids[11],reason='按导演要求使用精简版。'),dict(old=ids[6],new=ids[12],reason='使用包含片尾字幕的完整版本。')],
            breaks=[dict(after=ids[4],seconds=600,reason='观众交流'),dict(after=ids[12],seconds=300,reason='设备检查')]),
            queue=dict(name='',members=[],saved=None),timing=dict(starts_at='',turnaround_seconds=0,breaks={}),schedule=None,
            brief='为“社区开放电影之夜”编排片单并交付时间表。按策展初选、社群推荐、导演补充的顺序汇总；同一影片编号只保留首次出现。删除活动单的排除项，替换片占原片在汇总清单中的位置。短片指少于 10 分钟，长片指至少 10 分钟。按视频规则交替编排；标签版本从甲开始，再乙。各组内部保持有效汇总清单中的相对顺序，一组用完后将另一组剩余影片接在末尾。保存活动命名的队列，并按活动单设置开场、换片及指定影片后的休息时长，生成并保存与最终队列一致的时间表。无需等影片播完。'))
    return state


def timetable(state):
    w=state['world'];timing=w['timing'];current=datetime.fromisoformat(timing['starts_at']);rows=[]
    for index,target in enumerate(w['queue']['members']):
        item=state['domain']['objects'][target];end=current+timedelta(seconds=item['duration'])
        gap=timing['turnaround_seconds'] if index+1<len(w['queue']['members']) else 0
        rest=timing['breaks'].get(target,0)
        rows.append(dict(video=target,record_code=item['record_code'],name=item['name'],duration=item['duration'],starts_at=current.isoformat(),ends_at=end.isoformat(),turnaround_seconds=gap,break_seconds=rest))
        current=end+timedelta(seconds=gap+rest)
    return dict(name=w['queue']['name'],members=list(w['queue']['members']),timing=deepcopy(timing),rows=rows,ends_at=current.isoformat())


def timetable_csv(schedule):
    buffer=io.StringIO(newline='');writer=csv.writer(buffer)
    writer.writerow(['序号','影片编号','影片名称','开始时间','结束时间','片长秒','换片秒','休息秒'])
    for i,row in enumerate(schedule['rows'],1):writer.writerow([i,row['record_code'],row['name'],row['starts_at'],row['ends_at'],row['duration'],row['turnaround_seconds'],row['break_seconds']])
    writer.writerow(['活动结束','','',schedule['ends_at']])
    return buffer.getvalue()


def apply(state,op,target='',value='',ids=None):
    state=deepcopy(state);w=state['world'];q=w['queue'];objects=state['domain']['objects'];item_ids={x['id'] for x in state['items']}
    try:data=json.loads(value) if value else {}
    except (ValueError,TypeError) as exc:raise ValueError('操作字段须为 JSON') from exc
    if not isinstance(data,dict):raise ValueError('操作字段无效')
    if op=='queue.import':
        folder=next((f for f in w['folders'] if f['id']==target),None)
        if not folder:raise ValueError('收藏夹不存在')
        q['members']=list(dict.fromkeys(q['members']+folder['members']))
    elif op=='queue.add':
        if target not in item_ids:raise ValueError('影片不存在')
        if target not in q['members']:q['members'].append(target)
    elif op=='queue.remove':
        if target not in q['members']:raise ValueError('影片不在队列中')
        q['members'].remove(target)
    elif op=='queue.replace':
        if target not in q['members'] or set(data)!={'replacement'} or data['replacement'] not in item_ids or data['replacement'] in q['members']:raise ValueError('请选择队列中的影片及不同的替换影片')
        q['members'][q['members'].index(target)]=data['replacement']
    elif op=='queue.order':
        if not isinstance(ids,list) or len(ids)!=len(q['members']) or set(ids)!=set(q['members']):raise ValueError('排序须保留队列全部影片且不得重复')
        q['members']=list(ids)
    elif op=='queue.name':
        if set(data)!={'name'} or not isinstance(data['name'],str) or not data['name'].strip() or len(data['name'])>120:raise ValueError('请填写队列名称')
        q['name']=data['name'].strip()
    elif op=='queue.save':
        if not q['name'] or not q['members']:raise ValueError('请先填写队列名称并加入影片')
        q['saved']=dict(name=q['name'],members=list(q['members']))
    elif op=='timing.save':
        if set(data)!={'starts_at','turnaround_seconds','breaks'}:raise ValueError('请填写开场、换片及休息安排')
        try:start=datetime.fromisoformat(data['starts_at'])
        except (ValueError,TypeError):raise ValueError('开场时间无效')
        if start.tzinfo is None or type(data['turnaround_seconds']) is not int or not 0<=data['turnaround_seconds']<=600 or not isinstance(data['breaks'],dict) or any(k not in q['members'] or type(v) is not int or not 0<v<=3600 for k,v in data['breaks'].items()):raise ValueError('请使用带时区的开场时间及有效的秒数；休息须关联队列中的影片')
        w['timing']=deepcopy(data);w['timing']['starts_at']=start.isoformat()
    elif op=='schedule.save':
        if q['saved']!=dict(name=q['name'],members=q['members']) or not q['members']:raise ValueError('请先保存最终播放队列')
        if not w['timing']['starts_at']:raise ValueError('请先保存放映时间设置')
        if not set(w['timing']['breaks'])<=set(q['members']):raise ValueError('休息安排包含已移出队列的影片，请更新放映时间设置')
        w['schedule']=timetable(state)
        state['domain']['files']['screening-timetable']=file_record(q['name']+'-放映时间表.csv',timetable_csv(w['schedule']))
    else:raise ValueError('未知放映操作')
    return state
