import { apiFetch, apiUrl, authHeaders } from './client.js'

export function createAIConversation(name = '我的AI助手') {
  return apiFetch('/ai/conversations', {
    method: 'POST',
    json: { name },
  })
}

export function sendAIMessage(conversationId, content) {
  const q = new URLSearchParams({ stream: 'false' })
  return apiFetch(`/ai/conversations/${conversationId}/messages?${q}`, {
    method: 'POST',
    json: { content },
  })
}

export async function sendAIMessageStream(conversationId, content, handlers = {}) {
  const headers = authHeaders({ 'Content-Type': 'application/json' })
  const res = await fetch(apiUrl(`/ai/conversations/${conversationId}/messages`), {
    method: 'POST',
    headers,
    body: JSON.stringify({ content }),
  })

  if (!res.ok) {
    let data = null
    try {
      data = await res.json()
    } catch {
      // ignore
    }
    const err = new Error(data?.error?.message || res.statusText || 'AI 回复失败')
    err.status = res.status
    err.code = data?.error?.code
    err.body = data
    throw err
  }

  if (!res.body) {
    return sendAIMessage(conversationId, content)
  }

  const reader = res.body.getReader()
  const decoder = new TextDecoder()
  let buffer = ''
  let donePayload = null

  const handleEvent = (raw) => {
    const line = raw
      .split('\n')
      .map((part) => part.trim())
      .find((part) => part.startsWith('data:'))
    if (!line) return
    const payload = JSON.parse(line.slice(5).trim())
    if (payload.type === 'start') handlers.onStart?.(payload)
    if (payload.type === 'delta') handlers.onDelta?.(String(payload.content || ''), payload)
    if (payload.type === 'done') {
      donePayload = payload
      handlers.onDone?.(payload)
    }
    if (payload.type === 'error') {
      const err = new Error('AI 回复失败')
      err.code = payload.code || 'AI_SERVICE_ERROR'
      throw err
    }
  }

  while (true) {
    const { value, done } = await reader.read()
    if (done) break
    buffer += decoder.decode(value, { stream: true })
    const parts = buffer.split('\n\n')
    buffer = parts.pop() || ''
    for (const part of parts) {
      if (part.trim()) handleEvent(part)
    }
  }
  buffer += decoder.decode()
  if (buffer.trim()) handleEvent(buffer)
  return donePayload
}
