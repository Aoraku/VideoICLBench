# 即时通讯系统 API 文档 (完整版)

> **版本**: v3.0  
> **基础路径**: `https://<domain>/api`  
> **WebSocket 路径**: `wss://<domain>/ws/chat/`  
> **认证方式**: JWT (JSON Web Token)  
> **日期**: 2026-03  
> **技术栈**: Django + Django REST Framework + Django Channels + React

---

## 全局约定

### 认证机制

除注册、登录、刷新 Token 接口外，所有接口均需在请求头中携带 JWT：

```
Authorization: Bearer <access_token>
```

### 通用错误响应格式

```json
{
  "error": {
    "code": "ERROR_CODE",
    "message": "人类可读的错误描述"
  }
}
```

### 通用状态码

| 状态码 | 含义 |
|--------|------|
| 200 | 请求成功 |
| 201 | 资源创建成功 |
| 204 | 操作成功，无返回内容 |
| 400 | 请求参数错误 |
| 401 | 未认证 / Token 过期 |
| 403 | 无权限执行该操作 |
| 404 | 资源不存在 |
| 409 | 资源冲突 |
| 422 | 请求格式正确但语义错误 |
| 429 | 请求过于频繁（限流） |
| 500 | 服务器内部错误 |

第一优先：401 Unauthorized    — 用户未登录 / Token 无效或过期
    ↓
第二优先：404 Not Found       — 资源不存在（会话、消息、用户等）
    ↓
第三优先：403 Forbidden       — 资源存在但无权操作（非成员、非群主等）
    ↓
第四优先：409 Conflict        — 有权操作但状态冲突（已是好友、已处理等）
    ↓
第五优先：400 Bad Request     — 参数格式校验错误

### 分页约定

支持分页的接口统一使用以下 query 参数：

| 参数 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `page` | int | 1 | 页码，从 1 开始 |
| `page_size` | int | 20 | 每页条数，最大 100 |

分页响应统一包含：

```json
{
  "total": 128,
  "page": 1,
  "page_size": 20,
  "results": [...]
}
```

### 消息类型枚举

全局统一的消息 `type` 枚举值：

| type | 说明 | content 结构 |
|------|------|-------------|
| `text` | 纯文本 | `{ "text": "..." }` |
| `image` | 图片 | `{ "url": "...", "thumbnail_url": "...", "width": 1920, "height": 1080, "size": 204800 }` |
| `video` | 视频 | `{ "url": "...", "thumbnail_url": "...", "duration": 120, "width": 1920, "height": 1080, "size": 10485760 }` |
| `audio` | 语音消息 | `{ "url": "...", "duration": 15, "size": 51200 }` |
| `file` | 文件 | `{ "url": "...", "filename": "report.pdf", "size": 1048576, "mime_type": "application/pdf" }` |
| `code` | 代码 | `{ "language": "python", "code": "print('hello')" }` |
| `contact_card` | 好友名片 | `{ "user_id": 1001, "username": "alice", "avatar": "..." }` |
| `forward` | 合并转发 | `{ "title": "alice 和 bob 的聊天记录", "summary": ["alice: ...", "bob: ..."], "msg_list": [...] }` |
| `system` | 系统消息 | `{ "action": "member_joined", "text": "eve 加入了群聊" }` |

> **实现注意**：前端根据 `type` 字段选择不同的消息气泡组件渲染。后端在存储时 `content` 字段以 JSON 格式存储（Django 的 `JSONField`）。

---

# 一、用户认证模块 (Auth)

---

## 1.1 用户注册

`POST /api/auth/register`

**无需认证**

### Request Body

```json
{
  "username": "alice",
  "password": "P@ssw0rd123",
  "email": "alice@example.com",
  "phone": "13800138000"
}
```

| 字段 | 类型 | 必填 | 校验规则 |
|------|------|------|----------|
| `username` | string | 是 | 3-20 字符，仅字母、数字、下划线，全局唯一 |
| `password` | string | 是 | 8-32 字符，需包含大写字母、小写字母、数字中至少两种 |
| `email` | string | 否 | 合法邮箱格式 |
| `phone` | string | 否 | 合法手机号格式 |

### Response — 201 Created

```json
{
  "user_id": 1001,
  "username": "alice",
  "email": "alice@example.com",
  "phone": "13800138000",
  "avatar": null,
  "created_at": "2026-03-14T10:00:00Z"
}
```

### 异常状态码

| 状态码 | error.code | 触发条件 |
|--------|------------|----------|
| 400 | `INVALID_PARAMS` | 缺少必填字段或格式不合法 |
| 409 | `USERNAME_EXISTS` | 用户名已被注册 |
| 409 | `EMAIL_EXISTS` | 邮箱已被注册 |
手机已被注册？

> **实现注意**：后端使用 Django 的 `make_password()` 对密码加盐哈希存储，禁止明文存储。

---

好，这个改动很合理。以下是修改后的 1.2 接口：

---

## 1.2 用户登录

`POST /api/auth/login`

**无需认证**

### Request Body

```json
{
  "login_type": "username",
  "identifier": "alice",
  "password": "P@ssw0rd123"
}
```

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `login_type` | string | 是 | 登录方式：`username` / `email` / `phone` |
| `identifier` | string | 是 | 对应的登录凭证（用户名 / 邮箱 / 手机号） |
| `password` | string | 是 | 密码 |

### 三种登录方式示例

```json
{ "login_type": "username", "identifier": "alice", "password": "P@ssw0rd123" }
```

```json
{ "login_type": "email", "identifier": "alice@example.com", "password": "P@ssw0rd123" }
```

```json
{ "login_type": "phone", "identifier": "13800138000", "password": "P@ssw0rd123" }
```

### Response — 200 OK

（与原来相同，不变）

```json
{
  "access_token": "eyJhbGciOiJIUzI1NiIs...",
  "refresh_token": "eyJhbGciOiJIUzI1NiIs...",
  "expires_in": 3600,
  "user": {
    "user_id": 1001,
    "username": "alice",
    "avatar": "https://cdn.example.com/avatars/1001.jpg",
    "email": "alice@example.com",
    "phone": "13800138000",
    "status": {
      "presence": "online",
      "status_text": "",
      "status_emoji": ""
    }
  }
}
```

### 异常状态码

| 状态码 | error.code | 触发条件 |
|--------|------------|----------|
| 400 | `INVALID_PARAMS` | 缺少必填字段 / `login_type` 不合法 |
| 401 | `INVALID_CREDENTIALS` | 账号或密码错误 |
| 404 | `ACCOUNT_NOT_FOUND` | 该邮箱/手机号未绑定任何账号 |

> **实现注意**：
> - 后端根据 `login_type` 选择查询字段：`username` → `User.username`，`email` → `User.email`，`phone` → `User.phone`。
> - 邮箱和手机号登录前提是用户注册时绑定了对应信息。如果用户没绑邮箱却用邮箱登录，返回 `ACCOUNT_NOT_FOUND`。
> - 出于安全考虑，`INVALID_CREDENTIALS` 和 `ACCOUNT_NOT_FOUND` 在生产环境中可以统一返回模糊提示"账号或密码错误"，避免暴露哪些邮箱/手机号已注册。但大作业里分开返回更方便调试。
> - 登录成功后，后端应将用户状态设为 `online`，并通过 WebSocket 向其所有好友推送 `presence_change` 事件。
> - 前端登录成功后应**立即建立 WebSocket 连接**，然后调用 `GET /api/sync/messages` 拉取离线增量消息，最后调用 `GET /api/conversations` 获取最新会话列表。
> **前端**：登录页面提供一个切换标签或下拉选择，让用户选择"用户名登录 / 邮箱登录 / 手机号登录"，输入框的 placeholder 随之变化。
> 
---

## 1.3 刷新 Token

`POST /api/auth/refresh`

**无需认证**（使用 refresh_token）

### Request Body

```json
{
  "refresh_token": "eyJhbGciOiJIUzI1NiIs..."
}
```

### Response — 200 OK

```json
{
  "access_token": "eyJhbGciOiJIUzI1NiIs...(新)",
  "expires_in": 3600
}
```

### 异常状态码

| 状态码 | error.code | 触发条件 |
|--------|------------|----------|
| 401 | `INVALID_REFRESH_TOKEN` | refresh_token 无效或过期 |

---

## 1.4 用户登出

`POST /api/auth/logout`

**需要认证**

### Request Body

```json
{
  "refresh_token": "eyJhbGciOiJIUzI1NiIs..."
}
```

### Response — 204 No Content

### 异常状态码

| 状态码 | error.code | 触发条件 |
|--------|------------|----------|
| 401 | `UNAUTHORIZED` | 未携带有效 access_token |

> **实现注意**：后端将 refresh_token 加入黑名单、将用户状态设为 `offline` 并记录 `last_seen` 时间、关闭该用户的 WebSocket 连接、向好友推送 `presence_change` 事件。

---

## 1.5 注销账号

`DELETE /api/auth/account`

**需要认证**

### Request Body

```json
{
  "password": "P@ssw0rd123"
}
```

### Response — 204 No Content

### 异常状态码

| 状态码 | error.code | 触发条件 |
|--------|------------|----------|
| 401 | `UNAUTHORIZED` | 未认证 |
| 403 | `WRONG_PASSWORD` | 确认密码不正确 |
| 409 | `OWNED_GROUP_EXISTS` | 用户仍是群主，需要先转让或解散群聊 |

> **实现注意**：后端需级联处理以下数据：
> 1. 删除所有好友关系和待处理的好友申请
> 2. 退出所有群聊（若是群主需先转让群主或解散群聊）
> 3. 该用户发出的历史消息中，发送者标记为"已注销用户"
> 4. 删除所有隐私设置、状态、收藏等个人数据
> 5. 通过 WebSocket 通知所有相关用户

# 二、用户信息模块 (Users)

---

## 2.1 获取当前用户信息

`GET /api/users/me`

**需要认证**

### Response — 200 OK

```json
{
  "user_id": 1001,
  "username": "alice",
  "avatar": "https://cdn.example.com/avatars/1001.jpg",
  "email": "alice@example.com",
  "phone": "13800138000",
  "status": {
    "presence": "online",
    "status_text": "考试周",
    "status_emoji": "📚"
  },
  "privacy": {
    "allow_search_by_username": true,
    "allow_search_by_email": false,
    "allow_search_by_phone": false,
    "allow_add_from_group": true
  },
  "created_at": "2026-03-14T10:00:00Z"
}
```

---

## 2.2 修改个人信息

`PUT /api/users/me`

**需要认证**

> 统一接口处理所有个人信息的修改。根据字段敏感程度，部分修改需要额外验证。

### Request Body

```json
{
  "username": "alice_new",
  "phone": "13900139000",
  "email": "new@example.com",
  "password": "NewP@ss456",
  "old_password": "P@ssw0rd123"
}
```

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `username` | string | 否 | 新用户名 |
| `phone` | string | 否 | 新手机号（普通信息，直接修改） |
| `email` | string | 否 | 新邮箱 |
| `password` | string | 否 | 新密码 |
| `old_password` | string | 条件必填 | 修改手机号、邮箱或密码时必填，用于验证当前密码 |

**验证规则**：

| 修改的字段 | 所需验证 |
|-----------|---------|
| `username` | 无需额外验证 |
| `phone` | 必须传 `old_password` 验证当前密码 |
| `password` | 必须传 `old_password` 验证旧密码 |
| `email` | 必须传 `old_password` 验证当前密码 |

### Response — 200 OK

