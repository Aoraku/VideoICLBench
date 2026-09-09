import { apiFetch } from './client.js'

/**
 * POST /api/auth/register
 * body: { username, password, email?, phone? }
 * resp: 201 { user_id, username, email, phone, avatar, created_at }
 */
export function register({ username, password, email, phone }) {
  return apiFetch('/auth/register', {
    method: 'POST',
    json: { username, password, email, phone },
  })
}

/**
 * POST /api/auth/login
 * body: { login_type: 'username'|'email'|'phone', identifier, password }
 * resp: 200 { access_token, refresh_token, expires_in, user }
 */
export function login({ login_type, identifier, password }) {
  return apiFetch('/auth/login', {
    method: 'POST',
    json: { login_type, identifier, password },
  })
}

/**
 * POST /api/auth/refresh
 * body: { refresh_token }
 * resp: 200 { access_token, expires_in }
 */
export function refreshToken({ refresh_token }) {
  return apiFetch('/auth/refresh', {
    method: 'POST',
    json: { refresh_token },
  })
}

/**
 * POST /api/auth/logout
 * body: { refresh_token }
 * resp: 204 No Content
 */
export function logout({ refresh_token }) {
  return apiFetch('/auth/logout', {
    method: 'POST',
    json: { refresh_token },
  })
}

/**
 * DELETE /api/auth/account
 * body: { password }
 * resp: 204 No Content
 */
export function deleteAccount({ password }) {
  return apiFetch('/auth/account', {
    method: 'DELETE',
    json: { password },
  })
}
