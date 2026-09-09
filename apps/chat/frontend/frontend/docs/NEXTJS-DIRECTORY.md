# Next.js 前端目录结构说明（CSR）

> 以 **Next.js（CSR）** 为框架，与即时通讯 API 文档模块对应，便于按模块接入接口与扩展。  
> **包管理器**：项目使用 **npm**，以下命令均以 npm 为例；目录结构与 pnpm/yarn 完全一致，仅安装与运行命令不同。

---

## 一、目录树

```
frontend/
├── public/                    # 静态资源，直接通过 / 访问
├── src/
│   ├── api/                   # 后端接口封装（按 API 文档模块划分）
│   │   ├── client.js          # 统一请求：JWT、baseURL、错误处理
│   │   ├── auth.js            # 一、用户认证
│   │   ├── conversations.js   # 四、会话
│   │   └── messages.js        # 五、消息（好友、群、上传等可继续加）
│   │
│   ├── components/            # 按功能域划分，避免单目录过长
│   │   ├── layout/            # 整体布局：三栏（侧边栏 / 列表 / 聊天区）
│   │   │   └── AppLayout.jsx
│   │   ├── common/            # 通用 UI：Button、Modal、Input 等（按需添加）
│   │   ├── conversations/     # 会话列表、会话项、搜索栏（对应 API 4.x）
│   │   ├── messages/          # 消息气泡、输入区、引用、状态图标（对应 API 5.x）
│   │   ├── friends/           # 好友列表、申请、分组（对应 API 三）
│   │   ├── groups/            # 群信息、成员、公告（对应 API 六）
│   │   └── ai/                # AI 会话与气泡（对应 API 九，拓展）
│   │
│   ├── contexts/              # 全局状态：认证、主题、WebSocket
│   │   └── AuthContext.jsx
│   │
│   ├── hooks/                 # 可复用的数据/行为逻辑
│   │   └── useConversations.js
│   │
│   ├── lib/                   # 常量、工具、与框架无关的底层逻辑
│   │   └── constants.js       # API_BASE_URL、WS_BASE_URL 等
│   │
│   ├── mock/                  # 未接后端时的假数据
│   │   ├── conversations.js
│   │   └── messages.js
│   │
│   ├── pages/                 # Next.js 路由：文件即路由
│   │   ├── _app.jsx           # 全局包裹（样式、Context）
│   │   ├── index.jsx          # / → 根据登录态跳转
│   │   ├── login.jsx          # /login
│   │   ├── register.jsx       # /register（按需）
│   │   ├── conversations/
│   │   │   ├── index.jsx      # /conversations 会话列表
│   │   │   └── [id].jsx       # /conversations/2001 单会话聊天
│   │   ├── friends/           # 好友、申请、分组（按需）
│   │   ├── settings.jsx      # 设置、隐私、状态（按需）
│   │   └── ai/
│   │       └── [id].jsx       # AI 会话（拓展）
│   │
│   └── styles/                # 全局样式，与设计稿一致
│       ├── theme.css          # 设计令牌
│       └── globals.css        # 基础标签、#__next
│
├── docs/
│   └── NEXTJS-DIRECTORY.md    # 本文件
├── jsconfig.json              # @/ 路径别名
├── next.config.mjs            # Next 配置（CSR 不依赖 SSR）
├── package.json
├── Dockerfile                 # 可沿用，命令改为 next start
└── .gitignore
```

---

## 二、设计原因说明

### 1. 使用 Next.js 且强调 CSR 的原因

- 课程/幻灯片推荐：**Next.js 基于 React，路由清晰，便于与后端分离部署。**
- **CSR**：不在服务端做 getServerSideProps 取数，所有接口请求在浏览器里发（`api/client` + hooks）。这样：
  - 前端只依赖自己的 Node 构建与静态/Node 服务，不依赖 Django 的 SSR；
  - 与现有 **Django + DRF + Channels** 后端天然分离：前端 `npm run build` 后可单独部署或挂到 Nginx/Docker。
- 若以后需要 SEO 或首屏加速，再对少数页面开 SSR 或 SSG 即可，目录不必大改。

### 2. 为什么用 `src/` 包一层

- 根目录只放配置（`next.config.mjs`、`jsconfig.json`、`package.json`），源码全部在 `src/` 下，结构清晰。
- 与很多现有 Vite/React 项目习惯一致，迁移时心理负担小。

### 3. 为什么 `api/` 按模块拆（auth、conversations、messages…）

