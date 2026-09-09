import { apiFetch } from './client.js'

export function getManual() {
  return apiFetch('/manual')
}

