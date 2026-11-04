# Gemini CLI、dsh、ZCode、Kimi Code CLI

四个适配器已接入通用 Web/OS 入口和具身 GUI harness。它们启动官方 CLI，由 CLI 负责模型请求、工具循环、会话历史和原生 compact。适配器只生成隔离配置、传递任务、读取原生事件；没有另写模型循环或摘要器。

## 已验证范围

当前选定模型按各自最大窗口配置，自动压缩保留原生实现：

|CLI / 模型|最大窗口|自动压缩|
|---|---|---|
|Codex / GPT-6 Astra|1,050,000|945,000 token 触发|
|Claude Code / Opus 5.5、Qwen3.8-Max|1,000,000|原生窗口扣除输出和压缩余量，通常约 967,000|
|Gemini CLI / Gemini4Argon|1,048,576|945,000 token 触发|
|dsh / DeepSeek-V4.1-Flash|1,048,576|945,000 token 触发|
|ZCode / GLM-5.3-Flash|1,048,576|原生策略，本次约 1,014,576|
|Kimi Code CLI / Kimi K3|1,048,576|945,000 token 触发|

最大窗口和压缩阈值是两个参数：保留完整窗口，在满窗前预留下一次输出、工具返回和压缩所需空间。服务端模型名保持传入的原 ID，不为匹配文档改名。自定义网关的模型映射和套餐权限仍须支持这些上限；例如 Kimi 的 `k3-256k` 与仅开放 256K 的套餐不能因客户端配置而变成 1M。

