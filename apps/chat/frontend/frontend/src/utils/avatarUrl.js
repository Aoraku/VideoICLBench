/**
 * 将接口返回的头像地址转为当前页面可请求的 URL。
 * 对 /avatars/* 与 /media/* 统一归一到同源路径，避免后端返回内网域名导致图片加载失败。
 */
export function resolveAvatarSrc(avatar) {
  if (avatar == null) return ''

  let raw = avatar
  if (raw && typeof raw === 'object') {
    const obj = /** @type {Record<string, unknown>} */ (raw)
    raw = obj.url ?? obj.avatar ?? obj.src ?? obj.path ?? ''
  }

  const s = String(raw).trim()
  if (!s) return ''
  if (['null', 'undefined', 'none', 'nan'].includes(s.toLowerCase())) return ''
  if (/^data:image\//i.test(s)) return s

  if (!/^https?:\/\//i.test(s)) {
    const path = s.startsWith('/') ? s : `/${s}`
    if (path.startsWith('/avatars/')) return `/media${path}`
    return path
  }

  try {
    const u = new URL(s)
    if (u.pathname.startsWith('/avatars/')) {
      return `/media${u.pathname}${u.search}${u.hash}`
    }
    if (u.pathname.startsWith('/media/')) {
      const isDevPort =
        typeof window !== 'undefined' &&
        (window.location.port === '5173' || window.location.port === '5174')
      return isDevPort ? `${u.pathname}${u.search}${u.hash}` : s
    }
    return s
  } catch {
    return s
  }
}
