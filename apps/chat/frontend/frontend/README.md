# ChatGLMJ 前端（Vite + React）

本目录使用 **npm** 管理依赖：

```bash
npm install
npm run dev
```

终端里会打印实际地址（例如 `http://localhost:5173/`）。若出现 **`Port 5173 is in use`**，Vite 会改用 **5174、5175…**——请用终端显示的端口打开页面，不要死盯 5173。

若浏览器仍报 **ERR_EMPTY_RESPONSE / Connection reset**：

1. 关掉所有旧的 `npm run dev` 终端，再重新执行 `npm run dev`。
2. **释放 5173**（Linux/WSL）：`fuser -k 5173/tcp` 或查占用后结束进程；Windows 可在 PowerShell：`netstat -ano | findstr :5173`，再用任务管理器结束对应 PID。
3. Cursor 内置预览连不上时，直接用 **Chrome 打开终端里给出的 Local 链接**。

## 环境变量（与队友对齐）

复制 [.env.example](.env.example) 为 `.env`：

| 变量 | 说明 |
|------|------|
| `VITE_API_BASE_URL` | REST 根路径，默认 `/api`（开发时由 Vite 代理到后端） |
| `VITE_WS_BASE_URL` | WebSocket 根，如 `ws://localhost:8000`，用于 `wss?` 拼接 `/ws/chat/` |

## 登录态约定（开发者 A 维护）

- **Token 存储键**：`access_token`、`refresh_token` 见 [src/constants/storage.js](src/constants/storage.js)；用户缓存 `auth_user`（JSON）。
- **401 处理**：`apiFetch` 会先尝试 `POST /api/auth/refresh` 刷新 access（并发只触发一次）；失败则清空会话并跳转 `/login`。
- **路由分工**：A 负责 `/login`、`/register`、`/settings/*`；B 负责 `/contacts`、`/friends/requests`、`/user/:userId` 等（勿改对方路由根路径）。

## 技术说明

本项目基于 Vite 的 React 模板，支持 HMR 与 ESLint。官方提供两种 React 插件：

- [@vitejs/plugin-react](https://github.com/vitejs/vite-plugin-react/blob/main/packages/plugin-react) — 使用 [Babel](https://babeljs.io/)（在 [rolldown-vite](https://vite.dev/guide/rolldown) 中可选用 [oxc](https://oxc.rs)）实现 Fast Refresh。
- [@vitejs/plugin-react-swc](https://github.com/vitejs/vite-plugin-react/blob/main/packages/plugin-react-swc) — 使用 [SWC](https://swc.rs/) 实现 Fast Refresh。

## React Compiler

默认未启用 React Compiler，以免影响开发与构建性能。如需启用，参见 [官方文档](https://react.dev/learn/react-compiler/installation)。

## 扩展 ESLint

若用于生产级应用，建议启用 TypeScript 与类型感知规则。可参考 Vite 的 [TS 模板](https://github.com/vitejs/vite/tree/main/packages/create-vite/template-react-ts)，并接入 [`typescript-eslint`](https://typescript-eslint.io)。
