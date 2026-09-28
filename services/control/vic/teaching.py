"""Deterministic, variant-blind teaching data for ordinary application workspaces.

A batch demonstration contains 24 objects; its held-out query contains six.
Single-choice and editing tasks use multiple episodes (managed separately).
No label, decision, rule, or expected output is stored in the public fixture.
"""
from copy import deepcopy
from datetime import datetime, timedelta, timezone
import ast
import random
from . import teaching_materials

FIXTURE_VERSION = 3
BATCH_TASKS = {5, 6, 8, 13, 14, 16, 22, 23, 24, 25, 32, 33, 34,
               38, 39, 42, 43, 48, 49, 54, 55, 56, 57, 65}

# Realistic independent titles: title features must not be manufactured by appending
# an object ID or by encoding a classification in a name.
NAMES = {
    'music': ['Morning Walk', 'Blue Hour', 'Summer Breeze', 'City Lights 7', 'After the Rain', 'Night Train 22', 'Paper Boats', 'Quiet Streets', 'Sunday Radio', 'Window Seat', 'Amber Sky', 'Northbound', 'Second Sunrise', 'Late Coffee', 'River Song', 'Small Hours', 'Lost Postcard', 'Home Again', 'Silver Lining', 'Green Fields', 'September Letters', 'Ocean Drive', 'Last Station', 'Distant Stars'],
    'news': ['城市图书馆延长夜间开放时间', '2026 年公共交通服务报告', '社区花园迎来收获季', '地铁 7 号线增加班次', '河岸步道完成无障碍改造', '青年设计师分享街区实践', '博物馆推出夜间导览', '3 所学校开放体育场地', '周末市集迎来手工艺人', '12 个街区开展环境调查', '社区食堂征集居民意见', '第 8 届城市读书节开幕', '老街修缮方案开始公示', '新建 5 处社区休息亭', '公交驾驶员讲述沿途故事', '步行地图收录 14 条路线', '街角书店发起旧书交换', '2 家剧院推出公益演出', '园艺志愿者举办交流会', '河流监测新增 6 个站点', '社区合唱团开启排练', '9 月文化活动指南发布', '城市夜行摄影展开放', '35 位居民参与口述历史'],
    'chat': ['Anna Wen', 'Bryn Ng', 'Chloe Lin', 'Daniel Zhu', 'Emma Han', 'Sky Ng', 'Mia Chen', 'Noah Li', 'Rhys Ng', 'Will Sun', 'Owen Lu', 'Lily He', 'Iris Gu', 'Mark Hu', 'Vera Luo', 'Lynn Ng', 'Grace Ma', 'Eric Tang', 'Rose Fang', 'Ben Su', 'Yuki Shen', 'Seth Qin', 'Amy Zhou', 'Drew Xia'],
    'im': ['林若宁', '陈子安', '许安', '欧阳晓', '周思远', '李可', '张宁', '王悦', '刘晨', '赵然', '沈一舟', '陈明远', '顾安', '苏晴', '李知夏', '周小满', '许知远', '陆洲', '唐可心', '秦朗', '宋雨', '吴书言', '程小禾', '何予安'],
    'media': ['森林清晨', '意外的访客', '森林里的冒险', '大兔子与朋友', '林间故事', '开放电影之夜', '午后追逐', '河岸来信', '穿过草地', '朋友的礼物', '树影之间', '远处的脚步', '奇妙的计划', '小路转弯处', '风中的种子', '意外的相遇', '一个晴天', '出发的早晨', '林间回声', '湖边野餐', '黄昏归途', '一起看星星', '新的邻居', '周末约定'],
    'blog': ['我的城市散步路线', '读完 7 本书之后', '在家搭建工作角', '第 2 次海边旅行', '社区花园的四季', '每周写作笔记', '街角咖啡馆日记', '山里的周末', '摄影与自然光', '厨房里的小实验', '读书会的夏天', '写给未来的信', '整理旧相册', '骑车穿过城市', '一间安静的书房', '从阳台开始种菜', '雨天的观察', '如何安排假期', '我的旅行手账', '公交车窗外', '夜间图书馆', '工作日的午餐', '陌生街道的地图', '朋友带来的礼物'],
    'studio': ['会议纪要助手', '研究摘要助手', '代码审阅助手', '旅行规划助手', '课程设计助手', '周报整理助手', '活动策划记录', '书评素材整理', '访谈转录整理', '路线比较记录', '阅读提纲', '社区调查总结', '故事梗概', '产品调研笔记', '摄影说明草稿', '课程练习草案', '邮件草稿', '预算分析笔记', '志愿活动简报', '知识库索引', '设计会议记录', '实验观察', '日程整理', '资料归档'],
    'shop': ['帆布通勤背包', '不锈钢保温杯', '便携机械键盘', '桌面阅读灯', '旅行收纳包', '无线静音鼠标', '折叠雨伞', '软木笔记本', '便携咖啡杯', '亚麻桌布', '磁吸书签', '帆布笔袋', '桌面收纳盒', '手机支架', '阅读靠垫', '便携水壶', '棉质手提袋', '无线充电座', '多口充电器', '陶瓷马克杯', '旅行眼罩', '线缆收纳袋', '简约挂钟', '防滑桌垫'],
    'bank': ['日常储蓄账户', '旅行专项账户', '家庭共同账户', '学习预算账户', '房租备用账户', '应急储蓄账户', '书籍采购账户', '休假储备账户', '运动预算账户', '交通支出账户', '文具采购账户', '摄影储蓄账户', '生活备用账户', '周末活动账户', '志愿活动账户', '家居采购账户', '植物养护账户', '年度计划账户', '医疗备用账户', '水电支出账户', '订阅服务账户', '亲友礼物账户', '维修储备账户', '长期储蓄账户'],
    'code': ['两数之和', '合并有序数组', '括号匹配', '二叉树遍历', '最短路径', '区间合并', '旋转数组', '字符串压缩', '链表反转', '岛屿数量', '矩阵搜索', '课程安排', '窗口最大值', '编辑距离', '路径总和', '环形队列', '位运算入门', '数独验证', '字母异位词', '缓存设计', '子序列匹配', '拓扑排序', '前缀树查询', '单调栈练习'],
    'travel': [f'G{n} · 北京南至上海虹桥' for n in range(101, 149, 2)],
}


