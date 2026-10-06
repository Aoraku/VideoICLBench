/** Original Chat API contract backed by an isolated benchmark business database.
 * No rule version, expected answer, or evaluation endpoint is available here.
 */
const route = location.pathname.match(/^\/native\/chat\/([a-f0-9]{32})/);
export const nativeRun = route?.[1] || "";
export const nativeBase = nativeRun ? `/native/chat/${nativeRun}` : "";
const tokenKey = `vic-chat:${nativeRun}`;
const token = nativeRun
  ? location.hash.slice(1) || sessionStorage.getItem(tokenKey) || ""
  : "";
if (nativeRun && token) {
  if (sessionStorage.getItem(tokenKey) !== token) sessionStorage.removeItem(tokenKey + ":read");
  sessionStorage.setItem(tokenKey, token);
  localStorage.setItem("access_token", token);
}
let latest = null, snapshotTime = 0;
const readConversations = new Set(
  JSON.parse(sessionStorage.getItem(tokenKey + ":read") || "[]"),
);
export async function business(path = "", body) {
  if (!path && !body && latest && Date.now()-snapshotTime<500) return latest;
  const response = await fetch(`/api/runs/${nativeRun}${path}`, {
    method: body ? "POST" : "GET",
    headers: {
      Authorization: `Bearer ${token}`,
      "Content-Type": "application/json",
    },
    body: body ? JSON.stringify(body) : undefined,
  });
  const data = await response.json();
  if ([403, 410].includes(response.status)) {
    window.dispatchEvent(new CustomEvent("vic-session-unavailable"));
  }
  if (!response.ok)
    throw new Error(
      typeof data.detail === "string" ? data.detail : "操作未能保存，请重试",
    );
  latest = data; snapshotTime = Date.now();
  return data;
}
export async function command(op, target = "", value = "", ids = []) {
  const current = await business();
  const data = await business("/commands", {
    op,
    target,
    value,
    ids,
    epoch: current.epoch,
    action_id: crypto.randomUUID(),
  });
  window.dispatchEvent(
    new CustomEvent("vic-chat-updated", { detail: data.state }),
  );
  return data.state;
}
export function currentBusiness() {
  return latest?.state;
}
export function workspaceLink(module) { return `/native/product/${module}/${nativeRun}#${token}`; }
export function currentScope() { return sessionStorage.getItem(tokenKey+':scope') || ''; }
export function setCurrentScope(scope) {
  sessionStorage.setItem(tokenKey+':scope',scope);
  window.dispatchEvent(new CustomEvent('vic-chat-updated',{detail:{scopeChanged:true}}));
  window.dispatchEvent(new CustomEvent('vic-chat-scope'));
}
function inScope(state,item) { return !state.v2_worksets || !currentScope() || item.scope_id===currentScope(); }
export function adjacentConversation(objectId,delta) {
  if(!objectId || !currentBusiness()?.domain?.objects[objectId])return undefined;
  const state=currentBusiness(), order=state.domain.orders.main;
  const ids=state.v2_worksets ? order.filter(id=>state.domain.objects[id].scope_id===state.domain.objects[objectId].scope_id) : order;
  return ids[ids.indexOf(objectId)+delta];
}
export async function moveConversation(objectId,delta) {
  const other=adjacentConversation(objectId,delta);if(!other)return;
  const ids=[...currentBusiness().domain.orders.main],i=ids.indexOf(objectId),j=ids.indexOf(other);
  [ids[i],ids[j]]=[ids[j],ids[i]];
  return command('order','','',ids);
}
const pageOf = (rows) => ({
  results: rows,
  total: rows.length,
  has_more: false,
  page: 1,
  page_size: 50,
});
function user(state, id) {
  id = Number(id);
  if(state.workflow==='communications')return {id,user_id:id,username:id===1?(state.source.operator || '我'):state.world.conversations.find(c=>c.user_id===id)?.name || '联系人',remark:'',avatar:null,is_friend:true,presence:'online',status:'online'};
  const index = id - 10,
    item = state.items[index];
  const name =
    id === 1
      ? (state.source.operator || '我')
      : id === 2
        ? state.source.recipient
        : id === 3 && state.task_id === 13 ? state.source.sender : item?.name || "联系人";
  return {
    id,
    user_id: id,
    username: name,
    benchmark_identity_name: state.task_id === 2 && (id === 2 || state.v2_worksets) ? name : undefined,
    remark:
      id === 2 && state.task_id === 2
        ? state.outputs.target || state.source.text
        : state.v2_worksets && state.task_id===2 && item ? state.domain.objects[item.id].nickname || '' : "",
    avatar: null,
    status: "online",
    presence: "online",
    bio: "一起把事情做好。",
    email: "",
    gender: "unknown",
    group_id:
      state.task_id === 6 && item && state.domain.objects[item.id].label
        ? state.options.indexOf(state.domain.objects[item.id].label) + 1
        : null,
    is_friend: true,
    benchmark_contact_time: item?.last_contact_at,
    benchmark_unread: item?.unread,
    benchmark_surname: item && [6, 9].includes(state.task_id) ? item.surname : undefined,
    benchmark_given_name: item && [6, 9].includes(state.task_id) ? item.name.split(" ").slice(0, -1).join(" ") : undefined,
    benchmark_contact_summary: state.task_id === 9,
    benchmark_scope: item?.scope_name,
    benchmark_scope_kind: state.scopes?.find(s=>s.id===item?.scope_id)?.kind,
    benchmark_account: item?.record_code,
    group_name:
      state.task_id === 6 && item ? state.domain.objects[item.id].label : "",
  };
}
function message(
  state,
  id,
  body,
  senderId = 2,
  conversation = 2,
  object = null,
) {
  return {
    msg_id: id,
    conversation_id: conversation,
    type: "text",
    content: { text: body },
    sender: user(state, senderId),
    sender_id: senderId,
    sender_name: user(state, senderId).username,
    created_at: object?.created_at || state.source.reference_time,
    is_recalled: false,
    reactions: [],
    read_by_count: 1,
    benchmark_object: object?.id,
    benchmark_label:
      object?.label ||
      (object?.archived ? "已归档" : object?.starred ? "已收藏" :
        state.task_id === 13 && object && state.domain.messages.some(m => m.sender === "self" && m.reference === object.id) ? "已转发" : ""),
    benchmark_options: state.type === "C" ? state.options : [],
  };
}
function messages(state, conv) {
  conv = Number(conv);
  if(state.workflow==='communications') {
    const fileMessage=(mid,fileId,sender,body,reference)=>{
      const file=state.domain.files[fileId];
      const row={...message(state,mid,body,sender,conv),type:'file',content:{filename:file.name,size:file.size,mime_type:'text/plain',url:`data:text/plain;base64,${file.content}`,text:body}};
      const request=state.world.requests.find(r=>r.id===reference);
      if(request)row.reply_to={msg_id:request.message_id,sender_name:user(state,request.requester).username,content:{text:request.body},type:'text'};
      return row;
    };
    const rows=state.task_id===11 ? [
      ...state.world.requests.filter(r=>r.conversation===conv).map(r=>message(state,r.message_id,r.body,r.requester,conv)),
      ...state.items.filter(x=>x.conversation===conv && state.domain.files[x.id]).map(item=>fileMessage(item.message_id,item.id,conv,`${item.project} · ${item.file_type} · ${item.version}`))
    ] : state.items.filter(x=>x.conversation===conv).map(item=>message(state,item.message_id,item.text,conv,conv,state.domain.objects[item.id]));
    return [...rows,...state.domain.messages.flatMap((m,i)=>Number(m.recipient)!==conv?[]:[m.attachment?fileMessage(10000+i,m.attachment,1,m.body,m.reference):message(state,10000+i,m.body,1,conv)])];
  }
  if(state.v2_worksets && state.task_id===2){
    const identity=(item)=>`我是 ${item.name}，我的成员账号是 ${item.record_code}。请使用我的姓名整理通讯录备注。`;
    if(conv===5)return state.items.flatMap((item,i)=>item.scope_id==='scope-1'?[message(state,500+i,identity(item),10+i,5)]:[]);
    const item=state.items[conv-10];return item?[message(state,100+conv,identity(item),conv,conv)]:[];
  }
  if (state.task_id === 13) {
    if (conv === 3) return state.items.map((item, i) =>
      message(state, 100 + i, item.text, 3, 3, state.domain.objects[item.id]))
      .sort((a, b) => a.created_at.localeCompare(b.created_at));
    if (conv === 2) return state.domain.messages.filter(m => m.sender === "self").map((m, i) =>
      message(state, 1000 + i, m.body, 1, 2));
    return [];
  }
  if (conv === 2) {
    if (state.task_id === 11) {
      return [
        message(state, 1, "共享资料已放在聊天文件中，请把需要的附件发给我。"),
        ...state.domain.messages.filter(m => m.sender === "self" && m.attachment).map((m, i) => {
          const file = state.domain.files[m.attachment];
          return {
            ...message(state, 1000 + i, "", 1, 2),
            type: "file",
            content: { filename: file.name, size: file.size, mime_type: "text/plain",
              url: `data:text/plain;base64,${file.content}` },
          };
        }),
      ];
    }
    const rows = [
      message(
        state,
        1,
        state.task_id === 2
          ? `请在通讯录中整理我的备注信息，原始备注是：\n${state.source.text}`
          : `请帮我整理下面这段内容，整理好后在这里发给我：\n${state.source.text}`,
      ),
    ];
    if ([5, 13].includes(state.task_id))
      return state.items.map((item, i) =>
        message(state, 100 + i, item.text, 2, 2, state.domain.objects[item.id]),
      );
    return [
      ...rows,
      ...state.domain.messages
        .filter((m) => m.sender === "self")
        .map((m, i) => message(state, 1000 + i, m.body, 1, 2)),
    ];
  }
  const item = state.items[conv - 10];
  if(item && state.v2_worksets && state.task_id===9) return [
    message(state,100+conv,item.text,conv,conv,state.domain.objects[item.id]),
    ...state.domain.messages.filter(m=>m.sender==='self' && m.recipient===item.id).map((m,i)=>message(state,1000+i,m.body,1,conv))
  ];
  return item
    ? [
        message(
          state,
          100 + conv,
          item.text,
          conv,
          conv,
          state.domain.objects[item.id],
        ),
      ]
    : [];
}
function conversations(state, scoped=true) {
  if(state.workflow==='communications')return state.world.conversations.map(c=>({conversation_id:c.id,type:'private',name:c.name,peer_user:user(state,c.user_id),unread_count:0,last_message:messages(state,c.id).at(-1),updated_at:state.source.reference_time,benchmark_scope:c.project,benchmark_record:''}));
  if (state.task_id === 13) return [3, 2].map(id => ({
    conversation_id: id, type: "private", peer_user: user(state, id),
    unread_count: id === 3 && !readConversations.has(3) ? state.items.length : 0,
    last_message: messages(state, id).at(-1) || null,
    updated_at: state.source.reference_time,
  }));
  const rows = (state.task_id === 11 ? [] : state.items).map((item, i) => {
    const object = state.domain.objects[item.id];
    return {
      conversation_id: 10 + i,
      type: state.task_id === 8 ? "group" : "private",
      name: item.name,
      peer_user: state.task_id === 8 ? null : user(state, 10 + i),
      member_count: item.members,
      is_pinned: object.pinned,
      is_muted: object.muted,
      unread_count:
        object.read || readConversations.has(10 + i) ? 0 : item.unread,
      last_message: messages(state, 10 + i)[0],
      updated_at: state.task_id===14 ? object.created_at : new Date(
        Date.parse(state.source.reference_time) -
          (state.task_id === 12
            ? state.domain.orders.main.indexOf(item.id)
            : i) *
            60000,
      ).toISOString(),
      benchmark_object: item.id,
      benchmark_label: object.label || (object.archived ? "已归档" : ""),
      benchmark_timestamp: item.timestamp,
      benchmark_age_days: item.age_days,
      benchmark_scope: item.scope_name,
      benchmark_scope_id: item.scope_id,
      benchmark_record: item.record_code,
      benchmark_snapshot_unread: state.v2_worksets ? item.unread : undefined,
      benchmark_archived: object.archived,
    };
  });
  if ([1, 2, 3, 4, 5, 11, 13].includes(state.task_id) && !(state.v2_worksets && state.task_id===2))
    rows.unshift({
      conversation_id: 2,
      type: "private",
      peer_user: user(state, 2),
      unread_count: readConversations.has(2) ? 0 : 1,
      last_message: messages(state, 2).at(-1),
      updated_at: state.source.reference_time,
    });
  if(state.v2_worksets && state.task_id===2)rows.unshift({conversation_id:5,type:'group',name:state.scopes[0].name,
    member_count:6,unread_count:5,last_message:messages(state,5).at(-1),updated_at:state.source.reference_time,benchmark_scope_id:'scope-1'});
  return scoped && state.v2_worksets ? rows.filter(c=>!currentScope() || c.benchmark_scope_id===currentScope()) : rows;
}
export async function nativeRequest(path, options = {}) {
  const method = options.method || "GET",
    body = options.json || {},
    url = new URL(path, location.origin),
    p = url.pathname.replace(/\/$/, "");
  const { state } = await business();
  if(state.workflow==='communications') {
    if(method==='GET' && p==='/friends')return pageOf(state.world.conversations.map(c=>user(state,c.user_id)));
    if(method==='GET' && p==='/bookmarks') {
      const archived=url.searchParams.get('archived')==='true';
      return pageOf(state.items.filter(x=>archived?state.domain.objects[x.id].archived:state.domain.objects[x.id].starred).map(item=>({
        bookmark_id:item.message_id,conversation_id:item.conversation,conversation_name:user(state,item.conversation).username,
        title:item.text,note:'',is_archived:archived,message:message(state,item.message_id,item.text,item.conversation,item.conversation,state.domain.objects[item.id])
      })));
    }
    if(method==='POST' && p==='/messages/forward' && state.task_id===13) {
      if(body.target_conv_ids?.length!==1 || body.target_conv_ids[0]!==2)throw new Error('本次转发收件人为'+state.source.recipient);
      for(const mid of body.msg_ids||[]) {
        const item=state.items.find(x=>x.message_id===Number(mid)&&x.conversation===body.source_conv_id);
        if(!item)throw new Error('请选择原会话中的消息');
        await command('action',item.id,'转发');
      }
      return {success:true};
    }
    if(method==='POST' && p==='/bookmarks' && state.task_id===13) {
      const item=state.items.find(x=>x.message_id===Number(body.msg_id));if(!item)throw new Error('消息不存在');
      await command('action',item.id,'收藏');return {bookmark_id:item.message_id};
    }
  }
  if (method === "GET") {
    if (p === "/users/me") return user(state, 1);
    if (/^\/users\/\d+$/.test(p)) return user(state, p.split("/").at(-1));
    if (p === "/friends" && state.task_id === 13) return pageOf([user(state, 2), user(state, 3)]);
    if (p === "/friends")
      return pageOf([
        ...([1, 2, 3, 4, 5, 11, 13].includes(state.task_id) && !(state.v2_worksets && state.task_id===2)
          ? [user(state, 2)]
          : []),
        ...(state.task_id === 11 ? [] : state.items).flatMap((item,i)=>inScope(state,item)?[user(state,10+i)]:[]),
      ]);
    if (p === "/friends/groups")
      return {
        groups:
          state.task_id === 6
            ? state.options.map((name, i) => ({
                group_id: i + 1,
                name,
                friend_count: state.items.filter(
                  (item) => inScope(state,item) && state.domain.objects[item.id].label === name,
                ).length,
              }))
            : [],
      };
    if (
      p === "/friends/requests" ||
      p === "/friends/blacklist" ||
      p === "/friends/whitelist" ||
      p === "/users/search"
    )
      return pageOf([]);
    if (p === "/conversations") return pageOf(conversations(state));
    if (p === "/conversations/search") {
      const keyword = url.searchParams.get("keyword")?.toLowerCase() || "";
      return pageOf(
        conversations(state)
          .flatMap((c) =>
            messages(state, c.conversation_id).map((m) => ({
              ...m,
              conversation_name: c.name || c.peer_user.username,
              benchmark_unread: state.task_id === 10 ? c.unread_count : undefined,
            })),
          )
          .filter((m) =>
            (m.content.text + " " + m.conversation_name)
              .toLowerCase()
              .includes(keyword),
          ),
      );
    }
    const msg = p.match(/^\/conversations\/(\d+)\/messages$/);
    if (msg)
      return pageOf(
        messages(state, msg[1]).filter(
          (m) =>
            !url.searchParams.get("keyword") ||
            m.content.text.includes(url.searchParams.get("keyword")),
        ),
      );
    const groupInfo=p.match(/^\/conversations\/(\d+)\/group(?:\/(members|announcements))?$/);
    if(groupInfo && state.v2_worksets && state.task_id===2 && Number(groupInfo[1])===5){
      const members=[{...user(state,1),role:'owner'},...state.items.flatMap((item,i)=>item.scope_id==='scope-1'?[{...user(state,10+i),role:'member'}]:[])];
      if(groupInfo[2]==='members')return pageOf(members);
      if(groupInfo[2]==='announcements')return pageOf([]);
      return {conversation_id:5,name:state.scopes[0].name,owner:members[0],member_count:members.length,
        created_at:state.source.reference_time,my_group_nickname:(state.source.operator || '我'),latest_announcement:null};
    }
    if(groupInfo && state.v2_worksets && state.task_id===8) {
      const item=state.items[Number(groupInfo[1])-10];if(!item)throw new Error('群聊不存在');
      if(groupInfo[2]==='members')return pageOf(item.group_members);
      if(groupInfo[2]==='announcements')return pageOf([]);
      return {conversation_id:Number(groupInfo[1]),name:item.name,owner:item.group_members[0],member_count:item.group_members.length,
        created_at:item.created_at,my_group_nickname:(state.source.operator || '我'),latest_announcement:null};
    }
    const conv = p.match(/^\/conversations\/(\d+)$/);
    if (conv)
      return conversations(state,false).find(
        (c) => c.conversation_id === Number(conv[1]),
      );
    if (p === "/sync/messages")
      return {
        messages: [],
        has_more: false,
        sync_timestamp: state.source.reference_time,
      };
    if (p === "/bookmarks") {
      const archived = url.searchParams.get("archived") === "true";
      const ids = archived
        ? state.items.filter(item => state.domain.objects[item.id].archived).map(item => item.id)
        : (state.domain.collections.favorites || []);
      return pageOf(ids.map(id => {
        const item = state.domain.objects[id];
        const index = state.items.findIndex(row => row.id === id);
        const conversation = state.task_id === 13 ? 3 : 2;
        return {
          bookmark_id: 100 + index, conversation_id: conversation,
          conversation_name: state.task_id === 13 ? state.source.sender : state.source.recipient,
          title: item.text, note: "", is_archived: archived,
          message: message(state, 100 + index, item.text, conversation, conversation, item),
        };
      }));
    }
    if (p === "/groups")
      return {
        groups: conversations(state)
          .filter((c) => c.type === "group")
          .map((c) => ({ ...c, group_id: c.conversation_id })),
        results: [],
      };
    if (p.startsWith("/calendar")) return { events: [], results: [] };
    if (p.includes("privacy")) return { allow_friend_request: true };
  }
  const sending = p.match(/^\/conversations\/(\d+)\/messages$/);
  if(method==='POST' && sending && state.v2_worksets && state.task_id===9) {
    const item=state.items[Number(sending[1])-10];if(!item)throw new Error('收件人不存在');
    if(body.type!=='text' || typeof body.content?.text!=='string')throw new Error('请发送文本通知');
    const next=await command('message.send',item.id,body.content.text);
    return {...messages(next,Number(sending[1])).at(-1),client_msg_id:body.client_msg_id};
  }
  if (method === "POST" && sending && [1, 3, 4].includes(state.task_id)) {
    if (Number(sending[1]) !== 2)
      throw new Error(
        `目标会话是 ${state.source.recipient}，此练习的其他会话只读。`,
      );
    if (body.type !== "text" || typeof body.content?.text !== "string")
      throw new Error("请发送文本消息");
    const next = await command("save", "target", body.content.text);
    return { ...messages(next, 2).at(-1), client_msg_id: body.client_msg_id };
  }
  if (method === "POST" && p === "/conversations") {
    if (state.task_id === 9 && !state.v2_worksets) {
      const item = state.items[Number(body.peer_user_id) - 10];
      if (!item) throw new Error("收件人不存在");
      await command("select", "", "", [item.id]);
    }
    return { conversation_id: Number(body.peer_user_id), existing: true };
  }
  const group = p.match(/^\/friends\/groups\/(\d+)$/);
  if (method === "PUT" && group && state.task_id === 6) {
    for (const uid of body.add_friend_ids || []) {
      const item = state.items[Number(uid) - 10];
      if (item)
        await command("label", item.id, state.options[Number(group[1]) - 1]);
    }
    for (const uid of body.remove_friend_ids || []) {
      const item = state.items[Number(uid) - 10];
      if (item) await command("label", item.id, "");
    }
    return { success: true };
  }
  if (method === "POST" && p === "/messages/forward" && state.task_id === 13) {
    if (body.source_conv_id !== 3) throw new Error("请从原消息会话中转发");
    if (body.target_conv_ids?.length !== 1 || body.target_conv_ids[0] !== 2)
      throw new Error(`请转发至 ${state.source.recipient}`);
    for (const mid of body.msg_ids || []) {
      const item = state.items[Number(mid) - 100];
      if (item) await command("action", item.id, "转发");
    }
    return { success: true };
  }
  const remark = p.match(/^\/friends\/(\d+)\/remark$/);
  if(method==='PUT' && remark && state.v2_worksets && state.task_id===2){
    const item=state.items[Number(remark[1])-10];if(!item)throw new Error('联系人不存在');
    await command('contact.nickname',item.id,body.remark);return {remark:body.remark};
  }
  if (
    method === "PUT" &&
    remark &&
    state.task_id === 2 &&
    Number(remark[1]) === 2
  ) {
    await command("save", "target", body.remark);
    return { remark: body.remark };
  }
  if (method === "PUT" && /\/conversations\/\d+\/read$/.test(p)) {
    readConversations.add(Number(p.split("/")[2]));
    sessionStorage.setItem(
      tokenKey + ":read",
      JSON.stringify([...readConversations]),
    );
    return { read: true };
  }
  const settings = p.match(/^\/conversations\/(\d+)$/);
  if (method === "PUT" && settings && state.task_id === 14) {
    const item = state.items[Number(settings[1]) - 10];
    if (!item) throw new Error("会话不存在");
    const changes={};if('is_pinned' in body)changes.pinned=body.is_pinned;if('is_muted' in body)changes.muted=body.is_muted;
    const next=await command('conversation.settings',item.id,JSON.stringify(changes));
    const saved=next.domain.objects[item.id];return {is_pinned:saved.pinned,is_muted:saved.muted};
  }
  if (method === "POST" && p === "/bookmarks" && state.task_id === 13) {
    const item = state.items[Number(body.msg_id) - 100];
    if (item) {
      await command("action", item.id, "收藏");
      return { bookmark_id: body.msg_id };
    }
  }
  throw new Error(`此独立练习尚未接入该功能：${method} ${p}`);
}
