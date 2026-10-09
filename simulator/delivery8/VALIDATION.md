# 八题交付验收

2026-10-10，Agentlab，robosuite1.5.1 / MuJoCo3.2.6 / Linux OSMesa。

- 8题×A/B/C，共24段成功作者示范：校验视频SHA256、冻结源码指纹、同规则成功终态与解码证据；部署时重新完整解码，生成每段12张按时间采样的输入图。
- Mac和Agentlab各18项测试通过：七个历史控制器的默认动作逐项相同，可变小数步长正确进入控制指令，越界／NaN／布尔值／字符串拒绝，旧观察重复请求不再执行，管理密钥与actor输入隔离。
- 实际HTTP服务24/24条件通过：创建seed7执行实例、正确A/B/C示范、三路相机、7.5毫米动作、过期观察409、非法距离422、提交后410、执行MP4与私有日志保存。八题各自的A/B/C执行世界指纹相同。
- Hosted客户端与本地模拟模型端点跑通两轮：每轮12张示范图加3张当前相机，第一轮提交3.5毫米动作，第二轮结束。该检查是传输验收，不是独立模型任务成绩。
- 实际Chromium面板检查：连接平台、列出8题、选择F44-C、显示640×480观察、输入7.5毫米、执行一次、提交并保存。截图见 [控制面板](validation/dashboard.png)。

自由空间中的实际末端Z位移：

| 请求距离 | 实测位移 | 绝对误差 |
| --- | --- | --- |
| 0.5 mm | 0.387 mm | 0.113 mm |
| 7.5 mm | 7.039 mm | 0.461 mm |
| 25 mm | 24.131 mm | 0.869 mm |
| 50 mm | 48.603 mm | 1.397 mm |

以上是单一自由空间探针，说明参数确实改变物理控制；不保证接触或工作空间边缘同样达到请求位移。

原始证据：[HTTP24条件](validation/http-smoke-v1.json)、[末端位移](validation/motion-probe-v1.json)、[Linux18项检查](validation/unit-tests-v1.log.txt)、[Hosted与浏览器](validation/report.json)。

`protocol_smoke`和手动面板测试均单独标记，不计入agent成功率。真人录制、真实模型的完整八题成功率仍未验收。

部署：独立用户服务 `videoicl-tabletop8.service`，监听 `127.0.0.1:18664`。运行目录 `/home/qingle/services/videoicl-tabletop8/release-v1`，数据根目录 `/home/qingle/services/videoicl-tabletop8/service-data`。旧服务未切换。