```json
{
  "user_id": 1001,
  "username": "alice_new",
  "avatar": "https://cdn.example.com/avatars/1001.jpg",
  "email": "new@example.com",
  "phone": "13900139000",
  "created_at": "2026-03-14T10:00:00Z"
}
```

### 异常状态码

| 状态码 | error.code | 触发条件 |
|--------|------------|----------|
| 400 | `INVALID_PARAMS` | 字段格式不合法 |
| 403 | `WRONG_PASSWORD` | 旧密码验证失败 |
| 403 | `OLD_PASSWORD_REQUIRED` | 修改手机号、邮箱或密码但未提供当前密码 |
| 409 | `USERNAME_EXISTS` | 新用户名已被占用 |
| 409 | `EMAIL_EXISTS` | 新邮箱已被占用 |
| 409 | `PHONE_EXISTS` | 新手机号已被占用 |

---

## 2.3 上传头像

`POST /api/users/me/avatar`

**需要认证**

### Request

`Content-Type: multipart/form-data`

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `file` | File | 是 | 图片文件，支持 jpg/png/gif/webp，最大 5MB |

### Response — 200 OK

```json
{
  "avatar": "https://cdn.example.com/avatars/1001_v3.jpg"
}
```

### 异常状态码

| 状态码 | error.code | 触发条件 |
|--------|------------|----------|
| 400 | `INVALID_FILE_TYPE` | 文件类型不支持 |
| 400 | `FILE_TOO_LARGE` | 文件超过 5MB |

---

## 2.4 搜索用户【注：从全体用户列表而非好友列表中搜索，可以添加陌生人】

`GET /api/users/search?keyword=ali&page=1&page_size=20`

**需要认证**

### Query Parameters

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `keyword` | string | 是 | 搜索关键词 |
| `page` | int | 否 | 默认 1 |
| `page_size` | int | 否 | 默认 20 |


### Response — 200 OK

```json
{
  "total": 2,
  "page": 1,
  "page_size": 20,
  "results": [
    {
      "user_id": 1001,
      "username": "alice",
      "avatar": "https://cdn.example.com/avatars/1001.jpg",
      "status": {
        "presence": "online",
        "status_text": "",
        "status_emoji": ""
      }
    }
  ]
}
```

> **实现注意**：后端搜索时需检查目标用户的隐私设置。根据 `keyword` 匹配的字段不同，分别检查：
> - 匹配用户名 → 检查 `allow_search_by_username`
> - 匹配邮箱 → 检查 `allow_search_by_email`
> - 匹配手机号 → 检查 `allow_search_by_phone`
>
> 被隐私设置屏蔽的用户不出现在搜索结果中。

---

## 2.5 获取指定用户公开信息

`GET /api/users/{user_id}`

**需要认证**

### Response — 200 OK

```json
{
  "user_id": 1002,
  "username": "bob",
  "avatar": "https://cdn.example.com/avatars/1002.jpg",
  "status": {
    "presence": "online",
    "status_text": "Working",
    "status_emoji": "💻"
  },
  "is_friend": true,
  "is_blocked": false,
  "remark": "Bob同学",
  "created_at": "2026-03-01T08:00:00Z"
}
```

> **实现注意**：
> - `is_friend` 和 `is_blocked` 基于当前用户与目标用户的关系。
> - `remark` 为当前用户为该好友设置的备注名，非好友则为 `null`。
> - 如果目标用户将 presence 设为 `invisible`（隐身），则返回的 `presence` 应显示为 `"offline"`。

### 异常状态码

| 状态码 | error.code | 触发条件 |
|--------|------------|----------|
| 404 | `USER_NOT_FOUND` | 用户不存在或已注销 |

---

## 2.6 隐私权限设置

`PUT /api/users/me/privacy`

**需要认证**

### Request Body

```json
{
  "allow_search_by_username": true,
  "allow_search_by_email": false,
  "allow_search_by_phone": false,
  "allow_add_from_group": true
}
```

| 字段 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `allow_search_by_username` | bool | true | 是否允许通过用户名被搜索到 |
| `allow_search_by_email` | bool | true | 是否允许通过邮箱被搜索到 |
| `allow_search_by_phone` | bool | true | 是否允许通过手机号被搜索到 |
| `allow_add_from_group` | bool | true | 是否允许群聊内成员直接添加好友 |

> 所有字段均可选，只传需要修改的字段。

### Response — 200 OK

```json
{
  "allow_search_by_username": true,
  "allow_search_by_email": false,
  "allow_search_by_phone": false,
  "allow_add_from_group": true,
  "updated_at": "2026-03-14T11:00:00Z"
}
```

---

## 2.7 获取隐私权限设置

`GET /api/users/me/privacy`

**需要认证**

### Response — 200 OK

```json
{
  "allow_search_by_username": true,
  "allow_search_by_email": false,
  "allow_search_by_phone": false,
  "allow_add_from_group": true
}
```

---

## 2.8 设置自定义状态

`PUT /api/users/me/status`

**需要认证**

### Request Body

```json
{
  "presence": "busy",
  "status_text": "考试周，回复可能较慢",
  "status_emoji": "📚"
}
```

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `presence` | string | 否 | `online` / `offline` / `busy` / `away` / `invisible`（隐身） |
| `status_text` | string | 否 | 自定义状态文本，最大 100 字符，空字符串表示清除 |
| `status_emoji` | string | 否 | 状态表情，单个 emoji，空字符串表示清除 |

### Response — 200 OK

```json
{
  "presence": "busy",
  "status_text": "考试周，回复可能较慢",
  "status_emoji": "📚",
  "updated_at": "2026-03-14T11:05:00Z"
}
```

> **实现注意**：
> - 状态变更后通过 WebSocket 向所有好友推送 `presence_change` 事件。
> - `invisible` 状态下，好友看到的 `presence` 为 `"offline"`，但该用户实际可以正常收发消息。
> - 自动状态切换：WebSocket 连接建立时自动设为 `online`（除非用户手动设了其他状态），WebSocket 断开时自动设为 `offline` 并记录 `last_seen`。
>
> **前端**：好友列表和聊天界面顶栏显示对方的 presence 图标和 status_text。设置状态的入口放在个人头像下拉菜单中。

---

## 2.9 个人 AI API Key 设置【拓展功能】

`GET /api/users/me/ai-key`

**需要认证**

### Response — 200 OK

```json
{
  "configured": true,
  "masked_key": "QC-fa...13b",
  "ai_base_url": "https://aiping.cn/api/v1",
  "ai_model": "DeepSeek-R1-0528"
}
```

`PUT /api/users/me/ai-key`

```json
{
  "api_key": "QC-xxxxxxxx"
}
```

`DELETE /api/users/me/ai-key`

> **实现注意**：后端只返回脱敏后的 `masked_key`，不返回完整 API Key。AI 会话和群聊 `@AI` 均使用发起用户自己的 API Key；未配置时返回 `AI_API_KEY_REQUIRED`。

---

# 三、好友关系模块 (Friends)

---

## 3.1 发送好友申请

`POST /api/friends/request`

**需要认证**

### Request Body

```json
{
  "target_user_id": 1002,
  "message": "Hi, I'm Alice from the project group.",
  "source": "search"
}
```

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `target_user_id` | int | 是 | 目标用户 ID |
| `message` | string | 否 | 验证消息 |
| `source` | string | 否 | 来源：`search` / `group:{conv_id}` / `contact_card:{msg_id}` |

### Response — 201 Created

```json
{
  "request_id": 5001,
  "from_user_id": 1001,
  "to_user_id": 1002,
  "message": "Hi, I'm Alice from the project group.",
  "source": "search",
  "status": "pending",
  "created_at": "2026-03-14T10:30:00Z"
}
```

### 异常状态码

| 状态码 | error.code | 触发条件 |
|--------|------------|----------|
| 400 | `SELF_REQUEST` | 不能添加自己为好友 |
| 403 | `PRIVACY_DENIED` | 对方隐私设置不允许该来源的添加（见下方说明） |
| 403 | `USER_BLOCKED` | 你已被对方拉黑 |
| 404 | `USER_NOT_FOUND` | 目标用户不存在 |
| 409 | `ALREADY_FRIENDS` | 已经是好友 |
| 409 | `REQUEST_EXISTS` | 已有待处理的好友申请 |

> **实现注意 — 隐私检查规则**：
> - `source = "search"` → 正常通过，搜索阶段已经根据隐私设置过滤了
> - `source = "group:*"` → 检查对方 `allow_add_from_group`，若为 false 则返回 `PRIVACY_DENIED`
> - `source = "contact_card:*"` → **跳过所有隐私检查**，名片添加一律允许申请
> - 如果对方在黑名单中，**一律拒绝**（优先级最高）
>
> 发送成功后通过 WebSocket 向对方推送 `friend_request` 通知。

---

## 3.2 获取好友申请列表

`GET /api/friends/requests?type=received&status=pending&page=1&page_size=20`

**需要认证**

### Query Parameters

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `type` | string | 否 | `received`（默认）/ `sent` |
| `status` | string | 否 | `pending`（默认）/ `accepted` / `rejected` / `all` |


### Response — 200 OK

```json
{
  "total": 2,
  "page": 1,
  "page_size": 20,
  "results": [
    {
      "request_id": 5002,
      "from_user": {
        "user_id": 1003,
        "username": "charlie",
        "avatar": "https://cdn.example.com/avatars/1003.jpg"
      },
      "message": "Hello!",
      "source": "contact_card:9050",
      "status": "pending",
      "created_at": "2026-03-14T09:00:00Z"
    }
  ]
}
```

---

## 3.3 处理好友申请

`PUT /api/friends/requests/{request_id}`

**需要认证**

### Request Body

```json
{
  "action": "accept"
}
```

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `action` | string | 是 | `accept` / `reject` |

### Response — 200 OK

```json
{
  "request_id": 5002,
  "status": "accepted",
  "updated_at": "2026-03-14T10:35:00Z"
}
```

### 异常状态码

| 状态码 | error.code | 触发条件 |
|--------|------------|----------|
| 403 | `NOT_RECIPIENT` | 只有接收方可以处理 |
| 404 | `REQUEST_NOT_FOUND` | 申请不存在 |
| 409 | `REQUEST_ALREADY_HANDLED` | 已处理过 |

> **实现注意**：同意后，后端建立双向好友关系。通过 WebSocket 通知双方 `friend_request_result` 事件。

---

## 3.4 获取好友列表【注：查看自己的好友列表，前端看到通讯录列表】

`GET /api/friends?page=1&page_size=50`

**需要认证**

### Response — 200 OK

```json
{
  "total": 15,
  "page": 1,
  "page_size": 50,
  "results": [
    {
      "user_id": 1002,
      "username": "bob",
      "avatar": "https://cdn.example.com/avatars/1002.jpg",
      "remark": "Bob同学",
      "status": {
        "presence": "online",
        "status_text": "Working",
        "status_emoji": "💻"
      },
      "group_id": 101,
      "group_name": "同事",
      "is_blocked": false,
      "added_at": "2026-03-10T08:00:00Z"
    }
  ]
}
```

> **前端**：好友列表按分组折叠展示。未分组的好友归入"我的好友"默认分组。每个好友项显示头像、用户名（有备注则显示备注名）、在线状态图标和状态文本。被拉黑的好友可以用灰色标识。

---

## 3.5 删除好友

`DELETE /api/friends/{friend_user_id}`

**需要认证**

### Response — 204 No Content

### 异常状态码

| 状态码 | error.code | 触发条件 |
|--------|------------|----------|
| 404 | `FRIEND_NOT_FOUND` | 该用户不是你的好友 |

