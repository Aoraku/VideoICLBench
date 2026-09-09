# 逐题应用与评测索引

任务 1–75 使用应用 benchmark 模式，共 225 个规则版本。任务 76–100 的系统执行与采集适配暂缓。

每题通过 `POST /v1/tasks/{task_id}/eval` 接收 `run_id`。管理服务封存该运行，按固定版本检查完整业务结果与过程约束；非目标状态必须保持一致。模型凭证只允许截图与键鼠输入。

契约链接提供初始化参数、种子划分、读取字段、过程约束、请求结构与返回字段。规则中的指定词、阈值、联系人等参数以该运行的任务资料为准。

## 软件与游戏

| 题号／契约 | 应用 | 任务 | A | B | C | 判分读取字段 |
|---|---|---|---|---|---|---|
| [001](../tasks/contracts/001.json) | chat | 通讯 A：发送一条指定文本 | 首字母小写、其余大写 | 首字母大写、其余小写 | 每个单词首字母大写 | `messages.recipient`、`messages.body` |
| [002](../tasks/contracts/002.json) | chat | 通讯 A：修改联系人昵称 | 去掉所有空格 | 空格改为下划线 | 全部转为小写 | `objects.nickname` |
| [003](../tasks/contracts/003.json) | chat | 通讯 A：编辑并发送模板消息 | 句末加“.” | 句末加“!” | 句末加“?” | `messages.body` |
| [004](../tasks/contracts/004.json) | chat | 通讯 A：把草稿转换为指定格式后发送 | 数字前加“#” | 数字后加“号” | 数字改写为英文单词 | `messages.body` |
| [005](../tasks/contracts/005.json) | chat | 通讯 A：给收到的消息打标签 | 含问号归蓝色 | 含问号归红色 | 含问号归绿色 | `objects.label` |
| [006](../tasks/contracts/006.json) | chat | 通讯 A：整理联系人分组 | 名字长度为偶数归“甲” | 长度为奇数归“甲” | 名字含元音归“甲” | `objects.label` |
| [007](../tasks/contracts/007.json) | chat | 通讯 A：标记会话优先级 | 未读数最多为高优先级 | 未读数最少为高优先级 | 最近消息最新为高优先级 | `objects.label` |
| [008](../tasks/contracts/008.json) | chat | 通讯 A：给群聊添加状态标签 | 成员数大于 5 为大型 | 成员数不大于 5 为大型 | 群名含数字为大型 | `objects.label` |
| [009](../tasks/contracts/009.json) | chat | 通讯 A：从联系人中选收件人 | 选择姓氏最早者 | 选择最近联系者 | 选择未读消息最多者 | `settings` |
| [010](../tasks/contracts/010.json) | chat | 通讯 A：从搜索结果打开目标会话 | 选结果第一项 | 选结果最后一项 | 选未读数最多一项 | `settings` |
| [011](../tasks/contracts/011.json) | chat | 通讯 A：从附件列表选择文件发送 | 选体积最小者 | 选体积最大者 | 选名称最短者 | `messages.attachment` |
| [012](../tasks/contracts/012.json) | chat | 通讯 A：整理会话列表顺序 | 按未读数降序 | 按最近消息升序 | 按会话名反向字母序 | `orders.main` |
| [013](../tasks/contracts/013.json) | chat | 通讯 A：处理一组待办消息 | 含“紧急”的消息转发给联系人甲 | 含“紧急”的消息收藏 | 含“紧急”的消息归档 | `objects`、`messages`、`collections`、`artifacts` |
| [014](../tasks/contracts/014.json) | chat | 通讯 A：清理会话状态 | 已读会话全部归档 | 未读会话全部置顶 | 超过 3 天的会话全部静音 | `objects`、`messages`、`collections`、`artifacts` |
| [015](../tasks/contracts/015.json) | im | 通讯 B：创建群聊并邀请成员 | 邀请名字最短的 3 人 | 邀请最近联系的 3 人 | 邀请未读数最高的 3 人 | `memberships` |
| [016](../tasks/contracts/016.json) | im | 通讯 B：处理消息回执 | 看到“收到”就标记已读 | 看到“收到”就添加星标 | 看到“收到”就回复固定文本 | `objects`、`messages`、`collections`、`artifacts` |
| [017](../tasks/contracts/017.json) | music | 音乐：修改歌曲显示名称 | 标题全部大写 | 标题全部小写 | 只大写最后一个字母 | `objects.display_name` |
| [018](../tasks/contracts/018.json) | music | 音乐：生成播放列表名称 | 歌手名在前 | 歌曲数量在前 | 日期在前 | `objects.name` |
| [019](../tasks/contracts/019.json) | news | 新闻：规范化文章标题 | 删除标点 | 保留标点并加句号 | 在标题前加来源简称 | `objects.title` |
| [020](../tasks/contracts/020.json) | news | 新闻：修改文章标签文本 | 标签之间用“/” | 标签之间用“\|” | 标签之间用“,” | `objects.tags_text` |
| [021](../tasks/contracts/021.json) | media | 视频：修改收藏夹名称 | 名称首尾加方括号 | 名称首尾加圆括号 | 名称首尾加书名号 | `objects.name` |
| [022](../tasks/contracts/022.json) | music | 音乐：给歌曲按属性分类 | 时长超过 4 分钟为“长” | 时长不超过 4 分钟为“长” | 播放量超过阈值为“长” | `objects.label` |
| [023](../tasks/contracts/023.json) | news | 新闻：给文章标注内容类别 | 标题含数字为“数据” | 标题不含数字为“数据” | 来源为指定媒体为“数据” | `objects.label` |
| [024](../tasks/contracts/024.json) | news | 新闻：给文章标注来源类型 | 来源名以元音开头为“甲” | 以辅音开头为“甲” | 来源名长度超过 5 为“甲” | `objects.label` |
| [025](../tasks/contracts/025.json) | media | 视频：给视频标注时长类别 | 短于 10 分钟为“短” | 不短于 10 分钟为“短” | 时长为偶数分钟为“短” | `objects.label` |
| [026](../tasks/contracts/026.json) | media | 信息流：给内容标注推荐等级 | 评分最高的两项为“推荐” | 评分最低的两项为“推荐” | 评论数最多的两项为“推荐” | `objects.label` |
| [027](../tasks/contracts/027.json) | music | 音乐：从搜索结果选择歌曲 | 选评分最高者 | 选播放量最低者 | 选标题最短者 | `settings` |
| [028](../tasks/contracts/028.json) | music | 音乐：整理播放列表顺序 | 按发行年份升序 | 按时长降序 | 按歌手名反向排序 | `orders.main` |
| [029](../tasks/contracts/029.json) | news | 新闻：从列表选择文章阅读 | 选发布时间最新者 | 选发布时间最早者 | 选标题最长者 | `settings` |
| [030](../tasks/contracts/030.json) | news | 新闻：筛选需要阅读的文章 | 保留标签数最多的文章 | 保留标签数最少的文章 | 保留评论数为偶数的文章 | `collections.reading_list` |
| [031](../tasks/contracts/031.json) | media | 视频：从推荐列表选择视频 | 选观看时长最短者 | 选点赞率最高者 | 选发布时间最早者 | `settings` |
| [032](../tasks/contracts/032.json) | music | 音乐：把歌曲加入播放列表 | 评分高于阈值的歌曲加入列表甲 | 评分低于阈值的歌曲加入列表甲 | 时长为偶数的歌曲加入列表甲 | `collections.list-a` |
| [033](../tasks/contracts/033.json) | news | 新闻：批量处理文章状态 | 标题含指定词的文章标记已读 | 标题含指定词的文章收藏 | 标题含指定词的文章隐藏 | `objects`、`messages`、`collections`、`artifacts` |
| [034](../tasks/contracts/034.json) | media | 视频：处理观看列表 | 播放完成的视频移入历史 | 播放完成的视频移入收藏 | 播放完成的视频从列表删除 | `collections.watchlist`、`collections.history`、`collections.favorites` |
| [035](../tasks/contracts/035.json) | media | 视频：调整播放队列 | 每个短视频后插入一个长视频 | 每个长视频后插入一个短视频 | 按指定标签交替插入 | `orders.main` |
| [036](../tasks/contracts/036.json) | blog | 博客：编辑文章标题后保存 | 标题首字母大写 | 标题末字母大写 | 标题中每个数字加括号 | `objects.title` |
| [037](../tasks/contracts/037.json) | studio | AI 工作台：整理输入提示词 | 每条要求前加“-” | 每条要求前加序号 | 每条要求后加分号 | `objects.prompt` |
| [038](../tasks/contracts/038.json) | blog | 博客：给文章添加类别 | 字数超过阈值为“长文” | 字数不超过阈值为“长文” | 标题含问号为“长文” | `objects.label` |
| [039](../tasks/contracts/039.json) | studio | AI 工作台：给生成结果打标签 | 包含数字为“事实” | 不包含数字为“事实” | 包含引用符号为“事实” | `objects.label` |
| [040](../tasks/contracts/040.json) | blog | 博客：从草稿中选择文章发布 | 选择更新时间最新者 | 选择更新时间最早者 | 选择字数最少者 | `objects.published`、`artifacts` |
| [041](../tasks/contracts/041.json) | studio | AI 工作台：选择生成模型 | 选择上下文窗口最大的模型 | 选择价格最低的模型 | 选择名称最短的模型 | `settings.model` |
| [042](../tasks/contracts/042.json) | blog | 博客：发布满足条件的文章 | 带有两个以上标签的文章发布 | 没有标签的文章发布 | 标题含指定字符的文章发布 | `objects`、`messages`、`collections`、`artifacts` |
| [043](../tasks/contracts/043.json) | studio | AI 工作台：处理生成结果 | 结果通过检查后保存 | 结果通过检查后复制 | 结果通过检查后提交给指定联系人 | `checks`、`artifacts`、`messages`、`browser.clipboard` |
| [044](../tasks/contracts/044.json) | travel | 旅游：填写乘客信息 | 姓名姓与名之间加空格 | 姓名姓与名之间加连字符 | 姓名全部大写 | `objects.full_name` |
| [045](../tasks/contracts/045.json) | shop | 购物：填写商品备注 | 数量写在商品名前 | 数量写在商品名后 | 数量改为中文数字 | `objects.note` |
| [046](../tasks/contracts/046.json) | bank | 银行：填写转账备注 | 账号只保留后四位 | 账号只保留前四位 | 账号中间部分替换为星号 | `objects.note` |
| [047](../tasks/contracts/047.json) | travel | 旅游：给出行方案分类 | 耗时最短为“快” | 价格最低为“快” | 换乘最少为“快” | `objects.label` |
| [048](../tasks/contracts/048.json) | shop | 购物：给商品分类 | 评分不低于阈值为“优选” | 销量不低于阈值为“优选” | 评论数为偶数为“优选” | `objects.label` |
| [049](../tasks/contracts/049.json) | bank | 银行：给交易标注类型 | 金额为偶数为“常规” | 金额为奇数为“常规” | 备注长度超过阈值为“常规” | `objects.label` |
| [050](../tasks/contracts/050.json) | bank | 银行：给账户标注风险等级 | 余额最高的账户为“重点” | 余额最低的账户为“重点” | 最近交易最多的账户为“重点” | `objects.label` |
| [051](../tasks/contracts/051.json) | travel | 旅游：从路线列表选择方案 | 选价格最低者 | 选总时长最短者 | 选出发时间最晚者 | `settings` |
| [052](../tasks/contracts/052.json) | shop | 购物：从商品列表选择商品 | 选评分最高者 | 选价格最高者 | 选库存最少者 | `settings` |
| [053](../tasks/contracts/053.json) | bank | 银行：从交易列表选择记录 | 选金额最大者 | 选金额最小者 | 选日期最早者 | `settings` |
| [054](../tasks/contracts/054.json) | travel | 旅游：确认预订 | 价格低于阈值的方案确认 | 价格高于阈值的方案确认 | 换乘次数为偶数的方案确认 | `artifacts.booking` |
| [055](../tasks/contracts/055.json) | shop | 购物：处理购物车 | 带有指定标签的商品加入购物车 | 带有指定标签的商品移出购物车 | 带有指定标签的商品加入收藏 | `collections.cart`、`collections.favorites` |
| [056](../tasks/contracts/056.json) | bank | 银行：执行转账 | 收款人姓名含指定字母时转账 | 账号末位为偶数时转账 | 金额低于阈值时转账 | `ledger`、`balances` |
| [057](../tasks/contracts/057.json) | bank | 银行：设置账户提醒 | 余额低于阈值时开启提醒 | 余额高于阈值时开启提醒 | 连续两笔交易同日时开启提醒 | `objects.reminder` |
| [058](../tasks/contracts/058.json) | code | OJ：按规则整理代码后提交 | 缩进使用 2 个空格 | 缩进使用 4 个空格 | 缩进使用制表符 | `objects.code`、`artifacts.submission` |
| [059](../tasks/contracts/059.json) | code | OJ：规范化答案文本 | 每行末尾加分号 | 每行开头加序号 | 所有空格替换为下划线 | `objects.text` |
| [060](../tasks/contracts/060.json) | code | OJ：修改代码变量名 | 变量名统一加前缀 `x_` | 统一加后缀 `_v` | 统一转为大写 | `objects.code`、`AST.bindings` |
| [061](../tasks/contracts/061.json) | code | OJ：给提交结果标注类别 | 通过全部测试为“绿” | 存在运行错误为“绿” | 运行时间最低为“绿” | `objects.label` |
| [062](../tasks/contracts/062.json) | code | OJ：给题目标注难度 | 样例数最多为“难” | 样例数最少为“难” | 题目编号为偶数为“难” | `objects.label` |
| [063](../tasks/contracts/063.json) | code | OJ：从题库选择题目 | 选择编号最小者 | 选择通过率最高者 | 选择标题最长者 | `settings` |
| [064](../tasks/contracts/064.json) | code | OJ：从提交记录选择待检查结果 | 选择最新提交 | 选择最早提交 | 选择代码行数最多的提交 | `settings` |
| [065](../tasks/contracts/065.json) | code | OJ：提交满足条件的代码 | 代码通过本地检查后提交 | 代码包含指定函数名后提交 | 代码长度低于阈值后提交 | `checks`、`artifacts.submission` |
| [066](../tasks/contracts/066.json) | gomoku | 五子棋：识别并点击目标落子点 | 能形成四连的位置标蓝 | 能形成三连的位置标蓝 | 能堵住对手四连的位置标蓝 | `board`、`moves`、`marks`、`selection`、`stopped`、`events` |
| [067](../tasks/contracts/067.json) | gomoku | 五子棋：从候选点选择落子 | 选择横向相邻棋子最多的位置 | 选择纵向相邻棋子最多的位置 | 选择距离中心最近的位置 | `board`、`moves`、`marks`、`selection`、`stopped`、`events` |
| [068](../tasks/contracts/068.json) | games | 2048：选择下一步移动方向 | 优先选择可合并方块最多的方向 | 选择本步合并得分最高的方向 | 优先选择最高方块保持在角落的方向 | `board`、`moves`、`marks`、`selection`、`stopped`、`events` |
| [069](../tasks/contracts/069.json) | games | 2048：执行一组移动 | 出现目标数字后立即停止 | 达到指定分数后停止 | 棋盘无空格后停止 | `board`、`moves`、`marks`、`selection`、`stopped`、`events` |
| [070](../tasks/contracts/070.json) | games | 数独：识别需要填写的格子 | 候选集全部为偶数的格子标记 | 候选集全部为奇数的格子标记 | 候选数字数量最少的格子标记 | `board`、`moves`、`marks`、`selection`、`stopped`、`events` |
| [071](../tasks/contracts/071.json) | games | 数独：按视频规则填写数字 | 填入候选数字中最小者 | 填入候选数字中最大者 | 填入与所在行首数字同奇偶性的数字 | `board`、`moves`、`marks`、`selection`、`stopped`、`events` |
| [072](../tasks/contracts/072.json) | games | 扫雷：从候选格中选择安全格 | 选择周围已揭示线索数字之和最小的安全候选格 | 选择周围未开格最多的格子 | 选择距离左上角最近的格子 | `board`、`moves`、`marks`、`selection`、`stopped`、`events` |
| [073](../tasks/contracts/073.json) | games | 扫雷：执行标记操作 | 数字为 1 的格子插旗 | 数字为 2 的格子插旗 | 边界格子插旗 | `board`、`moves`、`marks`、`selection`、`stopped`、`events` |
| [074](../tasks/contracts/074.json) | games | 黑白棋：选择落子位置 | 选择可翻转棋子最多的位置 | 选择靠近角落的位置 | 选择可翻转棋子最少的位置 | `board`、`moves`、`marks`、`selection`、`stopped`、`events` |
| [075](../tasks/contracts/075.json) | games | 黑白棋：完成一轮操作 | 翻转后己方棋子数更多时落子 | 选择落子后对手合法落点最少的位置 | 翻转后占据边缘时落子 | `board`、`moves`、`marks`、`selection`、`stopped`、`events` |

