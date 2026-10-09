# 八题交付：HTTP agent 与控制面板

交付任务、难度标签和24段A/B/C视频见 [TASKS.md](TASKS.md)。本批入口与旧50题预览独立，服务端口为18664。源码、任务清单、已录视频、冻结场景与部署工具均在仓库main的 `simulator/` 内；平台密钥和执行数据不提交Git。

## 可以直接转发的访问说明

服务部署在Agentlab，使用时只需要建立访问连接。需要服务器SSH登录权限。

**1. 终端运行并保持窗口开启：**

```bash
ssh -N \
  -o ExitOnForwardFailure=yes \
  -o ServerAliveInterval=15 \
  -o ServerAliveCountMax=3 \
  -L 127.0.0.1:18767:127.0.0.1:18664 \
  qingle@134.175.168.162
```

连接成功后没有输出是正常的。

**2. 使用HTTP agent（不需要浏览器或安装仿真）：**

从服务下载标准库客户端和通用提示词到同一个目录：

```bash
curl --fail http://127.0.0.1:18767/client/hosted.py -o tabletop8_agent.py
curl --fail http://127.0.0.1:18767/client/prompt.txt -o prompt.txt
printf '平台访问密钥: '
read -r -s TABLETOP8_KEY
export TABLETOP8_KEY
```

也可由团队自己的密钥管理方式设置环境变量。平台密钥由维护者单独提供，不是SSH密码。仅在团队内部分享。

先检查服务和任务列表，不调用模型、不创建任务：

```bash
python3 tabletop8_agent.py --check
```

配置支持图片输入的Chat Completions兼容模型端点，例如服务商提供的 `/v1` 根地址，然后运行：

```bash
export VLM_BASE_URL='https://你的模型服务/v1'
export VLM_MODEL='你的视觉模型名称'
export VLM_API_KEY='你的模型API密钥'
python3 tabletop8_agent.py --task F44 --variant A --seed 7 --max-calls 100
```

选择其他任务时替换task；版本为A/B/C。示范固定seed0，执行seed必须大于0。不要同时启动多个任务；本服务一次运行一个世界。达到调用上限或模型请求失败后暂停，使用打印出的 `--session SESSION_ID` 接续，或在控制台结束任务。不会自动重试付费请求。

客户端每次发送12张按时间均匀采样的示范图、当前三路相机、动作说明与最近8次决策。完整示范MP4仍可通过 `/demo` 下载；此客户端是采样帧输入，不宣称给模型传了完整视频。模型凭据只用于客户端到模型提供商的调用，不上传仿真服务器。请求和动作历史保存在客户端脚本旁 `runs/hosted/`。

**3. 可选控制面板：**

浏览器打开 <http://127.0.0.1:18767/>，输入平台密钥并连接。可选择八题与A/B/C、观看完整示范、创建手动调试任务、输入移动距离、查看三路相机、结束任务。HTTP客户端已经创建任务时，点击“刷新／接入当前任务”查看同一世界。运行agent时只观察；并行手动动作会令agent的旧观察失效。

## 动作距离已可输入

每次动作支持任意 `step_mm` 数值，范围 **0.5–50毫米**，例如1.2、7.5、30，不再固定20毫米。左右臂共享本次距离，各自选择方向。`rotation_deg` 为0.5–20度。

```json
{
  "left": "UP",
  "right": "STILL",
  "step_mm": 7.5,
  "rotation_deg": 3,
  "expected_observation": 0
}
```

这是末端控制目标的增量；接触、控制误差与可达空间会影响实际位移。每次动作推进0.4秒。未填写距离时普通平移20毫米，`_FINE`平移2毫米；显式数值覆盖这两类默认值。旋转默认10度，`_FINE`默认1度。GRASP/RELEASE保持夹爪命令，不提供抓取成功真值。两臂动作同时执行。

## 接入自己的agent

维护者带 `Authorization: Bearer PLATFORM_KEY` 调用：

- `GET /control/tasks`：八题列表。
- `POST /control/sessions`：`{"task":"F44","variant":"A","seed":7,"trial_kind":"agent"}`，返回session和actor_url。
- `GET /control/status`：接入当前任务。
- `GET /control/results/{session}`：结束后的私有判定，主指标success。
- `GET /control/execution/{session}`：结束后的执行MP4。

把 `actor_url` 交给参测agent。actor无需平台密钥，只持有随机session地址：

- `GET /actor/{session}/observe`：三路JPEG base64、observation_id、通用委托、动作字母表和剩余预算。
- `GET /actor/{session}/demo`：同规则完整MP4。
- `GET /actor/{session}/demo-frames`：12张时间采样JPEG base64。
- `POST /actor/{session}/action`：上面的JSON。expected_observation必须等于最近观察ID，重复旧请求返回409，不重复执行。
- `POST /actor/{session}/submit`：结束、稳定检查并保存执行视频。不给actor返回成功真值。

session地址是本局的访问凭据，不开放管理目录或源码。参测agent不应持有平台密钥；有选择版本需求的外层客户端负责创建任务，模型输入不含版本标签、规则文字、目标坐标或即时评分。每局最多1600次动作，默认30分钟；管理员可创建时设置wall_seconds，最大两小时。

## 场景与历史示范的一致性

八题来自七份历史冻结源码。`release.private.json` 固定归档、视频、源码与场景指纹；启动前校验24段视频和解码证据，运行时按题加载对应冻结场景与判定。未修改冻结文件，也未把历史录像改标为新源码录像。

唯一执行扩展是 `motion.py` 的可变步长原语。测试逐个比较七份历史控制器的默认动作输出，保持20毫米／2毫米和10度／1度旧行为；场景、目标、抓取物理与接触事件仍使用冻结版本。新增步长适配器指纹单独写入每局私有清单。本交付是按题固定版本的八题集合，不是全50题统一源码验收。

服务端保存位置：`/home/qingle/services/videoicl-tabletop8/service-data/episodes/`，每局含初终态、execution.mp4、动作JSONL、运行清单和私有成功判定。断电或进程被强杀可能使正在写的视频不完整；正常提交会封装视频。

## 维护者重新部署

在仓库根目录打包：

```bash
python3 -m simulator.delivery8.package --output simulator/delivery8/runs/tabletop8-v1.tar.gz
scp simulator/delivery8/runs/tabletop8-v1.tar.gz qingle@134.175.168.162:/home/qingle/services/tabletop8-v1.tar.gz
```

服务器将包解压到新目录，复用已安装的robosuite1.5.1、MuJoCo3.2.6与OSMesa Python环境，从解压根目录执行：

```bash
MUJOCO_GL=osmesa PYOPENGL_PLATFORM=osmesa \
  bash simulator/delivery8/deploy.sh
systemctl --user status videoicl-tabletop8.service
curl --fail http://127.0.0.1:18664/health
```

部署脚本先完整解码24段示范生成12帧输入，再创建独立systemd用户服务。密钥首次生成到 `/home/qingle/services/videoicl-tabletop8/service-data/platform.key`，权限0600。更新部署保留同一数据根目录与密钥。归档仅含 `simulator/`，附bundle-manifest.json用于逐文件SHA256核对。旧18660/18661/18662与web/OS服务均使用独立端口。

验证记录见 [VALIDATION.md](VALIDATION.md)。物理作者演示、接口验收和独立模型成功率是不同证据；本交付不把协议检查当作agent任务成功率。