> **实现注意**：后端删除双向好友关系。对应的私聊会话不自动删除，但前端可以提示用户是否同时删除。

---

## 3.6 获取好友分组列表

`GET /api/friends/groups`

**需要认证**

### Response — 200 OK

```json
{
  "groups": [
    { "group_id": null, "name": "未分组", "friend_count": 3 },
    { "group_id": 101, "name": "同事", "friend_count": 5 },
    { "group_id": 102, "name": "同学", "friend_count": 8 }
  ]
}
```

---

## 3.7 创建好友分组

`POST /api/friends/groups`

**需要认证**

### Request Body

```json
{
  "name": "家人"
}
```

### Response — 201 Created

```json
{
  "group_id": 103,
  "name": "家人",
  "friend_count": 0
}
```

### 异常状态码

| 状态码 | error.code | 触发条件 |
|--------|------------|----------|
| 409 | `GROUP_NAME_EXISTS` | 分组名已存在 |

---

## 3.8 修改好友分组

`PUT /api/friends/groups/{group_id}`

**需要认证**

### Request Body

```json
{
  "name": "家人和亲戚",
  "add_friend_ids": [1004, 1005],
  "remove_friend_ids": [1002]
}
```

### Response — 200 OK

```json
{
  "group_id": 103,
  "name": "家人和亲戚",
  "friend_count": 2
}
```

### 异常状态码

| 状态码 | error.code | 触发条件 |
|--------|------------|----------|
| 404 | `GROUP_NOT_FOUND` | 分组不存在 |
| 404 | `FRIEND_NOT_FOUND` | add_friend_ids 中包含非好友用户 |

---

## 3.9 删除好友分组

`DELETE /api/friends/groups/{group_id}`

**需要认证**

### Response — 204 No Content

> 该分组下的好友变为未分组状态。

---

## 3.10 设置好友备注

`PUT /api/friends/{friend_user_id}/remark`

**需要认证**

### Request Body

```json
{
  "remark": "Bob同学"
}
```

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `remark` | string | 是 | 备注名，最大 30 字符。空字符串表示清除备注 |

### Response — 200 OK

```json
{
  "friend_user_id": 1002,
  "remark": "Bob同学",
  "updated_at": "2026-03-14T11:10:00Z"
}
```

### 异常状态码

| 状态码 | error.code | 触发条件 |
|--------|------------|----------|
| 404 | `FRIEND_NOT_FOUND` | 不是好友 |

> **前端**：设置备注后，该好友在好友列表、会话列表、聊天界面中的显示名称均替换为备注名。

---

## 3.11 拉入黑名单

`POST /api/friends/blacklist`

**需要认证**

### Request Body

```json
{
  "user_id": 1005
}
```

### Response — 201 Created

```json
{
  "user_id": 1005,
  "username": "eve",
  "blocked_at": "2026-03-14T11:15:00Z"
}
```

### 异常状态码

| 状态码 | error.code | 触发条件 |
|--------|------------|----------|
| 400 | `SELF_BLOCK` | 不能拉黑自己 |
| 409 | `ALREADY_BLOCKED` | 已在黑名单 |

> **实现注意**：
> - 拉黑后对方无法发送好友申请、无法发送私聊消息。
> - 如果双方是好友，拉黑**不会自动删除好友关系**，但对方发的消息会被服务端过滤不推送。
> - 拉黑是单向的：A 拉黑 B，B 不会收到任何通知，B 发消息不会报错但 A 收不到。

---

## 3.12 解除黑名单

`DELETE /api/friends/blacklist/{user_id}`

**需要认证**

### Response — 204 No Content

### 异常状态码

| 状态码 | error.code | 触发条件 |
|--------|------------|----------|
| 404 | `NOT_IN_BLACKLIST` | 该用户不在黑名单中 |

---

## 3.13 获取黑名单列表

`GET /api/friends/blacklist`

**需要认证**

### Response — 200 OK

```json
{
  "results": [
    {
      "user_id": 1005,
      "username": "eve",
      "avatar": "https://cdn.example.com/avatars/1005.jpg",
      "blocked_at": "2026-03-14T11:15:00Z"
    }
  ]
}
```

---

## 3.14 添加到白名单【注：类似微信星标好友】

`POST /api/friends/whitelist`

**需要认证**

### Request Body

```json
{
  "user_id": 1006
}
```

### Response — 201 Created

```json
{
  "user_id": 1006,
  "username": "frank",
  "added_at": "2026-03-14T11:20:00Z"
}
```

> **实现注意**：白名单用户在好友申请时跳过隐私权限检查（效果类似名片添加），但仍受黑名单约束。白名单优先级：黑名单 > 白名单 > 隐私设置。

---

## 3.15 移除白名单

`DELETE /api/friends/whitelist/{user_id}`

**需要认证**

### Response — 204 No Content

---

## 3.16 获取白名单列表

`GET /api/friends/whitelist`

**需要认证**

### Response — 200 OK

```json
{
  "results": [
    {
      "user_id": 1006,
      "username": "frank",
      "avatar": null,
      "added_at": "2026-03-14T11:20:00Z"
    }
  ]
}
```

---

# 四、会话模块 (Conversations)

---

## 4.1 获取会话列表【注：会话指的是聊天窗口，之所以用会话id索引而不用用户id索引是为了统一私聊和群聊】

`GET /api/conversations?page=1&page_size=30`

**需要认证**

### Response — 200 OK

```json
{
  "total": 12,
  "page": 1,
  "page_size": 30,
  "results": [
    {
      "conversation_id": 2001,
      "type": "private",
      "name": null,
      "avatar": null,
      "peer_user": {
        "user_id": 1002,
        "username": "bob",
        "remark": "Bob同学",
        "avatar": "https://cdn.example.com/avatars/1002.jpg",
        "status": {
          "presence": "online",
          "status_text": "",
          "status_emoji": ""
        }
      },
      "last_message": {
        "msg_id": 9001,
        "sender_id": 1002,
        "sender_name": "bob",
        "type": "text",
        "content": { "text": "Hey, are you free tonight?" },
        "created_at": "2026-03-14T10:40:00Z"
      },
      "unread_count": 3,
      "is_pinned": false,
      "is_muted": false,
      "updated_at": "2026-03-14T10:40:00Z"
    },
    {
      "conversation_id": 2002,
      "type": "group",
      "name": "项目讨论组",
      "avatar": "https://cdn.example.com/groups/2002.jpg",
      "peer_user": null,
      "last_message": {
        "msg_id": 9050,
        "sender_id": 1003,
        "sender_name": "charlie",
        "type": "text",
        "content": { "text": "明天下午开会" },
        "created_at": "2026-03-14T10:38:00Z"
      },
      "unread_count": 0,
      "is_pinned": true,
      "is_muted": false,
      "updated_at": "2026-03-14T10:38:00Z"
    }
  ]
}
```

> **实现注意**：
> - 排序规则：置顶会话排在最前（置顶内部按 `updated_at` 降序），其余按 `updated_at` 降序。
> - `unread_count` 由服务端计算（会话最新消息序号 - 用户的 `read_index`）。
> - 私聊会话的 `name` 为 null，前端应显示 `peer_user.remark`（有备注时）或 `peer_user.username`。
> - `is_muted` 为 true 时，前端未读角标样式变灰、不弹桌面通知。
> - `last_message.content` 在会话列表中只需要展示摘要，前端根据 `type` 取摘要：text 取文本，image 显示"[图片]"，video 显示"[视频]"，file 显示"[文件] xxx.pdf"，code 显示"[代码]"，audio 显示"[语音]"，contact_card 显示"[名片]"，forward 显示"[聊天记录]"。

---

## 4.2 创建会话

`POST /api/conversations`

**需要认证**

### Request Body — 创建私聊

```json
{
  "type": "private",
  "peer_user_id": 1002
}
```

### Request Body — 创建群聊

```json
{
  "type": "group",
  "name": "项目讨论组",
  "member_ids": [1002, 1003, 1004]
}
```

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `type` | string | 是 | `private` / `group` |
| `peer_user_id` | int | 私聊必填 | 对方用户 ID |
| `name` | string | 群聊必填 | 群聊名称，1-50 字符 |
| `member_ids` | int[] | 群聊必填 | 初始成员 ID 列表（不含自己），必须为自己的好友 |

### Response — 201 Created

```json
{
  "conversation_id": 2003,
  "type": "group",
  "name": "项目讨论组",
  "created_at": "2026-03-14T11:00:00Z",
  "members": [
    { "user_id": 1001, "username": "alice", "role": "owner" },
    { "user_id": 1002, "username": "bob", "role": "member" },
    { "user_id": 1003, "username": "charlie", "role": "member" },
    { "user_id": 1004, "username": "david", "role": "member" }
  ]
}
```

### 异常状态码

| 状态码 | error.code | 触发条件 |
|--------|------------|----------|
| 400 | `INVALID_PARAMS` | 缺少必填字段 / member_ids 为空 |
| 403 | `NOT_FRIEND` | member_ids 中包含非好友用户 |
| 404 | `USER_NOT_FOUND` | 用户不存在 |
| 409 | `CONVERSATION_EXISTS` | 与该用户的私聊已存在（返回已有 conversation_id） |

> **实现注意**：创建群聊后，后端自动生成一条系统消息"alice 创建了群聊"，并通过 WebSocket 通知所有被加入的成员。

---

## 4.3 获取会话详情【注：前端用于渲染小窗，放上头像、昵称、和最近一条聊天记录】

`GET /api/conversations/{conv_id}`

**需要认证**

### Response — 200 OK

```json
{
  "conversation_id": 2001,
  "type": "private",
  "name": null,
  "peer_user": {
    "user_id": 1002,
    "username": "bob",
    "remark": "Bob同学",
    "avatar": "https://cdn.example.com/avatars/1002.jpg",
    "status": { "presence": "online", "status_text": "", "status_emoji": "" }
  },
  "is_pinned": false,
  "is_muted": false,
  "unread_count": 3,
  "created_at": "2026-03-10T08:00:00Z",
  "updated_at": "2026-03-14T10:40:00Z"
}
```


### 异常状态码

| 状态码 | error.code | 触发条件 |
|--------|------------|----------|
| 403 | `NOT_MEMBER` | 不是会话成员 |
| 404 | `CONVERSATION_NOT_FOUND` | 会话不存在 |

---

## 4.4 更新会话设置（置顶 / 免打扰）

`PUT /api/conversations/{conv_id}`

**需要认证**

### Request Body

```json
{
  "is_pinned": true,
  "is_muted": false
}
```

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `is_pinned` | bool | 否 | 是否置顶 |
| `is_muted` | bool | 否 | 是否免打扰 |

### Response — 200 OK

```json
{
  "conversation_id": 2001,
  "is_pinned": true,
  "is_muted": false,
  "updated_at": "2026-03-14T11:05:00Z"
}
```

> **前端**：置顶和免打扰操作入口建议放在会话列表右键菜单中。

---

## 4.5 删除会话

`DELETE /api/conversations/{conv_id}`

**需要认证**

> 仅删除当前用户侧的会话和本地聊天记录视图，不影响其他成员。
> 需要注意此时数据库的处理，每个人存一份聊天记录？

### Response — 204 No Content

---

## 4.6 标记会话已读

`PUT /api/conversations/{conv_id}/read`

**需要认证**

### Request Body

```json
{
  "last_read_msg_id": 9050
}
```

### Response — 204 No Content

> **实现注意**：
> - 后端更新该用户在该会话的 `read_index`。
> - 更新后通过 WebSocket 向会话中的其他成员推送 `read_receipt` 事件（用于已读回执展示）。
> - 前端在用户打开/切换到某个会话时自动调用此接口。