- API 文档按「认证、用户、好友、会话、消息、群、上传、同步、AI」分章，**前端接口层与文档一一对应**，便于：
  - 按文档查错、对字段；
  - 多人分工（一人负责会话+消息，一人负责好友+群等）。
- `client.js` 统一处理 **JWT（Authorization: Bearer）**、baseURL、401/403 跳登录等，各模块只关心入参和返回结构。

### 4. 为什么 `components/` 按功能域再分子目录

- 即时通讯界面组件多（会话项、多种消息气泡、输入区、群成员、AI 气泡等），若全放在一个 `components/` 下会很难找。
- 按 **conversations / messages / friends / groups / ai** 分，和 API 模块、产品功能对应：
  - 改「会话列表」主要看 `conversations/`；
  - 改「消息展示与发送」主要看 `messages/`；
  - 附录 B 的「消息气泡按 type 渲染」「右键菜单」「@提及」等都可归到 `messages/` 或 `common/`。

### 5. 为什么有 `contexts/` 和 `hooks/`

- **AuthContext**：登录态、logout、token 失效后的跳转，多处需要，集中在一处避免到处传 props。
- **WebSocketContext**（后续可加）：连接、重连、事件分发与 API 文档「十、WebSocket」一致，只写一次，各页面/组件订阅即可。
- **hooks**（如 `useConversations`）：把「调哪个接口、怎么分页、和 WebSocket 未读更新怎么合」封装起来，页面只关心「列表、loading、error、refetch」，便于复用和测试。

### 6. 为什么 `pages/` 这样拆

- **`_app.jsx`**：全局样式（theme + globals）和 Context 只在这里注入一次，符合 Next 约定。
- **`index.jsx`**：根路径根据「是否有 token」在客户端跳 `/login` 或 `/conversations`，纯 CSR 逻辑。
- **`/conversations` 与 `/conversations/[id]`**：对应「会话列表」和「某个会话的聊天窗口」，和 API 4.1（列表）、5.2（聊天记录）、WebSocket（新消息）一一对应；`[id]` 即 `conversation_id`。
- 好友、设置、AI 等按需再加 `pages/friends/`、`pages/settings.jsx`、`pages/ai/[id].jsx`，不破坏现有结构。

### 7. 为什么保留 `mock/`

- 后端未就绪或联调不稳定时，用 mock 数据保证前端可开发、可演示；接真实接口后逐步替换为 `api/` 调用，mock 可保留给单测或 Storybook。

### 8. 为什么 `lib/constants.js` 单独放

- `API_BASE_URL`、`WS_BASE_URL` 可能随环境（开发/生产、是否同域）变化，集中在一处便于改成 `process.env.NEXT_PUBLIC_*`，且 `api/client`、WebSocket 初始化都只依赖这里，不散落各文件。

---

## 三、与 API 文档的对应关系（简要）

| API 文档章节     | 前端位置 |
|------------------|----------|
| 一、认证         | `api/auth.js`、`contexts/AuthContext.jsx`、`pages/login.jsx` |
| 二、用户信息     | `api/users.js`（可新建）、设置/个人页 |
| 三、好友         | `api/friends.js`（可新建）、`components/friends/`、`pages/friends/` |
| 四、会话         | `api/conversations.js`、`hooks/useConversations.js`、`components/conversations/`、`pages/conversations/` |
| 五、消息         | `api/messages.js`、`components/messages/`、WebSocket 新消息 |
| 六、群聊管理     | `api/` 下群相关、`components/groups/` |
| 七、上传         | `api/upload.js`（可新建），发图/发文件前调用 |
| 八、同步         | 登录后调 `GET /api/sync/messages`，可在 `hooks` 或 Context 里 |
| 九、AI           | `api/ai.js`（可新建）、`components/ai/`、`pages/ai/` |
| 十、WebSocket    | `lib/wsClient.js` 或 `contexts/WebSocketContext.jsx` |

---

## 四、运行与构建（使用 npm）

```bash
npm install
npm run dev    # 开发：默认 Vite 端口见终端输出
npm run build
npm run preview   # 预览生产构建
```

- 开发时若后端在不同端口，可在环境变量中配置 `VITE_API_BASE_URL` 等，保证请求发到正确后端。
- 若使用 pnpm / yarn，将上述 `npm run` 换成对应工具的等价命令即可，目录与脚本不变。

按上述结构扩展即可在保持「Next.js + CSR」的前提下，与现有 API 文档和课程推荐的 Next 用法一致，且便于团队分工和后续加 SSR/SSG。
