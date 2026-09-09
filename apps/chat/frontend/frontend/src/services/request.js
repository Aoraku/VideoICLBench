/**
 * 公共 HTTP 封装入口（与 api/client.js 对齐，避免重复实现）
 * 约定：此处只做 re-export；若调整鉴权/重试逻辑，由负责人一次性改 api/client.js。
 */
export { apiFetch } from '../api/client.js'