---

## 4.7 搜索聊天记录（全局或指定会话搜索，前端在不同位置调用这个接口） 【拓展功能】

`GET /api/conversations/search?keyword=会议&page=1&page_size=20`

**需要认证**

### Query Parameters

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `keyword` | string | 是 | 搜索关键词 |
| `conversation_id` | int | 否 | 限定在某个会话内搜索，不传则全局搜索 |
| `page` | int | 否 | 默认 1 |
| `page_size` | int | 否 | 默认 20 |

### Response — 200 OK

```json
{
  "total": 8,
  "page": 1,
  "page_size": 20,
  "results": [
    {
      "msg_id": 9010,
      "conversation_id": 2002,
      "conversation_name": "项目讨论组",
      "conversation_type": "group",
      "sender": {
        "user_id": 1003,
        "username": "charlie"
      },
      "type": "text",
      "content": { "text": "明天下午会议改到3点" },
      "created_at": "2026-03-13T14:00:00Z",
      "highlight": "明天下午<em>会议</em>改到3点"
    }
  ]
}
```

> **实现注意**：
> - 后端使用 Django 的 `__icontains` 进行模糊搜索，如需更高性能可用 PostgreSQL 全文索引。
> - `highlight` 字段将关键词用 `<em>` 标签包裹，前端可据此高亮显示。
> - 仅搜索 `type: text` 和 `type: code` 的消息内容。
>
> **前端**：搜索结果列表中，点击某条结果可以跳转到对应会话并定位到该消息位置。

---

# 五、消息模块 (Messages)

---

## 5.1 发送消息

`POST /api/conversations/{conv_id}/messages`

**需要认证**

### Request Body — 文本消息

```json
{
  "type": "text",
  "content": { "text": "Hello everyone!" },
  "reply_to_msg_id": null,
  "mentions": []
}
```

### Request Body — 图片消息

```json
{
  "type": "image",
  "content": {
    "url": "https://cdn.example.com/uploads/img_001.jpg",
    "thumbnail_url": "https://cdn.example.com/uploads/img_001_thumb.jpg",
    "width": 1920,
    "height": 1080,
    "size": 204800
  }
}
```

### Request Body — 视频消息

```json
{
  "type": "video",
  "content": {
    "url": "https://cdn.example.com/uploads/vid_001.mp4",
    "thumbnail_url": "https://cdn.example.com/uploads/vid_001_thumb.jpg",
    "duration": 120,
    "width": 1920,
    "height": 1080,
    "size": 10485760
  }
}
```

### Request Body — 语音消息 【拓展功能】

```json
{
  "type": "audio",
  "content": {
    "url": "https://cdn.example.com/uploads/audio_001.webm",
    "duration": 15,
    "size": 51200
  }
}
```

### Request Body — 文件消息

```json
{
  "type": "file",
  "content": {
    "url": "https://cdn.example.com/uploads/report.pdf",
    "filename": "report.pdf",
    "size": 1048576,
    "mime_type": "application/pdf"
  }
}
```

### Request Body — 代码消息

```json
{
  "type": "code",
  "content": {
    "language": "python",
    "code": "def hello():\n    print('Hello, World!')"
  }
}
```

### Request Body — 好友名片 【拓展功能】

```json
{
  "type": "contact_card",
  "content": {
    "user_id": 1005,
    "username": "eve",
    "avatar": "https://cdn.example.com/avatars/1005.jpg"
  }
}
```

### 通用字段

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `type` | string | 是 | 消息类型枚举（见全局约定） |
| `content` | object | 是 | 消息内容，结构随 type 不同 |
| `reply_to_msg_id` | int | 否 | 回复的目标消息 ID |
| `mentions` | int[] | 否 | 被 @ 的用户 ID 列表（仅群聊有效）【拓展功能】 |

### Response — 201 Created

```json
{
  "msg_id": 9100,
  "conversation_id": 2001,
  "sender": {
    "user_id": 1001,
    "username": "alice",
    "avatar": "https://cdn.example.com/avatars/1001.jpg",
    "group_nickname": null
  },
  "type": "text",
  "content": { "text": "Hello everyone!" },
  "reply_to": null,
  "reply_count": 0,
  "mentions": [],
  "reactions": [],
  "is_recalled": false,
  "created_at": "2026-03-14T11:10:00Z"
}
```

> 当 `reply_to_msg_id` 不为 null 时，`reply_to` 返回被回复消息的摘要：

```json
"reply_to": {
  "msg_id": 9050,
  "sender_id": 1003,
  "sender_name": "charlie",
  "type": "text",
  "content_summary": "明天下午开会"
}
```

### 异常状态码

| 状态码 | error.code | 触发条件 |
|--------|------------|----------|
| 400 | `INVALID_MESSAGE_TYPE` | 不支持的消息类型 |
| 400 | `EMPTY_CONTENT` | 消息内容为空 |
| 400 | `CONTENT_TOO_LONG` | 文本超过 5000 字符 / 代码超过 50000 字符 |
| 403 | `NOT_MEMBER` | 不是会话成员 |
| 403 | `BLOCKED_BY_USER` | 私聊中被对方拉黑（消息不会送达，但不告知发送者具体原因，可返回通用的发送失败） |
| 404 | `CONVERSATION_NOT_FOUND` | 会话不存在 |
| 404 | `REPLY_MSG_NOT_FOUND` | 被回复的消息不存在 |

> **实现注意**：
> - 发送成功后，服务端通过 WebSocket 推送 `new_message` 给会话所有在线成员。
> - 图片/视频/音频/文件类消息的资源 URL 需先通过文件上传接口（7.1）获得。
> - **名片消息**：后端需验证 `content.user_id` 对应的用户存在且是发送者的好友。
> - **@提及**：后端检查 `mentions` 列表中的用户是否为群成员。被 @ 的用户即使设置了免打扰也应收到提醒。
>
> **前端**：
> - 不同类型消息使用不同的气泡组件渲染：文本气泡、图片预览（点击放大）、视频播放器、语音播放条、文件卡片（含下载按钮和文件大小）、代码块（语法高亮）、名片卡片（可点击查看资料/添加好友）。
> - 回复消息时，输入框上方显示引用预览条。
> - @提及：输入 `@` 后弹出群成员选择器，选中后在消息文本中插入 `@username`，消息体中 `mentions` 传入对应 user_id。

---

## 5.2 获取聊天记录【注：指定会话（聊天窗口）的所有聊天记录】

`GET /api/conversations/{conv_id}/messages?page=1&page_size=50`

**需要认证**

### Query Parameters

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `before` | string (ISO 8601) | 否 | 获取此时间之前的消息 |
| `after` | string (ISO 8601) | 否 | 获取此时间之后的消息 |
| `sender_id` | int | 否 | 按发送者筛选 |
| `keyword` | string | 否 | 按消息内容搜索 |
| `type` | string | 否 | 按消息类型筛选（`text` / `image` / `file` 等） |
| `page` | int | 否 | 默认 1 |
| `page_size` | int | 否 | 默认 50 |

### Response — 200 OK

```json
{
  "total": 238,
  "page": 1,
  "page_size": 50,
  "results": [
    {
      "msg_id": 9001,
      "sender": {
        "user_id": 1002,
        "username": "bob",
        "avatar": "https://cdn.example.com/avatars/1002.jpg",
        "group_nickname": "Bob the Builder"
      },
      "type": "text",
      "content": { "text": "Hey, are you free tonight?" },
      "reply_to": null,
      "reply_count": 1,
      "mentions": [],
      "reactions": [
        { "emoji": "👍", "count": 2, "users": [1001, 1003], "is_me": true }
      ],
      "read_by_count": 5,
      "is_recalled": false,
      "created_at": "2026-03-14T10:40:00Z"
    }
  ]
}
```

> **实现注意**：
> - 消息默认按 `created_at` 升序排列（最旧的在前）。
> - `group_nickname` 为发送者在该群聊中设置的群昵称，私聊中为 null。
> - `is_recalled` 为 true 的消息，前端应将气泡内容替换为"xxx 撤回了一条消息"。
> - `read_by_count` 在私聊中为 0 或 1（对方是否已读），群聊中为已读人数。
> - 当用户已删除某条消息时（5.5），该消息不应出现在返回结果中。
>
> **前端**：
> - 首次进入会话时加载最新一页消息，上滑加载更多历史消息。
> - 点击回复消息中的引用部分应跳转/滚动到被回复的消息位置。
> - 前端可以给出两个入口，一个是首页顶部搜索框，一个是会话中的搜索框？

---

## 5.3 获取消息的回复列表【注：对某条消息的回复，但比微信的“引用”加了一个聚合功能：消息的气泡下方会显示一个标签"3条回复"。用户点击这个标签时，前端调用这个接口拿到回复列表，弹出一个浮层展示所有回复内容，这样用户就能看到围绕该话题的所有讨论，而不用在大量聊天记录中来回翻找】

`GET /api/conversations/{conv_id}/messages/{msg_id}/replies?page=1&page_size=20`

**需要认证**

### Response — 200 OK

```json
{
  "original_msg": {
    "msg_id": 9001,
    "sender_name": "bob",
    "type": "text",
    "content_summary": "Hey, are you free tonight?"
  },
  "reply_count": 3,
  "total": 3,
  "page": 1,
  "page_size": 20,
  "results": [
    {
      "msg_id": 9002,
      "sender": {
        "user_id": 1001,
        "username": "alice",
        "avatar": "https://cdn.example.com/avatars/1001.jpg"
      },
      "type": "text",
      "content": { "text": "Sure, what's up?" },
      "created_at": "2026-03-14T10:41:00Z"
    }
  ]
}
```

### 异常状态码

| 状态码 | error.code | 触发条件 |
|--------|------------|----------|
| 403 | `NOT_MEMBER` | 不是会话成员 |
| 404 | `MESSAGE_NOT_FOUND` | 消息不存在 |

> **前端**：点击消息气泡上的"X条回复"标签时，可以弹出回复列表浮层，或展开为消息下方的回复线程。

---

## 5.4 获取消息已读详情【注：我们的软件还是有已读未读功能比较好……】

`GET /api/conversations/{conv_id}/messages/{msg_id}/read-status`

**需要认证**

> 群聊中仅群主和管理员可查看完整已读名单；普通成员只能看到已读人数。私聊中所有人可见。

### Response — 200 OK（群主/管理员视角）

```json
{
  "msg_id": 9001,
  "total_members": 15,
  "read_count": 10,
  "unread_count": 5,
  "read_members": [
    { "user_id": 1002, "username": "bob", "read_at": "2026-03-14T10:41:00Z" },
    { "user_id": 1003, "username": "charlie", "read_at": "2026-03-14T10:42:00Z" }
  ],
  "unread_members": [
    { "user_id": 1004, "username": "david" },
    { "user_id": 1005, "username": "eve" }
  ]
}
```

### Response — 200 OK（普通成员视角）

```json
{
  "msg_id": 9001,
  "total_members": 15,
  "read_count": 10,
  "unread_count": 5,
  "read_members": null,
  "unread_members": null
}
```

### 异常状态码

| 状态码 | error.code | 触发条件 |
|--------|------------|----------|
| 403 | `NOT_MEMBER` | 不是会话成员 |
| 404 | `MESSAGE_NOT_FOUND` | 消息不存在 |

> **前端**：
> - 私聊：消息气泡下方显示"已读"/"未读"文字。
> - 群聊：消息气泡下方显示"X人已读"。群主/管理员点击可弹出详细的已读/未读名单面板。

