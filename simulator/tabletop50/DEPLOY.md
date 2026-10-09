# 部署与查看

所有新版任务、工具、视频、测试和验收资料都位于 `simulator/`。只复制这个目录即可部署；不需要仓库外的 `scripts/`、`artifacts/` 或 `tests/`。

## 先看任务和视频

在仓库根目录运行：

```bash
python3 -m http.server 18662 --bind 127.0.0.1 --directory simulator/tabletop50
```

打开 <http://127.0.0.1:18662/>。页面列出全部50题，各有A/B/C三个位置；已有视频直接播放，没有视频的明确标为待完成。GitHub上可直接打开 [视频索引](VIDEOS.md)，逐条点击MP4；GitHub文件页不会执行HTML。

目前随仓库附51段合格历史预览，覆盖17族完整三版本。录像对应的冻结源码、解码证据和失败诊断放在 `artifacts/`。这不是最终统一源码的150段交付。

预览页面包含私有规则和验收资料，只供设计者查看。不要把预览静态服务器作为agent评测接口。

## Agentlab服务

把 `simulator/` 放到 Agentlab 的任意工作目录中，例如 `/home/qingle/services/videoicl-main/simulator`。以下命令从它的父目录执行。Linux需Python3.11和OSMesa动态库（Ubuntu包 `libosmesa6`）；已有环境可直接复用。

```bash
python3.11 -m venv simulator/.venv
simulator/.venv/bin/python -m pip install -r simulator/benchmark/requirements.txt
TABLETOP50_PYTHON="$PWD/simulator/.venv/bin/python" bash simulator/tabletop50/tools/deploy-agentlab.sh
curl --fail http://127.0.0.1:18661/health
```

部署脚本创建用户systemd服务 `videoicl-tabletop50-fpv.service`。默认监听18661，默认数据目录 `/home/qingle/services/videoicl-tabletop50-fpv-v1/service-data`；可用 `TABLETOP50_SERVICE_ROOT` 指定另一个数据根目录。管理token只保存在数据目录，不提交Git。

远程查看视频可在服务器运行上面的18662预览命令，再从电脑转发：

```bash
ssh -L 18662:127.0.0.1:18662 qingle@134.175.168.162
```

## 重新录制及安装正式示范

从包含 `simulator/` 的目录执行。Linux无头录制需要以下环境变量，macOS不要设置OSMesa变量。

```bash
export MUJOCO_GL=osmesa PYOPENGL_PLATFORM=osmesa
export OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1
python simulator/tabletop50/tools/record.py --task F01 --variant A --seed 0 --output simulator/tabletop50/runs/check-01 --record
python simulator/tabletop50/tools/audit-media.py --recordings simulator/tabletop50/runs/check-01 --output simulator/tabletop50/runs/audited-01
```

固定录制源码，运行中不要修改。每次换新输出目录保留失败证据。批量录制入口为同目录的 `batch.py`，尚无实现的任务不会伪装为普通抓放。

正式 `sim_video` 会检查示范与服务源码一致、同规则、不同推理seed和成功解码证据。将当前服务源码下录制并审计出的完整案例目录复制到 `$TABLETOP50_SERVICE_ROOT/service-data/demos/`（如 `F01-A-0/`），再通过管理接口创建会话。**打包的历史预览不能直接用作当前版本正式示范**；缺失合格示范返回409。`no_demo` 可用于接口工程检查，不代表已完成视频ICL实验。

actor仅开放 `/actor/{session}/observe`、`action`、`demo`、`submit`。完整管理接口说明见 [README](README.md)。当前运行配方50/50（含F42/F43/F46未验收原型）；尚需修复、统一录制和验收全部150条件。


## Agentlab 已部署的视频预览

2026-10-09 已部署独立预览副本 `/home/qingle/services/videoicl-tabletop50-fpv-v1/main-review-v92`，只包含 `simulator/`，随包附48段历史合格MP4与50题卡片。systemd用户服务 `videoicl-tabletop50-review.service` 监听服务器 `127.0.0.1:18662`，已通过HTTP健康检查。此入口用于维护者审阅；生产actor服务18661仍使用tools-v69，未切换到未验收原型。

在自己的电脑运行：

```bash
ssh -N -L 18663:127.0.0.1:18662 agentlab-qingle
```

然后打开 <http://127.0.0.1:18663/>。若没有SSH别名，可使用 `qingle@134.175.168.162`。本机18662已有同一仓库的视频预览，可直接查看。

预览副本对应v92冻结部署包。后续控制器试验源码独立冻结，不会在运行测试中修改该副本；视频对应各自历史冻结版本，不代表当前50族已全部验收。

该v92部署副本已通过280项Linux检查（含渲染和actor API）。测试通过不代表作者已完成50族执行验收。

预览页与媒体已增量更新至51段（新增F08三规则），对应静态文件均可读；v92执行源码指纹未变。新增F07物理验收与冻结源码也已同步，F07录像仍在独立目录录制。
