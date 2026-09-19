import { useEffect, useState } from "react";
import { modules } from "./applicationModules";
import "./launchpad.css";
import { taskBrief } from "./taskBrief";

export function Launchpad({
  id,
  module,
  diagnostic,
}: {
  id: string;
  module: string;
  diagnostic: React.ReactNode;
}) {
  const [data, setData] = useState<any>(null),
    [error, setError] = useState(""),
    [debug, setDebug] = useState(false);
  const token = location.hash.slice(1),
    config = modules[module as keyof typeof modules];
  useEffect(() => {
    fetch(`/api/runs/${id}`, { headers: { Authorization: `Bearer ${token}` } })
      .then(async (r) => {
        const d = await r.json();
        if (!r.ok) throw Error(d.detail);
        setData(d);
      })
      .catch((e) => setError(String(e)));
  }, []);
  if (debug) return <>{diagnostic}</>;
  const s = data?.state,
    native = Object.keys(modules).includes(module);
  return (
    <div className="launchpad">
      <header>
        <span className="launch-brand">
          V<span>VideoICL</span>
        </span>
        <span>应用工作台</span>
        <span className="launch-user">周予安 · 个人工作区</span>
      </header>
      <main>
        <p className="launch-eyebrow">WORKSPACE</p>
        <h1>开始今天的工作</h1>
        <p className="launch-intro">打开应用，继续处理消息、文档与日常事务。</p>
        {error && <p role="alert">{error}</p>}
        <section className="launch-grid">
          <article className="launch-app">
            <div className="launch-icon" style={{ background: config.color }}>
              {" "}
              {module === "chat" ? "☏" : config.title.slice(4, 5)}{" "}
            </div>
            <h2>{config.title}</h2>
            <p>{config.subtitle}</p>
            {native ? (
              <a
                className="launch-open"
                href={
                  [
                    "media",
                    "blog",
                    "studio",
                    "travel",
                    "shop",
                    "bank",
                    "games",
                  ].includes(module)
                    ? `/native/product/${module}/${id}#${token}`
                    : module === "im"
                      ? `/native-assets/im/?run=${id}#${token}`
                      : `/native/${module}/${id}${["chat", "music", "code", "gomoku"].includes(module) ? "/" : ""}#${token}`
                }
              >
                打开应用 →
              </a>
            ) : (
              <>
                <p className="launch-pending">原应用录制适配待验收</p>
                <button className="launch-debug" onClick={() => setDebug(true)}>
                  进入开发诊断界面
                </button>
              </>
            )}
          </article>
          <article className="launch-brief">
            <span className="launch-eyebrow">待办事项</span>
            <h2>{s?.title || "正在载入…"}</h2>
            {s && (
              <>
                <p>{taskBrief(s, config.title)}</p>
                <div className="launch-note">
                  从此页开始录制，打开应用后保留首页与导航过程。
                </div>
              </>
            )}
          </article>
        </section>
        <footer>个人工作区 · 会话数据独立保存</footer>
      </main>
    </div>
  );
}
