# 团队 inference 使用说明（无需填写模型 API key）

同事只需选择任务、demo 和 harness，即可使用执行机上配置好的模型。模型 API key 与平台管理密钥由执行机读取，无需复制到同事电脑，也无需执行 `export ...KEY=...`。

## 1. 连接执行机

| 组件 | 地址 / 位置 |
|---|---|
| 推理执行机 | Qingle 的 Mac；项目目录 `/Users/qingle/Documents/ChatGPT/VideoICL` |
| 任务环境 | agentlab 上的团队平台 |
| 执行机访问平台 | `http://127.0.0.1:18765`，通过执行机的 SSH 隧道连接 agentlab |
| Codex 模型 | `gpt-5.5` |
| Claude Code 模型 | `claude-sonnet-4-6` |

**开始前需要管理员提供执行机的 SSH 地址并开通登录权限。仅能登录 agentlab 或打开平台网页，不等于能启动模型推理。** agentlab 的平台服务不包含这台 Mac 的私有模型配置。本文不假设同事已拥有 Mac 的远程登录权限。

在自己电脑的 `~/.ssh/config` 中配置管理员提供的地址：

```sshconfig
Host videoicl-runner
    HostName <管理员提供的 Mac 可达地址>
    User qingle
    ServerAliveInterval 30
```

用自己的 SSH 私钥登录；这不是模型 API key：

```bash
ssh videoicl-runner
bash
cd /Users/qingle/Documents/ChatGPT/VideoICL
```

以下命令均在该执行机的 Bash 中运行。若直接使用这台 Mac 的终端，从 `bash` 和 `cd` 开始即可。

此方式适用于可信团队共用执行账号：同事**不需要知道或填写** API key，但同一系统账号具有读取该账号私有文件的权限。如果要求“同事在权限上也无法读取 key”，需采用独立服务账号和受限作业提交接口；不能将共享 SSH 账号视为密钥隔离。

## 2. 准备一次运行

检查平台连接，并定义快捷命令：

```bash
curl --fail http://127.0.0.1:18765/healthz
export PATH="/Users/qingle/.local/bin:/Users/qingle/.nvm/versions/node/v20.20.2/bin:$PATH"
mkdir -p .local/team-inference
umask 077

infer() {
  local engine="$1"
  shift
  .venv/bin/python scripts/native_agent.py "$engine" \
    --credentials .local/native-agents/credentials.json \
    --admin-token-file .local/agentlab-admin-token \
    --control-url http://127.0.0.1:18765 \
    --output-root .local/team-inference \
    --timeout 1200 --max-actions 100 \
    --max-budget-usd 1.5 --evaluate "$@"
}
```

`infer` 在本次 Bash 会话内有效。每次运行自动创建独立任务环境和唯一结果目录，无需人工先在网页创建任务。模型、网关及兼容选项从私有配置读取，默认保留原生上下文管理和自动压缩。

`--timeout 1200` 为 20 分钟，`--max-actions 100` 为输入动作上限。`--max-budget-usd 1.5` 仅作用于 Claude Code 的原生估算费用上限，**不是 Codex 的费用限制**，也不保证等于代理商账单。

## 3. 跑 OS 任务

```bash
# Codex
infer codex --os-case OS-SEL-01 --variant A --seed 20261006

# Claude Code：相同任务、版本和执行种子，独立环境
infer claude --os-case OS-SEL-01 --variant A --seed 20261006
```

可将 `OS-SEL-01` 换为平台 **OS · 36 题** 中的题号，例如 `OS-REC-01`、`OS-XAPP-01`。版本可选 `A`、`B`、`C`。

OS 任务自动下载并校验对应版本的官方 demo；无需传视频或填写规则。执行 seed 应与 demo 的 seed 不同。两个 harness 做对比时使用相同任务、版本、执行 seed 和预算，并保留所有尝试。

## 4. 跑 Web 任务

先在执行机准备视频目录：

```bash
mkdir -p .local/team-demos
```

在**同事自己的电脑**另开终端上传视频，替换本地视频路径：

```bash
scp "/本地路径/11-A.mp4" \
  videoicl-runner:/Users/qingle/Documents/ChatGPT/VideoICL/.local/team-demos/11-A.mp4
```

回到执行机，使用第 2 节定义的 `infer`：

```bash
infer codex --task 11 --variant A --seed 10001 \
  --demo "$PWD/.local/team-demos/11-A.mp4"

infer claude --task 11 --variant A --seed 10001 \
  --demo "$PWD/.local/team-demos/11-A.mp4"
```

