import { apiFetch } from './client.js'

/**
 * GET /api/sync/messages?since=...&limit=...
 * resp: 200 { messages: [...], has_more: bool, sync_timestamp: string }
 */
export function syncMessages({ since, limit = 200 }) {
  const q = new URLSearchParams({
    since,
    limit: String(limit),
  })
  return apiFetch(`/sync/messages?${q}`)
}

