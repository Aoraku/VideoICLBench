"""Build the maintainer gallery from audited, bundled historical recordings."""
import hashlib
import html
import json
from pathlib import Path

BASE = Path(__file__).resolve().parents[1]
BATCHES = ["foundation-v1", "assembly-preview-v15", "visible-preview-v46",
           "sweep-preview-v48", "corner-preview-v53", "clearance-preview-v67", "shovel-preview-v69", "guidance-preview-v81", "shape-preview-v79", "vacancy-preview-v79", "stack-recovery-preview-v79", "mosaic-preview-v114", "ring-preview-v117", "rack-preview-v118", "key-preview-v119", "relocate-preview-v117", "correction-preview-v118", "access-preview-v117", "reference-row-preview-v117", "contents-preview-v120", "topup-preview-v125", "arrows-preview-v128", "lengths-preview-v128", "height-pair-preview-v128"]


def main():
    selected = {}
    for batch in BATCHES:
        manifest = json.loads((BASE/"artifacts"/batch/"manifest.private.json").read_text())
        for row in manifest["cases"]:
            if not row.get("usable_for_agent_demo", False):
                continue
            folder = BASE/"artifacts"/batch/row["folder"]
            video = folder/"video.mp4"
            assert video.is_file(), video
            assert hashlib.sha256(video.read_bytes()).hexdigest() == row["video_sha256"], video
            selected[row["task"], row["variant"]] = dict(row, batch=batch,
                path=str(video.relative_to(BASE)), poster=str((folder/"final.jpg").relative_to(BASE)))
    families = json.loads((BASE/"families.json").read_text())["families"]
    complete = sum(all((f["id"], v) in selected for v in "ABC") for f in families)
    out = ["<!doctype html><html lang='zh-CN'><meta charset='utf-8'>",
           "<meta name='viewport' content='width=device-width,initial-scale=1'>",
           "<title>桌面双臂 50 任务 · 查看入口</title>",
           "<style>body{font:16px/1.6 system-ui;max-width:1250px;margin:32px auto;padding:0 20px;background:#f5f6f8;color:#17202a}section{background:white;border:1px solid #ddd;border-radius:12px;padding:20px;margin:20px 0}.videos{display:grid;grid-template-columns:repeat(auto-fit,minmax(280px,1fr));gap:16px}video{width:100%;background:#111}a{color:#165ab0}small{color:#555}</style>",
           "<h1>桌面双臂 50 任务</h1>",
           f"<p>50族设计 / 150规则条件；合格历史预览 <b>{len(selected)}/150</b>，完整三版本 <b>{complete}/50</b>。</p>",
           "<p>下列视频随仓库一起提供，可以直接播放。均为仿真作者示范；真人视频和独立agent实验尚未完成。历史录像对应各自冻结源码，不能直接装入最新版actor服务。</p>",
           "<p><a href='TASKS_50.md'>50题录制卡</a> · <a href='PROGRESS.md'>实现与验收进度</a> · <a href='DEPLOY.md'>部署说明</a> · <a href='artifacts/README.md'>历史验收证据</a></p>"]
    md = ["# 50题视频索引", "", f"合格历史预览{len(selected)}段，完整三版本{complete}族。未完成项明确留空；不是最终统一源码150段验收。", "", "| 任务 | A | B | C |", "| --- | --- | --- | --- |"]
    for f in families:
        ident = f["id"]
        out += [f"<section id='{ident}'><h2>{ident} {html.escape(f['title'])}</h2>",
                f"<p>{html.escape(f['challenge'])}</p><div class='videos'>"]
        links = []
        for variant in "ABC":
            row = selected.get((ident, variant))
            out.append(f"<article><h3>规则 {variant}：{html.escape(f['rules'][variant])}</h3>")
            if row:
                out.append(f"<video controls preload='none' poster='{row['poster']}' src='{row['path']}'></video><small>{row['duration_seconds']:.1f}秒 · {row['batch']}</small>")
                links.append(f"[视频]({row['path']})")
            else:
                out.append("<p>尚无合格视频</p>")
                links.append("待完成")
            out.append("</article>")
        out.append("</div></section>")
        md.append(f"| {ident} {f['title']} | {' | '.join(links)} |")
    out.append("</html>")
    (BASE/"index.html").write_text("\n".join(out)+"\n")
    (BASE/"VIDEOS.md").write_text("\n".join(md)+"\n")
    print(json.dumps(dict(bundled_verified_videos=len(selected), complete_families=complete)))


if __name__ == "__main__":
    main()