---

## 5.5 删除消息

`DELETE /api/conversations/{conv_id}/messages/{msg_id}`

**需要认证**

> 仅对当前用户不可见（软删除），不影响其他成员。

### Response — 204 No Content

### 异常状态码

| 状态码 | error.code | 触发条件 |
|--------|------------|----------|
| 403 | `NOT_MEMBER` | 不是会话成员 |
| 404 | `MESSAGE_NOT_FOUND` | 消息不存在 |

---

## 5.6 撤回消息 【拓展功能】

`POST /api/conversations/{conv_id}/messages/{msg_id}/recall`

**需要认证**

### Response — 200 OK

```json
{
  "msg_id": 9100,
  "is_recalled": true,
  "recalled_at": "2026-03-14T11:12:00Z"
}
```

### 异常状态码

| 状态码 | error.code | 触发条件 |
|--------|------------|----------|
| 403 | `NOT_SENDER` | 只有消息发送者可以撤回 |
| 403 | `RECALL_TIMEOUT` | 超过 2 分钟不可撤回 |
| 404 | `MESSAGE_NOT_FOUND` | 消息不存在 |
| 409 | `ALREADY_RECALLED` | 消息已被撤回 |

> **实现注意**：
> - 撤回后服务端将消息标记为 `is_recalled: true`，原始内容保留在数据库但不再返回给客户端。
> - 通过 WebSocket 向会话所有成员推送 `message_recalled` 事件。
> - 群主和管理员可以撤回群内任何人的消息（额外的权限规则）。
>
> **前端**：收到 `message_recalled` 事件后，将对应消息气泡内容替换为灰色的"xxx 撤回了一条消息"。

---

## 5.7 转发消息 【拓展功能】

`POST /api/messages/forward`

**需要认证**

### Request Body — 逐条转发

```json
{
  "mode": "individual",
  "msg_ids": [9001, 9002, 9003],
  "source_conv_id": 2001,
  "target_conv_ids": [2002, 2003]
}
```

### Request Body — 合并转发

```json
{
  "mode": "merged",
  "msg_ids": [9001, 9002, 9003],
  "source_conv_id": 2001,
  "target_conv_ids": [2002]
}
```

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `mode` | string | 是 | `individual`（逐条转发）/ `merged`（合并转发） |
| `msg_ids` | int[] | 是 | 要转发的消息 ID 列表，最多 30 条 |
| `source_conv_id` | int | 是 | 消息来源会话 ID |
| `target_conv_ids` | int[] | 是 | 目标会话 ID 列表，最多 5 个 |

### Response — 201 Created

```json
{
  "forwarded_count": 3,
  "target_conversations": [
    {
      "conversation_id": 2002,
      "msg_ids": [9200, 9201, 9202]
    }
  ]
}
```

### 异常状态码

| 状态码 | error.code | 触发条件 |
|--------|------------|----------|
| 400 | `TOO_MANY_MESSAGES` | 超过 30 条 |
| 400 | `TOO_MANY_TARGETS` | 超过 5 个目标会话 |
| 403 | `NOT_MEMBER` | 不是来源或目标会话的成员 |
| 404 | `MESSAGE_NOT_FOUND` | 消息不存在 |

> **实现注意**：
> - 逐条转发：在目标会话中依次创建相同内容的新消息，发送者为当前用户，标记为转发。
> - 合并转发：在目标会话中创建一条 `type: "forward"` 的消息，`content` 包含标题（"alice 和 bob 的聊天记录"）、摘要（前 3 条消息预览）和完整消息列表。
>
> **前端**：
> - 用户长按/右键选择消息后，在工具栏出现"转发"按钮。
> - 点击后弹出会话选择器（可多选），并选择逐条/合并模式。
> - 合并转发的消息气泡显示为卡片样式，标题+摘要，点击可展开查看完整内容。

---

## 5.8 Emoji 表情回应 【拓展功能，贴表情】

### 添加 Reaction

`POST /api/conversations/{conv_id}/messages/{msg_id}/reactions`

**需要认证**

#### Request Body

```json
{
  "emoji": "👍"
}
```

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `emoji` | string | 是 | 单个 Emoji 字符 |

#### Response — 201 Created

```json
{
  "msg_id": 9001,
  "emoji": "👍",
  "user_id": 1001,
  "created_at": "2026-03-14T11:20:00Z"
}
```

#### 异常状态码

| 状态码 | error.code | 触发条件 |
|--------|------------|----------|
| 403 | `NOT_MEMBER` | 不是会话成员 |
| 409 | `REACTION_EXISTS` | 已对该消息使用过该 Emoji |

### 取消 Reaction

`DELETE /api/conversations/{conv_id}/messages/{msg_id}/reactions/{emoji}`

**需要认证**

#### Response — 204 No Content

> **实现注意**：
> - Reaction 变更通过 WebSocket 推送 `reaction_update` 事件给会话所有成员。
> - 每人对同一条消息的同一个 Emoji 只能发一次，但可以对同一条消息发不同的 Emoji。
>
> **前端**：
> - 消息气泡下方显示 Emoji 和对应计数，如"👍 3 ❤️ 1"。
> - 鼠标悬浮在 Emoji 上可以查看具体是谁回应的。
> - 右键/悬浮消息弹出的拓展菜单中包含常用 Emoji 快速选择栏。

---

## 5.9 收藏消息 【拓展功能】

### 添加收藏

`POST /api/bookmarks`

**需要认证**

#### Request Body

```json
{
  "msg_id": 9001,
  "conversation_id": 2001,
  "note": "重要会议信息"
}
```

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `msg_id` | int | 是 | 消息 ID |
| `conversation_id` | int | 是 | 消息所在会话 ID |
| `note` | string | 否 | 收藏备注 |

#### Response — 201 Created

```json
{
  "bookmark_id": 7001,
  "msg_id": 9001,
  "conversation_id": 2001,
  "conversation_name": "项目讨论组",
  "message": {
    "sender_name": "charlie",
    "type": "text",
    "content": { "text": "明天下午3点会议室集合" },
    "created_at": "2026-03-13T14:00:00Z"
  },
  "note": "重要会议信息",
  "created_at": "2026-03-14T11:25:00Z"
}
```

### 获取收藏列表

`GET /api/bookmarks?page=1&page_size=20`

**需要认证**

#### Response — 200 OK

```json
{
  "total": 5,
  "page": 1,
  "page_size": 20,
  "results": [
    {
      "bookmark_id": 7001,
      "msg_id": 9001,
      "conversation_id": 2001,
      "conversation_name": "项目讨论组",
      "message": {
        "sender_name": "charlie",
        "type": "text",
        "content": { "text": "明天下午3点会议室集合" },
        "created_at": "2026-03-13T14:00:00Z"
      },
      "note": "重要会议信息",
      "created_at": "2026-03-14T11:25:00Z"
    }
  ]
}
```

### 删除收藏

`DELETE /api/bookmarks/{bookmark_id}`

**需要认证**

#### Response — 204 No Content

> **前端**：
> - 收藏入口在消息右键/悬浮菜单中。
> - 独立的"我的收藏"页面，列出所有收藏的消息，点击可跳转到对应会话和消息位置。

---

# 六、群聊管理模块 (Group)

---

## 6.1 获取群信息【注：和点进某个人的页面看他消息功能类似，看某个群的详情，而不是看群聊消息】

`GET /api/conversations/{conv_id}/group`

**需要认证**

### Response — 200 OK

```json
{
  "conversation_id": 2002,
  "name": "项目讨论组",
  "avatar": "https://cdn.example.com/groups/2002.jpg",
  "owner": {
    "user_id": 1001,
    "username": "alice"
  },
  "member_count": 15,
  "my_group_nickname": "Alice PM",
  "created_at": "2026-03-01T08:00:00Z",
  "latest_announcement": {
    "announcement_id": 301,
    "content": "明天下午3点开项目评审会",
    "publisher": { "user_id": 1001, "username": "alice" },
    "created_at": "2026-03-13T09:00:00Z"
  }
}
```

### 异常状态码

| 状态码 | error.code | 触发条件 |
|--------|------------|----------|
| 403 | `NOT_MEMBER` | 不是群成员 |
| 404 | `CONVERSATION_NOT_FOUND` | 会话不存在或不是群聊 |

---

## 6.2 修改群信息【注：不像微信任何人都能改群名】

`PUT /api/conversations/{conv_id}/group`

**需要认证**（仅群主和管理员）

### Request Body

```json
{
  "name": "项目讨论组（新）"
}
```

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `name` | string | 否 | 新群名称，1-50 字符 |

### Response — 200 OK

```json
{
  "conversation_id": 2002,
  "name": "项目讨论组（新）",
  "updated_at": "2026-03-14T11:30:00Z"
}
```

### 异常状态码

| 状态码 | error.code | 触发条件 |
|--------|------------|----------|
| 403 | `PERMISSION_DENIED` | 非群主或管理员 |

> **实现注意**：群名称修改后，后端生成系统消息"alice 修改了群名称为 xxx"并通过 WebSocket 推送。

---

## 6.3 上传群头像

`POST /api/conversations/{conv_id}/group/avatar`

**需要认证**（仅群主和管理员）

### Request

`Content-Type: multipart/form-data`

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `file` | File | 是 | 图片文件，支持 jpg/png/gif/webp，最大 5MB |

### Response — 200 OK

```json
{
  "avatar": "https://cdn.example.com/groups/2002_v2.jpg"
}
```

### 异常状态码

| 状态码 | error.code | 触发条件 |
|--------|------------|----------|
| 400 | `INVALID_FILE_TYPE` | 文件类型不支持 |
| 400 | `FILE_TOO_LARGE` | 文件超过 5MB |
| 403 | `PERMISSION_DENIED` | 非群主或管理员 |

> **前端**：群头像默认可以自动拼接前 9 个成员的头像（纯前端 Canvas 实现），群主/管理员可以在群设置页面上传自定义群头像覆盖默认效果。

---

## 6.4 获取群成员列表

`GET /api/conversations/{conv_id}/group/members?page=1&page_size=50`

**需要认证**

### Response — 200 OK

```json
{
  "total": 15,
  "page": 1,
  "page_size": 50,
  "results": [
    {
      "user_id": 1001,
      "username": "alice",
      "avatar": "https://cdn.example.com/avatars/1001.jpg",
      "role": "owner",
      "group_nickname": "Alice PM",
      "remark": null,
      "status": { "presence": "online", "status_text": "", "status_emoji": "" },
      "joined_at": "2026-03-01T08:00:00Z"
    },
    {
      "user_id": 1002,
      "username": "bob",
      "avatar": "https://cdn.example.com/avatars/1002.jpg",
      "role": "admin",
      "group_nickname": null,
      "remark": "Bob同学",
      "status": { "presence": "offline", "status_text": "", "status_emoji": "" },
      "joined_at": "2026-03-01T08:00:00Z"
    }
  ]
}
```

> **实现注意**：
> - `role` 可为 `"owner"` / `"admin"` / `"member"`。
> - `group_nickname` 为该成员在本群的昵称。
> - `remark` 为当前请求用户对该成员设置的好友备注（非好友则为 null）。
>
> **前端**：群成员列表中显示名称的优先级：好友备注 > 群昵称 > 用户名。群主显示皇冠图标，管理员显示盾牌图标。

---

## 6.5 设置群昵称

`PUT /api/conversations/{conv_id}/group/my-nickname`

**需要认证**

### Request Body

```json
{
  "nickname": "Alice PM"
}
```

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `nickname` | string | 是 | 群昵称，最大 30 字符，空字符串表示清除 |

