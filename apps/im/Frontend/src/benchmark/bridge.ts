/** Isolated business API adapter for the upstream Next.js interface. */
const native =
  typeof window !== "undefined" &&
  process.env.NEXT_PUBLIC_VIC_BENCHMARK === "1";
let run = "",
  token = "";
if (native) {
  run =
    new URLSearchParams(location.search).get("run") ||
    sessionStorage.getItem("vic-im-run") ||
    "";
  token =
    location.hash.slice(1) || sessionStorage.getItem("vic-im-token") || "";
  if (run && token) {
    sessionStorage.setItem("vic-im-run", run);
    sessionStorage.setItem("vic-im-token", token);
    localStorage.setItem("token", token);
    localStorage.setItem("user_id", "1");
    localStorage.setItem("username", "周予安");
  }
}
export const nativeIM = native;
async function business(path = "", body?: object) {
  const response = await globalThis.fetch(`/api/runs/${run}${path}`, {
    method: body ? "POST" : "GET",
    headers: {
      Authorization: `Bearer ${token}`,
      "Content-Type": "application/json",
    },
    body: body ? JSON.stringify(body) : undefined,
  });
  const data = await response.json();
  if (!response.ok) throw Error(data.detail);
  if (typeof data.epoch === 'number') sessionStorage.setItem('vic-im-epoch', String(data.epoch));
  return data;
}
export async function imCommand(
  op: string,
  target = "",
  value = "",
  ids: string[] = [],
) {
  const current = await business();
  return business("/commands", {
    op,
    target,
    value,
    ids,
    epoch: current.epoch,
    action_id: crypto.randomUUID(),
  });
}
export async function nativeFetch(
  input: RequestInfo | URL,
  init?: RequestInit,
): Promise<Response> {
  if (!native || !run || !String(input).startsWith("/api/"))
    return globalThis.fetch(input, init);
  const respond = (data: object, status = 200) =>
    new Response(JSON.stringify({ code: 0, ...data }), {
      status,
      headers: { "Content-Type": "application/json" },
    });
  try {
    const { state: s } = await business(),
      path = new URL(String(input), location.origin).pathname.replace(
        /\/$/,
        "",
      ),
      method = init?.method || "GET",
      body = typeof init?.body === "string" ? JSON.parse(init.body) : {};
    if(s.workflow==='payment_projects') {
      const peerId=Number(path.match(/^\/api\/conversations\/(\d+)/)?.[1]),person=s.world.people.find((p:any)=>p.id===peerId),stamp=1790899200;
      if(method==='GET' && path==='/api/workspace')return respond({instructions:s.world.brief,bank:`/native/product/bank/${run}#${token}`});
      if(method==='GET' && path==='/api/friends')return respond({friends:s.world.people.map((p:any)=>({user_id:p.id,username:p.name,group:p.role}))});
      if(method==='GET' && path==='/api/conversations')return respond({conversations:s.world.people.map((p:any)=>({conversation_id:p.id,type:'private',name:p.name,peer_user:{user_id:p.id,username:p.name},other_user_id:p.id,unread_count:0,last_message:{content:s.world.receipts.some((r:any)=>r.recipient===p.id)?'十月付款对账清单':'账单通知与付款核对',created_at:stamp}}))});
      if(method==='GET' && path.endsWith('/messages') && person) {
        const requests=s.world.bills.map((b:any,i:number)=>({...b,index:i})).filter((b:any)=>b.coordinator===peerId).map((b:any)=>{
          const payee=s.domain.objects[b.payee],payer=s.world.accounts.find((a:any)=>a.id===b.payer);
          return {msg_id:1000+b.index,sender_id:peerId,sender_name:person.name,created_at:stamp+b.index,content:b.id+' · '+b.purpose,payment_request:{id:b.id,title:b.project+' · '+b.purpose,body:'账单 '+b.id+' · 批次 '+b.batch+'\n供应商：'+payee.record_code+' · '+payee.name+' · '+payee.company+'\n付款账户：'+payer.name+' · '+payer.number+'\n金额：'+(b.cents/100).toFixed(2)+' 元\n账单附言：'+b.note,url:`/native/product/bank/${run}?bill=${encodeURIComponent(b.id)}#${token}`}};
        });
        const receipts=s.world.receipts.filter((r:any)=>r.recipient===peerId).map((r:any,i:number)=>({msg_id:10000+Number(r.id.split('-')[1]),sender_id:1,sender_name:'周予安',created_at:stamp+100+i,content:'十月付款对账清单',payment_share:{id:r.id,body:r.body,url:`/native/product/bank/${run}?report=1#${token}`}}));
        const discussion=s.world.discussion.filter((m:any)=>m.recipient===peerId).map((m:any)=>({msg_id:20000+m.id,sender_id:1,sender_name:'周予安',created_at:stamp+1000+m.id,content:m.body}));
        return respond({messages:[...requests,...receipts,...discussion].sort((a:any,b:any)=>b.created_at-a.created_at)});
      }
      const profile=s.world.people.find((p:any)=>p.id===Number(path.match(/\/user\/(\d+)/)?.[1]));
      if(method==='GET' && profile)return respond({user_id:profile.id,username:profile.name,bio:profile.role});
      if(method==='POST' && path.endsWith('/messages') && person){await imCommand('message.send',String(peerId),JSON.stringify({text:body.content}));return respond({msg_id:20000+s.world.discussion.length+1});}
    }
    if(s.workflow==='shop_projects') {
      const peerId=Number(path.match(/^\/api\/conversations\/(\d+)/)?.[1]),person=s.world.people.find((p:any)=>p.id===peerId),stamp=1790726400;
      if(method==='GET' && path==='/api/workspace')return respond({instructions:'按每份采购通知的商品范围与标签整理用品，再把包含实际数量、收藏状态及商品链接的交接单发给通知联系人。',shop:`/native/product/shop/${run}#${token}`});
      if(method==='GET' && path==='/api/friends')return respond({friends:s.world.people.map((p:any)=>({user_id:p.id,username:p.name,group:'采购联系人'}))});
      if(method==='GET' && path==='/api/conversations')return respond({conversations:s.world.people.map((p:any)=>({conversation_id:p.id,type:'private',name:p.name,peer_user:{user_id:p.id,username:p.name},other_user_id:p.id,unread_count:0,last_message:{content:s.world.receipts.filter((r:any)=>r.recipient===p.id).at(-1)?.request || '本期采购整理与交接',created_at:stamp}}))});
      if(method==='GET' && path.endsWith('/messages') && person) {
        const requests=s.world.requests.map((r:any,i:number)=>({...r,index:i})).filter((r:any)=>r.recipient===peerId).map((r:any)=>({msg_id:1000+r.index,sender_id:peerId,sender_name:person.name,created_at:stamp+r.index,content:r.title,shopping_request:{id:r.id,title:r.title,body:'清单 '+r.id+' · 指定标签：'+r.label+'\n新增入车使用下列数量，已在车内的不重复添加。\n'+r.products.map((id:string)=>{const p=s.domain.objects[id];return p.record_code+' · '+p.name+' · '+p.spec+' × '+r.quantities[id];}).join('\n'),url:`/native/product/shop/${run}?request=${encodeURIComponent(r.id)}#${token}`}}));
        const receipts=s.world.receipts.filter((r:any)=>r.recipient===peerId).map((r:any,i:number)=>({msg_id:10000+Number(r.id.split('-')[1]),sender_id:1,sender_name:'周予安',created_at:stamp+100+i,content:'采购交接：'+r.request,shopping_share:{id:r.id,title:s.world.requests.find((q:any)=>q.id===r.request).title,body:r.body,url:`/native/product/shop/${run}?handover=${encodeURIComponent(r.request)}#${token}`}}));
        const discussion=s.world.discussion.filter((m:any)=>m.recipient===peerId).map((m:any)=>({msg_id:20000+m.id,sender_id:1,sender_name:'周予安',created_at:stamp+1000+m.id,content:m.body}));
        return respond({messages:[...requests,...receipts,...discussion].sort((a:any,b:any)=>b.created_at-a.created_at)});
      }
      const profile=s.world.people.find((p:any)=>p.id===Number(path.match(/\/user\/(\d+)/)?.[1]));
      if(method==='GET' && profile)return respond({user_id:profile.id,username:profile.name,bio:'采购联系人'});
      if(method==='POST' && path.endsWith('/messages') && person){await imCommand('message.send',String(peerId),JSON.stringify({text:body.content}));return respond({msg_id:20000+s.world.discussion.length+1});}
    }
    if(s.workflow==='procurement') {
      const peerId=Number(path.match(/^\/api\/conversations\/(\d+)/)?.[1]);
      const department=s.world.departments.find((d:any)=>d.im===peerId);
      if(method==='GET' && path==='/api/workspace')return respond({instructions:'各部门的采购申请、有效更正与追加申请。消息卡片中的编号、商品规格和数量与采购系统一致；打开申请链接可核对原始单据。',shop:`/native/product/shop/${run}#${token}`});
      if(method==='GET' && path==='/api/friends')return respond({friends:s.world.departments.map((d:any)=>({user_id:d.im,username:d.contact,group:d.name+'采购联系人'}))});
      if(method==='GET' && path==='/api/conversations')return respond({conversations:s.world.departments.map((d:any)=>({conversation_id:d.im,type:'private',name:d.contact,peer_user:{user_id:d.im,username:d.contact},other_user_id:d.im,unread_count:0,last_message:{content:d.name+' · 采购申请与更正',created_at:1790726400}}))});
      if(method==='GET' && path.endsWith('/messages') && department) {
        const requests=s.world.requests.map((r:any,i:number)=>({...r,index:i})).filter((r:any)=>r.department===department.id).map((r:any)=>{
          const title=r.number+' · 第 '+r.revision+' 版';
          const body=department.name+' · '+r.date+'\n申请编号：'+r.id+'\n'+r.lines.map((line:any)=>{const p=s.world.products.find((p:any)=>p.id===line.sku);return p.name+' · '+p.spec+' · '+p.id+' × '+line.quantity;}).join('\n');
          return {msg_id:1000+r.index,sender_id:peerId,sender_name:department.contact,created_at:Date.parse(r.date+'T08:00:00+08:00')/1000+r.index,content:title,procurement_request:{id:r.id,title,body,url:`/native/product/shop/${run}?request=${encodeURIComponent(r.id)}#${token}`}};
        });
        const discussion=s.world.discussion.filter((m:any)=>m.recipient===peerId).map((m:any)=>({msg_id:20000+m.id,sender_id:1,sender_name:'周予安',created_at:1790726400+1000+m.id,content:m.body}));
        return respond({messages:[...requests,...discussion].sort((a:any,b:any)=>b.created_at-a.created_at)});
      }
      const profile=s.world.departments.find((d:any)=>d.im===Number(path.match(/\/user\/(\d+)/)?.[1]));
      if(method==='GET' && profile)return respond({user_id:profile.im,username:profile.contact,bio:profile.name+'采购联系人'});
      if(method==='POST' && path.endsWith('/messages') && department){await imCommand('message.send',String(peerId),JSON.stringify({text:body.content}));return respond({msg_id:20000+s.world.discussion.length+1});}
    }
    if(s.workflow==='travel_projects') {
      const peerId=Number(path.match(/^\/api\/conversations\/(\d+)/)?.[1]);
      const person=s.world.people.find((p:any)=>p.im===peerId),stamp=1771891200;
      if(method==='GET' && path==='/api/workspace')return respond({instructions:'出差通知、旅客编号与差旅审批。申请链接打开行远旅行中的对应安排；确认行程单包含实际预订号与乘客资料。',travel:`/native/product/travel/${run}#${token}`});
      if(method==='GET' && path==='/api/friends')return respond({friends:s.world.people.map((p:any)=>({user_id:p.im,username:p.name,group:'旅客 '+p.id}))});
      if(method==='GET' && path==='/api/conversations')return respond({conversations:s.world.people.map((p:any)=>({conversation_id:p.im,type:'private',name:p.name,peer_user:{user_id:p.im,username:p.name},other_user_id:p.im,unread_count:0,last_message:{content:s.world.receipts.filter((r:any)=>r.recipient===p.im).at(-1)?.booking || '出差安排与审批',created_at:stamp}}))});
      if(method==='GET' && path.endsWith('/messages') && person) {
        const notices=s.world.notices.map((n:any,i:number)=>({...n,index:i})).filter((n:any)=>n.recipient===peerId).map((n:any)=>({msg_id:1000+n.index,sender_id:peerId,sender_name:person.name,created_at:stamp+n.index,content:n.title+'\n'+n.body,travel_request:{id:n.id,title:n.title,url:`/native/product/travel/${run}${n.slot?'?request='+encodeURIComponent(n.slot):''}#${token}`}}));
        const receipts=s.world.receipts.filter((r:any)=>r.recipient===peerId).map((r:any,i:number)=>({msg_id:10000+Number(r.id.split('-')[1]),sender_id:1,sender_name:'周予安',created_at:stamp+100+i,content:'出差行程单：'+r.booking,travel_share:{id:r.id,booking:r.booking,body:r.body,url:`/native/product/travel/${run}?booking=${encodeURIComponent(r.booking)}#${token}`}}));
        const discussion=s.world.discussion.filter((m:any)=>m.recipient===peerId).map((m:any)=>({msg_id:20000+m.id,sender_id:1,sender_name:'周予安',created_at:stamp+1000+m.id,content:m.body}));
        return respond({messages:[...notices,...receipts,...discussion].sort((a:any,b:any)=>b.created_at-a.created_at)});
      }
      const profile=s.world.people.find((p:any)=>p.im===Number(path.match(/\/user\/(\d+)/)?.[1]));
      if(method==='GET' && profile)return respond({user_id:profile.im,username:profile.name,bio:'旅客 '+profile.id});
      if(method==='POST' && path.endsWith('/messages') && person){await imCommand('message.send',String(peerId),JSON.stringify({text:body.content}));return respond({msg_id:20000+s.world.discussion.length+1});}
    }
    if(s.workflow==='studio_projects') {
      const peerId=Number(path.match(/^\/api\/conversations\/(\d+)/)?.[1]);
      const person=s.world.people.find((a:any)=>a.id===peerId),stamp=1770681600;
      if(method==='GET' && path==='/api/workspace')return respond({instructions:'查看项目生成结果及其交付记录。结果卡片包含完整代码，链接可打开 Studio 中的对应源文件。',studio:`/native/product/studio/${run}#${token}`});
      if(method==='GET' && path==='/api/friends')return respond({friends:s.world.people.map((a:any)=>({user_id:a.id,username:a.name,group:'项目联系人'}))});
      if(method==='GET' && path==='/api/conversations')return respond({conversations:s.world.people.map((a:any)=>({conversation_id:a.id,type:'private',name:a.name,peer_user:{user_id:a.id,username:a.name},other_user_id:a.id,unread_count:0,last_message:{content:s.world.receipts.filter((n:any)=>n.recipient===a.id).at(-1)?.name || '项目结果交付',created_at:stamp}}))});
      if(method==='GET' && path.endsWith('/messages') && person) {
        const receipts=s.world.receipts.filter((n:any)=>n.recipient===peerId).map((n:any,i:number)=>({msg_id:10000+Number(n.id.split('-')[1]),sender_id:1,sender_name:'周予安',created_at:stamp+i+1,content:'生成结果：'+n.record_code+' · '+n.name,
          studio_share:{id:n.id,target:n.target,name:n.name,record_code:n.record_code,body:n.body,url:`/native/product/studio/${run}?output=${encodeURIComponent(n.target)}#${token}`}}));
        const discussion=s.world.discussion.filter((m:any)=>m.recipient===peerId).map((m:any)=>({msg_id:20000+m.id,sender_id:1,sender_name:'周予安',created_at:stamp+1000+m.id,content:m.body}));
        return respond({messages:[...receipts,...discussion].sort((a:any,b:any)=>b.created_at-a.created_at)});
      }
      const profile=s.world.people.find((a:any)=>a.id===Number(path.match(/\/user\/(\d+)/)?.[1]));
      if(method==='GET' && profile)return respond({user_id:profile.id,username:profile.name,bio:'项目联系人'});
      if(method==='POST' && path.endsWith('/messages') && person){await imCommand('message.send',String(peerId),JSON.stringify({text:body.content}));return respond({msg_id:20000+s.world.discussion.length+1});}
    }
    if(s.workflow==='publishing') {
      const peerId=Number(path.match(/^\/api\/conversations\/(\d+)/)?.[1]);
      const author=s.world.authors.find((a:any)=>a.id===peerId);
      const stamp=Date.parse(s.world.reference_time)/1000;
      if(method==='GET' && path==='/api/workspace')return respond({instructions:'栏目文章的发布回执与作者沟通。通知卡片中的链接打开实际发布正文。',blog:`/native/product/blog/${run}#${token}`});
      if(method==='GET' && path==='/api/friends')return respond({friends:s.world.authors.map((a:any)=>({user_id:a.id,username:a.name,group:'稿件作者 · '+a.account}))});
      if(method==='GET' && path==='/api/conversations')return respond({conversations:s.world.authors.map((a:any)=>({conversation_id:a.id,type:'private',name:a.name,peer_user:{user_id:a.id,username:a.name},other_user_id:a.id,unread_count:0,last_message:{content:s.world.notifications.filter((n:any)=>n.recipient===a.id).at(-1)?.title || '稿件发布沟通',created_at:stamp}}))});
      if(method==='GET' && path.endsWith('/messages') && author) {
        const notices=s.world.notifications.filter((n:any)=>n.recipient===peerId).map((n:any,i:number)=>({msg_id:10000+Number(n.id.split('-')[1]),sender_id:1,sender_name:'周予安',created_at:stamp+i+1,content:'文章已发布：'+n.title,
          publication_share:{id:n.publication,title:n.title,summary:n.summary,publish_at:n.publish_at,url:`/native/product/blog/${run}?post=${encodeURIComponent(n.publication)}#${token}`}}));
        const discussion=s.world.discussion.filter((m:any)=>m.recipient===peerId).map((m:any)=>({msg_id:20000+m.id,sender_id:1,sender_name:'周予安',created_at:stamp+1000+m.id,content:m.body}));
        return respond({messages:[...notices,...discussion].sort((a:any,b:any)=>b.created_at-a.created_at)});
      }
      const profile=s.world.authors.find((a:any)=>a.id===Number(path.match(/\/user\/(\d+)/)?.[1]));
      if(method==='GET' && profile)return respond({user_id:profile.id,username:profile.name,bio:'稿件作者 · '+profile.account});
      if(method==='POST' && path.endsWith('/messages') && author){await imCommand('message.send',String(peerId),JSON.stringify({text:body.content}));return respond({msg_id:20000+s.world.discussion.length+1});}
    }
    if(s.workflow==='music_projects') {
      const groupId=Number(path.match(/^\/api\/conversations\/(\d+)/)?.[1]);
      const group=s.world.groups.find((g:any)=>g.id===groupId);
      const musicHome=`/native/music/${run}/#${token}`;
      const stamp=1770681600;
      if(method==='GET' && path==='/api/workspace')return respond({instructions:'活动歌单与筹备讨论。分享中的链接会打开对应音乐歌单，歌曲清单保留发送时的内容。',music:musicHome});
      if(method==='GET' && path==='/api/friends')return respond({friends:[]});
      if(method==='GET' && path==='/api/conversations')return respond({conversations:s.world.groups.map((g:any)=>({
        conversation_id:g.id,type:'group',name:g.name,unread_count:0,
        last_message:{content:s.world.shares.filter((share:any)=>share.group===g.id).at(-1)?.name || '活动音乐筹备',created_at:stamp}
      }))});
      if(method==='GET' && path.endsWith('/messages') && group) {
        const track=(id:string)=>{const o=s.domain.objects[id];return `${o.name} · ${o.edition} · ${o.record_code}`;};
        const shares=s.world.shares.filter((share:any)=>share.group===groupId).map((share:any,i:number)=>({
          msg_id:10000+Number(share.id.split('-')[1]),sender_id:1,sender_name:'周予安',created_at:stamp+i+1,
          content:`分享歌单：${share.name}`,music_share:{name:share.name,count:share.members.length,tracks:share.members.map(track),added:share.added.map(track),url:`/native/music/${run}/${share.link}#${token}`}
        }));
        const messages=s.world.messages.filter((m:any)=>m.group===groupId).map((m:any)=>({msg_id:20000+m.id,sender_id:1,sender_name:'周予安',created_at:stamp+1000+m.id,content:m.body}));
        return respond({messages:[...shares,...messages].sort((a:any,b:any)=>b.created_at-a.created_at)});
      }
      if(method==='GET' && path.endsWith('/group') && group)return respond({name:group.name,owner_id:2,created_at:stamp,description:'活动筹备与音乐分享',announcements:[],members:[{user_id:1,username:'周予安',role:'member'},{user_id:2,username:'活动协调员',role:'owner'}]});
      if(method==='POST' && path.endsWith('/messages') && group) {
        await imCommand('group.message',String(groupId),JSON.stringify({text:body.content}));return respond({msg_id:20000+s.world.messages.length+1});
      }
    }
    const projectReceipts = s.v2_worksets && s.task_id === 16;
    const projectGroups = s.workflow === 'communications' && s.task_id === 15;
    const scopeForConversation = (id: number) => projectReceipts ? s.scopes[id - 10] : undefined;
    const user = (i: number) => ({
      user_id: 10 + i,
      username: s.items[i].name,
      avatar: undefined,
      group: `${projectGroups ? s.items[i].project_name+' · '+s.items[i].account+' · ' : ''}最近联系 ${String(s.items[i].last_contact_at).replace('T', ' ').slice(0, 16)} UTC · 初始未读 ${s.items[i].unread}`,
    });
    if(projectGroups) {
      const groupId=path.match(/^\/api\/conversations\/(\d+)/)?.[1];
      const group=groupId ? s.world.groups[groupId] : undefined;
      const stamp=Date.parse(s.source.reference_time)/1000;
      if(method==='GET' && path==='/api/workspace')return respond({instructions:s.world.brief,projects:true});
      if(method==='GET' && path==='/api/projects')return respond({projects:s.world.projects,candidates:s.items.map((item:any,i:number)=>({...user(i),object_id:item.id,project:item.project,account:item.account,unread:item.unread,last_contact_at:item.last_contact_at}))});
      if(method==='GET' && path==='/api/conversations')return respond({conversations:[
        {conversation_id:2,type:'private',name:'项目启动通知',peer_user:{user_id:2,username:'项目协调员'},other_user_id:2,unread_count:3,last_message:{content:'三个项目的工作群、公告和资料待准备',created_at:stamp}},
        ...Object.values(s.world.groups).map((g:any)=>({conversation_id:g.id,type:'group',name:g.name,unread_count:0,last_message:{content:g.messages.at(-1)?.body || '工作群已创建',created_at:stamp}}))
      ]});
      if(method==='GET' && path.endsWith('/messages')) {
        if(groupId==='2')return respond({messages:s.world.projects.map((p:any,i:number)=>({msg_id:5000+i,sender_id:2,sender_name:'项目协调员',created_at:stamp+i,
          content:`项目 ${p.id}：${p.name}\n请从项目通知中的候选名单选择三人，建立“${p.group_name}”。\n群公告：${p.announcement}\n项目资料：${p.material_link}`})).reverse()});
        return respond({messages:(group?.messages||[]).map((m:any)=>({msg_id:10000+m.id,sender_id:1,sender_name:'周予安',created_at:stamp+m.id,content:m.body})).reverse()});
      }
      if(method==='GET' && path.endsWith('/group') && group)return respond({name:group.name,owner_id:1,created_at:stamp,description:'项目工作群',
        announcements:group.announcement?[{id:1,content:group.announcement,publisher_name:'周予安',created_at:stamp}]:[],
        members:[{user_id:1,username:'周予安',role:'owner'},...s.items.flatMap((item:any,i:number)=>group.members.includes(item.id)?[{...user(i),role:'member'}]:[])]});
      if(method==='POST' && path==='/api/conversations' && Array.isArray(body.member_ids)) {
        const ids=body.member_ids.map((id:number)=>s.items[id-10]?.id);
        if(ids.some((id:any)=>!id))throw Error('联系人不存在');
        const next=await imCommand('group.create','',JSON.stringify({name:body.name,members:ids}));
        return respond({conversation_id:100+next.state.next_group-1});
      }
      if(method==='PUT' && path.endsWith('/group') && group && typeof body.name==='string') {
        await imCommand('group.name',groupId,JSON.stringify({text:body.name}));return respond({name:body.name});
      }
      if(method==='POST' && path.endsWith('/group/announcement') && group) {
        await imCommand('group.announcement',groupId,JSON.stringify({text:body.content}));return respond({published:true});
      }
      if(method==='POST' && path.endsWith('/messages') && group) {
        await imCommand('group.message',groupId,JSON.stringify({text:body.content}));return respond({msg_id:10000+group.messages.length+1});
      }
      if(group && ((method==='POST' && path.endsWith('/group/invite')) || (method==='DELETE' && path.endsWith('/group/members')))) {
        const item=s.items[Number(body.user_id)-10];if(!item)throw Error('请选择有效成员');
        const members=method==='POST' ? Array.from(new Set([...group.members,item.id])) : group.members.filter((id:string)=>id!==item.id);
        await imCommand('group.members',groupId,JSON.stringify({members}));return respond({updated:true});
      }
      if(method==='POST' && path.endsWith('/group/leave') && group) {
        await imCommand('group.delete',groupId);return respond({left:true});
      }
      const profileId=Number(path.match(/\/user\/(\d+)/)?.[1]);
      if(method==='GET' && profileId>=10 && s.items[profileId-10])return respond({...user(profileId-10),bio:s.items[profileId-10].account});
    }
    const msg = (item: any, i: number) => ({
      msg_id: 100 + i,
      sender_id: projectReceipts ? item.receipt_sender_id : 2,
      sender_name: projectReceipts ? item.name : "林若宁",
      sender_avatar: undefined,
      content: item.text,
      created_at: Date.parse(item.created_at) / 1000,
      benchmark_object: item.id,
      benchmark_read: s.domain.objects[item.id].read,
      benchmark_starred: s.domain.objects[item.id].starred,
    });
    if (method === "GET") {
      if (path === "/api/workspace")
        return respond({ instructions: projectReceipts ? s.public_parameters : undefined });
      if (path === "/api/user/profile")
        return respond({ user_id: 1, username: "周予安", avatar: undefined });
      if (path === "/api/friends")
        return respond({
          friends: projectReceipts
            ? s.scopes.map((scope: any, i: number) => ({user_id:10+i,username:scope.name,group:'项目联络人'}))
            : s.task_id === 16
            ? [{user_id: 2, username: s.source.recipient, group: '联系人'}]
            : s.items.map((_: any, i: number) => user(i)),
        });
      if (path === "/api/conversations") {
        if (projectReceipts) return respond({conversations:s.scopes.map((scope: any, i: number) => ({
          conversation_id:10+i,type:'group',name:scope.name,
          peer_user:{user_id:10+i,username:scope.name},other_user_id:10+i,unread_count:0,
          last_message:{content:'项目通知回执 · 请核对通知编号和批次',created_at:1768471200},
        }))});
        const conversations = [
          {
            conversation_id: 2,
            type: "private",
            name: "林若宁",
            peer_user: { user_id: 2, username: "林若宁" },
            other_user_id: 2,
            unread_count: 0,
            last_message: {
              content: "项目消息已同步，请查看待办",
              created_at: 1768471200,
            },
          },
        ];
        if (s.domain.memberships["group-1"])
          conversations.push({
            conversation_id: 20,
            type: "group",
            name: "项目讨论组",
            peer_user: { user_id: 1, username: "周予安" },
            other_user_id: 1,
            unread_count: 0,
            last_message: {
              content: `已创建群聊，共 ${s.domain.memberships["group-1"].length} 位成员`,
              created_at: 1768471400,
            },
          });
        return respond({ conversations });
      }
      if (/\/conversations\/\d+\/messages$/.test(path)) {
        const conversationId = Number(path.split('/')[3]);
        const scope = scopeForConversation(conversationId);
        if (projectReceipts ? !scope : conversationId !== 2) return respond({messages: []});
        const rows = s.task_id === 16 ? s.items.flatMap((item: any, i: number) => !projectReceipts || item.scope_id === scope.id ? [msg(item,i)] : []) : [];
        rows.push(
          ...s.domain.messages
            .filter((m: any) => m.sender === "self" && (!projectReceipts || m.recipient === scope.id))
            .map((m: any, i: number) => ({
              msg_id: 1000 + i,
              sender_id: 1,
              sender_name: "周予安",
              content: m.body,
              created_at: Date.parse(s.source.reference_time) / 1000 + i,
              reply_to: m.reference
                ? {
                    msg_id:
                      100 + s.items.findIndex((x: any) => x.id === m.reference),
                    sender_name: projectReceipts ? s.domain.objects[m.reference].name : "林若宁",
                    content: s.domain.objects[m.reference].text,
                  }
                : undefined,
            })),
        );
        return respond({ messages: rows.sort((a: any, b: any) => b.created_at - a.created_at) });
      }
      if (/\/conversations\/\d+\/group$/.test(path)) {
        const scope = scopeForConversation(Number(path.split('/')[3]));
        if (scope) {
          const members = Array.from(new Map(s.items.filter((item: any) => item.scope_id === scope.id)
            .map((item: any) => [item.receipt_sender_id, {user_id:item.receipt_sender_id,username:item.name}])).values());
          return respond({name:scope.name,owner_id:1,created_at:Date.parse(s.source.reference_time)/1000,
            description:'项目通知与回执',announcements:[],members:[{user_id:1,username:'周予安'},...members]});
        }
        if (path !== '/api/conversations/20/group' || !s.domain.memberships['group-1'])
          throw Error('该会话不是群聊');
        return respond({
          name: "项目讨论组",
          owner_id: 1,
          created_at: Date.parse(s.source.reference_time) / 1000,
          announcements: [],
          description: '',
          members: [
            { user_id: 1, username: "周予安" },
            ...s.items
              .map((_: any, i: number) => user(i))
              .filter((u: any) =>
                s.domain.memberships["group-1"]?.includes(
                  s.items[u.user_id - 10].id,
                ),
              ),
          ],
        });
      }
      if (path.includes("/user/")) {
        const id = Number(path.match(/\/user\/(\d+)/)?.[1]);
        const scope = scopeForConversation(id);
        const person = projectReceipts ? s.items.find((item: any) => item.receipt_sender_id === id) : undefined;
        return respond({
          user_id: person?.receipt_sender_id || (scope ? 10 + s.scopes.indexOf(scope) : 2),
          username: person?.name || scope?.name || "林若宁",
          avatar: undefined,
          bio: "产品与设计协作",
        });
      }
      if (path.includes("/friends/requests")) return respond({ requests: [] });
    }
    if (
      method === "POST" &&
      path === "/api/conversations" &&
      Array.isArray(body.member_ids)
    ) {
      const ids = body.member_ids.map((n: number) => s.items[n - 10]?.id);
      if (ids.some((x: any) => !x)) throw Error("联系人不存在");
      await imCommand("invite", "", "", ids);
      return respond({ conversation_id: 20 });
    }
    if (method === "POST" && path.endsWith("/read"))
      return respond({ read: true });
    if (method === "POST" && path.endsWith("/messages") && s.task_id === 16) {
      const item = s.items[Number(body.reply_to_id) - 100];
      if (!item) throw Error("请选择需要回复的原消息");
      if (projectReceipts && scopeForConversation(Number(path.split('/')[3]))?.id !== item.scope_id)
        throw Error("原消息不属于当前项目会话");
      if (body.content !== s.source.fixed_reply)
        throw Error(`回复内容应为“${s.source.fixed_reply}”`);
      await imCommand("action", item.id, "回复");
      return respond({ msg_id: 1000 + s.domain.messages.length });
    }
    throw Error("此独立练习尚未接入该功能");
  } catch (error) {
    return respond({ code: 1, info: String(error) }, 422);
  }
}
