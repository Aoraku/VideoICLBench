/**
 * 聊天域共享类型（JSDoc，与 API-document.md 对齐；变更前请在群内同步）。
 */

/** @typedef {number|string} ConversationId */

/** @typedef {'pending'|'sent'|'failed'} MessageSendStatus */

/**
 * API 5.2 / 5.1 发送者（snake_case）
 * @typedef {Object} ApiMessageSender
 * @property {number} user_id
 * @property {string} username
 * @property {string|null} [avatar]
 * @property {string|null} [group_nickname]
 */

/**
 * @typedef {Object} ApiReplyToSummary
 * @property {number} msg_id
 * @property {number} sender_id
 * @property {string} sender_name
 * @property {string} type
 * @property {string} content_summary
 */

/**
 * API 5.2 / 5.1 消息行（snake_case）
 * @typedef {Object} ApiChatMessage
 * @property {number|null} [msg_id]
 * @property {string|null} [client_msg_id]
 * @property {ApiMessageSender} sender
 * @property {string} type
 * @property {Record<string, unknown>} content
 * @property {ApiReplyToSummary|null} [reply_to]
 * @property {number} [reply_count]
 * @property {unknown[]} [mentions]
 * @property {unknown[]} [reactions]
 * @property {number} [read_by_count]
 * @property {boolean} [is_recalled]
 * @property {string} created_at
 * @property {'pending'|'failed'} [send_status]
 */

/**
 * @typedef {Object} MessageFilter
 * @property {string} [keyword]
 * @property {number|string} [sender_id]
 * @property {string} [after]
 * @property {string} [before]
 * @property {string} [type]
 * @property {string} [startTime]
 * @property {string} [endTime]
 */

/**
 * @typedef {Object} LastMessagePreview
 * @property {string} [text]
 * @property {string} createdAt
 */

/**
 * @typedef {Object} MessageSentPayload
 * @property {ConversationId} conversationId
 * @property {string} previewText
 * @property {string} [at]
 */

/**
 * @typedef {Object} ConversationSettings
 * @property {boolean} [isMuted]
 * @property {boolean} [isPinned]
 */

/**
 * @typedef {Object} Conversation
 * @property {ConversationId} conversationId
 * @property {'private'|'group'} [type]
 * @property {string} [title]
 * @property {string} [lastMessagePreview]
 * @property {string} [lastMessageTime]
 * @property {number} [unreadCount]
 * @property {ConversationSettings} [settings]
 */

export {}
