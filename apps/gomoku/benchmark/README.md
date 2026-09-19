# VIC Gomoku benchmark 模式

任务：66, 67。

入口由本仓库的 `benchmark/app.py` 提供。共享的 `vic_apps` 负责事务数据库和 HTTP 协议，应用界面由 `apps/gomoku/main.cpp` 提供，从应用工作台进入默认首页，再通过导航完成业务操作。任务在独立数据库中初始化；普通操作不读取 A/B/C 规则。

控制平台通过应用 Worker 的私有 `prepare` / `seal` 接口管理任务；应用用户只使用 `/api/runs/{id}` 与 `commands`。模块支持在统一 Worker 中运行，也可用 `uvicorn --app-dir apps/gomoku/benchmark app:create_app --factory --port 8771` 单独启动。需要设置 `VIC_APP_RUNTIME_TOKEN`，其值与控制平台一致。

评测检查领域对象、消息、成员、列表、产物、账本等实际状态。任务数据与会话独立保存。`apps/portal/src/Application.tsx` 仅为开发诊断界面，不作为正式录制入口。界面预览与人工验收范围见 `docs/native-frontends.md`。
