from pathlib import Path
import json

ROOT = Path(__file__).resolve().parents[1]
config = {
    "chat": ("VIC Chat", "沟通与协作", ["会话", "联系人", "已发送"], "#15786e"),
    "im": ("VIC IM", "团队消息", ["消息", "群组", "回执"], "#4672ca"),
    "music": ("VIC Music", "音乐资料库", ["音乐库", "播放列表", "正在播放"], "#7354b6"),
    "news": ("VIC News", "新闻阅读室", ["文章", "阅读清单", "收藏"], "#b74435"),
    "media": ("VIC Media", "视频与信息流", ["发现", "观看列表", "播放队列"], "#d65d43"),
    "blog": ("VIC Blog", "文章与发布", ["草稿", "文章", "发布记录"], "#447e48"),
    "studio": ("VIC Studio", "内容工作室", ["编辑器", "模型库", "交付记录"], "#7757b5"),
    "travel": ("VIC Travel", "出行与预订", ["路线", "乘客", "预订记录"], "#1b809d"),
    "shop": ("VIC Shop", "商品与购物车", ["商品", "购物车", "收藏"], "#ad6836"),
    "bank": ("VIC Bank", "账户与交易", ["账户", "交易", "转账记录"], "#345b84"),
    "code": ("VIC Code", "编程工作区", ["编辑器", "题库", "提交记录"], "#3b5978"),
    "gomoku": ("VIC Gomoku", "五子棋", ["棋盘", "操作记录"], "#987048"),
    "games": ("VIC Games", "益智游戏", ["棋盘", "操作记录"], "#516d8e"),
}
tasks = json.loads((ROOT / "tasks/catalog.json").read_text())["tasks"]
modules = {}
for key, (title, subtitle, tabs, color) in config.items():
    d = ROOT / "apps" / key / "benchmark"
    d.mkdir(parents=True, exist_ok=True)
    m = dict(
        id=key,
        title=title,
        subtitle=subtitle,
        tabs=tabs,
        color=color,
        tasks=[t["id"] for t in tasks if t["app"] == key],
        schema_version=1,
        entrypoint="vic_apps.server:create_app",
        state_backend="sqlite-domain-tables",
        surface="application-benchmark",
    )
    (d / "module.json").write_text(json.dumps(m, ensure_ascii=False, indent=2) + "\n")
    modules[key] = m
    (d / "app.py").write_text(
        '''"""Application-specific benchmark entrypoint."""\nimport os\nfrom vic_apps.server import create_app as shared_app\n\ndef create_app():\n    os.environ['VIC_APP_MODULES']='''
        + repr(key)
        + """\n    return shared_app()\n"""
    )
    (d / "README.md").write_text(
        f"""# {title} benchmark 模式\n\n任务：{", ".join(map(str, m["tasks"]))}。\n\n入口由本仓库的 `benchmark/app.py` 提供。共享的 `vic_apps` 负责事务数据库和 HTTP 协议，领域界面由 `apps/portal/src/Application.tsx` 按 `module.json` 配置渲染。任务在独立数据库中初始化；普通操作不读取 A/B/C 规则。\n\n控制平台通过应用 Worker 的私有 `prepare` / `seal` 接口管理任务；应用用户只使用 `/api/runs/{{id}}` 与 `commands`。模块支持在统一 Worker 中运行，也可用 `uvicorn --app-dir apps/{key}/benchmark app:create_app --factory --port 8771` 单独启动。需要设置 `VIC_APP_RUNTIME_TOKEN`，其值与控制平台一致。\n\n评测检查领域对象、消息、成员、列表、产物、账本等实际状态。基准模式具有专用 UI 和数据模型；原仓库的普通模式数据不参与这套基准。\n"""
    )
(ROOT / "apps/portal/src/applicationModules.ts").write_text(
    "export const modules = "
    + json.dumps(modules, ensure_ascii=False, indent=2)
    + " as const;\n"
)
(ROOT / "packages/app_runtime/vic_apps/modules.json").write_text(
    json.dumps(modules, ensure_ascii=False, indent=2) + "\n"
)
print("13 application modules generated")
