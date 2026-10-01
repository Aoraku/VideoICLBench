"""Trip requests, traveler identities, simulated reservations and real itineraries."""
from copy import deepcopy
from datetime import datetime,timedelta
import json
import random
from vic import business
from .domain import initialize
from .communications import file_record

TASKS={44,51,54}


def fixture(task_id,seed,spec):
    base=business.generate(task_id,seed);items=[]
    names=[('林若宁','Lin','Ruoning'),('陈嘉树','Chen','Jiashu'),('程知夏','Cheng','Zhixia'),('许清和','Xu','Qinghe'),('林若宁（其他部门）','Lin','Ruoning')]
    people=[dict(id=f'TR-{i+1:03d}',name=n,surname=sur,given_name=given,document=f'TEST-PASSPORT-{i+1:04d}',contact=f'traveler{i+1}@example.test',im=10+i) for i,(n,sur,given) in enumerate(names)]
    def route(code,leg,origin,destination,departure,arrival,price,transfers=0):
        item=deepcopy(base['items'][len(items)%6]);item.update(id=code,record_code=code,name=code,leg=leg,origin=origin,destination=destination,depart_at=departure,arrive_at=arrival,duration=int((datetime.fromisoformat(arrival)-datetime.fromisoformat(departure)).total_seconds()/60),price=price,transfers=transfers,seat='二等座',available=True);items.append(item)
    def stamp(clock,day='24'):return f'2026-02-{day}T{clock}:00+08:00'
    legs=[];requests=[]
    if task_id==51:
        cities=[('北京','济南'),('济南','南京'),('南京','上海')]
        rows=[ [('G101','07:00','09:30',80),('G102','09:00','09:50',180),('G103','09:15','10:20',160),('G104','09:55','10:25',20)],
               [('G201','11:00','13:40',60),('G202','11:20','13:10',150),('G203','11:50','13:50',130),('G204','11:55','14:20',10)],
               [('G301','15:10','18:00',50),('G302','15:00','17:00',150),('G303','15:40','18:10',100),('G304','16:00','19:00',30),('G305','15:45','17:30',250)] ]
        for i,choices in enumerate(rows):
            origin,destination=cities[i];leg=f'leg-{i+1}'
            for code,dep,arr,price in choices:route(code,leg,origin,destination,stamp(dep),stamp(arr),price)
            legs.append(dict(id=leg,name=f'第 {i+1} 段 · {origin} → {destination}',origin=origin,destination=destination,meeting_start=stamp(['10:30','14:30','18:20'][i]),meeting_end=stamp(['11:00','15:00','18:50'][i]),passengers=['TR-001'],cost_center='CC-研发',contact=people[0]['contact'],candidates=[]))
    elif task_id==44:
        for i,(origin,dest,day,dep,arr) in enumerate([('北京','南京','24','08:00','12:00'),('南京','上海','25','09:00','11:00')]):
            leg=f'leg-{i+1}';route(f'G44{i+1}',leg,origin,dest,stamp(dep,day),stamp(arr,day),280+i*40)
            legs.append(dict(id=leg,name=f'第 {i+1} 段 · {origin} → {dest}',origin=origin,destination=dest,passengers=[p['id'] for p in people[:4]],cost_center='CC-研发',contact='trip-coordinator@example.test',candidates=[]))
    else:
        for i,(price,transfers) in enumerate([(120,0),(250,1),(500,2),(200,3),(350,0),(80,1)]):
            key=f'AP-{i+1:03d}';departure=datetime.fromisoformat(stamp('08:00'))+timedelta(days=i)
            route(f'G54{i+1}',key,'北京',['济南','南京','上海'][i%3],departure.isoformat(),(departure+timedelta(minutes=120+30*i)).isoformat(),price,transfers)
            p=people[i%4];requests.append(dict(id=key,person=p['id'],recipient=p['im'],cost_center=['CC-研发','CC-运营','CC-设计'][i%3],contact=p['contact'],route_code=f'G54{i+1}',purpose=['客户需求访谈','项目评审','合作方培训'][i%3],batch='2026-02'))
    random.Random(seed).shuffle(items);base['items']=items;state=initialize(base)
    by_code={r['record_code']:r['id'] for r in state['items']}
    for leg in legs:leg['candidates']=[r['id'] for r in state['items'] if r['leg']==leg['id']]
    for request in requests:request['route']=by_code[request['route_code']]
    profiles={p['id']:dict(full_name=(p['surname']+p['given_name'] if task_id==44 else p['surname']+' '+p['given_name']),document=p['document'],contact=p['contact']) for p in people}
    brief={44:'为四位同事维护两段出差预订草稿。以旅客编号和模拟证件号核对身份，按视频姓名格式同时保存常用旅客资料及每段预订的乘客名单。出行通知列出的四人每段都参加，其他部门同名旅客不参加。按通知填写成本中心和联系人；保存两张草稿及合并行程单，无需确认或付款。',
        51:'为 TR-001 规划北京、济南、南京、上海三段出行。所有时间为北京时间；首段不得早于 2026-02-24 07:00。每段票价不超过 200 元，到达不得晚于该地会议开始。下一段出发既不得早于上一场会议结束，也不得早于上一段到达后 90 分钟。按段顺序，在仍可完成全部后续行程的候选中应用视频选择标准；并列按车次编号升序。核对旅客、成本中心和联系方式后完成模拟确认，保存完整行程单。',
        54:'处理本期六份差旅申请。价格阈值为 250 元，按视频条件决定确认集合；只为命中申请填写对应旅客、模拟证件、成本中心与联系信息，保存并模拟确认。将真实预订号回填原申请，把行程单发给申请人，最后保存合并行程单。非命中申请保持待处理。'}[task_id]
    notices=[]
    if task_id==44:
        notices=[dict(id='notice-trip',recipient=10,title='两段出差安排',slot='',body='出行人员：'+ '、'.join(p['id']+' '+p['name']+'（'+p['document']+'）' for p in people[:4])+'。两段均为以上四人。成本中心：CC-研发；联系人：trip-coordinator@example.test。\n'+'\n'.join(leg['name']+'；指定车次 '+next(r['record_code'] for r in state['items'] if r['id']==leg['candidates'][0]) for leg in legs))]
    elif task_id==54:
        notices=[dict(id='notice-'+r['id'],recipient=r['recipient'],title=r['id']+' · '+r['purpose'],slot=r['id'],body=f'{r["person"]} 申请 {r["route_code"]}，成本中心 {r["cost_center"]}，联系邮箱 {r["contact"]}。请按本期审批标准处理，并回传确认后的行程单。') for r in requests]
    state.update(workflow='travel_projects',linked_apps=['travel'] if task_id==51 else ['travel','im'],execution=dict(assignment=spec['assignment'],instructions=spec['inference']['instructions'],delivery=spec['delivery']),world=dict(people=people,profiles=profiles,legs=legs,requests=requests,notices=notices,bookings={},approvals={},receipts=[],discussion=[],itinerary=None,cost_centers=['CC-研发','CC-运营','CC-设计'],brief=brief,threshold=250,connection_minutes=90,earliest_departure=stamp('07:00'),budget=200))
    return state


