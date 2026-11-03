> 模型资产、纹理和视频位于 Hugging Face 数据集。先在仓库根目录运行 `python fetch_assets.py` 下载，原路径会自动恢复。

# 全部50题现有代码、资产与示范快照

按用户“先全部上传，不做验收”的要求，原样汇集当前50题运行代码、配置、仿真模型/纹理、原始real/sim示范和已生成的加速sim。

本目录是源码与资源快照，未启动仿真或模型验收。新版任务正在修改的状态也保留；不要把“已上传”理解为50题全部验收通过。

- `runtime/`：当前运行源码、机器人、推理替换对象及新版任务规格。
- `asset_roots/`：完整现有源物体、机械结构、纹理依赖，按原环境变量名称分目录。
- `media/real` / `sim-original` / `sim-speedmatched`：已有示范，缺失原片不补造。
- `tasks-original/` / `tasks-qa-export/`：已有任务导出，保留原host路径便于追溯；在其他机器运行时应按本机根目录改路径。
- `evaluator/`：公开题库和仅控制侧使用的答案，勿提供给模型。

**最初UR5十题的可移植独立包和启动命令位于 [g2-ur5-v1](../g2-ur5-v1/README.md)**，其中资源和路径已整理。其E09/E20仍为旧版局部任务。

其他题的仿真安装沿用 Isaac Sim5.0/对应IsaacLab；设置`VIC_FULL50_RIGID_ASSETS`、`VIC_MECHANISM_ASSETS`等为本目录`asset_roots/`下同名路径，`VIC_INFERENCE_ASSETS`指向`runtime/inference-generalization-v1/assets/`。不包含原账号、API密钥、GPU进程或私有会话日志。