QUERY_NAMES = {
    'chat': ['Rhys Ng', 'Lynn Ng', 'Alice Qiu', 'Victor Bai', 'June Wei', 'May Deng'],
    'im': ['方宁', '江夏', '陶然', '白景川', '邓嘉禾', '魏星河'],
    'news': ['天文馆延长周末参观时间', '18 条公交线路开通夜间服务', '旧车站改建为社区展厅', '4 家书店联合举办交换集市', '湿地观察活动面向居民开放', '2027 年自然教育项目启动'],
    'music': ['Open Windows', 'Autumn Lanterns', 'Across the Valley', 'First Snow', 'Orange Moon', 'Saturday Market'],
    'media': ['林间新伙伴', '湖畔的惊喜', '晨雾消散以后', '旅途中的朋友', '落叶的故事', '回到熟悉的地方'],
    'blog': ['第一次参加露营', '春天的花园计划', '我的早晨书单', '海边小城漫游', '尝试烘焙面包', '收集城市声音'],
    'studio': ['餐饮访谈整理', '露营计划草案', '植物观察总结', '演出材料整理', '城市声音记录', '运动课程提纲'],
    'shop': ['帆布通勤背包 · 秋日款', '不锈钢保温杯 · 冬季款', '便携机械键盘 · 旅行款', '桌面阅读灯 · 夜读款', '旅行收纳包 · 轻量款', '无线静音鼠标 · 随行款'],
    'bank': ['露营预算账户', '植物养护储备', '家电维修账户', '烘焙材料账户', '音乐学习账户', '公益活动账户'],
    'code': ['最长回文子串', '乘积最大子数组', '地图着色', '航班路线规划', '堆排序', '区间查询'],
    'travel': [f'D{n} · 北京南至上海虹桥' for n in (701,703,705,707,709,711)],
}


