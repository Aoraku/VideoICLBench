/**
 * 4.1：置顶在前（置顶内部按 updated_at 降序），其余按 updated_at 降序。
 * @param {Array<Record<string, unknown>>} list
 */
export function sortConversations(list) {
  if (!Array.isArray(list)) return []
  return [...list].sort((a, b) => {
    const pa = Boolean(a.is_pinned)
    const pb = Boolean(b.is_pinned)
    if (pa !== pb) return pa ? -1 : 1
    const ta = new Date(a.updated_at || 0).getTime()
    const tb = new Date(b.updated_at || 0).getTime()
    return tb - ta
  })
}
