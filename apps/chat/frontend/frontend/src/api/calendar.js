import { apiFetch } from './client.js'

export function listCalendarEvents({ startAt, endAt, page = 1, pageSize = 100 }) {
  const q = new URLSearchParams({
    start_at: String(startAt || ''),
    end_at: String(endAt || ''),
    page: String(page),
    page_size: String(pageSize),
  })
  return apiFetch(`/calendar/events?${q}`)
}

export function createCalendarEvent({ title, description = '', startAt, endAt, inviteeIds = [] }) {
  return apiFetch('/calendar/events', {
    method: 'POST',
    json: {
      title,
      description,
      start_at: startAt,
      end_at: endAt,
      invitee_ids: inviteeIds.map((id) => Number(id)).filter((id) => Number.isFinite(id) && id > 0),
    },
  })
}

export function updateCalendarEvent(eventId, { title, description, startAt, endAt }) {
  const json = {}
  if (title !== undefined) json.title = title
  if (description !== undefined) json.description = description
  if (startAt !== undefined) json.start_at = startAt
  if (endAt !== undefined) json.end_at = endAt
  return apiFetch(`/calendar/events/${eventId}`, { method: 'PUT', json })
}

export function deleteCalendarEvent(eventId) {
  return apiFetch(`/calendar/events/${eventId}`, { method: 'DELETE' })
}

export function respondCalendarInvitation(participantId, action) {
  return apiFetch(`/calendar/invitations/${participantId}`, {
    method: 'PUT',
    json: { action },
  })
}

export function getCalendarAvailability({ userIds = [], startAt, endAt }) {
  const q = new URLSearchParams({
    user_ids: userIds.join(','),
    start_at: String(startAt || ''),
    end_at: String(endAt || ''),
  })
  return apiFetch(`/calendar/availability?${q}`)
}