## 系统任务：执行适配暂缓

| 题号／契约 | 应用 | 任务 | A | B | C | 判分读取字段 |
|---|---|---|---|---|---|---|
| [076](../tasks/contracts/076.json) | windows | Windows 文件管理：批量重命名文件 | 文件名前加日期 | 文件名后加日期 | 扩展名前加日期 | `files.name` |
| [077](../tasks/contracts/077.json) | windows | Windows 文本工具：批量替换文本 | 所有逗号替换为空格 | 所有逗号替换为分号 | 所有逗号替换为换行 | `files.text` |
| [078](../tasks/contracts/078.json) | windows | Windows 文件管理：把文件归入文件夹 | 扩展名为图片归“甲” | 扩展名为文档归“甲” | 文件名含数字归“甲” | `files.parent` |
| [079](../tasks/contracts/079.json) | windows | Windows 文件管理：选择要处理的文件 | 选择体积最大的文件 | 选择修改最早的文件 | 选择名称最短的文件 | `selection.file` |
| [080](../tasks/contracts/080.json) | windows | Windows 文件管理：转换并保存路径文本 | 路径分隔符改为 `/` | 路径分隔符改为 `\\` | 路径中的空格改为下划线 | `artifacts.path_text` |
| [081](../tasks/contracts/081.json) | windows | Windows 文件管理：生成备份文件名 | 备份名加前缀 `bak_` | 备份名加后缀 `_copy` | 备份名加入当天日期 | `files.backup_name` |
| [082](../tasks/contracts/082.json) | windows | Windows 文档应用：修改窗口或文档标题 | 标题全部大写 | 标题全部小写 | 标题首尾加方括号 | `documents.title` |
| [083](../tasks/contracts/083.json) | windows | Windows 任务管理器：给进程分类 | 内存占用最高的进程为“重点” | CPU 占用最高的进程为“重点” | 名称最长的进程为“重点” | `annotations.process` |
| [084](../tasks/contracts/084.json) | windows | Windows 桌面：选择要打开的应用 | 选择启动最快的应用 | 选择名称最短的应用 | 选择最近使用的应用 | `processes.started` |
| [085](../tasks/contracts/085.json) | windows | Windows 窗口管理：整理窗口状态 | 标题含指定词的窗口最大化 | 标题含指定词的窗口最小化 | 标题含指定词的窗口关闭 | `windows.state` |
| [086](../tasks/contracts/086.json) | windows | Windows 设置：修改日期时间显示 | 日期使用年-月-日 | 日期使用日/月/年 | 日期使用月.日.年 | `settings.short_date` |
| [087](../tasks/contracts/087.json) | windows | Windows 网络设置：给网络分类 | 名称含数字的网络为“可信” | 名称不含数字的网络为“可信” | 信号最强的网络为“可信” | `annotations.network` |
| [088](../tasks/contracts/088.json) | windows | Windows 通知设置：给通知分类 | 来自系统的通知为“重要” | 来自应用的通知为“重要” | 包含感叹号的通知为“重要” | `annotations.notification` |
| [089](../tasks/contracts/089.json) | windows | Windows 设备设置：选择目标设备 | 选择电量最高的设备 | 选择电量最低的设备 | 选择名称最长的设备 | `selection.device` |
| [090](../tasks/contracts/090.json) | windows | Windows 显示设置：改变显示状态 | 屏幕亮度低于阈值时开启夜间模式 | 亮度高于阈值时开启夜间模式 | 外接显示器存在时开启夜间模式 | `settings.night_light` |
| [091](../tasks/contracts/091.json) | android | Android 设备设置：连接目标设备 | 名称以指定字母开头的设备连接 | 信号最强的设备连接 | 电量最高的设备连接 | `devices.connected` |
| [092](../tasks/contracts/092.json) | linux | Linux 终端：格式化命令输出 | 每行前加行号 | 每行末尾加分号 | 字段之间改用制表符 | `artifacts.output_text` |
| [093](../tasks/contracts/093.json) | linux | Linux 终端：转换路径或命令文本 | 相对路径改为绝对路径 | 绝对路径改为相对路径 | 路径中的大写字母转小写 | `artifacts.path_text` |
| [094](../tasks/contracts/094.json) | linux | Linux 终端：给命令结果分类 | 返回码为 0 为“成功” | 输出包含警告词为“成功” | 输出行数为偶数为“成功” | `annotations.command` |
| [095](../tasks/contracts/095.json) | linux | Linux 终端：给进程标注状态 | 运行时间最长为“关注” | 占用内存最多为“关注” | 进程号最大的为“关注” | `annotations.process` |
| [096](../tasks/contracts/096.json) | linux | Linux 终端：选择要操作的进程 | 选择 CPU 占用最高者 | 选择内存占用最低者 | 选择进程名最短者 | `selection.process` |
| [097](../tasks/contracts/097.json) | linux | Linux 终端：选择命令作用对象 | 选择修改时间最新的文件 | 选择文件大小最小的文件 | 选择扩展名最短的文件 | `selection.file` |
| [098](../tasks/contracts/098.json) | linux | Linux 终端：执行命令序列 | 命令成功后继续下一条 | 命令失败后继续下一条 | 出现警告后暂停 | `command_events`、`execution.paused` |
| [099](../tasks/contracts/099.json) | android | Android 设置：改变系统状态 | 电量低于阈值时开启省电模式 | 电量高于阈值时开启省电模式 | 连接 Wi-Fi 时开启省电模式 | `settings.battery_saver` |
| [100](../tasks/contracts/100.json) | android | Android 应用管理：处理应用状态 | 未使用超过阈值的应用强制停止 | 占用空间最大的应用强制停止 | 名称含指定字母的应用强制停止 | `packages.stopped` |
