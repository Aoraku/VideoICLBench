import { useState } from "react";
import {
  Frame,
  PageHead,
  Notice,
  Classify,
  Tags,
  minutes,
  type ProductAPI,
} from "./kit";
export function Media({ api }: { api: ProductAPI }) {
  const { s, d } = api,
    [page, setPage] = useState("home"),
    [selected, setSelected] = useState(""),
    [text, setText] = useState(s.outputs.target ?? s.source.text),
    [query, setQuery] = useState("");
  const rows = s.items.map((x: any) => d.objects[x.id]),
    active = d.objects[selected];
  const index = (id: string) => s.items.findIndex((x: any) => x.id === id);
  async function play(id: string) {
    if (s.task_id === 31 && !(await api.mutate("select", "", "", [id]))) return;
    setSelected(id);
    setPage("player");
  }
  const list =
    page === "watchlist"
      ? rows.filter((x: any) => d.collections.watchlist.includes(x.id))
      : page === "history"
        ? rows.filter((x: any) => d.collections.history.includes(x.id))
        : page === "favorites"
          ? rows.filter((x: any) => d.collections.favorites.includes(x.id))
          : page === "queue"
            ? d.orders.main.map((id: string) => d.objects[id])
            : rows;
  const operations = (item: any) => (
    <>
      {[25, 26].includes(s.task_id) && <Classify item={item} api={api} />}{" "}
      {s.task_id === 34 && (
        <div className="product-actions">
          {["移入历史", "收藏", "删除"].map((action) => (
            <button
              key={action}
              disabled={api.busy}
              onClick={() => api.mutate("action", item.id, action)}
            >
              {action}
            </button>
          ))}
        </div>
      )}
    </>
  );
  function move(i: number, delta: number) {
    const ids = [...d.orders.main],
      to = i + delta;
    if (to < 0 || to >= ids.length) return;
    [ids[i], ids[to]] = [ids[to], ids[i]];
    void api.mutate("order", "", "", ids);
  }
  return (
    <Frame
      brand="映像放映室"
      accent="#ae583d"
      page={page}
      navigate={setPage}
      tabs={[
        ["home", "发现"],
        ["library", "视频资料库"],
        ["watchlist", "稍后观看"],
        ["queue", "播放队列"],
        ["history", "观看历史"],
        ["favorites", "收藏夹"],
      ]}
      tools={
        <input
          placeholder="搜索视频"
          value={query}
          onChange={(e) => {
            setQuery(e.target.value);
            setPage("library");
          }}
        />
      }
    >
      <main className="product-main">
        <Notice api={api} />
        {page === "home" ? (
          <>
            <section className="media-hero">
              <img
                src="/native-assets/media/poster-0.jpg"
                alt="Big Buck Bunny 电影剧照"
              />
              <div>
                <span>OPEN MOVIE · BLENDER FOUNDATION</span>
                <h1>走进一片有故事的森林。</h1>
                <p>Big Buck Bunny · 开放电影精选片段</p>
                <button onClick={() => play(rows[0].id)}>▶ 开始观看</button>
              </div>
            </section>
            <div className="product-section">
              <h2>为你精选</h2>
              <button onClick={() => setPage("library")}>全部视频 →</button>
            </div>
          </>
        ) : null}
        {page === "player" && active ? (
          <>
            <button className="product-back" onClick={() => setPage("library")}>
              ← 返回视频资料库
            </button>
            <video
              className="media-player"
              controls
              autoPlay
              src={`/native-assets/media/clip-${index(active.id)}.mp4`}
              poster={`/native-assets/media/poster-${index(active.id)}.jpg`}
            />
            <div className="media-player-info">
              <div>
                <h1>{active.name}</h1>
                <p>{active.text}</p>
                <p>
                  {minutes(active.duration)} · 评分 {active.rating}/100 · 点赞率{" "}
                  {active.like_rate}% · 发布时间序号 {active.timestamp}
                </p>
                <Tags item={active} api={api} />
              </div>
              <div>{operations(active)}</div>
            </div>
            <footer className="media-credit">
              Big Buck Bunny © 2008 Blender Foundation · CC BY 3.0 ·
              片段与循环剪辑{" "}
              <a
                href="https://peach.blender.org/about/"
                target="_blank"
                rel="noreferrer"
              >
                影片来源与许可
              </a>
            </footer>
          </>
        ) : (
          <>
            {page !== "home" && (
              <PageHead
                eyebrow="YOUR COLLECTION"
                title={
                  page === "watchlist"
                    ? "稍后观看"
                    : page === "history"
                      ? "观看历史"
                      : page === "favorites"
                        ? "收藏夹"
                        : page === "queue"
                          ? "播放队列"
                          : "视频资料库"
                }
                description={`${list.length} 个视频`}
              />
            )}{" "}
            {s.task_id === 21 && page === "favorites" && (
              <section className="media-folder">
                <span>▣</span>
                <div>
                  <h2>收藏夹名称</h2>
                  <p>原名称：{s.source.text}</p>
                  <input
                    value={text}
                    onChange={(e) => setText(e.target.value)}
                  />
                  <button
                    className="product-primary"
                    disabled={api.busy}
                    onClick={() => api.mutate("save", "target", text)}
                  >
                    保存名称
                  </button>
                  {s.outputs.target && (
                    <p className="product-ok">已保存：{s.outputs.target}</p>
                  )}
                </div>
              </section>
            )}
            {page === "queue" ? (
              <div className="media-queue">
                {list.map((item: any, i: number) => (
                  <article key={item.id} data-object-id={item.id}>
                    <span>{String(i + 1).padStart(2, "0")}</span>
                    <img
                      src={`/native-assets/media/poster-${index(item.id)}.jpg`}
                      alt="影片剧照"
                    />
                    <div>
                      <button
                        className="product-text-link"
                        onClick={() => play(item.id)}
                      >
                        <h3>{item.name}</h3>
                      </button>
                      <p>
                        {minutes(item.duration)} · {item.category} 类
                      </p>
                    </div>
                    {s.task_id === 35 && (
                      <div className="product-actions">
                        <button
                          aria-label={`上移 ${item.name}`}
                          disabled={api.busy || i === 0}
                          onClick={() => move(i, -1)}
                        >
                          ↑
                        </button>
                        <button
                          aria-label={`下移 ${item.name}`}
                          disabled={api.busy || i === list.length - 1}
                          onClick={() => move(i, 1)}
                        >
                          ↓
                        </button>
                      </div>
                    )}
                  </article>
                ))}
              </div>
            ) : (
              <div className="media-grid">
                {list
                  .filter((x: any) => x.name.includes(query))
                  .map((item: any) => (
                    <article key={item.id} data-object-id={item.id}>
                      <button
                        className="media-thumbnail"
                        onClick={() => play(item.id)}
                      >
                        <img
                          src={`/native-assets/media/poster-${index(item.id)}.jpg`}
                          alt={item.name}
                        />
                        <span>▶</span>
                        <small>{minutes(item.duration)}</small>
                      </button>
                      <div>
                        <button
                          className="product-text-link"
                          onClick={() => play(item.id)}
                        >
                          <h3>{item.name}</h3>
                        </button>
                        <p>
                          评分 {item.rating}/100 · {item.comments} 条评论
                        </p>
                        <p>
                          点赞率 {item.like_rate}% · 发布序号 {item.timestamp}
                        </p>
                        <p className="product-muted">
                          {item.completed ? "✓ 已看完" : "未看完"} ·{" "}
                          {item.category} 类
                        </p>
                        {operations(item)}
                      </div>
                    </article>
                  ))}
              </div>
            )}
            {list.length === 0 && (
              <div className="product-empty">这里还没有视频。</div>
            )}
          </>
        )}
      </main>
    </Frame>
  );
}
