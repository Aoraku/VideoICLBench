# 装配本批次的物理环境

SDK 和 GUI 从同一提交的 `simulator/native-codex-20261106/VideoICLBench` 运行。单独安装 native Python，版本与已有 IsaacSim / IsaacLab 环境对齐。模型进程使用 GUI Python。组装脚本本身只用 Python 标准库。

先准备这批的物理资源。已有完整 full-v2 发布包时，直接使用其中的 `runtime/`。从原先的交付包迁移时，获取 [具身交付数据](https://huggingface.co/datasets/JJimmyL/VideoICL-Embodied-Handoff-20261103)，按原目录解包。旧分支 [embodied/full50-current](https://github.com/Aoraku/VideoICLBench/tree/codex/embodied-all-handoff-20261103/embodied/full50-current) 提供原有 runtime 代码和资源布局。新包附本批 Python 代码、执行规范、配置和物理资源 SHA256，USD、纹理、三角网格等由数据侧提供。

获取冻结的数据集版本（需要有该数据集的读取权限）：

```sh
hf download JJimmyL/VideoICL-Embodied-Handoff-20261103 --repo-type dataset \
  --revision a43cf0cf0c2f8601d7d39d9bab501f1da2e946b1 --include 'full50-current/*' --local-dir "$DATA"
export FULL50="$DATA/full50-current"
```

972 项 runtime 的来源为 559 项随 Git 发布的文件、404 项与数据集冻结清单匹配的文件、9 项从原始机构生成的铃资产。运行时还需单独配置当前主机的外部资产根及示范视频。

从本目录的上一级（`simulator/astra-iclworld-20261106`）执行。例如：

```sh
python3 deploy/build_bell_overlay.py --mechanisms "$VIC_MECHANISM_ASSETS" --output "$WORK/astra-bell"
python3 deploy/assemble_runtime.py --source "$FULL50/runtime" --source "$WORK/astra-bell" --output "$WORK/astra-runtime"
export VIC_EXECUTION_DESIGN_ASSETS="$WORK/astra-runtime/execution-design-v3/assets"
export VIC_INFERENCE_ASSETS="$WORK/astra-runtime/inference-generalization-v1/assets"
```

也可只向 `--source` 传入完整的 full-v2 runtime。输出路径须尚未创建。组装时逐文件寻找校验值匹配的副本，缺项会列出相对路径并退出；可以另加 `--source` 指向补齐的资源树。对于 E33 的精确容器判定，组装时会校验 `configs/source_geometry/e33/e33-original-bin-triangles.npz`。E26C/I 的九个铃资产可从原版机制重新生成；两个刚体仅在水平尺寸变为 1.06 倍，弹簧、行程和按压阈值沿用原版。

本批实际启动还依赖 I 和 E 的成对 binding、E 的继承基准 I、E41 短尺原始尺寸到 0.96 倍的显式适配，以及每题固定 task root、seed 和演示内容。使用本批 cases 指向的对应 binding。运行时将原生脚本的 `--runtime-root` 指向刚组装的目录。单机复现无需执行旧 RTX 故障恢复或重复提交历史任务。工程验收历史归档和 GPU 运行输出不在代码发布物中。

在打包机离线完成了 972 项 runtime 归并校验，并从原始机制生成 E26 的 9 项资源，各 SHA256 均匹配当次冻结发布物。上述验证使用了本地 full-v2 资源；未从一台空机器验证 Hugging Face 全量下载。
