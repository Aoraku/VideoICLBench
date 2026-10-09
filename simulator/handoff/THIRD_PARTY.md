# 第三方素材与许可

本清单描述独立资源包。新增真人视频、演示帧、完整运行录像、动作日志和作者标注不随 GitHub 代码分支发布。

- `backends/robocasa/media/human_demo.mp4` 及 `demo_frames/`：EPIC-KITCHENS P05_03，University of Bristol／EPIC-KITCHENS 作者，原时间 136.2–146.3 秒；裁剪、去音频、缩放 640px、10fps，无字幕、无动作重排、无变速。原始作者标注在 `human_annotations_author_only.json`，只供作者审核，不给 Agent。
- 来源：[原视频](https://data.bris.ac.uk/datasets/3h91syskeag572hl6tvuovwv4d/videos/train/P05/P05_03.MP4)、[标注](https://github.com/epic-kitchens/epic-kitchens-100-annotations)、[数据集及版权说明](https://epic-kitchens.github.io/2025)。素材采用 [CC BY-NC 4.0](https://creativecommons.org/licenses/by-nc/4.0/)，仅非商业使用，改动如上；不暗示作者背书。
- RoboCasa [v0.2 源码](https://github.com/robocasa/robocasa/tree/v0.2) 与 robosuite 各遵循上游许可。完整外部资产和 HDF5 不包含在本仓库。旧版轨迹来源：[数据镜像](https://huggingface.co/datasets/siyuhsu/robocasa-v0.2-datasets/tree/main/v0.1/multi_stage/defrosting_food/MicrowaveThawing/2024-05-11)；兼容资产来源：[haosulab/RoboCasa](https://huggingface.co/datasets/haosulab/RoboCasa)。模型／纹理可能有独立许可，不能因项目代码许可推定所有资产同许可。
- `sim_demo.mp4` 为改造后的杯子场景物理渲染，控制来自 MicrowaveThawing demo_2，非 Agent 生成动作。环境初始化后仅 env.step，未逐帧恢复物体状态。显示在运行录像中的上述演示素材仍保留原许可。
- GUMI 前端来自 Show-Harness commit `137d5718c3b7af0150764d8f9beeb252c9f2794a`，许可保留在 `../embodied_icl/GUMI_LICENSE`。RoboCasa index.html 同源派生，适用同一许可。
- 双 Panda 使用 MuJoCo Menagerie，许可证和来源清单保留在 `../simulation_b01/assets/franka_emika_panda/`。

会议纪要、私人对话、SSH 密码、API 密钥和账号配置不随包发布。作者侧规则／判分代码是开源开发资料，不是模型输入。
