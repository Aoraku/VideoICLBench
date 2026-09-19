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
  sessionStorage.setItem(tokenKey, token);
  localStorage.setItem("access_token", token);
}
let latest = null;
const readConversations = new Set(
  JSON.parse(sessionStorage.getItem(tokenKey + ":read") || "[]"),
);
export async function business(path = "", body) {
  const response = await fetch(`/api/runs/${nativeRun}${path}`, {
    method: body ? "POST" : "GET",
    headers: {
      Authorization: `Bearer ${token}`,
      "Content-Type": "application/json",
    },
    body: body ? JSON.stringify(body) : undefined,
  });
  const data = await response.json();
  if (!response.ok)
    throw new Error(
      typeof data.detail === "string" ? data.detail : "操作未能保存，请重试",
    );
  latest = data;
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
const pageOf = (rows) => ({
  results: rows,
  total: rows.length,
  has_more: false,
  page: 1,
  page_size: 50,
});
function user(state, id) {
  id = Number(id);
  const index = id - 10,
    item = state.items[index];
  const name =
    id === 1
      ? "周予安"
      : id === 2
        ? state.source.recipient
        : item?.name || "联系人";
  return {
    id,
    user_id: id,
    username: name,
    remark:
      id === 2 && state.task_id === 2
        ? state.outputs.target || state.source.text
        : "",
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
    benchmark_contact_time: item?.contact_time,
    benchmark_unread: item?.unread,
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
    created_at: "2026-01-15T09:30:00Z",
    is_recalled: false,
    reactions: [],
    read_by_count: 1,
    benchmark_object: object?.id,
    benchmark_label:
      object?.label ||
      (object?.archived ? "已归档" : object?.starred ? "已收藏" : ""),
    benchmark_options: state.type === "C" ? state.options : [],
  };
}
function messages(state, conv) {
  conv = Number(conv);
  if (conv === 2) {
    const rows = [
      message(
        state,
        1,
        `请帮我整理下面这段内容，整理好后在这里发给我：\n${state.source.text}`,
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
function conversations(state) {
  const rows = state.items.map((item, i) => {
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
      updated_at: new Date(
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
    };
  });
  if ([1, 2, 3, 4, 5, 13].includes(state.task_id))
    rows.unshift({
      conversation_id: 2,
      type: "private",
      peer_user: user(state, 2),
      unread_count: readConversations.has(2) ? 0 : 1,
      last_message: messages(state, 2).at(-1),
      updated_at: state.source.reference_time,
    });
  return rows;
}
export async function nativeRequest(path, options = {}) {
  const method = options.method || "GET",
    body = options.json || {},
    url = new URL(path, location.origin),
    p = url.pathname.replace(/\/$/, "");
  const { state } = await business();
  if (method === "GET") {
    if (p === "/users/me") return user(state, 1);
    if (/^\/users\/\d+$/.test(p)) return user(state, p.split("/").at(-1));
    if (p === "/friends")
      return pageOf([
        ...([1, 2, 3, 4, 5, 13].includes(state.task_id)
          ? [user(state, 2)]
          : []),
        ...state.items.map((_, i) => user(state, 10 + i)),
      ]);
    if (p === "/friends/groups")
      return {
        groups:
          state.task_id === 6
            ? state.options.map((name, i) => ({
                group_id: i + 1,
                name,
                friend_count: state.items.filter(
                  (item) => state.domain.objects[item.id].label === name,
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
    const conv = p.match(/^\/conversations\/(\d+)$/);
    if (conv)
      return conversations(state).find(
        (c) => c.conversation_id === Number(conv[1]),
      );
    if (p === "/sync/messages")
      return {
        messages: [],
        has_more: false,
        sync_timestamp: state.source.reference_time,
      };
    if (p === "/bookmarks")
      return pageOf(
        (state.domain.collections.favorites || []).map((id, i) => ({
          bookmark_id: i + 1,
          title: state.domain.objects[id].name,
          note: state.domain.objects[id].text,
          message: message(state, 100 + i, state.domain.objects[id].text),
        })),
      );
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
    if (state.task_id === 9) {
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
    if (!body.target_conv_ids?.includes(2))
      throw new Error(`请转发至 ${state.source.recipient}`);
    for (const mid of body.msg_ids || []) {
      const item = state.items[Number(mid) - 100];
      if (item) await command("action", item.id, "转发");
    }
    return { success: true };
  }
  const remark = p.match(/^\/friends\/(\d+)\/remark$/);
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
    if (state.task_id === 10) {
      const item = state.items[Number(p.split("/")[2]) - 10];
      if (item) await command("select", "", "", [item.id]);
    }
    return { read: true };
  }
  const settings = p.match(/^\/conversations\/(\d+)$/);
  if (method === "PUT" && settings && state.task_id === 14) {
    const item = state.items[Number(settings[1]) - 10];
    if (!item) throw new Error("会话不存在");
    if (body.is_pinned) await command("action", item.id, "置顶");
    else if (body.is_muted) await command("action", item.id, "静音");
    else throw new Error("此会话操作不适用于当前练习");
    return { success: true };
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