def booking_snapshot(booking):return {key:deepcopy(booking[key]) for key in ('slot','route','passengers','cost_center','contact')}


def booking_text(state,booking):
    r=state['domain']['objects'][booking['route']]
    rows=[f'# {booking["id"]} · '+('已确认行程' if booking['status']=='confirmed' else '预订草稿'),f'关联：{booking["slot"]}',f'车次：{r["record_code"]} · {r["origin"]} → {r["destination"]}',f'出发：{r["depart_at"]}',f'到达：{r["arrive_at"]}',f'席别：{r["seat"]}；单人票价：{r["price"]} 元',f'成本中心：{booking["cost_center"]}',f'联系邮箱：{booking["contact"]}',f'模拟确认号：{booking.get("confirmation","")}', '','## 乘客']
    for p in booking['passengers']:rows.append(f'{p["id"]} · {p["full_name"]} · {p["document"]} · {p["contact"]}')
    rows+=['',f'合计：{r["price"]*len(booking["passengers"])} 元','本行程为隔离账户中的模拟差旅记录。']
    return '\n'.join(rows)+'\n'


def itinerary_text(state,ids):return '# 完整出差行程单\n\n'+'\n---\n\n'.join(booking_text(state,state['world']['bookings'][id]) for id in ids)


def apply(state,op,target='',value='',ids=None):
    state=deepcopy(state);w=state['world'];people={p['id']:p for p in w['people']};routes=state['domain']['objects']
    try:data=json.loads(value) if value else {}
    except (ValueError,TypeError) as exc:raise ValueError('操作内容须为 JSON') from exc
    if not isinstance(data,dict):raise ValueError('操作字段无效')
    if op=='profile.save':
        if state['task_id']!=44 or target not in people or set(data)!={'full_name'} or not isinstance(data['full_name'],str) or not 1<=len(data['full_name'])<=100:raise ValueError('请选择旅客并填写显示姓名')
        w['profiles'][target]['full_name']=data['full_name'];return state
    if op=='message.send':
        if target not in [str(p['im']) for p in w['people']] or set(data)!={'text'} or not isinstance(data['text'],str) or not data['text'].strip() or len(data['text'])>4000:raise ValueError('请选择联系人并填写消息')
        w['discussion'].append(dict(id=len(w['discussion'])+1,recipient=int(target),body=data['text'].strip()));return state
    if op=='booking.create':
        slots={x['id']:x for x in (w['requests'] if state['task_id']==54 else w['legs'])}
        if target not in slots or set(data)!={'route'} or data['route'] not in {r['id'] for r in state['items']} or routes[data['route']]['leg']!=target:raise ValueError('请选择当前申请或行程段对应的车次')
        if any(b['slot']==target for b in w['bookings'].values()):raise ValueError('此行程已有预订，请先移除不需要的预订')
        key=f'BOOK-{state.get("next_booking",1):03d}';state['next_booking']=state.get('next_booking',1)+1
        w['bookings'][key]=dict(id=key,slot=target,route=data['route'],passengers=[],cost_center='',contact='',status='draft',confirmation='',saved=None);return state
    if op=='approval.record':
        if state['task_id']!=54 or target not in {r['id'] for r in w['requests']} or set(data)!={'booking'} or data['booking'] not in w['bookings'] or w['bookings'][data['booking']]['status']!='confirmed':raise ValueError('请关联已确认预订')
        w['approvals'][target]=data['booking'];return state
    if op=='approval.clear':w['approvals'].pop(target,None);return state
    if op=='receipt.withdraw':
        if target not in {r['id'] for r in w['receipts']}:raise ValueError('通知不存在')
        w['receipts']=[r for r in w['receipts'] if r['id']!=target];return state
    if op=='itinerary.save':
        if set(data)!={'bookings'} or not isinstance(data['bookings'],list) or not data['bookings'] or len(data['bookings'])!=len(set(data['bookings'])) or any(id not in w['bookings'] or w['bookings'][id]['saved']!=booking_snapshot(w['bookings'][id]) for id in data['bookings']):raise ValueError('请选择已保存且没有待保存编辑的预订')
        ordered=sorted(data['bookings'],key=lambda id:(routes[w['bookings'][id]['route']]['depart_at'],id))
        body=itinerary_text(state,ordered);w['itinerary']=dict(bookings=ordered,body=body)
        state['domain']['files']['travel-itinerary']=file_record('完整出差行程单.md',body);return state
    if op=='itinerary.clear':w['itinerary']=None;state['domain']['files'].pop('travel-itinerary',None);return state
    if target not in w['bookings']:raise ValueError('预订不存在')
    b=w['bookings'][target]
    if op=='booking.delete':
        if target in w['approvals'].values() or any(r['booking']==target for r in w['receipts']) or (w['itinerary'] and target in w['itinerary']['bookings']):raise ValueError('请先撤回通知、清除申请回填及合并行程单，避免留下无效引用')
        del w['bookings'][target];state['domain']['files'].pop('booking-'+target,None);return state
    if op=='receipt.send':
        if state['task_id']!=54 or b['status']!='confirmed' or set(data)!={'recipient'} or data['recipient'] not in [p['im'] for p in w['people']]:raise ValueError('请先确认预订并选择收件人')
        if any(r['booking']==target and r['recipient']==data['recipient'] for r in w['receipts']):raise ValueError('此行程单已发给该联系人')
        key=f'receipt-{state.get("next_receipt",1):03d}';state['next_receipt']=state.get('next_receipt',1)+1
        w['receipts'].append(dict(id=key,booking=target,recipient=data['recipient'],body=booking_text(state,b),link='bookings/'+target));return state
    if b['status']=='confirmed':raise ValueError('预订已确认；如需重做，请先清除关联记录并取消预订')
    if op=='booking.passengers':
        if set(data)!={'passengers','cost_center','contact'} or data['cost_center'] not in w['cost_centers'] or not isinstance(data['contact'],str) or not 1<=len(data['contact'])<=200 or not isinstance(data['passengers'],list) or not data['passengers']:raise ValueError('请填写乘客、成本中心及联系邮箱')
        seen=set()
        for p in data['passengers']:
            if not isinstance(p,dict) or set(p)!={'id','full_name','document','contact'} or p['id'] not in people or p['id'] in seen or any(not isinstance(p[k],str) or not 1<=len(p[k])<=200 for k in ('full_name','document','contact')):raise ValueError('旅客资料无效或重复')
            seen.add(p['id'])
        b.update(deepcopy(data))
    elif op=='booking.save':
        if not b['passengers'] or not b['cost_center'] or not b['contact']:raise ValueError('请先填写乘客与联系资料')
        b['saved']=booking_snapshot(b);state['domain']['files']['booking-'+target]=file_record(target+'-行程单.md',booking_text(state,b))
    elif op=='booking.confirm':
        if state['task_id']==44:raise ValueError('本次只需保存预订草稿')
        if not b['passengers'] or b['saved']!=booking_snapshot(b):raise ValueError('请先保存最新旅客资料及预订草稿')
        b['status']='confirmed';b['confirmation']='SIM-'+target
        state['domain']['files']['booking-'+target]=file_record(target+'-行程单.md',booking_text(state,b))
    else:raise ValueError('未知差旅操作')
    return state
