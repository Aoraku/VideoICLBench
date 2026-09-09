# ChatGLMJ 项目开发环境与协作规范说明书

本文档旨在统一 ChatGLMJ 项目组的前后端开发环境配置与版本控制协作规范。本项目采用 React + Django + SQLite 技术栈，并全量使用 Docker 进行容器化开发与部署，结合 GitLab CI/CD 进行代码质量控制。请每位成员在正式开发前，严格按照以下步骤完成环境初始化。

## 一、 Git 与 SSH 认证配置

为避免每次代码交互时输入凭证，团队成员需配置 SSH 密钥认证。

1. **生成本地 SSH 密钥对**
在终端（Windows 用户请使用 Git Bash）执行以下命令，连续回车接受默认设置：
```bash
ssh-keygen -t ed25519 -C "你的邮箱地址"

```


2. **读取并复制公钥**
```bash
cat ~/.ssh/id_ed25519.pub

```


复制终端输出的完整内容（以 `ssh-ed25519` 开头）。
3. **配置 SECoder GitLab**
登录 `https://gitlab.spring26b.secoder.net`，进入右上角头像 -> **Preferences** -> 左侧导航栏 **SSH Keys**。点击 **Add new key**，将公钥粘贴至 Key 文本框并添加。
4. **克隆项目到本地**
```bash
git clone git@gitlab.spring26b.secoder.net:2024010854/chatglmj.git
cd chatglmj

```



## 二、 Docker 环境配置与网络优化

本项目不依赖宿主机（本地电脑）的 Node.js 或 Python 运行环境。所有代码的执行均在 Docker 容器内部完成，以确保多端开发环境的绝对一致性。

1. **安装 Docker Desktop**
前往 Docker 官方网站下载对应操作系统（Windows/Mac）的 Docker Desktop 安装包，按默认选项安装并启动。确保软件状态显示为 "Engine running"。
2. **配置网络代理或镜像源（极其重要）**
因国内网络限制，默认拉取 Docker Hub 镜像及 Node/Python 依赖极易出现超时（`i/o timeout`）。请根据自身网络情况选择以下**其中一种**解决方案：
* **方案 A：配置本地代理（推荐，适用于拥有代理软件的成员）**
打开 Docker Desktop -> **Settings** -> **Resources** -> **Proxies**。
开启 **Manual proxy configuration**。
在 Web Server (HTTP) 和 Secure Web Server (HTTPS) 处填入本地代理地址，例如 `http://127.0.0.1:7890`（端口号以实际代理软件为准）。
在 Bypass proxy settings for 处填入：`localhost,127.0.0.1`。
点击 Apply & restart。
* **方案 B：配置国内镜像加速器（适用于无代理软件的成员）**
打开 Docker Desktop -> **Settings** -> **Docker Engine**。在右侧的 JSON 配置文件中添加 `"registry-mirrors"` 字段：
```json
{
  "builder": {
    "gc": {
      "defaultKeepStorage": "20GB",
      "enabled": true
    }
  },
  "experimental": false,
  "registry-mirrors": [
    "https://docker.m.daocloud.io",
    "https://mirror.ccs.tencentyun.com",
    "https://hub-mirror.c.163.com"
  ]
}

```


点击 Apply & restart。



## 三、 项目构建与运行验证

在 `chatglmj` 项目根目录下，执行以下命令构建并启动前后端容器：

```bash
docker compose up --build

```

*说明：首次构建因需要下载基础镜像和安装依赖，耗时较长（约 3-5 分钟），后续启动将利用缓存，达到秒级启动。*

**验证标准：**
当终端日志输出不再包含 Error，且同时出现 Vite 和 Django 的运行提示时，请在浏览器分别访问：

* 前端 React 界面：`http://localhost:5173`
* 后端 Django 界面：`http://localhost:8000`
若均能正常访问，说明本地环境配置成功。

## 四、 本地与容器的工作模式关系

理解本地环境与 Docker 的分工是日常开发的基础：

1. **本地环境（Conda / 本地 Node）的定位**：
本地环境仅用作 IDE（如 VS Code / PyCharm）的**语法分析引擎**。你可以在本地安装 Python 和 Node，以获取代码高亮、跳转和自动补全，但**绝不要**在本地终端运行 `python manage.py runserver` 或 `npm run dev`。
2. **热更新机制（Volumes）**：
`docker-compose.yml` 中已配置目录映射。你在本地 IDE 中修改的任何代码（按 `Ctrl+S` 保存后），都会实时同步至 Docker 容器内部。前端 Vite 和后端 Django 的监控进程会自动重载应用，你只需刷新浏览器即可查看最新效果。

