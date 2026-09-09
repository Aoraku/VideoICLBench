# ChatGLMJ

2026 Spring,
Project of Software Engineering Course, Tsinghua University
Group: Gao Yajing, Jing Meitian, Liu Qingle, Ma Zirun (arranged by first letter)

## 后端部署（Docker Compose）

1. 复制环境变量模板：`cp .env.deploy.example .env.deploy`
2. 编辑 `.env.deploy`：至少配置 `DJANGO_SECRET_KEY`、`DJANGO_DEBUG=0`、`DJANGO_ALLOWED_HOSTS`（含你的域名或服务器 IP）
3. 启动（根目录 `Dockerfile`，含迁移入口脚本）：

```bash
docker compose up -d --build
```

4. 查看日志：`docker compose logs -f backend`

5. 本地开发（映射代码目录、无 nginx）：`docker compose -f docker-compose.dev.yml up --build`

### AI 配置

后端 AI 调用使用 OpenAI-compatible `POST {AI_BASE_URL}/chat/completions` 格式。AI API Key 由每个用户在个人设置中维护，后端不会读取统一的服务端 API Key。远程 Docker 部署时，在 `.env.deploy` 中配置模型服务地址和模型名：

```env
AI_BASE_URL=https://aiping.cn/api/v1
AI_MODEL=DeepSeek-R1-0528
AI_TIMEOUT_SECONDS=30
AI_RATE_LIMIT_PER_MINUTE=10
```

用户未配置个人 API Key 时，AI 会话和群聊 `@AI` 会返回 `AI_API_KEY_REQUIRED`。修改 `.env.deploy` 后执行 `docker compose up -d --build` 或 `docker compose restart backend` 让容器读取新的环境变量。

### 文件说明

| 文件 | 说明 |
|------|------|
| `Dockerfile` | 生产镜像（根目录构建） |
| `deploy/docker-entrypoint.sh` | 启动前执行 `migrate` |
| `deploy/nginx/backend.conf` | 反代 + `/ws/` WebSocket |
| `docker-compose.yml` | 生产：backend + nginx:80 |
| `docker-compose.dev.yml` | 本地开发 |

### GitLab CI / Secoder 自动部署

`dev` 分支：`test` → `sonar` → `build`（`deployer build`）→ `deploy`（`deployer dyno replace`）。

课程说明：[部署密钥和 registry 密钥](https://lab.cs.tsinghua.edu.cn/software-engineering/handout/ci-cd/) —— **两种密钥不要混用**：

| CI 变量 | 内容 | 怎么拿到 |
|---------|------|----------|
| **`REGISTRY_PWD`** | **GitLab Personal Access Token**，权限 **`read_registry`** | GitLab → **Settings → Access Tokens** 创建，再填到 **CI/CD → Variables** |
| **`DEPLOY_TOKEN`** | Secoder **部署密钥** | 大作业一般由 **Secoder 在流水线里预注入**；小作业需自己在 Variables 里加 |

`dyno replace` 命令里用的是 **`gitlab-ci-token` + `REGISTRY_PWD`** 去拉镜像；**不是**把部署密钥填进 `REGISTRY_PWD`。若把部署密钥误填进 `REGISTRY_PWD`，容易出现 **401 Attach token**。

流水线里 **不要** 再写 `export DEPLOY_ENV=$GITLAB_USER_LOGIN`（会覆盖团队环境，课程文档要求大作业去掉）。

**Secoder 上容器镜像仍是 `nginx`：** 新建 dyno 默认镜像是 nginx；**build + deploy 成功** 后应被替换成 Registry 里的后端镜像。也可在部署管理里手动改镜像地址。
