/**
 * 将接口错误转换为用户可见文案，不展示路径、HTTP 状态原文或后端内部信息。
 * @param {unknown} err - apiFetch 抛出的 Error（可带 .code）
 * @param {string} [fallback]
 */
const BY_CODE = {
  INVALID_CREDENTIALS: '账号或密码错误',
  ACCOUNT_NOT_FOUND: '账号或密码错误',
  USERNAME_EXISTS: '该用户名已被使用',
  USERNAME_TAKEN: '该用户名已被使用',
  EMAIL_EXISTS: '该邮箱已被使用',
  EMAIL_TAKEN: '该邮箱已被使用',
  PHONE_EXISTS: '该手机号已被使用',
  INVALID_VERIFY_CODE: '验证码无效或已过期',
  VERIFY_CODE_EXPIRED: '验证码已过期',
  WEAK_PASSWORD: '密码不符合要求',
  INVALID_PASSWORD: '密码错误',
  OLD_PASSWORD_WRONG: '当前密码不正确',
  UNAUTHORIZED: '请先登录',
  FORBIDDEN: '没有权限执行此操作',
  RATE_LIMITED: '操作过于频繁，请稍后再试',
  USER_NOT_FOUND: '用户不存在',
  ALREADY_FRIENDS: '对方已是你的好友',
  REQUEST_EXISTS: '已发送申请，请等待对方处理',
  BLOCKED: '无法发送好友申请',
  GROUP_EXISTS: '分组名称已存在',
  NOT_FOUND: '资源不存在',
  EMPTY_CONTENT: '消息内容不能为空',
  CONTENT_TOO_LONG: '消息过长',
  INVALID_MESSAGE_TYPE: '不支持的消息类型',
  BLOCKED_BY_USER: '消息发送失败',
  NOT_MEMBER: '你不是该会话成员',
  NOT_OWNER: '仅群主可执行此操作',
  PERMISSION_DENIED: '没有权限执行此操作',
  OWNER_CANNOT_LEAVE: '请先转让群主后再退出群聊',
  NOT_FRIEND: '对方不是你的好友',
  ALREADY_MEMBER: '对方已在群内',
  INVITATION_EXISTS: '已有待处理的入群邀请',
  INVALID_PARAMS: '请求参数不合法',
  MEMBER_NOT_FOUND: '成员不存在',
  CANNOT_REMOVE_SELF: '不能移除自己，请使用退出群聊',
  ALREADY_ADMIN: '该成员已是管理员',
  NOT_ADMIN: '该成员不是管理员',
  CONVERSATION_NOT_FOUND: '会话不存在',
  REPLY_MSG_NOT_FOUND: '被回复的消息不存在',
}

export function userFacingError(err, fallback = '操作失败，请稍后重试') {
  const code = err && typeof err === 'object' && err !== null && 'code' in err ? err.code : null
  const msg = err && typeof err === 'object' && err !== null && typeof err.message === 'string' ? err.message.trim() : ''
  if (typeof code === 'string' && BY_CODE[code]) return BY_CODE[code]
  if (typeof code === 'string' && msg) return msg
  return fallback
}