`--task` 为 Web 题号 1–75。视频必须对应题目及版本，且符合该题教学规则。Web 视频需显式传入；省略 `--demo` 会成为无示范条件。视频通过带时间戳的画面帧提供给模型，不包含音轨。

文字规则对照实验将 `--demo ...` 替换为 `--rule-file /绝对路径/rule.txt`，二者不能同时提供。规则文件只写通用规则，不写本次实例的答案。

## 5. 查看结果

前台命令完成后会输出 JSON，其中 `artifacts` 是结果目录。查看最新一次运行：

```bash
.venv/bin/python - <<'PY'
import json
from pathlib import Path
files = list(Path('.local/team-inference').glob('*/result.json'))
if not files:
    print('没有已写出的结果；运行可能仍在进行，请查看本次日志。')
else:
    path = max(files, key=lambda p: p.stat().st_mtime)
    result = json.loads(path.read_text())
    print('目录:', path.parent)
    for key in ('outcome', 'execution_status', 'agent_finished', 'duration_seconds'):
        print(key + ':', result.get(key))
    print('evaluation:', json.dumps(result.get('evaluation'), ensure_ascii=False))
PY
```

多人并行时请使用各自命令输出的 `artifacts`，不要把“最新一次”当作自己的运行。

| 字段 / 文件 | 含义 |
|---|---|
| `outcome: success / fail` | 平台 evaluator 判定通过 / 未通过，不以模型口头宣称为准 |
| `execution_status: completed` | Agent 正常结束 |
| `execution_status: budget_exhausted` | 原生费用或轮次预算耗尽，仍按实际环境评分 |
| `agent_error / environment_error / evaluation_error / incomplete` | 推理或评测链路未正常收尾，需要反馈；不当作任务答错统计 |
| `result.json` | 最终结果、评分和退出原因 |
| `manifest.json` | 题号、版本、seed、模型和运行编号 |
| `computer.jsonl` | 截图、输入、demo 帧和结束操作记录 |

`--evaluate` 会提交评分并封存本次运行；想重做时重新执行命令，生成新环境。不要对已封存运行使用 resume。退出码 0 不代表任务做对，正确率以 `outcome` 为准。

分享反馈时提供：任务与版本、模型、seed、运行编号、`outcome`、`execution_status` 和相关截图。**不要打包整个运行目录**：其中 `profile/` 和 `computer-private.json` 含有模型或运行访问凭证。通常只需分享 `result.json`、`manifest.json` 及必要截图，并检查内容。

## 6. 断开 SSH 后继续执行

在执行机运行以下完整命令，不依赖 `infer` 函数。先完成第 2 节的 PATH 和目录准备：

```bash
job_log=".local/team-inference/job-$(date +%Y%m%d-%H%M%S)-$$.log"
nohup /usr/bin/caffeinate -i .venv/bin/python scripts/native_agent.py codex \
  --credentials .local/native-agents/credentials.json \
  --admin-token-file .local/agentlab-admin-token \
  --control-url http://127.0.0.1:18765 \
  --output-root .local/team-inference \
  --os-case OS-SEL-01 --variant A --seed 20261006 \
  --timeout 1200 --max-actions 100 --evaluate \
  > "$job_log" 2>&1 < /dev/null &
echo "进程=$! 日志=$job_log"
```

将 `codex` 换成 `claude` 并加 `--max-budget-usd 1.5` 可运行 CC。记下日志路径，重连后用 `tail -n 80 <日志路径>` 查看。`caffeinate` 在任务期间防止空闲睡眠；电脑关机、合盖或断网仍可能中断任务。

## 7. 常见问题

| 现象 | 处理 |
|---|---|
| SSH 无法登录执行机 | 请管理员确认 Mac 的远程登录、可达地址和个人 SSH 公钥授权；不要索取模型 key |
| `healthz` 连接失败 | 请管理员恢复执行机到 agentlab 的平台隧道 |
| 找不到 `credentials.json` 或 `/Users/qingle/...` | 确认登录的是已配置的 Mac，而不是 agentlab 或自己的电脑 |
| `node` / `claude` 找不到 | 执行第 2 节的 PATH 命令；仍失败请管理员检查工具安装位置 |
| 401、429、网关超时 | 保留运行编号和错误，由管理员检查凭证、额度或网关；不要改成 success/fail 掩盖错误 |
| CC 预算耗尽且评分 fail | 查看实际完成步骤；需要更高预算时另开运行，并记录预算差异 |

原生 harness 的具体启动参数以仓库 `packages/sdk/vic_sdk/native_agent.py` 和 `--help` 为准。Codex 的非交互执行入口采用官方支持的 `codex exec`：[OpenAI 原生 harness 说明](https://developers.openai.com/blog/codex-as-a-platform)。
