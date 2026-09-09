/**
 * 与 A 同学约定：WebSocket 收到业务事件后，由 A 在统一分发层调用 emitChatEvent。
 * B 只订阅这些 CustomEvent，不在页面里直接解析裸 ws 帧。
 */

import {
  CHAT_EVENT_NEW_MESSAGE as CHAT_EVENT_NEW_MESSAGE_STD,
  CHAT_EVENT_NEW_MESSAGE_LEGACY,
} from '../constants/chatEvents.js'

export const CHAT_EVENT_NEW_MESSAGE = CHAT_EVENT_NEW_MESSAGE_STD
export const CHAT_EVENT_NEW_MESSAGE_COMPAT = CHAT_EVENT_NEW_MESSAGE_LEGACY
export const CHAT_EVENT_MESSAGE_DELETED = 'chat:message_deleted'
export const CHAT_EVENT_MESSAGE_RECALLED = 'chat:message_recalled'

/**
 * @param {string} type
 * @param {unknown} detail
 */
export function emitChatEvent(type, detail) {
  if (typeof window === 'undefined') return
  window.dispatchEvent(new CustomEvent(type, { detail }))
}

/**
 * 新消息兼容派发：同时发标准和 legacy 事件名，避免两边代码错过订阅。
 * @param {unknown} detail
 */
export function emitNewMessageEvent(detail) {
  emitChatEvent(CHAT_EVENT_NEW_MESSAGE_STD, detail)
  emitChatEvent(CHAT_EVENT_NEW_MESSAGE_LEGACY, detail)
}

/**
 * @param {string} type
 * @param {(detail: unknown) => void} handler
 * @returns {() => void} unsubscribe
 */
export function subscribeChatEvent(type, handler) {
  if (typeof window === 'undefined') return () => {}
  /** @param {Event} e */
  const fn = (e) => {
    const ce = /** @type {CustomEvent} */ (e)
    handler(ce.detail)
  }
  window.addEventListener(type, fn)
  return () => window.removeEventListener(type, fn)
}