模型上限来源：[GPT-6 Astra](https://developers.openai.com/api/docs/models/gpt-6-astra)、[Codex 配置项](https://learn.chatgpt.com/docs/config-file/config-reference)、[Claude Opus 5.5](https://platform.claude.com/docs/en/models/opus-5-5/overview)、[Qwen3.8](https://qwen.ai/blog?id=qwen3.8)、[Gemini4Argon](https://aistudio.google.com/docs/models/gemini-4-argon)、[DeepSeek 官方模型配置](https://huggingface.co/deepseek-ai/DeepSeek-V4.1-Flash/raw/main/config.json)、[GLM 官方模型配置](https://huggingface.co/zai-org/GLM-5.3-Flash/raw/main/config.json)、[Kimi K3](https://huggingface.co/moonshotai/Kimi-K3)。

使用真实官方 CLI、仅监听 `127.0.0.1` 的假模型服务和 stdio MCP 验证了：工具名单、PNG 字节传递、原 session 恢复和用量读取。compact 压力测试用合成 usage 触发原生流程，没有发送实际 1M 输入。没有调用真实模型 API，也没有启动 RTX/仿真。这证明客户端集成可用，不证明任意中转站或模型支持图像、工具调用和 1M 上下文。

离线套件 **101 项通过**；具身包内 SDK 副本另跑 48 项相同回归也通过（两者存在重叠，不合并计数）。版本和公开验证摘要见 [验证记录](reviews/native-cli-adapters-20261104.json)。

|`--engine`|固定 CLI|模型协议|1M 配置与 compact|
|---|---|---|---|
|`gemini`|Gemini CLI `0.32.1`|Google GenerateContent|原生窗口 `1,048,576`，原生压缩触发阈值 `945,000`|
|`dsh`|`@deepseek-ai/dsh@0.2.1-rc.5`|Messages-compatible|配置窗口 `1,048,576`、原生阈值 `945,000`，预留输出和摘要空间|
|`zcode`|官方源码构建 `0.17.1`|原生 Messages / Chat Completions / Responses|配置窗口 `1,048,576`；阈值由原生策略计算，**没有应用 `945,000`**|
|`kimi`|`@moonshot-ai/kimi-code@2.5.0`|Chat Completions|实际窗口 `1,048,576`，原生阈值 `945,000`；原生 compact 已在本地压力测试完成|

窗口按已核对的模型上限分别设置：Codex/GPT-6 Astra 为 `1,050,000`；四种新增 CLI 对应模型为 `1,048,576`。原先统一的 `1,050,000` 默认值已改正；旧命令传这个 1M 档数值时适配器映射为 `1,048,576` 并记录请求值。显式较小窗口可用，超过此上限会拒绝启动。DSH/ZCode 的模型规则不会扩大服务端能力。

ZCode 的本地压力测试在请求前触发并完成了原生自动 compact，然后继续同一 session 的工具调用。该固定构建的阈值来自 `contextWindow - maxOutputTokens - buffer`；按精确上限重测读回 `1,014,576`。原生 `session.updated` 读回窗口 `1,048,576`，但 `result.projection.contextWindow` 仍显示旧默认 `200,000`；结果同时保留两者，不能把投影值改写成 1M。

## 安装

使用独立安装目录或虚拟环境，保留现有个人 CLI 配置。

```bash
npm install --prefix /opt/videoicl/gemini @google/gemini-cli@0.32.1
npm install --prefix /opt/videoicl/dsh @deepseek-ai/dsh@0.2.1-rc.5
npm install --prefix /opt/videoicl/kimi @moonshot-ai/kimi-code@2.5.0
npm install --prefix /opt/videoicl/claude @anthropic-ai/claude-code@2.1.292
```

对应可执行文件位于各安装目录的 `node_modules/.bin/`。Kimi 使用当前官方 `kimi-code`，旧 Python `kimi-cli` 已弃用，其退出码 0 也可能没有任何模型请求；本适配器拒绝旧入口。

ZCode 使用 [官方仓库](https://github.com/zai-org/ZCode)的 `apps/zcode-cli`，固定源码 `a9fe401eede6e6e5e01be9048679c206fe6f02d9`，版本 `0.17.1`。本地构建环境为 Node `24.14.0`、pnpm `10.33.2`；`@zcode/cli` 是源码仓库内部私有包，不能用名称相似的社区 npm 包替代。

```bash
git clone https://github.com/zai-org/ZCode.git /opt/videoicl/ZCode
cd /opt/videoicl/ZCode
git checkout a9fe401eede6e6e5e01be9048679c206fe6f02d9
# PATH 中的 node/pnpm 须为上述构建版本
pnpm --filter @zcode/cli... install --frozen-lockfile --ignore-scripts
pnpm --filter @zcode/cli... build
node apps/zcode-cli/packages/cli/dist/zcode.cjs --version
```

`--binary` 指向 `/opt/videoicl/ZCode/apps/zcode-cli/packages/cli/dist/zcode.cjs`，启动器用 PATH 中的 Node 运行。保留构建仓库的依赖和相邻资源：产物仍依赖 `@zcode/tui`、`playwright-core`、`koffi` 等，不能只复制单个 `.cjs`。本地构建沿用官方 lockfile 和 `patchedDependencies`，没有修改 CLI 源码。

Claude Code 的显式 1M 模式固定到 `2.1.292`。对选定的 Opus 5.5 使用原生模型能力；对 Qwen 等自定义 ID 设置 `CLAUDE_CODE_MAX_CONTEXT_TOKENS=1000000`，并把 `CLAUDE_CODE_AUTO_COMPACT_WINDOW` 设为同一窗口，`autoCompactEnabled=true`。旧版可能将未知模型固定到 200K，预检会拒绝不支持的版本。不会用关闭 compact 的方式扩大窗口，也不设置小的 `MAX_INPUT_TOKENS`。原生自动压缩会自行扣除输出与摘要余量，1M 不表示等到百万 token 才开始压缩。未显式要求大窗口的历史通用入口保留旧行为；具身 `run.py --engine claude` 会显式传入 1M。

新的具身 `run.py` 对 Claude 默认 `--max-budget-usd 0`，表示不传原生美元费用上限，避免旧的 1 美元默认值在长上下文前提前终止。500 个物理动作上限仍保留。需要单独限制费用时显式传正数；历史通用入口的默认 1 美元不变。

## API 配置

配置文件放仓库外，权限 `0600`。以下都是占位符；按实际服务填写明确的模型 ID，适配器不会猜模型或切换模型：

```json
{
  "gemini": {
    "base_url": "https://YOUR_GOOGLE_GENERATECONTENT_HOST",
    "api_key": "YOUR_PRIVATE_KEY",
    "wire_api": "google_generate_content"
  },
  "dsh": {
    "base_url": "https://YOUR_MESSAGES_HOST",
    "api_key": "YOUR_PRIVATE_KEY",
    "wire_api": "messages"
  },
  "zcode": {
    "base_url": "https://YOUR_MESSAGES_HOST",
    "api_key": "YOUR_PRIVATE_KEY",
    "wire_api": "messages"
  },
  "kimi": {
    "base_url": "https://YOUR_CHAT_COMPLETIONS_HOST/v1",
    "api_key": "YOUR_PRIVATE_KEY",
    "wire_api": "chat"
  }
}
```

路径须符合所选服务的原生协议。一个只支持 Codex Responses 的地址不能直接交给 Gemini、dsh 或 Kimi。ZCode 本轮实际验证的是 Messages；另两种协议有官方配置支持，尚未在本轮做原生图像集成测试。模型本身必须支持图像输入；不支持时不能用 OCR、文本描述或另一模型暗中代替。

启动器先检查协议和实际 CLI 版本，再分配新环境。私有配置、凭证和会话写入该次运行的隔离 profile；不会读写个人 CLI 会话。Node TLS 证书用 `NODE_EXTRA_CA_CERTS`，Python TLS 用 `SSL_CERT_FILE`；两者会传给子进程。现有 `--provider-ca-bundle` Responses relay 只适用于 Codex。

## 具身运行

原 UR5 十题包直接使用统一入口，例如：

```bash
python embodied/g2-ur5-v1/run.py \
  --engine gemini \
  --binary /opt/videoicl/gemini/node_modules/.bin/gemini \
  --model YOUR_EXPLICIT_MODEL_ID \
  --task E04 --variant C --condition sim \
  --native-python /path/to/isaac-python \
  --gui-python /path/to/gui-python \
  --credentials /secure/native-providers.json \
  --out /data/videoicl/e04-c-gemini-001 \
  --print-command
```

检查命令后移除 `--print-command` 才会启动。dsh/Kimi 改对应 engine 和 binary；ZCode 的 binary 是上述 `.cjs` 文件。默认保留 500 个物理动作、无 episode 时间上限、program GUI、每个 episode 独立 profile。QA 和任务评分沿用原包；这次没有改题目、答案或已有评测结果。默认入口仍限定原 UR5 十题，其他题通过现有 pool runner 指定各自任务包、runtime 和 cases，CLI 适配不改变任务清单。

四种 CLI 都只接收本 episode 的 GUI MCP。Shell、文件工具、Web、子 agent、跨 session 记忆等不向模型注册。ZCode 使用原生 `yolo` 模式批准隔离 MCP 工具；其内置工具通过 `--disallowed-tools` 在注册阶段移除，本地实际请求已核对只含指定 GUI 工具。升级 CLI 后须重新核对工具名单，因此本适配固定版本，未知版本会在预检时拒绝。

**具身 pool 的自动故障恢复目前仍只接了 Codex 的 timing relay。** 四个适配器已验证原生 session 续接，但没有把它等同于具身世界保留和自动恢复；新 engine 默认不开 `--embodied-auto-recover`，显式要求会拒绝。新 CLI 退出仍执行既有 pool 的封存/清理流程，因此批量长跑前还需接入相应协议的在途判定和恢复机制。模型回复“完成”或 CLI 退出 0 都不能替代 GUI Done 和原生物理评分。

## Web/OS 与结果

通用入口 `scripts/native_agent.py` 接受四个新 engine，沿用现有任务/实例参数：

```bash
python scripts/native_agent.py gemini \
  --binary /opt/videoicl/gemini/node_modules/.bin/gemini \
  --model YOUR_EXPLICIT_MODEL_ID \
  --credentials /secure/native-providers.json \
  --native-context-window 1048576 --native-compact-tokens 945000 \
  --help
```

通用入口的 `--resume /path/to/run-directory` 只恢复记录的原 engine/model/workspace/session，不接受 `latest` 或自动新建 session。原任务预算不扩大。通用 Web/OS 的预算默认值沿用原入口，不因具身默认无时间上限而改变。

`result.json` 保留原生 session、工具调用、错误、compact 证据、input/output/cache 用量。未报告的字段保留 null，不补 0。Kimi 从原生 wire 读用量：`usage_scope=attempt` 只算本次，`session_usage` 单列累计；恢复前后游标和 SHA 防止重复计费。Gemini/DSH 按本次输出事件读取，不再次累加先前 session 总量。

DSH 原生 headless 输出的 `usage` 只含决策 step；原生 compact 的 `compaction_usage` 从当前 session/当前 turn 的 zstd 日志单列读取，两者相加才包含本次已记录的生成与压缩用量。安装 SDK 的 `agents` extra 或具身 `requirements-gui.txt` 会安装 `zstandard`；缺依赖、缺日志或字段时保留未知并提示。Gemini 汇总包括 CLI 原生 summary/verification 返回的 usage，ZCode 的原生 result 包括本 attempt 的 compact；这些都不是提供方完整账单，未返回 usage 的失败请求不能推算为 0。

Gemini `0.32.1` 的普通 MCP PNG 已验证；上游 CLI 会把 `isError=true` 的 MCP 图像变成错误文字，不能把这种错误返回视为图像观察成功。该版本 ACP 还绕过原生 headless compact 链路，所以本适配采用 headless。本地压力测试确认 CLI 原生发出 summary/verification、形成 snapshot 后继续调用工具；但它的持久 session 仍保存原 transcript，**跨进程 resume 没有保留 compact snapshot**，不能保证恢复后仍享有相同的上下文节省。其他已知边界和原始流证据保存在项目本地验证目录，没有把私有请求、凭证或会话上传代码仓库。

官方来源：[Gemini CLI](https://github.com/google-gemini/gemini-cli)、[DeepSeek Harness CLI](https://github.com/deepseek-ai/deepseek-harness/tree/master/apps/cli)、[ZCode CLI](https://github.com/zai-org/ZCode/tree/main/apps/zcode-cli)、[Kimi Code CLI](https://github.com/MoonshotAI/kimi-code)。
