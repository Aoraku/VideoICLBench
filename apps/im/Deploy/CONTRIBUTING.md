# 贡献指南 (Contributing Guide)

本文档规定了团队在开发即时通讯系统过程中须遵守的协作规范。

## 1. Commit 规范

本项目采用 [Conventional Commits](https://www.conventionalcommits.org/) 规范。

### 格式

```
<type>(<scope>): <subject>
```

- 全部使用**英文**书写
- `subject` 使用祈使句，首字母小写，结尾不加句号
- `subject` 不超过 50 个字符

### Type 类型

| Type       | 说明                                     |
| ---------- | ---------------------------------------- |
| `feat`     | 新功能                                   |
| `fix`      | 修复 Bug                                 |
| `docs`     | 仅修改文档                               |
| `style`    | 代码格式调整（空格、分号等，不影响逻辑） |
| `refactor` | 重构（既非新功能，也非修复 Bug）         |
| `test`     | 添加或修改测试                           |
| `chore`    | 构建工具、依赖管理、CI 配置等           |
| `perf`     | 性能优化                                 |
| `ci`       | 修改 CI/CD 配置文件                      |

### Scope 范围

| Scope      | 说明                               |
| ---------- | ---------------------------------- |
| `frontend` | 前端相关改动                       |
| `backend`  | 后端通用改动                       |
| `auth`     | 用户认证、注册、登录相关           |
| `chat`     | 会话、消息收发、群聊相关           |
| `ws`       | WebSocket 连接管理相关             |
| `db`       | 数据库模型、迁移、Schema 相关      |
| `docs`     | 项目文档                           |

Scope 可省略，但建议尽量填写以便追踪改动范围。

### 示例

```
feat(auth): add user registration endpoint
fix(ws): fix websocket reconnection on token expiry
feat(chat): implement group chat message broadcasting
fix(frontend): fix unread count badge not updating
docs: update API documentation for friend endpoints
refactor(backend): extract message service layer
chore: add docker-compose configuration
ci: add unit test step to gitlab CI pipeline
test(auth): add login validation test cases
perf(db): add index on message table for conversation queries
```

### 禁止的写法

```
update                          # 无 type，描述模糊
fix: fix bug                    # 描述无意义
feat(chat): 添加群聊功能        # 不要用中文
FEAT(auth): Add Login           # type 不要大写，subject 首字母小写
feat(auth): add login.           # 结尾不加句号
```

### CI/CD检查

每次有人 push 代码，流水线自动检查 commit message 格式，不合格就报错。

## 2. 分支策略

### 主要分支

- `main` — 稳定分支，始终保持可部署状态，**禁止直接 push**
- `dev` — 开发分支，所有 feature 分支合入此处，定期合并到 `main`

### Feature 分支

从 `dev` 拉取，命名格式：

```
<type>/<scope>-<short-description>
```

示例：

```
feat/auth-user-registration
feat/chat-group-creation
fix/ws-heartbeat-timeout
refactor/db-message-schema
docs/api-documentation
```

### 工作流程

```
1. 从 dev 拉取最新代码
   git checkout dev
   git pull origin dev

2. 创建 feature 分支
   git checkout -b feat/auth-user-registration

3. 开发并提交（遵守 commit 规范）
   git add .
   git commit -m "feat(auth): add user registration endpoint"

   

4. 推送并创建 Merge Request
   git push origin feat/auth-user-registration
   → 在 GitLab 上创建 MR，目标分支选 dev


5. Code Review 通过后合并
   → 由全栈或相关模块负责人 Review 后合并
   → 合并后删除 feature 分支
```

## 3. Merge Request 规范

### MR 标题

与 commit 格式一致：

```
feat(auth): add user registration endpoint
```

### MR 描述模板

```markdown
## 改动说明
简要描述本次 MR 做了什么。

## 改动类型
- [ ] 新功能 (feat)
- [ ] Bug 修复 (fix)
- [ ] 重构 (refactor)
- [ ] 其他

## 测试情况
描述你如何测试了这些改动。

## 关联 Issue
closes #issue_number（如有）
```

### Review 规则

- 每个 MR 至少需要 **1 人 Review** 后才能合并
- 涉及**前后端交互**的改动**必须**且**至少**交给**全栈**Review
- 前端 MR 由全栈简单review
- 后端 MR 可以双方**互相**review，觉得不保险也可以额外加上全栈review

## 4. 项目架构

本项目采用前后端分仓库管理，共三个仓库：
 
### Frontend 仓库（前端）
 
```
Frontend/
├── src/
│   ├── components/          # 可复用组件
│   ├── pages/               # 页面组件
│   ├── services/            # API 调用与 WebSocket 管理
│   ├── store/               # 状态管理
│   ├── utils/               # 工具函数
│   └── App.tsx
├── package.json
├── Dockerfile
└── README.md
```
 
### Backend 仓库（后端）
 
```
Backend/
├── config/                  # Django 项目配置 (settings, urls, asgi)
├── apps/
│   ├── auth/                # 用户认证模块
│   ├── friend/              # 好友关系模块
│   ├── chat/                # 会话与消息模块
│   └── ws/                  # WebSocket consumers
├── requirements.txt
├── manage.py
├── Dockerfile
└── README.md
```
 
### Deploy 仓库（部署与文档）
 
```
Deploy/
├── nginx/
│   └── nginx.conf           # Nginx 反向代理与 HTTPS 配置
├── docker-compose.yml       # 一键启动所有服务
├── CONTRIBUTING.md          # 本文件（三仓库通用规范）
├── README.md                # 项目总体说明
└── docs/
    ├── api.md               # API 接口文档
    └── database.md          # 数据库设计文档
```
 
> 三个仓库均遵守本文件中的 Commit 规范、分支策略和 MR 规范。

## 5. 开发环境
 
### 启动项目
 
在 Deploy 仓库目录下执行：
 
```bash
docker-compose up --build
```
 
需确保 Frontend 和 Backend 仓库已克隆到 Deploy 同级目录下：
 
```
projects/
├── Frontend/
├── Backend/
└── Deploy/          ← 在这里执行 docker-compose up
```
 
### 各服务端口
 
| 服务     | 端口 |
| -------- | ---- |
| Nginx    | 443  |
| Frontend | 3000 |
| Backend  | 8000 |
| MySQL    | 3306 |
| Redis    | 6379 |
