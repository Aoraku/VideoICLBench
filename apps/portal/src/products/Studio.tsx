import { useState } from "react";
import { Frame, PageHead, Notice, Classify, type ProductAPI } from "./kit";
export function Studio({ api }: { api: ProductAPI }) {
  const { s, d } = api,
    [page, setPage] = useState("home"),
    [text, setText] = useState(s.outputs.target ?? s.source.text),
    [focused, setFocused] = useState(s.items[0].id),
    [tab, setTab] = useState("outputs");
  const rows = s.items.map((x: any) => d.objects[x.id]),
    active = d.objects[focused];
  return (
    <Frame
      brand="VIC Studio"
      accent="#7564a6"
      page={page}
      navigate={setPage}
      tabs={[
        ["home", "工作台"],
        ["prompts", "提示词库"],
        ["documents", "内容项目"],
        ["models", "模型库"],
      ]}
    >
      <main className="product-main">
        <Notice api={api} />
        {page === "home" ? (
          <>
            <PageHead
              eyebrow="CREATE WITH INTENTION"
              title="开始一次有条理的创作。"
              description="管理提示词、选择模型，整理生成内容与交付文件。"
            />
            <div className="studio-start">
              <span className="studio-spark">✳</span>
              <h2>今天想完成什么？</h2>
              <p>从已有项目继续，或打开提示词库整理你的工作方式。</p>
              <div>
                <button onClick={() => setPage("prompts")}>整理提示词</button>
                <button onClick={() => setPage("documents")}>
                  打开内容项目
                </button>
                <button onClick={() => setPage("models")}>选择模型</button>
              </div>
            </div>
            <div className="product-section">
              <h2>最近项目</h2>
            </div>
            <div className="studio-projects">
              {["研究报告摘要", "会议记录整理", "代码审阅"].map((name, i) => (
                <button
                  key={name}
                  onClick={() => {
                    setFocused(rows[i].id);
                    setPage("documents");
                  }}
                >
                  <span>▤</span>
                  <h3>{name}</h3>
                  <p>个人工作区 · 今天</p>
                </button>
              ))}
            </div>
          </>
        ) : page === "prompts" ? (
          <>
            <PageHead
              eyebrow="PROMPT LIBRARY"
              title="提示词库"
              description="将重复使用的指令保存为模板。"
            />
            <div className="studio-project-layout">
              <aside>
                <button className="active">研究报告摘要</button>
                <p>个人模板</p>
                <small>最近编辑 · 今天</small>
              </aside>
              <section>
                <label>
                  模板名称
                  <input value="研究报告摘要" readOnly />
                </label>
                <label>
                  提示词
                  <textarea
                    rows={12}
                    value={text}
                    onChange={(e) => setText(e.target.value)}
                  />
                </label>
                <button
                  className="product-primary"
                  disabled={api.busy}
                  onClick={() => api.mutate("save", "target", text)}
                >
                  保存模板
                </button>
              </section>
            </div>
          </>
        ) : page === "models" ? (
          <>
            <PageHead
              eyebrow="MODEL CATALOG"
              title="为项目选择模型"
              description="比较上下文窗口与使用价格，再设为项目默认模型。"
            />
            <div className="studio-models">
              {rows.map((item: any, i: number) => (
                <article key={item.id} data-object-id={item.id}>
                  <div className="studio-model-logo">
                    {["◈", "✳", "◇"][i % 3]}
                  </div>
                  <h2>{item.name}</h2>
                  <p>适合内容整理与日常工作任务</p>
                  <dl>
                    <dt>上下文窗口</dt>
                    <dd>{item.context} K</dd>
                    <dt>价格</dt>
                    <dd>¥{item.price} / 百万 token</dd>
                  </dl>
                  <button
                    className={
                      d.settings.model?.includes(item.id)
                        ? "chosen"
                        : "product-primary"
                    }
                    disabled={api.busy}
                    onClick={() => api.mutate("select", "", "", [item.id])}
                  >
                    {d.settings.model?.includes(item.id)
                      ? "✓ 已设为默认模型"
                      : "使用此模型"}
                  </button>
                </article>
              ))}
            </div>
          </>
        ) : (
          <>
            <PageHead
              eyebrow="CONTENT PROJECT"
              title="研究与内容项目"
              description="查看生成内容，完成核对后保存或交付。"
            />
            <div className="studio-project-layout">
              <aside>
                {rows.map((item: any) => (
                  <button
                    key={item.id}
                    className={focused === item.id ? "active" : ""}
                    onClick={() => setFocused(item.id)}
                  >
                    {item.name}
                  </button>
                ))}
              </aside>
              <section>
                <div className="product-tabs">
                  <button
                    className={tab === "outputs" ? "active" : ""}
                    onClick={() => setTab("outputs")}
                  >
                    生成内容
                  </button>
                  <button
                    className={tab === "saved" ? "active" : ""}
                    onClick={() => setTab("saved")}
                  >
                    已保存文件
                  </button>
                </div>
                {tab === "saved" ? (
                  <div>
                    {d.artifacts.map((a: any, i: number) => (
                      <article className="studio-file" key={i}>
                        <b>{d.objects[a.target]?.name}</b>
                        <pre>{a.body}</pre>
                      </article>
                    ))}
                  </div>
                ) : s.task_id === 39 ? (
                  <>
                    {rows.map((item: any) => (
                      <article
                        className="studio-paragraph"
                        key={item.id}
                        data-object-id={item.id}
                      >
                        <p>{item.text}</p>
                        <Classify item={item} api={api} />
                      </article>
                    ))}
                  </>
                ) : (
                  <>
                    <h2>{active.name}</h2>
                    <div className="studio-code-header">
                      Python <span>生成结果</span>
                    </div>
                    <pre className="studio-code">{active.code}</pre>
                    <div className="product-actions">
                      {["检查", "保存", "复制", "发送"].map((action) => (
                        <button
                          key={action}
                          disabled={api.busy}
                          onClick={async () => {
                            if (action === "复制" && navigator.clipboard)
                              await navigator.clipboard.writeText(active.code);
                            await api.mutate("action", focused, action);
                          }}
                        >
                          {action}
                        </button>
                      ))}
                    </div>
                    {d.checks
                      .filter((x: any) => x.target === focused)
                      .map((x: any, i: number) => (
                        <p
                          className={x.passed ? "product-ok" : "product-error"}
                          key={i}
                        >
                          {x.passed ? "✓ 语法检查通过" : "语法检查未通过"}
                        </p>
                      ))}
                    <p className="product-muted">
                      交付联系人：{s.source.recipient}
                    </p>
                  </>
                )}
              </section>
            </div>
          </>
        )}
      </main>
    </Frame>
  );
}
