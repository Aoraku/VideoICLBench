# 桌面双臂八题交付集

本批只交付以下八个任务族，每题A/B/C三规则，共24段已录制仿真作者示范。长度与难度按交付者指定标签保留，不由动作计数推算。

| ID | 任务 | 长度 | 难度 | A | B | C |
| --- | --- | --- | --- | --- | --- | --- |
| F01 | 三色积木叠放 | 短程 | 简单 | [视频](../tabletop50/artifacts/foundation-v1/F01-A-0/video.mp4) | [视频](../tabletop50/artifacts/foundation-v1/F01-B-0/video.mp4) | [视频](../tabletop50/artifacts/foundation-v1/F01-C-0/video.mp4) |
| F11 | 圆环分柱套放 | 短程 | 简单 | [视频](../tabletop50/artifacts/ring-preview-v117/F11-A-0/video.mp4) | [视频](../tabletop50/artifacts/ring-preview-v117/F11-B-0/video.mp4) | [视频](../tabletop50/artifacts/ring-preview-v117/F11-C-0/video.mp4) |
| F10 | 参照拼板变换 | 中程 | 中等 | [视频](../tabletop50/artifacts/mosaic-preview-v114/F10-A-0/video.mp4) | [视频](../tabletop50/artifacts/mosaic-preview-v114/F10-B-0/video.mp4) | [视频](../tabletop50/artifacts/mosaic-preview-v114/F10-C-0/video.mp4) |
| F08 | 形状匹配插孔 | 中程 | 中等 | [视频](../tabletop50/artifacts/shape-preview-v79/F08-A-0/video.mp4) | [视频](../tabletop50/artifacts/shape-preview-v79/F08-B-0/video.mp4) | [视频](../tabletop50/artifacts/shape-preview-v79/F08-C-0/video.mp4) |
| F22 | 双层托盘取放 | 长程 | 中等 | [视频](../tabletop50/artifacts/assembly-preview-v15/F22-A-0/video.mp4) | [视频](../tabletop50/artifacts/assembly-preview-v15/F22-B-0/video.mp4) | [视频](../tabletop50/artifacts/assembly-preview-v15/F22-C-0/video.mp4) |
| F17 | 堆叠取件与剩余结构恢复 | 长程 | 困难 | [视频](../tabletop50/artifacts/stack-recovery-preview-v79/F17-A-0/video.mp4) | [视频](../tabletop50/artifacts/stack-recovery-preview-v79/F17-B-0/video.mp4) | [视频](../tabletop50/artifacts/stack-recovery-preview-v79/F17-C-0/video.mp4) |
| F39 | 扫拢大颗粒 | 短程 | 困难 | [视频](../tabletop50/artifacts/sweep-preview-v48/F39-A-0/video.mp4) | [视频](../tabletop50/artifacts/sweep-preview-v48/F39-B-0/video.mp4) | [视频](../tabletop50/artifacts/sweep-preview-v48/F39-C-0/video.mp4) |
| F44 | 导向板送球 | 中程 | 困难 | [视频](../tabletop50/artifacts/guidance-preview-v81/F44-A-0/video.mp4) | [视频](../tabletop50/artifacts/guidance-preview-v81/F44-B-0/video.mp4) | [视频](../tabletop50/artifacts/guidance-preview-v81/F44-C-0/video.mp4) |

## F01 三色积木叠放

从视频学习颜色支撑次序；在新布局中重建

- A：红绿蓝，自下而上
- B：绿蓝红，自下而上
- C：蓝红绿，自下而上

冻结源码：[归档](../tabletop50/artifacts/foundation-source.tar.gz)。执行服务加载该归档的场景、目标与接触物理，移动距离通过独立动作适配器扩展。

## F11 圆环分柱套放

颜色到柱标记的映射；真实套入

- A：圆/三角/方柱套红绿蓝
- B：圆/三角/方柱套绿蓝红
- C：圆/三角/方柱套蓝红绿

冻结源码：[归档](../tabletop50/artifacts/reference-source-v117.tar.gz)。执行服务加载该归档的场景、目标与接触物理，移动距离通过独立动作适配器扩展。

## F10 参照拼板变换

将参照板按示范变换规则映射到空框

- A：保持相对位置
- B：顺时针旋转一格
- C：左右镜像

冻结源码：[归档](../tabletop50/artifacts/mosaic-source-v114.tar.gz)。执行服务加载该归档的场景、目标与接触物理，移动距离通过独立动作适配器扩展。

## F08 形状匹配插孔

视频决定取哪一套，形状决定插哪个孔

- A：插入红色套件
- B：插入绿色套件
- C：插入蓝色套件

冻结源码：[归档](../tabletop50/artifacts/full-source-v79.tar.gz)。执行服务加载该归档的场景、目标与接触物理，移动距离通过独立动作适配器扩展。

## F22 双层托盘取放

移开上层访问下层，更新后恢复上下层

- A：取出下层最大件
- B：取出下层中间尺寸件
- C：取出下层最小件

冻结源码：[归档](../tabletop50/artifacts/assembly-source-v15.tar.gz)。执行服务加载该归档的场景、目标与接触物理，移动距离通过独立动作适配器扩展。

## F17 堆叠取件与剩余结构恢复

目标埋在堆叠中，拆开取件后恢复剩余相对次序

- A：从底部数取第二层
- B：从底部数取第三层
- C：从底部数取第四层

冻结源码：[归档](../tabletop50/artifacts/full-source-v79.tar.gz)。执行服务加载该归档的场景、目标与接触物理，移动距离通过独立动作适配器扩展。

## F39 扫拢大颗粒

根据收集区位置组织接触方向，避免把已聚拢木球扫散

- A：扫入圆形标记区
- B：扫入三角标记区
- C：扫入方形标记区

冻结源码：[归档](../tabletop50/artifacts/sweep-source-v48.tar.gz)。执行服务加载该归档的场景、目标与接触物理，移动距离通过独立动作适配器扩展。

## F44 导向板送球

识别示范指定的盒标记，预测球的路径；配置导向板后提起挡球件，让球沿坡面滚入目标盒

- A：球进入圆形标记盒
- B：球进入三角标记盒
- C：球进入方形标记盒

冻结源码：[归档](../tabletop50/artifacts/guidance-source-v81.tar.gz)。执行服务加载该归档的场景、目标与接触物理，移动距离通过独立动作适配器扩展。

以上规则卡只供维护者选择版本；HTTP模型输入只含示范、当前相机和通用动作说明，不包含这些规则文字。
真人视频与独立模型成功率尚未验收。仿真示范是读取状态的作者控制器记录。
