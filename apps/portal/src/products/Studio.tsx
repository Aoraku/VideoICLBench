import { useRef, useState } from "react";
import { Frame, PageHead, Notice, Classify, type ProductAPI } from "./kit";
export function Studio({ api }: { api: ProductAPI }) {
  const { s, d } = api,
    [page, setPage] = useState("home"),
    [text, setText] = useState(s.outputs.target ?? s.source.text),
    [focused, setFocused] = useState(s.items[0].id),
    [tab, setTab] = useState("outputs"),
    [copyError, setCopyError] = useState(""),
    [copyBusy, setCopyBusy] = useState(false),
    actionPending = useRef(false),
    paragraphs = useRef<Record<string, HTMLElement | null>>({});
  const rows = s.items.map((x: any) => d.objects[x.id]),
    active = d.objects[focused];
  function statusOf(id: string) {
    return {
      checked: d.checks.filter((x: any) => x.target === id).at(-1),
      saved: d.artifacts.some((x: any) => x.target === id && x.kind === "document"),
      copied: d.clipboard_history.some((x: any) => x.target === id),
      sent: d.messages.some((x: any) => x.reference === id && x.sender === "self"),
    };
  }
  const activeStatus = statusOf(focused);
  function navigate(next: string) {
    api.clearNotice?.();
    setCopyError("");
    setPage(next);
  }
  async function perform(action: string) {
    if (actionPending.current) return;
    actionPending.current = true;
    setCopyBusy(true);
    setCopyError("");
    try {
      if (action === "复制") {
        if (!navigator.clipboard) throw Error("当前浏览器无法访问剪贴板，请使用支持剪贴板的浏览器打开应用。");
        await navigator.clipboard.writeText(active.code);
      }
      await api.mutate("action", focused, action);
    } catch {
      setCopyError("未能写入剪贴板，请检查浏览器权限后重试。");
    } finally {
      actionPending.current = false;
      setCopyBusy(false);
    }
  }
  return (
    <Frame
      brand="VIC Studio"
      accent="#7564a6"
      page={page}
      navigate={navigate}
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
                <button onClick={() => navigate("prompts")}>整理提示词</button>
                <button onClick={() => navigate("documents")}>
                  打开内容项目
                </button>
                <button onClick={() => navigate("models")}>选择模型</button>
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
                    navigate("documents");
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
                    disabled={api.busy || d.settings.model?.includes(item.id)}
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
            {s.task_id === 43 && <p className="studio-progress">
              共 {rows.length} 个文件 · 已检查 {rows.filter((x: any) => statusOf(x.id).checked).length} 个 ·
              已保存 {rows.filter((x: any) => statusOf(x.id).saved).length} 个 ·
              已复制 {rows.filter((x: any) => statusOf(x.id).copied).length} 个 ·
              已发送 {rows.filter((x: any) => statusOf(x.id).sent).length} 个
            </p>}
            <div className="studio-project-layout">
              <aside>
                {rows.map((item: any) => (
                  <button
                    key={item.id}
                    className={focused === item.id ? "active" : ""}
                    onClick={() => {
                      setFocused(item.id);
                      setTab("outputs");
                      setCopyError("");
                      api.clearNotice?.();
                      if (s.task_id === 39) paragraphs.current[item.id]?.scrollIntoView({ block: "center" });
                    }}
                  >
                    {item.name}
                    {s.task_id === 43 && <small className="studio-file-status">
                      {statusOf(item.id).checked ? (statusOf(item.id).checked.passed ? "检查通过" : "检查未通过") : "未检查"}
                      {statusOf(item.id).saved && " · 已保存"}
                      {statusOf(item.id).copied && " · 已复制"}
                      {statusOf(item.id).sent && " · 已发送"}
                    </small>}
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
                  {s.task_id === 43 && <button className={tab === "sent" ? "active" : ""} onClick={() => { setTab("sent"); api.clearNotice?.(); }}>已发送</button>}
                </div>
                {tab === "saved" ? (
                  <div>
                    {!d.artifacts.length && <p className="product-muted">还没有保存文件。</p>}
                    {d.artifacts.map((a: any, i: number) => (
                      <article className="studio-file" key={i}>
                        <b>{d.objects[a.target]?.name}</b>
                        <pre>{a.body}</pre>
                      </article>
                    ))}
                  </div>
                ) : tab === "sent" ? (
                  <div>
                    {!d.messages.length && <p className="product-muted">还没有发送记录。</p>}
                    {d.messages.map((message: any) => <article className="studio-file" key={message.id}>
                      <b>{d.objects[message.reference]?.name}</b>
                      <p>收件人：{d.objects[message.recipient]?.name || message.recipient}</p>
                      <pre>{message.body}</pre>
                    </article>)}
                  </div>
                ) : s.task_id === 39 ? (
                  <>
                    {rows.map((item: any) => (
                      <article
                        className="studio-paragraph"
                        key={item.id}
                        data-object-id={item.id}
                        ref={(node) => { paragraphs.current[item.id] = node; }}
                      >
                        <h3>{item.name}</h3>
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
                          disabled={api.busy || copyBusy || (action === "保存" && activeStatus.saved) || (action === "发送" && activeStatus.sent)}
                          onClick={() => void perform(action)}
                        >
                          {action === "保存" && activeStatus.saved ? "✓ 已保存" : action === "发送" && activeStatus.sent ? "✓ 已发送" : action === "复制" && activeStatus.copied ? "再次复制" : action}
                        </button>
                      ))}
                    </div>
                    {copyError && <p className="product-error" role="alert">{copyError}</p>}
                    {d.checks
                      .filter((x: any) => x.target === focused).slice(-1)
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
