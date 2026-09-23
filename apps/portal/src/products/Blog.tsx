import { useState } from "react";
import {
  Frame,
  PageHead,
  Notice,
  Tags,
  Classify,
  dateOf,
  type ProductAPI,
} from "./kit";
export function Blog({ api }: { api: ProductAPI }) {
  const { s, d } = api,
    [page, setPage] = useState("home"),
    [selected, setSelected] = useState(""),
    [text, setText] = useState(""),
    [query, setQuery] = useState("");
  const rows = s.items.map((x: any) => d.objects[x.id]),
    current = selected === "target" ? d.objects.target : d.objects[selected];
  function edit(id: string) {
    setSelected(id);
    setText(
      id === "target"
        ? (s.outputs.target ?? s.source.text)
        : d.objects[id].text,
    );
    setPage("editor");
  }
  const cards = (items: any[]) => (
    <div className="blog-cards">
      {items.map((item: any, i: number) => (
        <article key={item.id} data-object-id={item.id} className="blog-card">
          <div className={`blog-cover cover-${i % 3}`}>
            <span>FIELD NOTES</span>
            <b>{["观察", "记录", "思考"][i % 3]}</b>
          </div>
          <div>
            <small>
              {dateOf(item)} · {item.words} 字
            </small>
            <button className="product-text-link" onClick={() => edit(item.id)}>
              <h2>{item.name}</h2>
            </button>
            <p>{item.text}</p>
            <Tags item={item} api={api} />
            {s.task_id === 38 && <Classify item={item} api={api} />}
          </div>
        </article>
      ))}
    </div>
  );
  return (
    <Frame
      brand="墨记"
      accent="#3e7153"
      page={page}
      navigate={setPage}
      tabs={[
        ["home", "工作台"],
        ["drafts", "我的草稿"],
        ["published", "已发布"],
        ["tags", "标签管理"],
      ]}
      tools={
        <button
          className="product-primary"
          onClick={() => edit(s.type === "T" ? "target" : s.items[0].id)}
        >
          写文章
        </button>
      }
    >
      <main className="product-main">
        <Notice api={api} />
        {page === "home" ? (
          <>
            <PageHead
              eyebrow="YOUR WRITING DESK"
              title="把想法，写成值得留下的文字。"
              description="从一篇草稿开始，记录观察，整理思考。"
            />
            <section className="blog-welcome">
              <div>
                <span className="product-eyebrow">继续写作</span>
                <h2>{s.type === "T" ? (s.outputs.target ?? s.source.text) : rows[0].name}</h2>
                <p>编辑标题与正文，为文章整理标签，或准备发布。</p>
                <button
                  className="product-primary"
                  onClick={() => edit(s.type === "T" ? "target" : rows[0].id)}
                >
                  继续编辑 →
                </button>
              </div>
              <div className="blog-paper">
                Notes
                <br />
                <span>ideas / stories / everyday</span>
              </div>
            </section>
            <div className="product-section">
              <h2>最近草稿</h2>
              <button onClick={() => setPage("drafts")}>查看全部 →</button>
            </div>
            {cards(rows.slice(0, 3))}
          </>
        ) : page === "editor" && current ? (
          <>
            <button className="product-back" onClick={() => setPage("drafts")}>
              ← 返回草稿
            </button>
            <PageHead
              eyebrow="EDITOR"
              title={selected === "target" ? "编辑文章标题" : current.name}
              description="文字会保存到你的个人草稿库。"
              action={
                <button
                  className="product-primary"
                  disabled={api.busy || s.task_id === 38}
                  onClick={async () => {
                    if (s.task_id === 36)
                      await api.mutate("save", "target", text);
                    else if (s.task_id === 40)
                      await api.mutate("select", "", "", [selected]);
                    else if (s.task_id === 42)
                      await api.mutate("action", selected, "发布");
                  }}
                >
                  {s.task_id === 36 ? "保存草稿" : "发布文章"}
                </button>
              }
            />
            <section className="blog-editor">
              <span className="product-eyebrow">
                {dateOf(current)} · PERSONAL NOTES
              </span>
              {s.task_id === 36 ? (
                <>
                  <label>
                    文章标题
                    <input
                      className="blog-title-input"
                      value={text}
                      onChange={(e) => setText(e.target.value)}
                    />
                  </label>
                  <div className="blog-editor-body">
                    一篇好的记录，来自对日常的认真观察。这里是文章的正文草稿，你可以先整理标题，再继续完成写作。
                  </div>
                  <p>原始标题：{s.source.text}</p>
                </>
              ) : (
                <>
                  <h1>{current.name}</h1>
                  <div className="blog-editor-body">{current.text}</div>
                  <Tags item={current} api={api} />
                  <p className="product-muted">
                    {current.words} 字 · {current.tag_count} 个标签 · 时间序号{" "}
                    {current.timestamp}
                  </p>
                  {s.task_id === 38 && <Classify item={current} api={api} />}
                </>
              )}
            </section>
          </>
        ) : (
          <>
            <PageHead
              eyebrow="LIBRARY"
              title={
                page === "published"
                  ? "已发布文章"
                  : page === "tags"
                    ? "文章与标签"
                    : "我的草稿"
              }
              description={`${rows.filter((x: any) => (page === "published" ? x.published : !x.published)).length} 篇文章`}
              action={
                <input
                  placeholder="搜索文章"
                  value={query}
                  onChange={(e) => setQuery(e.target.value)}
                />
              }
            />
            {s.task_id === 36 && page === "drafts" && (
              <button
                className="blog-draft-link"
                onClick={() => edit("target")}
              >
                {s.outputs.target ?? s.source.text}
                <span>继续编辑 →</span>
              </button>
            )}
            {cards(
              rows.filter(
                (x: any) =>
                  (page === "published" ? x.published : !x.published) &&
                  x.name.includes(query),
              ),
            )}
          </>
        )}
      </main>
    </Frame>
  );
}