### Response — 200 OK

```json
{
  "conversation_id": 2002,
  "user_id": 1001,
  "nickname": "Alice PM",
  "updated_at": "2026-03-14T11:35:00Z"
}
```

### 异常状态码

| 状态码 | error.code | 触发条件 |
|--------|------------|----------|
| 403 | `NOT_MEMBER` | 不是群成员 |

> **前端**：群昵称设置入口在群设置页面中"我在本群的昵称"。设置后该群聊中自己发送的消息会显示群昵称。

---

## 6.6 设置管理员

`POST /api/conversations/{conv_id}/group/admins`

**需要认证**（仅群主）

### Request Body

```json
{
  "user_id": 1003
}
```

### Response — 200 OK

```json
{
  "user_id": 1003,
  "username": "charlie",
  "role": "admin",
  "updated_at": "2026-03-14T11:40:00Z"
}
```

### 异常状态码

| 状态码 | error.code | 触发条件 |
|--------|------------|----------|
| 403 | `NOT_OWNER` | 非群主 |
| 404 | `MEMBER_NOT_FOUND` | 不是群成员 |
| 409 | `ALREADY_ADMIN` | 已是管理员 |

> **实现注意**：设置/取消管理员后生成系统消息并通过 WebSocket 通知全体群成员。

---

## 6.7 取消管理员

`DELETE /api/conversations/{conv_id}/group/admins/{user_id}`

**需要认证**（仅群主）

### Response — 204 No Content

### 异常状态码

| 状态码 | error.code | 触发条件 |
|--------|------------|----------|
| 403 | `NOT_OWNER` | 非群主 |
| 404 | `MEMBER_NOT_FOUND` | 不是群成员 |
| 409 | `NOT_ADMIN` | 不是管理员 |

---

## 6.8 转让群主

`PUT /api/conversations/{conv_id}/group/owner`

**需要认证**（仅群主）

### Request Body

```json
{
  "new_owner_id": 1002
}
```

### Response — 200 OK

```json
{
  "conversation_id": 2002,
  "old_owner_id": 1001,
  "new_owner_id": 1002,
  "updated_at": "2026-03-14T11:45:00Z"
}
```

### 异常状态码

| 状态码 | error.code | 触发条件 |
|--------|------------|----------|
| 403 | `NOT_OWNER` | 非群主 |
| 404 | `MEMBER_NOT_FOUND` | 目标不是群成员 |

> **实现注意**：转让后原群主变为普通成员。生成系统消息并推送。

---

## 6.9 移除群成员

`DELETE /api/conversations/{conv_id}/group/members/{user_id}`

**需要认证**（群主或管理员）

### Response — 204 No Content

### 异常状态码

| 状态码 | error.code | 触发条件 |
|--------|------------|----------|
| 403 | `PERMISSION_DENIED` | 无权移除（管理员不可移除群主或其他管理员） |
| 403 | `CANNOT_REMOVE_SELF` | 不可移除自己（请用退出接口） |
| 404 | `MEMBER_NOT_FOUND` | 不是群成员 |

> **实现注意**：权限规则——群主可移除自己以外的任何人；管理员仅可移除普通成员。移除后生成系统消息。被移除者的 WebSocket 收到 `group_member_change` 事件（`action: "removed"`）。

---

## 6.10 退出群聊

`POST /api/conversations/{conv_id}/group/leave`

**需要认证**

### Response — 204 No Content

### 异常状态码

| 状态码 | error.code | 触发条件 |
|--------|------------|----------|
| 403 | `OWNER_CANNOT_LEAVE` | 群主需先转让群主 |
| 403 | `NOT_MEMBER` | 不是群成员 |

> **实现注意**：退出后生成系统消息"xxx 退出了群聊"。

---

## 6.11 邀请好友入群

`POST /api/conversations/{conv_id}/group/invitations`

**需要认证**（群成员）

### Request Body

```json
{
  "user_ids": [1005, 1006]
}
```

### Response — 201 Created

```json
{
  "invitations": [
    {
      "invitation_id": 6001,
      "user_id": 1005,
      "username": "eve",
      "status": "pending",
      "created_at": "2026-03-14T12:00:00Z"
    }
  ]
}
```

### 异常状态码

| 状态码 | error.code | 触发条件 |
|--------|------------|----------|
| 403 | `NOT_MEMBER` | 不是群成员 |
| 403 | `NOT_FRIEND` | 被邀请者不是你的好友 |
| 409 | `ALREADY_MEMBER` | 已是群成员 |
| 409 | `INVITATION_EXISTS` | 已有待处理邀请 |

> **实现注意**：邀请需群主/管理员审核。通过 WebSocket 通知群主和管理员。

---

## 6.12 获取入群申请列表

`GET /api/conversations/{conv_id}/group/invitations?status=pending&page=1&page_size=20`

**需要认证**（群主或管理员）

### Response — 200 OK

```json
{
  "total": 2,
  "page": 1,
  "page_size": 20,
  "results": [
    {
      "invitation_id": 6001,
      "invitee": {
        "user_id": 1005,
        "username": "eve",
        "avatar": "https://cdn.example.com/avatars/1005.jpg"
      },
      "inviter": {
        "user_id": 1003,
        "username": "charlie"
      },
      "status": "pending",
      "created_at": "2026-03-14T12:00:00Z"
    }
  ]
}
```

---

## 6.13 审核入群申请

`PUT /api/conversations/{conv_id}/group/invitations/{invitation_id}`

**需要认证**（群主或管理员）

### Request Body

```json
{
  "action": "approve"
}
```

### Response — 200 OK

```json
{
  "invitation_id": 6001,
  "status": "approved",
  "updated_at": "2026-03-14T12:05:00Z"
}
```

### 异常状态码

| 状态码 | error.code | 触发条件 |
|--------|------------|----------|
| 403 | `PERMISSION_DENIED` | 非群主或管理员 |
| 404 | `INVITATION_NOT_FOUND` | 邀请不存在 |
| 409 | `INVITATION_ALREADY_HANDLED` | 已处理过 |

> **实现注意**：通过后自动加入群聊，生成系统消息"eve 通过 charlie 的邀请加入了群聊"，通过 WebSocket 通知全体群成员和被邀请者。

---

## 6.14 发布群公告

`POST /api/conversations/{conv_id}/group/announcements`

**需要认证**（群主或管理员）

### Request Body

```json
{
  "content": "本周五下午3点线下开会，请大家准时参加。"
}
```

### Response — 201 Created

```json
{
  "announcement_id": 302,
  "content": "本周五下午3点线下开会，请大家准时参加。",
  "publisher": { "user_id": 1001, "username": "alice" },
  "created_at": "2026-03-14T12:10:00Z"
}
```

### 异常状态码

| 状态码 | error.code | 触发条件 |
|--------|------------|----------|
| 400 | `EMPTY_CONTENT` | 公告为空 |
| 403 | `PERMISSION_DENIED` | 非群主或管理员 |

> **实现注意**：发布后通过 WebSocket 推送 `group_announcement` 给全体群成员。
>
> **前端**：新公告推送到来时，可以在群聊界面顶部弹出公告横幅。

---

## 6.15 获取历史群公告

`GET /api/conversations/{conv_id}/group/announcements?page=1&page_size=10`

**需要认证**

### Response — 200 OK

```json
{
  "total": 5,
  "page": 1,
  "page_size": 10,
  "results": [
    {
      "announcement_id": 302,
      "content": "本周五下午3点线下开会",
      "publisher": { "user_id": 1001, "username": "alice" },
      "created_at": "2026-03-14T12:10:00Z"
    }
  ]
}
```

### 6.16 解散群聊

`DELETE /api/conversations/{conv_id}/group`

**需要认证**（仅群主）

#### Request Body

```json
{
  "confirm": true
}
```

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `confirm` | bool | 是 | 必须传 `true`，防止误操作 |

#### Response — 204 No Content

#### 异常状态码

| 状态码 | error.code | 触发条件 |
|--------|------------|----------|
| 400 | `CONFIRM_REQUIRED` | 未传 `confirm: true` |
| 403 | `NOT_OWNER` | 非群主 |
| 404 | `CONVERSATION_NOT_FOUND` | 会话不存在或不是群聊 |

> **实现注意**：
> - 解散后，后端执行以下操作：
>   1. 向群内所有成员推送 WebSocket 事件 `group_dissolved`
>   2. 生成最后一条系统消息"群主 alice 解散了群聊"
>   3. 将所有成员从会话中移除
>   4. 将会话标记为已解散状态（软删除，不物理删除，保留历史记录可查）
> - 解散后，该会话的所有接口（发消息、查成员等）均返回 **404**。
> - 已解散群聊的历史聊天记录，原成员仍可通过 `GET /api/conversations/{conv_id}/messages` 查看（只读），但不能发送新消息。

对应的 WebSocket 推送事件：

```json
{
  "type": "group_dissolved",
  "data": {
    "conversation_id": 2002,
    "conversation_name": "项目讨论组",
    "dissolved_by": {
      "user_id": 1001,
      "username": "alice"
    },
    "timestamp": "2026-03-14T14:00:00Z"
  }
}
```

> **前端**：
> - 收到 `group_dissolved` 事件后，在聊天界面显示"群聊已被群主解散"的提示横幅，输入框置灰不可输入。
> - 会话列表中该会话显示"[已解散]"标记，用户可以手动删除该会话。

同时这也解决了之前 **1.5 注销账号** 中的一个遗留问题——群主注销前需要先处理自己的群：要么转让群主，要么解散群聊。

---



# 七、文件上传模块 (Upload)

---

## 7.1 上传文件

`POST /api/upload`

**需要认证**

### Request

`Content-Type: multipart/form-data`

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `file` | File | 是 | 上传的文件 |
| `purpose` | string | 是 | 用途：`message`（消息附件）/ `avatar`（头像） |

### Response — 201 Created

```json
{
  "file_id": "f_20260314_001",
  "url": "https://cdn.example.com/uploads/2026/03/14/f_001.jpg",
  "thumbnail_url": "https://cdn.example.com/uploads/2026/03/14/f_001_thumb.jpg",
  "filename": "photo.jpg",
  "size": 204800,
  "mime_type": "image/jpeg",
  "width": 1920,
  "height": 1080,
  "duration": null
}
```

> `thumbnail_url` 仅图片和视频有值；`width` / `height` 仅图片和视频有值；`duration` 仅音频和视频有值。

### 异常状态码

| 状态码 | error.code | 触发条件 |
|--------|------------|----------|
| 400 | `INVALID_FILE_TYPE` | 文件类型不支持 |
| 400 | `FILE_TOO_LARGE` | 超出大小限制 |

### 文件大小限制

| 文件类型 | 最大大小 |
|---------|---------|
| 图片（jpg/png/gif/webp） | 10MB |
| 视频（mp4/webm） | 100MB |
| 音频（webm/ogg/mp3） | 10MB |
| 其他文件 | 50MB |

> **实现注意**：
> - 上传成功后返回的 `url` 用于后续发送消息时引用。
> - 图片和视频文件后端应自动生成缩略图（`thumbnail_url`），可用 Pillow 或 FFmpeg。
> - 音频文件后端应提取时长（`duration`），可用 FFprobe。
> - Django 中建议使用 `MEDIA_ROOT` 存储文件，生产环境可对接 OSS/S3。
>
> **前端**：
> - 发送图片/视频/音频/文件消息时，先调用此接口上传，拿到 url 和元数据后再调用发送消息接口。
> - 上传过程中显示进度条。
> - 语音消息：使用浏览器 MediaRecorder API 录制音频，录制完成后自动上传并发送。

