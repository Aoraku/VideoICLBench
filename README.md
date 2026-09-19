# VideoICL-Bench

VideoICL-Bench 为人类录制者和 GUI Agent 提供统一的应用、任务、截图输入、录像和状态评测平台。

应用界面预览与来源见 [应用界面](docs/native-frontends.md)。

团队成员访问共享执行服务，请阅读 [Agentlab 访问与验收说明](docs/agentlab.md)。任务问题可在本仓库 Issues 中选择“任务验收反馈”提交。

## 录制前就绪范围

- **75 个软件／游戏任务，225 个 A/B/C 规则版本**：具有业务状态与 eval 实现；应用任务路径的自动检查与人工视觉验收分别记录。
- **13 个应用模块**：六个来源仓库的 benchmark 模式，六个新增业务应用和一个游戏集合。
- **100 份逐题 eval 契约**：任务 1–75 有执行实现；76–100 的系统模拟器与系统执行适配暂缓。
- 每个运行使用独立应用数据库和独立 Chromium 进程，隔离 Cookie、页面和剪贴板。
- 录制支持规则字幕、鼠标指示、点击标记、15 FPS MP4；停止录制即封存输入。帧率可通过 `VIC_RECORDING_FPS` 设置为 5–30，默认单段上限 120 秒，配置范围 30–180 秒。
- 通过判分的教程可提交人工审核。正式数据集仍需要人工录制和审核的视频，因此运行结果中的 `official` 为 `false`。

软件／游戏的执行表面为 `native-task-workspace`。应用保留各自的首页与导航，通过适配器连接独立业务数据。Code 使用独立 Streamlit 进程，五子棋使用 Linux 容器里的原 SDL 程序；浏览器统一呈现画面和接收输入。

## 启动

```bash
python3 -m venv .venv
.venv/bin/pip install -c requirements.lock.txt -e '.[test]'
.venv/bin/python -m playwright install chromium
npm --prefix apps/portal ci
npm --prefix apps/portal run build
npm --prefix apps/chat/frontend/frontend ci
VITE_BASE_PATH=/native-assets/chat/ npm --prefix apps/chat/frontend/frontend run build
npx --yes pnpm@10.4.1 --dir apps/im/Frontend install --frozen-lockfile
NEXT_PUBLIC_VIC_BENCHMARK=1 npx --yes pnpm@10.4.1 --dir apps/im/Frontend build
.venv/bin/python scripts/start_platform.py
```

打开 [本地平台](http://127.0.0.1:8765/)。访问密钥位于 `.local/admin-token`，权限 0600。应用 Worker 在本机 8771 端口运行。两个服务分别对应 `scripts/dev.py` 和 `scripts/dev_apps.py`，统一启动器负责启动检查和退出清理。

包含原 SDL 五子棋的完整环境使用 Linux 容器。容器版构建全部前端，并使用 PostgreSQL 和独立应用数据卷：

```bash
python3 scripts/bootstrap.py
docker compose --env-file .local/docker.env -f infra/compose.yaml up --build -d
```

端口 8765 已占用时可在命令前设置 `VIC_PORT=8766`。容器访问密钥为 `.local/docker.env` 中的 `VIC_ADMIN_TOKEN`；凭证生成器不覆盖既有值。

## 应用与任务

| 应用 | 路径 | 任务 |
|---|---|---|
| 通讯 A | `apps/chat/benchmark` | 1–14 |
| 通讯 B | `apps/im/benchmark` | 15–16 |
| 音乐 | `apps/music/benchmark` | 17、18、22、27、28、32 |
| 新闻 | `apps/news/benchmark` | 19、20、23、24、29、30、33 |
| 视频／信息流 | `apps/media/benchmark` | 21、25、26、31、34、35 |
| 博客 | `apps/blog/benchmark` | 36、38、40、42 |
| 内容工作室 | `apps/studio/benchmark` | 37、39、41、43 |
| 旅游 | `apps/travel/benchmark` | 44、47、51、54 |
| 购物 | `apps/shop/benchmark` | 45、48、52、55 |
| 银行 | `apps/bank/benchmark` | 46、49、50、53、56、57 |
| 编程 | `apps/code/benchmark` | 58–65 |
| 五子棋 | `apps/gomoku/benchmark` | 66–67 |
| 2048／数独／扫雷／黑白棋 | `apps/games/benchmark` | 68–75 |

## 每题 eval API

管理凭证创建并结束任务，Agent 凭证只允许该运行的截图和键鼠输入。

```python
from vic_sdk import Client

runner = Client('http://127.0.0.1:8765', manager_token)
contract = runner.task_contract(1)
run = runner.create(task_id=1, variant='A', seed=10001, runtime='browser')
actor = Client('http://127.0.0.1:8765', run['actor_token'])
shot = actor.observation(run['id'])
# Agent 根据截图发出 actor.act(...)；不接触规则、业务 API 或判分接口。
result = runner.evaluate_task(1, run['id'])
```

对应 HTTP 接口：

```text
GET  /v1/tasks/{task_id}/contract
POST /v1/runs
GET  /v1/runs/{run_id}/observation
POST /v1/runs/{run_id}/actions
POST /v1/tasks/{task_id}/eval       {"run_id": "..."}
POST /v1/runs/{run_id}/reset
GET  /v1/runs/{run_id}/evidence
```

判分封存输入，检查业务结果、过程约束和额外操作，返回 `success`、`completion`、`checks`、`violations` 和证据引用。重复判分返回同一结果，任务编号不匹配会被拒绝。

[逐题应用与评测索引](docs/task-evaluation-map.md) 汇总全部任务、规则与读取字段。逐题契约位于 `tasks/contracts/001.json` 至 `100.json`。系统题返回明确的未接入错误，不生成模拟成功结果。

## 验证

```bash
.venv/bin/python -m pytest
.venv/bin/python scripts/check_native_ui.py 1,5,17,23,31,38,43,48,57,68 A
.venv/bin/python scripts/check_application_ui.py
.venv/bin/python scripts/smoke_application_pixels.py
.venv/bin/python scripts/smoke_application_concurrency.py
```

`check_native_ui.py` 从应用入口导航并操作原应用或新增产品界面；`check_application_ui.py` 仅检查开发诊断控件，不能证明原应用录制可用。模型执行协议为截图与键鼠输入。界面与验收范围见 [应用界面](docs/native-frontends.md)，操作说明见 [录制指南](docs/recording-guide.md)，架构见 [业务模型](docs/implementation-scope.md)。
