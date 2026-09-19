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
    const user = (i: number) => ({
      user_id: 10 + i,
      username: s.items[i].name,
      avatar: undefined,
      group: `最近联系 ${s.items[i].contact_time} · 未读 ${s.items[i].unread}`,
    });
    const msg = (item: any, i: number) => ({
      msg_id: 100 + i,
      sender_id: 2,
      sender_name: "林若宁",
      sender_avatar: undefined,
      content: item.text,
      created_at: 1768471200 + i * 60,
      benchmark_object: item.id,
      benchmark_read: s.domain.objects[item.id].read,
      benchmark_starred: s.domain.objects[item.id].starred,
    });
    if (method === "GET") {
      if (path === "/api/user/profile")
        return respond({ user_id: 1, username: "周予安", avatar: undefined });
      if (path === "/api/friends")
        return respond({
          friends: s.items.map((_: any, i: number) => user(i)),
        });
      if (path === "/api/conversations") {
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
        const rows = s.task_id === 16 ? s.items.map(msg) : [];
        rows.push(
          ...s.domain.messages
            .filter((m: any) => m.sender === "self")
            .map((m: any, i: number) => ({
              msg_id: 1000 + i,
              sender_id: 1,
              sender_name: "周予安",
              content: m.body,
              created_at: 1768471900 + i,
              reply_to: m.reference
                ? {
                    msg_id:
                      100 + s.items.findIndex((x: any) => x.id === m.reference),
                    sender_name: "林若宁",
                    content: s.domain.objects[m.reference].text,
                  }
                : undefined,
            })),
        );
        return respond({ messages: rows.reverse() });
      }
      if (/\/conversations\/\d+\/group$/.test(path))
        return respond({
          name: "项目讨论组",
          owner_id: 1,
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
      if (path.includes("/user/"))
        return respond({
          user_id: 2,
          username: "林若宁",
          avatar: undefined,
          bio: "产品与设计协作",
        });
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