---

# 八、消息同步模块 (Sync)

---

## 8.1 拉取离线增量消息

`GET /api/sync/messages?since=2026-03-14T08:00:00Z&limit=200`

**需要认证**

<!-- 技术问题：这个离线拉取增量信息如何和WebSocket配合 -->

### Query Parameters

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `since` | string (ISO 8601) | 是 | 上次同步时间戳 |
| `limit` | int | 否 | 最大条数，默认 200，最大 1000 |

### Response — 200 OK

```json
{
  "messages": [
    {
      "conversation_id": 2001,
      "msg_id": 9080,
      "sender": { "user_id": 1002, "username": "bob" },
      "type": "text",
      "content": { "text": "Good morning!" },
      "reply_to_msg_id": null,
      "mentions": [],
      "is_recalled": false,
      "created_at": "2026-03-14T08:30:00Z"
    }
  ],
  "events": [
    {
      "type": "friend_request",
      "id": 501,
      "updated_at": "2026-03-14T08:31:00Z",
      "data": {
        "request_id": 501,
        "from_user": { "user_id": 1002, "username": "bob", "avatar": null },
        "to_user": { "user_id": 1001, "username": "alice", "avatar": null },
        "source": "search",
        "message": "我是 Bob",
        "status": "pending",
        "created_at": "2026-03-14T08:31:00Z",
        "updated_at": "2026-03-14T08:31:00Z"
      }
    }
  ],
  "has_more": false,
  "sync_timestamp": "2026-03-14T11:00:00Z"
}
```

> **实现注意**：
> - 如果 `has_more` 为 true，前端需以返回的 `sync_timestamp` 继续请求直到 `has_more` 为 false。
> - 同步内容应包含：新消息、消息撤回事件、好友申请、群变更等所有离线通知。
> - 前端登录流程：登录 → 建立 WebSocket → 调用此接口拉取离线消息 → 加载会话列表。

---

# 九、智能对话模块 (AI) 【拓展功能】

---

## 9.1 创建 AI 会话

`POST /api/ai/conversations`

**需要认证**

### Request Body

```json
{
  "name": "我的AI助手"
}
```

### Response — 201 Created

```json
{
  "conversation_id": 3001,
  "type": "ai",
  "name": "我的AI助手",
  "ai_model": "DeepSeek-R1-0528",
  "created_at": "2026-03-14T12:30:00Z"
}
```

> **实现注意**：
> - AI 会话是特殊类型的会话（`type: "ai"`），只有创建者和 AI 两个参与者。
> - 后端维护该会话的上下文（最近 N 条对话历史）用于传给 LLM API。
> - AI API Key 由用户在个人设置中配置，后端不使用统一服务端 Key 兜底。

---

## 9.2 向 AI 发送消息

`POST /api/ai/conversations/{conv_id}/messages`

**需要认证**

### Request Body

```json
{
  "content": "请帮我写一段 Python 快速排序代码"
}
```

### Response — 200 OK（流式返回，SSE 格式）

```
data: {"type": "start", "msg_id": 9500}

data: {"type": "delta", "content": "def "}

data: {"type": "delta", "content": "quick_sort"}

data: {"type": "delta", "content": "(arr):"}

...

data: {"type": "done", "msg_id": 9500, "full_content": "def quick_sort(arr):\n    ..."}
```

### 非流式 Response — 200 OK

> 如果前端不支持 SSE，可以加 `?stream=false` 参数，返回完整响应：

```json
{
  "user_message": {
    "msg_id": 9499,
    "type": "text",
    "content": { "text": "请帮我写一段 Python 快速排序代码" },
    "created_at": "2026-03-14T12:31:00Z"
  },
  "ai_message": {
    "msg_id": 9500,
    "type": "text",
    "content": { "text": "def quick_sort(arr):\n    if len(arr) <= 1:\n        return arr\n    ..." },
    "created_at": "2026-03-14T12:31:02Z"
  }
}
```

### 异常状态码

| 状态码 | error.code | 触发条件 |
|--------|------------|----------|
| 400 | `EMPTY_CONTENT` | 消息为空 |
| 403 | `AI_API_KEY_REQUIRED` | 用户未配置个人 AI API Key |
| 404 | `CONVERSATION_NOT_FOUND` | AI 会话不存在 |
| 429 | `AI_RATE_LIMITED` | AI 调用频率限制（建议每用户每分钟最多 10 次） |
| 502 | `AI_SERVICE_ERROR` | LLM API 调用失败 |

> **实现注意**：
> - 后端调用 OpenAI-compatible API（默认 `https://aiping.cn/api/v1/chat/completions`），请求头使用发起用户的个人 API Key。
> - 建议传入最近 10 条对话历史作为上下文，控制 token 用量。
> - 流式响应使用 Django 的 `StreamingHttpResponse` 或 Django Channels 实现。
>
> **前端**：
> - AI 会话入口可以放在会话列表顶部或侧边栏。
> - AI 回复使用打字机效果逐字显示（解析 SSE 的 delta 事件）。
> - AI 的消息气泡使用特殊样式（如不同颜色/图标）与普通消息区分。

---

## 9.3 群聊 @AI 【拓展功能】

> 在群聊中 @AI 助手触发 LLM 回复。无需独立接口，复用消息发送接口（5.1）。

**实现方式**：
- 系统中预创建一个特殊用户"AI 助手"（`user_id` 固定，如 0 或 -1）。
- 发送消息时，后端检查 `mentions` 中是否包含 AI 助手的 user_id。
- 如果包含，后端使用发送者的个人 API Key 调用 LLM API，生成回复后以 AI 助手身份发送消息到该群聊。
- 发送者未配置个人 API Key 时，消息发送接口返回 `AI_API_KEY_REQUIRED`。
- AI 的上下文取该群最近 10 条消息。

> **前端**：@成员选择器中包含"AI 助手"选项。AI 助手的头像和名称用特殊样式展示。

---

# 十、WebSocket 实时通信

---

## 10.1 连接建立

**URL**: `wss://<domain>/ws/chat/?token=<access_token>`

### 连接成功

```json
{
  "type": "connection_established",
  "user_id": 1001,
  "timestamp": "2026-03-14T13:00:00Z"
}
```

### 连接失败 — WebSocket close code

| Code | 含义 |
|------|------|
| 4001 | Token 无效 |
| 4002 | Token 过期 |

> **实现注意**：
> - 使用 Django Channels 实现 WebSocket，配合 Redis 作为 Channel Layer。
> - 每个用户连接后加入以自己 `user_id` 命名的 channel group，以及其所有会话的 channel group。
> - 连接建立后自动将用户 presence 设为 `online`（除非手动设了其他状态）。

---

## 10.2 客户端 → 服务端

### 心跳

```json
{ "type": "ping" }
```

服务端回复：

```json
{ "type": "pong" }
```

> 建议每 30 秒发送一次心跳。服务端 60 秒未收到心跳视为断线。

### 消息送达确认 (ACK)

```json
{
  "type": "msg_ack",
  "msg_id": 9100,
  "conversation_id": 2001
}
```

> 客户端收到新消息后应发送 ACK。服务端据此确认消息已送达。

### 输入状态指示 【拓展功能】

```json
{
  "type": "typing",
  "conversation_id": 2001
}
```

> **实现注意**：服务端收到后转发给该会话的其他在线成员（不持久化）。前端设置 3 秒节流，避免频繁发送。

---

## 10.3 服务端 → 客户端推送事件

### 新消息 `new_message`

```json
{
  "type": "new_message",
  "data": {
    "conversation_id": 2001,
    "msg_id": 9100,
    "sender": {
      "user_id": 1002,
      "username": "bob",
      "avatar": "https://cdn.example.com/avatars/1002.jpg",
      "group_nickname": null
    },
    "type": "text",
    "content": { "text": "Hey Alice!" },
    "reply_to": null,
    "mentions": [],
    "created_at": "2026-03-14T13:05:00Z"
  }
}
```

> **前端**：
> - 收到后更新对应会话的 `last_message` 和 `unread_count`。
> - 如果会话未设置免打扰，弹出桌面通知（使用 Notification API）。
> - 如果该消息 `mentions` 包含当前用户，即使免打扰也弹出提醒。

### 消息撤回 `message_recalled` 【拓展功能】

```json
{
  "type": "message_recalled",
  "data": {
    "conversation_id": 2001,
    "msg_id": 9100,
    "recalled_by": { "user_id": 1002, "username": "bob" },
    "recalled_at": "2026-03-14T13:06:00Z"
  }
}
```

### 已读回执 `read_receipt`

```json
{
  "type": "read_receipt",
  "data": {
    "conversation_id": 2001,
    "user_id": 1002,
    "last_read_msg_id": 9100,
    "read_at": "2026-03-14T13:07:00Z"
  }
}
```

> **前端**：
> - 私聊：更新消息气泡的"已读/未读"状态。
> - 群聊：更新消息的 `read_by_count`。

### Reaction 更新 `reaction_update` 【拓展功能】

```json
{
  "type": "reaction_update",
  "data": {
    "conversation_id": 2001,
    "msg_id": 9001,
    "emoji": "👍",
    "action": "add",
    "user": { "user_id": 1003, "username": "charlie" },
    "current_count": 3
  }
}
```

### 好友申请 `friend_request`

```json
{
  "type": "friend_request",
  "data": {
    "request_id": 5010,
    "from_user": {
      "user_id": 1005,
      "username": "eve",
      "avatar": "https://cdn.example.com/avatars/1005.jpg"
    },
    "message": "Hi!",
    "source": "contact_card:9050",
    "created_at": "2026-03-14T13:10:00Z"
  }
}
```

### 好友申请结果 `friend_request_result`

```json
{
  "type": "friend_request_result",
  "data": {
    "request_id": 5002,
    "status": "accepted",
    "friend": {
      "user_id": 1003,
      "username": "charlie",
      "avatar": null
    },
    "updated_at": "2026-03-14T13:12:00Z"
  }
}
```

### 群邀请通知 `group_invitation`

```json
{
  "type": "group_invitation",
  "data": {
    "invitation_id": 6001,
    "conversation_id": 2002,
    "conversation_name": "项目讨论组",
    "invitee": { "user_id": 1005, "username": "eve" },
    "inviter": { "user_id": 1003, "username": "charlie" },
    "created_at": "2026-03-14T13:15:00Z"
  }
}
```

### 群邀请审核结果 `group_invitation_result`

```json
{
  "type": "group_invitation_result",
  "data": {
    "invitation_id": 6001,
    "conversation_id": 2002,
    "conversation_name": "项目讨论组",
    "status": "approved",
    "updated_at": "2026-03-14T13:17:00Z"
  }
}
```

### 群成员变更 `group_member_change`

```json
{
  "type": "group_member_change",
  "data": {
    "conversation_id": 2002,
    "action": "joined",
    "user": { "user_id": 1005, "username": "eve" },
    "timestamp": "2026-03-14T13:17:00Z"
  }
}
```

> `action` 可为 `"joined"` / `"left"` / `"removed"` / `"role_changed"`。

### 群公告 `group_announcement`

```json
{
  "type": "group_announcement",
  "data": {
    "conversation_id": 2002,
    "announcement_id": 302,
    "content": "本周五下午3点线下开会",
    "publisher": { "user_id": 1001, "username": "alice" },
    "created_at": "2026-03-14T12:10:00Z"
  }
}
```

### 在线状态变更 `presence_change`

```json
{
  "type": "presence_change",
  "data": {
    "user_id": 1002,
    "presence": "offline",
    "status_text": "",
    "status_emoji": "",
    "last_seen": "2026-03-14T13:20:00Z"
  }
}
```

