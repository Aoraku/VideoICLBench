# VideoICL-Bench

VideoICL-Bench 提供任务目录、独立运行环境、截图与键盘鼠标接口、教程录制、状态判分和可追溯证据。

## 可运行范围

| 能力 | 状态 |
|---|---|
| 六个来源仓库及固定提交记录 | 位于 `apps/`，来源记录见 `sources.lock.json` |
| 六个原应用容器与浏览器入口 | Compose profile 支持；启动与 HTTP/WebSocket 鉴权检查通过 |
| 100 个基础任务、300 个规则版本 | 任务目录完整 |
| 65 道软件题与 10 道游戏题 | 可使用 Chromium 开发工作台；包含确定性数据及私有判分器 |
| 真实截图、鼠标键盘、重置、凭证隔离、证据封存 | 本地控制服务支持 |
| MP4 录制、规则字幕、结果审核 | 本地录制服务支持，开发采样率 5 FPS |
| 六个原应用的任务接入认证 | 尚未完成；原应用和开发工作台是不同执行表面 |
| 25 道系统题 | 有任务规范与部分采集/生命周期工具，尚未接入可执行任务 |
| Windows/Linux/Android 正式执行池 | 需要实验室主机、系统镜像、客体初始化和操作适配器 |
| 300 段人工教程 | 需要同事录制、人工审核；自动测试视频不计入数据集 |

所有开发运行均返回 `official: false`。平台不会把 Chromium 开发环境自动替代为 Windows，也不会以未连接的系统模拟结果判分。

## 本地启动

要求 Python 3.11+、Node.js 20+。在仓库根目录执行：

```bash
python3 -m venv .venv
.venv/bin/pip install -c requirements.lock.txt -e '.[test]'
.venv/bin/python -m playwright install chromium
npm --prefix apps/portal ci
npm --prefix apps/portal run build
.venv/bin/python scripts/dev.py
```

浏览器访问 `http://127.0.0.1:8765`。访问密钥保存在 `.local/admin-token`，文件权限为 0600，不进入 Git。服务只绑定本机回环地址。

在任务大厅选择任务、规则版本、用途和种子，准备环境后在远程画面里完成操作。教程录制只允许演示运行；停止录制后执行判分，通过后提交人工审核。

停止录制会封存该轮输入；重置将录像和证据归档到对应 epoch。录制超出开发帧数上限会被拒绝，不能作为完整教程审核。

## 数据与凭证

- 演示种子范围为 0–999，开发种子为 1000–9999，正式预留种子从 10000 开始。
- 原始任务文档为 `VideoICL_100_tasks.md`；`scripts/build_catalog.py` 生成版本化目录。
- 规则、初始状态和标准答案只由控制服务与私有 evaluator 持有。
- 管理员凭证管理生命周期；Agent 凭证只允许本次运行的截图和输入；应用界面使用独立凭证。
- 每次运行有独立 SQLite 业务文件；控制数据库支持 SQLite 和 PostgreSQL。
- 重置增加 epoch，并归档上一轮证据；旧应用凭证和旧 epoch 操作失效。
- 正式任务必须先通过原生/辅助环境认证；开发工作台状态不能作为论文正式成绩。

## API 与 SDK

API 以 `/v1/runs` 为入口。Runner 持有管理凭证，模型进程只获得 `actor_token`。

```python
from vic_sdk import Client

runner = Client('http://127.0.0.1:8765', manager_token)
run = runner.create(task_id=1, variant='A', seed=1000)
actor = Client('http://127.0.0.1:8765', run['actor_token'])
observation = actor.observation(run['id'])
actor.act(run['id'], observation['epoch'], observation['frame'], 'click', x=750, y=385)
# 后续动作来自模型；模型不调用 evaluate。
result = runner.evaluate(run['id'])
```

`completion` 表示子目标完成比例；`success` 同时要求全部子目标与过程约束满足。评测终止输入并封存证据，重复调用返回同一结果。

## 验证

```bash
.venv/bin/python -m pytest
npm --prefix apps/portal run build
.venv/bin/python scripts/preflight.py
```

测试覆盖反事实可区分性、示范答案迁移隔离、棋盘规则、正确/错误轨迹、重复动作、运行隔离、重置和评分权限。部署与原应用接入要求见 `docs/deployment.md` 和 `docs/acceptance.md`。

启动本地服务后，执行 `scripts/smoke_pixels.py` 验证截图操作、判分与录像；执行 `scripts/smoke_concurrency.py` 验证 15 个开发会话（含 5 路录像）。原应用启动后可执行 `scripts/smoke_native.py`。这些检查不构成真实 Windows/Linux/Android 执行池的容量验收。

完整模块边界、任务分配和正式交付门槛见 [实现范围](docs/implementation-scope.md)。