## 五、 Docker 常用命令速查手册

日常开发中，请在项目根目录下使用以下命令进行容器管理：

* **启动项目**：
```bash
docker compose up

```


*(附加 `-d` 参数可使容器在后台运行，不占用当前终端窗口。)*
* **关闭并清理项目**：
```bash
docker compose down

```


*(附加 `-v` 参数将连同数据库卷和 node_modules 缓存一并删除，仅在环境彻底崩坏需要重置时使用，慎用！)*
* **实时查看后台运行日志**：
```bash
docker compose logs -f

```


* **进入后端容器执行 Django 命令（核心高频操作）**：
凡是涉及数据库迁移、创建超级管理员等需要在应用内部执行的命令，必须先进入后端容器。
1. 进入容器终端：
```bash
docker exec -it chatglmj-backend-1 /bin/bash

```


2. 在容器内部执行 Django 命令，例如：
```bash
python manage.py makemigrations
python manage.py migrate
python manage.py createsuperuser

```


3. 执行完毕后，输入 `exit` 退出容器。



## 六、 Git 代码协作与提交流程规范

本项目要求严格的 Git Flow 分支管理，禁止混乱的代码合并导致项目结构损坏。SECoder 平台已集成 SonarQube CI/CD 流水线，合并代码必须经过质量扫描。

**原则 1：绝对禁止直接推送 `main` 分支。** `main` 分支代表项目的稳定构建版本，受系统保护。
**原则 2：所有新功能必须在独立分支完成。**

### 标准开发工作流演示：

1. **同步主干代码**（每次开发前必备）：
```bash
git checkout main
git pull origin main

```


2. **创建功能分支**：
分支命名需语义化，如 `feature/login-api` 或 `bugfix/message-display`。
```bash
git checkout -b feature/你的功能名称

```


3. **本地开发与提交**：
在 IDE 中完成代码编写与本地测试。
```bash
git add .
git commit -m "feat: 新增了用户登录相关的校验逻辑" 
# commit message 规范：feat(新功能), fix(修复), docs(文档), chore(配置/基建)

```


4. **推送到远程仓库**：
将你的本地分支推送到云端。
```bash
git push origin feature/你的功能名称

```


5. **发起 Merge Request (MR)**：
* 登录 SECoder GitLab 网页端。
* 系统会提示你刚推送了新分支，点击 **Create Merge Request**。
* 选择将你的功能分支合并入 `main` 分支。
* **等待 CI/CD 扫描**：平台会自动触发 SonarQube 进行代码静态扫描。必须等待流水线执行通过（显示绿灯）。
* 邀请组员进行 Code Review，确认无误后，由管理员或 Reviewer 点击 **Merge**，将代码正式合入主分支。


## 七、 Git Commit 提交信息规范
为保证代码历史清晰可追溯，团队成员在执行 git commit 时，提交信息（Commit Message）必须遵循以下格式规范：

### 基本格式：

```
<类别>: <简短描述>

（可选的详细描述，解释为什么做这个改动）
```

### 类别 (Type) 严格限定为以下四种：

- init: —— 初始化与基建
用于项目初始化的搭建、环境配置的更改、依赖包的首次引入。

    - 示例： init: 搭建 React 和 Django 的 Docker 基础运行环境

- fix: —— Bug 修复 (Debug)
    - 示例： fix: 修复用户登录时密码大小写校验失效的问题

- add: —— 添加一般函数或局部功能
    - 用于日常开发中新增的小型功能模块、独立的 API 接口或工具函数。这是日常开发中使用频率最高的标签。
    - 示例： add: 增加获取历史聊天记录的后端 API 接口

    - 示例： add: 前端聊天界面的输入框 UI 组件

- feat: —— 重大阶段性突破 (Feature)
    - 用于具有里程碑意义的重大功能上线，或整合了多个 add 的完整业务模块发布。通常意味着一个大作业评分点的完成。

    - 示例： feat: 完整即时通讯模块（WebSocket 端到端互通）正式上线

    - 示例： feat: 核心数据库表结构（User, Message, Room）设计与迁移完成- 

(注：如果提交涉及纯文档修改，为了不干扰代码逻辑的追踪，建议使用 docs: 完善项目使用文档 作为补充。)

### 提交建议：
保持“小步快跑”的提交习惯。不要积攒了一周的代码才做一次 feat: 提交。每天完成一个小接口或修复一个小 bug 后，就应该对应使用 add: 或 fix: 进行提交，这能最大程度避免合并时的代码冲突。

---