> 仅推送给与该用户存在好友关系的在线用户。

### 输入状态 `typing_indicator` 【拓展功能】

```json
{
  "type": "typing_indicator",
  "data": {
    "conversation_id": 2001,
    "user_id": 1002,
    "username": "bob"
  }
}
```

> **前端**：收到后在聊天界面底部显示"bob 正在输入…"，3 秒后自动消失。如果是群聊且多人同时输入，显示"bob, charlie 正在输入…"。

---

# 附录 A：接口汇总表

| 序号 | 方法 | 路径 | 说明 | 拓展 |
|------|------|------|------|------|
| 1.1 | POST | `/api/auth/register` | 用户注册 | |
| 1.2 | POST | `/api/auth/login` | 用户登录 | |
| 1.3 | POST | `/api/auth/refresh` | 刷新 Token | |
| 1.4 | POST | `/api/auth/logout` | 用户登出 | |
| 1.5 | DELETE | `/api/auth/account` | 注销账号 | |
| 2.1 | GET | `/api/users/me` | 获取当前用户信息 | |
| 2.2 | PUT | `/api/users/me` | 修改个人信息（统一） | |
| 2.3 | POST | `/api/users/me/avatar` | 上传头像 | |
| 2.4 | GET | `/api/users/search` | 搜索用户 | |
| 2.5 | GET | `/api/users/{user_id}` | 获取用户公开信息 | |
| 2.6 | PUT | `/api/users/me/privacy` | 修改隐私设置 | |
| 2.7 | GET | `/api/users/me/privacy` | 获取隐私设置 | |
| 2.8 | PUT | `/api/users/me/status` | 设置自定义状态 | |
| 2.9 | GET/PUT/DELETE | `/api/users/me/ai-key` | 个人 AI API Key 设置 | ✅ |
| 3.1 | POST | `/api/friends/request` | 发送好友申请 | |
| 3.2 | GET | `/api/friends/requests` | 获取好友申请列表 | |
| 3.3 | PUT | `/api/friends/requests/{id}` | 处理好友申请 | |
| 3.4 | GET | `/api/friends` | 获取好友列表 | |
| 3.5 | DELETE | `/api/friends/{user_id}` | 删除好友 | |
| 3.6 | GET | `/api/friends/groups` | 获取好友分组列表 | |
| 3.7 | POST | `/api/friends/groups` | 创建好友分组 | |
| 3.8 | PUT | `/api/friends/groups/{id}` | 修改好友分组 | |
| 3.9 | DELETE | `/api/friends/groups/{id}` | 删除好友分组 | |
| 3.10 | PUT | `/api/friends/{user_id}/remark` | 设置好友备注 | |
| 3.11 | POST | `/api/friends/blacklist` | 拉入黑名单 | |
| 3.12 | DELETE | `/api/friends/blacklist/{user_id}` | 解除黑名单 | |
| 3.13 | GET | `/api/friends/blacklist` | 获取黑名单列表 | |
| 3.14 | POST | `/api/friends/whitelist` | 添加白名单 | |
| 3.15 | DELETE | `/api/friends/whitelist/{user_id}` | 移除白名单 | |
| 3.16 | GET | `/api/friends/whitelist` | 获取白名单列表 | |
| 4.1 | GET | `/api/conversations` | 获取会话列表 | |
| 4.2 | POST | `/api/conversations` | 创建会话 | |
| 4.3 | GET | `/api/conversations/{id}` | 获取会话详情 | |
| 4.4 | PUT | `/api/conversations/{id}` | 更新会话设置 | |
| 4.5 | DELETE | `/api/conversations/{id}` | 删除会话 | |
| 4.6 | PUT | `/api/conversations/{id}/read` | 标记已读 | |
| 4.7 | GET | `/api/conversations/search` | 全局搜索聊天记录 | ✅ |
| 5.1 | POST | `/api/conversations/{id}/messages` | 发送消息 | |
| 5.2 | GET | `/api/conversations/{id}/messages` | 获取聊天记录 | |
| 5.3 | GET | `.../messages/{id}/replies` | 获取回复列表 | |
| 5.4 | GET | `.../messages/{id}/read-status` | 获取已读详情 | |
| 5.5 | DELETE | `.../messages/{id}` | 删除消息 | |
| 5.6 | POST | `.../messages/{id}/recall` | 撤回消息 | ✅ |
| 5.7 | POST | `/api/messages/forward` | 转发消息 | ✅ |
| 5.8a | POST | `.../messages/{id}/reactions` | 添加 Reaction | ✅ |
| 5.8b | DELETE | `.../messages/{id}/reactions/{emoji}` | 取消 Reaction | ✅ |
| 5.9a | POST | `/api/bookmarks` | 添加收藏 | ✅ |
| 5.9b | GET | `/api/bookmarks` | 获取收藏列表 | ✅ |
| 5.9c | DELETE | `/api/bookmarks/{id}` | 删除收藏 | ✅ |
| 6.1 | GET | `.../group` | 获取群信息 | |
| 6.2 | PUT | `.../group` | 修改群信息 | |
| 6.3 | POST | `.../group/avatar` | 上传群头像 | |
| 6.4 | GET | `.../group/members` | 获取群成员列表 | |
| 6.5 | PUT | `.../group/my-nickname` | 设置群昵称 | |
| 6.6 | POST | `.../group/admins` | 设置管理员 | |
| 6.7 | DELETE | `.../group/admins/{user_id}` | 取消管理员 | |
| 6.8 | PUT | `.../group/owner` | 转让群主 | |
| 6.9 | DELETE | `.../group/members/{user_id}` | 移除群成员 | |
| 6.10 | POST | `.../group/leave` | 退出群聊 | |
| 6.11 | POST | `.../group/invitations` | 邀请好友入群 | |
| 6.12 | GET | `.../group/invitations` | 获取入群申请列表 | |
| 6.13 | PUT | `.../group/invitations/{id}` | 审核入群申请 | |
| 6.14 | POST | `.../group/announcements` | 发布群公告 | |
| 6.15 | GET | `.../group/announcements` | 获取历史群公告 | |
| 6.16 | DELETE | `/api/conversations/{conv_id}/group` | | |
| 7.1 | POST | `/api/upload` | 上传文件 | |
| 8.1 | GET | `/api/sync/messages` | 拉取离线增量消息 | |
| 9.1 | POST | `/api/ai/conversations` | 创建 AI 会话 | ✅ |
| 9.2 | POST | `/api/ai/conversations/{id}/messages` | 向 AI 发消息 | ✅ |
| — | WSS | `/ws/chat/` | WebSocket 实时通信 | |

---

# 附录 B：前端实现要点汇总

以下功能不涉及独立后端接口，由前端独立实现：

### 1. 会话草稿

- 用户在某个会话输入框中输入了内容但未发送就切走时，前端将草稿内容保存到 `localStorage`（key 为 `draft:{conversation_id}`）。
- 用户切回该会话时恢复草稿到输入框。
- 发送消息后清除草稿。
- 会话列表中有草稿的会话显示"[草稿] xxx"前缀（红色），优先级高于 last_message。

### 2. 消息气泡渲染

- 根据 `type` 选择不同组件：TextBubble、ImageBubble（点击放大）、VideoBubble（内嵌播放器）、AudioBubble（播放条+时长）、FileBubble（图标+文件名+大小+下载按钮）、CodeBubble（语法高亮，建议用 highlight.js 或 Prism.js）、ContactCardBubble（头像+用户名，点击跳转到资料页）、ForwardBubble（卡片式，点击展开）。
- 本人发送的消息居右、特殊背景色；他人消息居左。
- 已撤回消息显示灰色文字"xxx 撤回了一条消息"。

### 3. 右键/悬浮拓展菜单

- 鼠标悬浮或右键单击消息气泡弹出菜单，包含：回复、转发、收藏、@提及人（仅群聊）、撤回（仅自己 2 分钟内的消息）、删除。
- 菜单中还可以包含常用 Emoji 快速 Reaction 栏。

### 4. @提及交互

- 群聊输入框中输入 `@` 后弹出成员搜索下拉框。
- 选择成员后在输入框中插入 `@username` 文本（不可编辑的标签样式）。
- 发送时将被提及的用户 ID 列表放入 `mentions` 字段。

### 5. 语音消息录制

- 使用浏览器 `MediaRecorder` API 录制音频。
- 按住录音按钮开始录制，松开结束。
- 录制完成后自动上传（7.1）并发送语音消息。
- 显示录音时长计时器。

### 6. 输入状态指示

- 用户在输入框中键入时，通过 WebSocket 发送 `typing` 事件，设置 3 秒节流。
- 收到 `typing_indicator` 事件后，在聊天区域底部显示"xxx 正在输入…"。
- 3 秒无新 typing 事件自动消失。

### 7. 桌面通知

- 使用浏览器 Notification API 弹出桌面通知。
- 仅在会话未设置免打扰时弹出（`is_muted: false`）。
- 被 @提及时无视免打扰强制弹出。
- 点击通知跳转到对应会话。

### 8. 群头像自动拼接

- 默认群头像：用 Canvas 拼接前 9 个成员的头像，生成九宫格图片。
- 群主上传了自定义群头像后，使用自定义头像替代。

### 9. 消息气泡的显示名称优先级

- 群聊中每条消息的发送者显示名称优先级：当前用户设置的好友备注 > 发送者在该群的群昵称 > 发送者用户名。
- 私聊中对方显示名称优先级：好友备注 > 用户名。

---

# 附录 C：权限优先级总结

好友申请的权限判断顺序（优先级从高到低）：

```
1. 黑名单检查 → 如果对方在你的黑名单中，拒绝
2. 已是好友检查 → 如果已是好友，拒绝（409）
3. 来源为名片 (contact_card) → 跳过隐私检查，允许
4. 来源为白名单 → 跳过隐私检查，允许
5. 来源为群聊 (group) → 检查 allow_add_from_group
6. 来源为搜索 (search) → 搜索阶段已根据隐私设置过滤，此处放行
7. 默认允许
```

群聊操作的角色权限矩阵：

| 操作 | 群主 | 管理员 | 普通成员 |
|------|------|--------|---------|
| 修改群名称 / 群头像 | ✅ | ✅ | ❌ |
| 发布群公告 | ✅ | ✅ | ❌ |
| 设置 / 取消管理员 | ✅ | ❌ | ❌ |
| 转让群主 | ✅ | ❌ | ❌ |
| 移除群主 | — | ❌ | ❌ |
| 移除管理员 | ✅ | ❌ | ❌ |
| 移除普通成员 | ✅ | ✅ | ❌ |
| 邀请好友入群 | ✅ | ✅ | ✅ |
| 审核入群申请 | ✅ | ✅ | ❌ |
| 撤回他人消息 | ✅ | ✅ | ❌ |
| 查看已读名单 | ✅ | ✅ | ❌（仅看人数） |
| 退出群聊 | ❌（需先转让） | ✅ | ✅ |

---

# 附录 D：消息类型的会话列表摘要映射

前端在会话列表中展示 `last_message` 摘要时的映射规则：

| 消息 type | 摘要显示 |
|-----------|---------|
| `text` | 截取前 50 字符 |
| `image` | [图片] |
| `video` | [视频] |
| `audio` | [语音] |
| `file` | [文件] {filename} |
| `code` | [代码] |
| `contact_card` | [名片] {username} |
| `forward` | [聊天记录] |
| `system` | {text} |
| 已撤回 | xxx 撤回了一条消息 |
