import {nativeRun} from '../benchmark/bridge.js'
import { ACCESS_TOKEN_KEY } from '../constants/storage.js'

const HEARTBEAT_MS = 30000
const MAX_BACKOFF_MS = 15000

function buildSocketUrl() {
  const token = localStorage.getItem(ACCESS_TOKEN_KEY)
  if (!token) return ''
  const proto = typeof window !== 'undefined' && window.location.protocol === 'https:' ? 'wss:' : 'ws:'
  const host = typeof window !== 'undefined' ? window.location.host : ''
  return `${proto}//${host}/ws/chat/?token=${encodeURIComponent(token)}`
}

/**
 * 建立 WebSocket（API 10.1：`wss://<domain>/ws/chat/?token=<access_token>`）。
 * 同时实现 10.2 心跳（ping/pong）与断线重连。
 * 开发环境通过 Vite 将 `/ws` 代理到后端；见 vite.config.js。
 * @param {{ onMessage?: (data: unknown) => void, onOpen?: () => void, onClose?: () => void }} handlers
 * @returns {() => void} 断开连接
 */
export function connectChatSocket({ onMessage, onOpen, onClose } = {}) {
  // This single-user isolated instance uses the original page's HTTP polling.
  if (nativeRun) { const disconnect = () => {}; disconnect.send = () => false; return disconnect }
  let ws = null
  let stopped = false
  let reconnectMs = 1000
  let reconnectTimer = null
  let heartbeatTimer = null

  const clearTimers = () => {
    clearTimeout(reconnectTimer)
    clearInterval(heartbeatTimer)
  }

  const startHeartbeat = () => {
    clearInterval(heartbeatTimer)
    heartbeatTimer = window.setInterval(() => {
      if (!ws || ws.readyState !== WebSocket.OPEN) return
      try {
        ws.send(JSON.stringify({ type: 'ping' }))
      } catch {
        // 发送失败时等待 onclose 触发重连
      }
    }, HEARTBEAT_MS)
  }

  const scheduleReconnect = () => {
    if (stopped) return
    clearTimeout(reconnectTimer)
    reconnectTimer = window.setTimeout(() => {
      connect()
    }, reconnectMs)
    reconnectMs = Math.min(reconnectMs * 2, MAX_BACKOFF_MS)
  }

  const connect = () => {
    if (stopped) return
    const url = buildSocketUrl()
    if (!url) return
    try {
      ws = new WebSocket(url)
    } catch {
      scheduleReconnect()
      return
    }

    ws.onopen = () => {
      reconnectMs = 1000
      startHeartbeat()
      onOpen?.()
    }
    ws.onclose = () => {
      clearInterval(heartbeatTimer)
      onClose?.()
      scheduleReconnect()
    }
    ws.onmessage = (ev) => {
      try {
        const data = JSON.parse(ev.data)
        if (data?.type === 'pong') return
        onMessage?.(data)
      } catch {
        // 非 JSON 忽略
      }
    }
  }

  connect()
  const send = (payload) => {
    if (!ws || ws.readyState !== WebSocket.OPEN) return false
    try {
      ws.send(JSON.stringify(payload))
      return true
    } catch {
      return false
    }
  }

  const disconnect = () => {
    stopped = true
    clearTimers()
    try {
      ws?.close()
    } catch {
      // ignore
    }
  }
  disconnect.send = send
  return disconnect
}
