import { apiFetch } from './client.js'

export function uploadFile(file, purpose = 'message') {
  const form = new FormData()
  form.append('purpose', purpose)
  form.append('file', file)
  return apiFetch('/upload', { method: 'POST', body: form })
}
