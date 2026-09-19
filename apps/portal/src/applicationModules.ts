export const modules = {
  "chat": {
    "id": "chat",
    "title": "VIC Chat",
    "subtitle": "沟通与协作",
    "tabs": [
      "会话",
      "联系人",
      "已发送"
    ],
    "color": "#15786e",
    "tasks": [
      1,
      2,
      3,
      4,
      5,
      6,
      7,
      8,
      9,
      10,
      11,
      12,
      13,
      14
    ],
    "schema_version": 1,
    "frontend": "apps/chat/frontend/frontend/src",
    "entrypoint": "vic_apps.server:create_app",
    "state_backend": "sqlite-domain-tables",
    "surface": "native-task-workspace"
  },
  "im": {
    "id": "im",
    "title": "VIC IM",
    "subtitle": "团队消息",
    "tabs": [
      "消息",
      "群组",
      "回执"
    ],
    "color": "#4672ca",
    "tasks": [
      15,
      16
    ],
    "schema_version": 1,
    "frontend": "apps/im/Frontend/src",
    "entrypoint": "vic_apps.server:create_app",
    "state_backend": "sqlite-domain-tables",
    "surface": "native-task-workspace"
  },
  "music": {
    "id": "music",
    "title": "VIC Music",
    "subtitle": "音乐资料库",
    "tabs": [
      "音乐库",
      "播放列表",
      "正在播放"
    ],
    "color": "#7354b6",
    "tasks": [
      17,
      18,
      22,
      27,
      28,
      32
    ],
    "schema_version": 1,
    "frontend": "apps/music/blog/templates/blog",
    "entrypoint": "vic_apps.server:create_app",
    "state_backend": "sqlite-domain-tables",
    "surface": "native-task-workspace"
  },
  "news": {
    "id": "news",
    "title": "VIC News",
    "subtitle": "新闻阅读室",
    "tabs": [
      "文章",
      "阅读清单",
      "收藏"
    ],
    "color": "#b74435",
    "tasks": [
      19,
      20,
      23,
      24,
      29,
      30,
      33
    ],
    "schema_version": 1,
    "frontend": "apps/news/src/main/resources/web",
    "entrypoint": "vic_apps.server:create_app",
    "state_backend": "sqlite-domain-tables",
    "surface": "native-task-workspace"
  },
  "media": {
    "id": "media",
    "title": "VIC Media",
    "subtitle": "视频与信息流",
    "tabs": [
      "发现",
      "观看列表",
      "播放队列"
    ],
    "color": "#d65d43",
    "tasks": [
      21,
      25,
      26,
      31,
      34,
      35
    ],
    "schema_version": 1,
    "frontend": "apps/portal/src/products/Media.tsx",
    "entrypoint": "vic_apps.server:create_app",
    "state_backend": "sqlite-domain-tables",
    "surface": "native-task-workspace"
  },
  "blog": {
    "id": "blog",
    "title": "VIC Blog",
    "subtitle": "文章与发布",
    "tabs": [
      "草稿",
      "文章",
      "发布记录"
    ],
    "color": "#447e48",
    "tasks": [
      36,
      38,
      40,
      42
    ],
    "schema_version": 1,
    "frontend": "apps/portal/src/products/Blog.tsx",
    "entrypoint": "vic_apps.server:create_app",
    "state_backend": "sqlite-domain-tables",
    "surface": "native-task-workspace"
  },
  "studio": {
    "id": "studio",
    "title": "VIC Studio",
    "subtitle": "内容工作室",
    "tabs": [
      "编辑器",
      "模型库",
      "交付记录"
    ],
    "color": "#7757b5",
    "tasks": [
      37,
      39,
      41,
      43
    ],
    "schema_version": 1,
    "frontend": "apps/portal/src/products/Studio.tsx",
    "entrypoint": "vic_apps.server:create_app",
    "state_backend": "sqlite-domain-tables",
    "surface": "native-task-workspace"
  },
  "travel": {
    "id": "travel",
    "title": "VIC Travel",
    "subtitle": "出行与预订",
    "tabs": [
      "路线",
      "乘客",
      "预订记录"
    ],
    "color": "#1b809d",
    "tasks": [
      44,
      47,
      51,
      54
    ],
    "schema_version": 1,
    "frontend": "apps/portal/src/products/Travel.tsx",
    "entrypoint": "vic_apps.server:create_app",
    "state_backend": "sqlite-domain-tables",
    "surface": "native-task-workspace"
  },
  "shop": {
    "id": "shop",
    "title": "VIC Shop",
    "subtitle": "商品与购物车",
    "tabs": [
      "商品",
      "购物车",
      "收藏"
    ],
    "color": "#ad6836",
    "tasks": [
      45,
      48,
      52,
      55
    ],
    "schema_version": 1,
    "frontend": "apps/portal/src/products/Shop.tsx",
    "entrypoint": "vic_apps.server:create_app",
    "state_backend": "sqlite-domain-tables",
    "surface": "native-task-workspace"
  },
  "bank": {
    "id": "bank",
    "title": "VIC Bank",
    "subtitle": "账户与交易",
    "tabs": [
      "账户",
      "交易",
      "转账记录"
    ],
    "color": "#345b84",
    "tasks": [
      46,
      49,
      50,
      53,
      56,
      57
    ],
    "schema_version": 1,
    "frontend": "apps/portal/src/products/Bank.tsx",
    "entrypoint": "vic_apps.server:create_app",
    "state_backend": "sqlite-domain-tables",
    "surface": "native-task-workspace"
  },
  "code": {
    "id": "code",
    "title": "VIC Code",
    "subtitle": "编程工作区",
    "tabs": [
      "编辑器",
      "题库",
      "提交记录"
    ],
    "color": "#3b5978",
    "tasks": [
      58,
      59,
      60,
      61,
      62,
      63,
      64,
      65
    ],
    "schema_version": 1,
    "frontend": "apps/code/app/frontend.py",
    "entrypoint": "vic_apps.server:create_app",
    "state_backend": "sqlite-domain-tables",
    "surface": "native-task-workspace"
  },
  "gomoku": {
    "id": "gomoku",
    "title": "VIC Gomoku",
    "subtitle": "五子棋",
    "tabs": [
      "棋盘",
      "操作记录"
    ],
    "color": "#987048",
    "tasks": [
      66,
      67
    ],
    "schema_version": 1,
    "frontend": "apps/gomoku/main.cpp",
    "entrypoint": "vic_apps.server:create_app",
    "state_backend": "sqlite-domain-tables",
    "surface": "native-task-workspace"
  },
  "games": {
    "id": "games",
    "title": "VIC Games",
    "subtitle": "益智游戏",
    "tabs": [
      "棋盘",
      "操作记录"
    ],
    "color": "#516d8e",
    "tasks": [
      68,
      69,
      70,
      71,
      72,
      73,
      74,
      75
    ],
    "schema_version": 1,
    "frontend": "apps/portal/src/products/Games.tsx",
    "entrypoint": "vic_apps.server:create_app",
    "state_backend": "sqlite-domain-tables",
    "surface": "native-task-workspace"
  }
} as const;
