"""Distinct visible materials for batch lessons, without rules or answers."""


def messages(query=False):
    if query:
        return ['收到，露营清单已整理。', '湿地参观在哪里集合?',
                '紧急：请确认航班接驳时间。', '天文馆的门票还能预约吗?',
                '收到，志愿者名单已经核对。', '音乐教室周末照常开放。']
    return [
        '紧急：请确认会议室是否可用?', '收到，设计材料已经归档。',
        '周末活动的集合地点在哪里?', '本周阅读分享安排在周五下午。',
        '紧急：请核对交付清单和负责人。', '收到，明天会提前到场。',
        '收到，新版预算需要一起打印吗?', '请把访谈提纲放到共享文件夹。',
        '紧急：演出设备需要在今晚归还。', '收到，路线图已发给志愿者。',
        '工作坊的报名截止时间是几点?', '摄影展的海报已经送到前台。',
        '紧急：临时入口应当设在哪一侧?', '收到，投影仪已完成调试。',
        '图书角可以借用折叠桌吗?', '周二的植物观察笔记已整理。',
        '紧急：请补充车站接送的联系人。', '收到，需要我再联系场地管理员吗?',
        '短片放映结束后可以留场讨论吗?', '请为社区调查预留一些空白问卷。',
        '紧急：户外活动遇雨需要改期吗?', '收到，安全检查记录已经保存。',
        '这一版纪要是否还需要补充附件?', '下次读书会将讨论旅行随笔。',
    ]


def generated_passages(query=False):
    if query:
        return ['露营课程共有 8 名学员。', '老师说：“请检查帐篷。”',
                '观察记录写道：“发现了 6 种植物。”', '节目单见 [演出安排]。',
                '运动课程在周末举行。', '3 位受访者推荐了这条路线。']
    return [
        '调查覆盖了 3 个街区。', '居民说：“这里适合散步。”',
        '共有 12 位居民提到“夜间开放”。', '街角的公共空间正在修缮。',
        '材料索引见 [设计文档]。', '访谈记录已按主题归档。',
        '活动安排在 7 月举行。', '设计师说：“入口需要更宽。”',
        '“新增了 5 张长椅”，管理员这样介绍。', '花园里的树木已经修剪。',
        '会议纪要收录在 [讨论记录] 中。', '志愿者正在准备路线图。',
        '图书馆新增 24 个阅读座位。', '导览员提醒：“请沿标线行走。”',
        '报告指出：“有 18 人选择了步行。”', '影像资料展示了街道的季节变化。',
        '照片的说明参见 [场地照片]。', '请在采访前检查录音设备。',
        '工作坊收到 9 份报名表。', '组织者说：“欢迎带朋友参加。”',
        '通讯写道：“本次交流持续了 2 小时。”', '读书会将继续征集推荐书目。',
        '补充信息列在 [参考资料]。', '新的指示牌使用了更大的字体。',
    ]


def article_titles(query=False):
    if query:
        return ['Maya 的花园笔记', 'Ruth 的书评', 'Camera 入门记录',
                'Python 学习笔记', '烘焙日记', '露营随笔']
    return [
        'Anna 的旅行手记', 'Canva 排版练习', 'Atlas 项目观察', 'Camera 镜头笔记',
        'Maya 的阳台花园', 'Sora 的音乐周末', 'Oscar 的访谈记录', 'Daniel 的跑步日记',
        'Bryn 的工作笔记', 'Notion 读书清单', 'Python 异步编程入门', 'Rust 编程练习',
        'Ruby 语法札记', 'Word 文档排版技巧',
        'Linux 终端日常', 'Eric 的摄影路线',
        '城市散步地图', '每周写作记录', '秋日登山随笔', '厨房里的新尝试',
        '朋友推荐的书', '整理旧相册', '海边小城旅行', '公交车窗外的风景',
    ]


def account_names(query=False):
    names = (['Maya', 'Ruth', 'Oscar', 'Will', '方宁', '江夏'] if query else [
        'Anna', 'Daniel', 'Maya', 'Oscar', 'Lara', 'Sam', 'Nora', 'Grace',
        'Bryn', 'Chloe', 'Ruth', 'Will', 'Eric', 'Iris', 'Owen', 'Yuki',
        '林若宁', '陈子安', '方宁', '江夏', '李可', '张宁', '苏晴', '何予安'])
    purposes = ['储蓄', '房租', '旅行', '学习', '日常', '备用']
    return [f'{name} · {purposes[i % len(purposes)]}账户' for i, name in enumerate(names)]


def transaction_notes(query=False):
    if query:
        return ['营地租借费用', '音乐课程报名费', '采购户外用品及露营材料费结算',
                '购买户外用品及露营材料费用结算', '购买户外用品和露营材料费用已结算',
                '共同承担本次社区音乐活动和演出场地的租赁费用']
    return [
        '午餐结算', '地铁出行费用', '采购办公用品及打印材料费结算',
        '购买办公用品及打印材料费用结算', '购买办公用品和打印材料费用已结算',
        '共同承担本月水电宽带及公共区域清洁费用',
        '早餐费用', '周末车票', '采购园艺用品及种植材料费结算',
        '购买园艺用品及种植材料费用结算', '购买园艺用品和种植材料费用已结算',
        '联合支付本次社区活动场地租赁与音响设备费用',
        '咖啡结算', '图书采购费用', '采购烘焙用品及包装材料费结算',
        '购买烘焙用品及包装材料费用结算', '购买烘焙用品和包装材料费用已结算',
        '报销上周志愿者出行和调查材料复印的相关开支',
        '晚餐分摊', '电影票费用', '采购摄影用品及布景材料费结算',
        '购买摄影用品及布景材料费用结算', '购买摄影用品和布景材料费用已结算',
        '共同支付读书会茶点采购及活动资料印制费用',
    ]


def code_snippets(seed):
    # A single-digit literal preserves 24/25/26-character boundary examples.
    value = 2 + seed % 7
    if seed >= 1000:
        return [f'if x>{value}\n print(x)', f'print({value} ** 2)',
                f'def solve(x): return x*{value}', f'def solve(x):\n return x-{value}',
                f'def other(x):\n return x//{value}', f'values = [{value}, 8, 9\nprint(values)']
    return [
        f'print({value})', f'print({value} + 1)', f'total={value}\nprint(total)',
        f'print(sum([{value}, 8]))', f'def solve(): return {value}',
        f'def solve(x):return x+{value}', f'def solve(x): return x+{value}',
        f'def solve(x):\n return x+{value}', f'def solve(x):\n return x**{value}',
        f'def solve(data):\n    return sum(data) + {value}',
        f'def solve(data):\n    return max(data) - {value}',
        f'def solve(x)\n    return x + {value}',
        f'def other():return {value}', f'def total(x):return x+{value}',
        f'def other(x):\n return x+{value}', f'answer = {value}\nprint(answer)',
        f'values = [{value}, 8, 9]\nfor item in values:\n    print(item * 2)',
        f'count = {value}\nif count > 0:\n    print(count)',
        f'print({value}', f'total = \nprint({value})',
        f'def other(x)\n    return x + {value}',
        f'for item in range({value})\n    print(item)',
        f'if {value} > 0\n print({value})', f'values = [{value}, 8, 9\nprint(sum(values))',
    ]
