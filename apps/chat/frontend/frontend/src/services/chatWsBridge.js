/**
 * WebSocket 桥（与 A 协同）：
 * - A：建立连接、鉴权、心跳、解析服务端事件。
 * - 收到新消息/删除/撤回后，调用 `emitChatEvent(CHAT_EVENT_*, detail)`（见 chatEvents.js）。
 * - B：`useConversationMessages` 已订阅这些事件并更新消息列表。
 *
 * 此处不默认创建连接，避免在课程环境无 WS 地址时误连。
 */

export {}