def displayed_time(rank):
    """Chronological values and visible times have the same ordering across dates."""
    base = datetime(2026, 1, 1, 8, tzinfo=timezone.utc)
    return (base + timedelta(minutes=rank * 97)).isoformat(timespec='seconds')


def enrich(id_, seed, items, source, rng):
    n = 24 if id_ in BATCH_TASKS and seed < 1000 else 6
    app = items and source['_app']
    base = items
    items = [deepcopy(base[i % len(base)]) for i in range(n)]
    pool = (QUERY_NAMES if seed >= 1000 else NAMES)[app].copy()
    rng.shuffle(pool)
    # Keep product identifiers matching the edit target and attachment filenames.
    if id_ not in (8, 11, 41, 45):
        for item, name in zip(items, pool):
            item['name'] = name
    for i, item in enumerate(items):
        item.update(id=f'item-{i + 1}', asset_index=i % 6)

    def assign(field, values):
        values = list(values)
        values = (values * ((n + len(values) - 1) // len(values)))[:n]
        rng.shuffle(values)
        for item, value in zip(items, values):
            item[field] = value

    def threshold_examples(field, threshold):
        if n == 6:
            values = [threshold // 2, threshold - 1, threshold,
                      threshold + 1, threshold * 3 // 2, threshold * 2]
        else:
            values = ([threshold - 1] + rng.sample(range(1, threshold - 1), 9)
                      + [threshold] * 4 + [threshold + 1]
                      + rng.sample(range(threshold + 2, threshold * 2 + 1), 9))
        assign(field, values)

    # Features are independently permuted, so neither row order nor another
    # column's parity is a proxy for the rule being taught.
    for field in ('timestamp', 'contact_time', 'size', 'plays', 'rating', 'comments',
                  'price', 'words', 'balance', 'transactions', 'departure', 'stock',
                  'amount', 'pass_rate', 'runtime_ms', 'context', 'like_rate', 'sales'):
        assign(field, rng.sample(range(1, 100), n))
    assign('unread', [0, 3, 0, 7, 2, 0])
    assign('members', [4, 5, 6, 3, 8, 9])
    assign('duration', [119, 240, 301, 599, 600, 721])
    if id_ in (31, 47, 51):
        # Across a lesson, a chosen minimum must exceed distractors in other
        # episodes so that a fixed value or threshold cannot explain selection.
        durations_rng = random.Random(81000 + id_ * 100000 + seed)
        minimum = [90, 450, 210, 630, 300, 150][seed % 6] + durations_rng.randrange(30)
        durations = [minimum] + [minimum + offset for offset in durations_rng.sample(range(1, 241), 5)]
        durations_rng.shuffle(durations)
        for item, duration in zip(items, durations):
            item['duration'] = duration
    assign('age_days', [0, 3, 4, 7, 1, 5])
    assign('transfers', [0, 1, 2, 3, 4, 5])
    assign('tag_count', [0, 1, 2, 3, 4, 5])
    assign('completed', [True, False])
    assign('category', ['甲', '乙'])
    assign('samples', rng.sample(range(1, 40), n))
    assign('number', rng.sample(range(100, 300), n))
    assign('verdict', ['AC', 'WA', 'RE', 'AC', 'TLE', 'RE'])
    assign('publisher', ['Echo', 'North', 'Orbit', 'Sky', 'AtlasNews', 'Daily'])
    assign('artist', ['Vela', 'Arco', 'Sora', 'Mica', 'Kite', 'Nova'])
    assign('year', rng.sample(range(1980, 2026), n))
    assign('same_day', [True, False])

    if id_ == 7:
        assign('unread', rng.sample(range(1, 90), n))
        if seed % 3 == 0:
            items[rng.randrange(n)]['unread'] = 0
    if id_ in (47, 51):
        assign('transfers', [seed % 3 + x for x in (0,1,2,3,4,5)])
    if id_ == 22:
        threshold_examples('duration', 240)
        threshold_examples('plays', 50)
    if id_ == 25:
        threshold_examples('duration', 600)
    if id_ in (32, 38, 48, 54, 56, 57):
        field = {32:'rating', 38:'words', 48:'rating', 54:'price', 56:'amount', 57:'balance'}[id_]
        threshold_examples(field, 50)
        if id_ == 48:
            threshold_examples('sales', 50)
            assign('comments', [12, 25, 46, 57, 78, 91])
    if id_ in (5, 13, 16):
        assign('text', teaching_materials.messages(seed >= 1000))
    if id_ == 8:
        groups = ['设计协作组', '产品 3 组', '研发 7 组', '周末徒步', '阅读分享组', '项目 12 组']
        for i, item in enumerate(items):
            item['name'] = groups[i % 6] + (['', ' · 东区', ' · 西区', ' · 南区'][i // 6])
    if id_ == 23:
        # Balanced title-digit classes even in a six-object held-out query.
        pool = (QUERY_NAMES if seed >= 1000 else NAMES)['news']
        digits = [x for x in pool if any(c.isdigit() for c in x)]
        plain = [x for x in pool if not any(c.isdigit() for c in x)]
        rng.shuffle(digits)
        rng.shuffle(plain)
        digit_examples = digits[:n//2]
        assign('name', digit_examples + plain[:n-len(digit_examples)])
    if id_ == 24:
        assign('publisher', ['Iris', 'Aspen', 'Upland', 'Pine', 'Brook', 'Willow'] if seed >= 1000 else [
            'Echo', 'Atlas', 'Orbit', 'Elm', 'Aria', 'Opal',
            'Aurora', 'Indigo', 'Alpine', 'Outlook', 'Avenue', 'Evergreen',
            'Sky', 'North', 'Daily', 'Cedar', 'Mica', 'Nova',
            'Beacon', 'Harbor', 'Summit', 'Lantern', 'Chronicle', 'CityPost',
        ])
    if id_ == 33:
        flags = [True, False, True, False, False, True] * (n // 6)
        rng.shuffle(flags)
        for item, urgent in zip(items, flags):
            item['name'] = ('紧急：' if urgent else '') + item['name']
    if app == 'news':
        for item in items:
            item['text'] = teaching_materials.NEWS_ARTICLES[item['name'].removeprefix('紧急：')]
    if app == 'blog':
        for item in items:
            item['text'] = teaching_materials.BLOG_POSTS[item['name']]
            if id_ == 40:
                additions = [
                    '我把其中的细节记在本子里，准备下次再做比较。',
                    '与朋友聊起这件事，才发现每个人在意的地方并不相同。',
                    '有些想法还不成熟，先留在草稿里，等过几天再回头读一遍。',
                ]
                material_rng = random.Random(f'blog:{seed}:{item["name"]}')
                item['text'] += ''.join(material_rng.sample(additions, material_rng.randrange(4)))
            item['words'] = len(item['text'])
    if id_ == 38:
        flags = [True, False] * (n // 2)
        rng.shuffle(flags)
        for item, question in zip(items, flags):
            item['name'] = item['name'].rstrip('?') + ('?' if question else '')
    if id_ == 39:
        assign('text', teaching_materials.generated_passages(seed >= 1000))
    if id_ == 42:
        assign('name', teaching_materials.article_titles(seed >= 1000))
        for item in items:
            item['text'] = teaching_materials.article_body(item['name'])
            item['words'] = len(item['text'])
    if id_ == 56:
        assign('name', teaching_materials.account_names(seed >= 1000))
    if id_ == 49:
        assign('text', teaching_materials.transaction_notes(seed >= 1000))
        assign('amount', [12, 25, 46, 57, 78, 91])
    if id_ == 41:
        models = ['Birch', 'Lumen Plus', 'Pine', 'Vale Ultra', 'Elm', 'Maple Studio', 'Fern Pro', 'Willow', 'Clover Max', 'Aspen Lite', 'Oak', 'Ivy'] if seed >= 1000 else ['Atlas', 'Orion Pro', 'Nova Lite', 'Cedar', 'Aurora Long', 'Vela', 'Aria', 'Echo Small', 'Lynx', 'Cobalt XL', 'Quartz', 'Beryl', 'Coral Lite', 'Amber Max', 'Sage', 'Indigo', 'Reed', 'Aster', 'Dahlia Pro', 'Dove', 'Finch', 'Jade', 'Iris Max', 'Tern']
        shortest = (3 if seed >= 1000 else 4) + seed % 3
        winner = rng.choice([name for name in models if len(name) == shortest])
        assign('name', [winner] + rng.sample([name for name in models if len(name) > shortest], n - 1))
    if id_ == 35:
        assign('duration', [120, 300, 599, 600, 720, 901])
    if id_ in (43, 65):
        assign('code', teaching_materials.code_snippets(seed))
    if id_ == 43:
        file_names = teaching_materials.code_file_names(seed)
        for item in items:
            item['name'] = file_names[item['code']]

    tags = ['focus', 'blue', 'weekly', 'travel', 'ideas']
    account_prefixes = rng.sample(range(1000000, 9999999), n)
    endings = list(range(6)) * (n // 6)
    rng.shuffle(endings)
    for i, item in enumerate(items):
        item['account'] = str(account_prefixes[i]) + str(endings[i])
        # Rotate the tag vocabulary independently of count, including positives
        # on both sides of the initial cart membership.
        vocabulary = tags.copy()
        rng.shuffle(vocabulary)
        item['tags'] = vocabulary[:item['tag_count']]
        item['name_length'] = len(item['name'].replace(' ', '')) if id_ == 6 else len(item['name'])
        item['surname'] = item['name'].split()[-1] if app == 'chat' else item['name'][0]
        item['created_at'] = displayed_time(item['timestamp'])
        item['last_contact_at'] = displayed_time(item['contact_time'])
        if id_ == 14:
            updated = datetime.fromisoformat(source['reference_time']) - timedelta(days=item['age_days'])
            item['created_at'] = updated.isoformat(timespec='seconds')
            item['timestamp'] = int(updated.timestamp())
        item['opened_at'] = f'2025-{1+i%9:02d}-{1+seed%27:02d}'
        recent = datetime(2026, 1, 14, rng.randrange(24), rng.randrange(60), tzinfo=timezone.utc) - timedelta(days=i % 12)
        if item['same_day']:
            prior = recent.replace(hour=0, minute=0) + timedelta(minutes=rng.randrange(max(1, recent.hour * 60 + recent.minute)))
        else:
            prior = (recent - timedelta(days=1)).replace(hour=rng.randrange(24), minute=rng.randrange(60))
        # Short cross-midnight gaps and long within-day gaps rule out elapsed
        # time as a substitute for the calendar-date criterion.
        if item['same_day'] and i % 3 == 0:
            prior = recent.replace(hour=0, minute=10)
            recent = recent.replace(hour=23, minute=50)
        elif not item['same_day'] and i % 3 == 0:
            recent = recent.replace(hour=0, minute=10)
            prior = (recent - timedelta(days=1)).replace(hour=23, minute=50)
        item['recent_transactions'] = [
            {'id': f'transaction-{i}-{amount}', 'occurred_at': dt.isoformat(timespec='seconds'), 'amount': amount}
            for dt, amount in [(recent, 12+i), (prior, 30+i)]
        ]
        item['initial_in_cart'] = bool(rng.randrange(2))
        try:
            ast.parse(item['code'])
            item['check_pass'] = True
        except SyntaxError:
            item['check_pass'] = False
        if id_ == 11:
            item['file_text'] += '\n' + '请确认相关资料与负责人。\n' * rng.randrange(1, 50)
            item['size'] = len(item['file_text'].encode('utf-8'))
    rng.shuffle(items)
    source.pop('_app')
    demo = seed < 1000
    examples = ["Please Review the Design Draft", "Please Confirm the Meeting Room", "Please Share the Weekly Report", "Bring the Updated Budget Tomorrow", "Check the Delivery Notes Carefully", "Send the Workshop Schedule Today"] if demo else ["Discuss the New Library Plan", "Confirm the Garden Visit", "Prepare the Museum Guide", "Share the Walking Route", "Review the Evening Programme", "Send the Reading List"]
    if id_ == 1:
        source['text'] = (['pLeAsE rEVIEW the DESIGN draft', 'cONFIRM', 'share The weekly REPORT',
                           'BRING the Updated Budget', 'check Delivery NOTES carefully', 'sChEdUlE'] if demo else
                          ['dISCUSS the library PLAN', 'pREPARE', 'review The evening PROGRAMME',
                           'SHARE the Walking Route', 'confirm Garden VISIT today', 'rEaDiNg'])[seed % 6]
    if id_ == 2:
        source['text'] = (['Anna Wen','Chloe  Lin','eMMA','Noah   Li','Mia  Chen Han','LILY HE'] if demo else
                          ['Alice Qiu','Victor  Bai','jUNE','May   Deng','Rose  Su Mei','ERIC LUO'])[seed % 6]
    if id_ == 3:
        source['text'] = (['Please review the design draft', 'Can you confirm the room?',
                           'The weekly report is ready.', 'Bring the budget!',
                           'Note: check the delivery', 'Please send the schedule。'] if demo else
                          ['Discuss the library plan', 'Is the garden open?', 'The museum guide is ready.',
                           'Share the walking route!', 'Reminder: review the programme',
                           'Please send the reading list。'])[seed % 6]
    if id_ in (17,36):
        source['text'] = (['morning 3 Walk','summer 7 Breeze','city 2 Lights','river 12 Song','quiet 5 Hours','open 14 Windows'] if demo else ['autumn 8 Lanterns','winter 6 Letters','orange 9 Moon','green 10 Fields','ocean 11 Drive','first 4 Snow'])[seed % 6]
    if id_ == 18:
        source['date'] = f"2026-{1 if demo else 2:02d}-{1+seed%27:02d}"
    if id_ == 19:
        source['text'] = (['城市更新观察：街区如何变得更宜居？', '周末书单 (2026)：阅读与城市。',
                           'Night Walk! 老街新增 3 处照明', '社区手记——一起种花',
                           '开放日：「图书馆」的夜晚！', '2026/01/15, 城市声音采集计划.'] if demo else
                          ['湿地观察：春天有哪些新发现？', '植物笔记 (2027)：阳台四季。',
                           'Open Garden! 5 个社区参与共建', '海边漫游——潮汐与风',
                           '读书会：「自然」主题分享！', '2027/02/16, 公园声音记录.'])[seed % 6]
        source['publisher'], source['publisher_short'] = (
            [('Echo','EC:'),('North','NO:'),('Orbit','OR:'),('Sky','SK:'),('AtlasNews','AN:'),('Daily','DA:')] if demo else
            [('Field Notes','FN:'),('Garden Post','GP:'),('Coast Review','CR:'),('City Voice','CV:'),('Open Press','OP:'),('Park Journal','PJ:')]
        )[seed % 6]
    if id_ == 20:
        source['text'] = (NAMES if demo else QUERY_NAMES)['news'][seed % 6]
        vocabulary = ['research','design','travel','writing','music','community','science','history'] if demo else ['nature','reading','photography','gardening','cooking','hiking','architecture','education']
        source['tags'] = random.Random(seed + 4020).sample(vocabulary, 2 + seed % 3)
    if id_ == 21:
        source['text'] = (['书单','城市观察与阅读笔记','自然','周末旅行与影像记录集','街头摄影与光影练习','音乐会记录'] if demo else ['露营','图书馆漫游记','手作','雨天的骑行路线与地图','植物园周末游记','咖啡馆的阅读时光'])[seed % 6]
    if id_ == 37:
        topic = (['community research','design review','travel planning','book discussion','garden survey','music workshop'] if demo else
                 ['wildlife observation','museum visits','baking lessons','cycling routes','library services','photography walks'])[seed % 6]
        templates = [
            [f'Summarize the {topic} report', 'Use short sentences', 'List the key findings', 'Separate facts from opinions', 'Mention open questions', 'End with a brief conclusion'],
            [f'Prepare a {topic} outline', 'State the purpose', 'Describe the audience', 'Include three sections', 'Give one practical example', 'Keep the tone friendly'],
            [f'Review the {topic} notes', 'Group related ideas', 'Preserve important names', 'Identify missing details', 'Suggest two follow-up questions', 'Use plain language'],
            [f'Draft a {topic} invitation', 'Explain the meeting time', 'Introduce the activity', 'List what to bring', 'Include a contact person', 'Close with a welcome'],
            [f'Compare the {topic} options', 'Use the same criteria', 'Describe each benefit', 'Explain the limitations', 'Check the available budget', 'Provide a short recommendation'],
            [f'Create a {topic} checklist', 'Start with preparation', 'Include the main activity', 'Add a review step', 'Assign clear responsibilities', 'Finish with next actions'],
        ]
        source['text'] = '\n'.join(templates[seed % 6])
    if id_ == 44:
        source['given_name'] = (['Mei','Ruo Ning','Zi An','Yu Chen','Xiao Man','Jia He'] if demo else ['Jun','Qing Yue','Zhi Xia','Ming Yuan','Ke Xin','Yu An'])[seed % 6]
    source['transaction_window'] = {'start':'2025-12-17', 'end':'2026-01-15', 'days':30}
    if id_ == 4:
        source['text'] = (['评审改到会议室3，请在下午14点前确认', '请准备25份会议资料，送到会议室8', '周五到楼栋17参加讨论，请提前2小时确认', '请核对10份预算表并打印6份备份', '会议安排在楼层20，请联系工位4', '活动分为12组，集合时间为上午9点'] if demo else ['请到会议室16领取8份资料', '班车安排在车位23，请在上午10点集合', '展览使用楼层15和6，请准备40张门票', '路线包含18个站点和2处休息区', '讲座开放35个座位，请提前7分钟入场', '请核对24份反馈并选取9个问题'])[seed % 6]
    if id_ == 45:
        source['quantity'] = 2 + seed % 7
    if id_ == 46:
        length = [10, 12, 16, 19, 14, 18][seed % 6]
        source['text'] = str(random.Random(seed + 8461).randrange(10**(length-1), 10**length))
    if id_ == 58:
        source['text'] = f'limit = {seed % 9 + 2}\nfor index in range(limit):\n   if index % 2 == 0:\n      print(index)\n   else:\n      print(-index)'
    if id_ == 59:
        source['text'] = (examples[seed % 6] + '\n' + source['text'])
        source['text'] += '\nRead the input carefully\nKeep intermediate values\nCheck the boundary cases\nReturn the final result'
    if id_ == 60:
        names = ([('value', 'total'), ('length', 'area'), ('price', 'cost'), ('count', 'result'),
                  ('limit', 'answer'), ('scores', 'average')] if demo else
                 [('height', 'volume'), ('budget', 'remaining'), ('items', 'subtotal'),
                  ('steps', 'distance'), ('target', 'attempt'), ('samples', 'mean')])
        a, b = names[seed % 6]
        source['rename_targets'] = [a, b]
        source['text'] = [
            f'{a} = {seed + 7}\nif {a} > 0:\n   {b} = {a} + 1\n   print({b})',
            f'{a} = {seed + 3}\n{b} = {a} * {a}\nprint({b}, {a})',
            f'{a} = [7, 12, 5]\n{b} = sum({a})\nif {b} > 20:\n   print({b} - min({a}))',
            f'{b} = 0\nfor {a} in range({seed + 4}):\n   {b} += {a}\nprint({b})',
            f'{a} = {seed + 2}\n{b} = 1\nwhile {b} < {a}:\n   {b} *= 2\nprint({b}, {a})',
            f'{a} = [6, 8, 10]\n{b} = sum({a}) / len({a})\nprint(round({b}, 2))',
        ][seed % 6]
    return items
