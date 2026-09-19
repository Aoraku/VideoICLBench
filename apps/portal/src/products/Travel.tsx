import { useState } from "react";
import { Frame, PageHead, Notice, Classify, type ProductAPI } from "./kit";
const time = (n: number) =>
  `${String(6 + Math.floor(n / 6)).padStart(2, "0")}:${String((n % 6) * 10).padStart(2, "0")}`;
export function Travel({ api }: { api: ProductAPI }) {
  const { s, d } = api,
    [page, setPage] = useState("home"),
    [text, setText] = useState(s.outputs.target ?? ""),
    [selected, setSelected] = useState(""),
    [query, setQuery] = useState("");
  const rows = s.items.map((x: any) => d.objects[x.id]),
    active = d.objects[selected];
  function open(id: string) {
    setSelected(id);
    setPage("details");
  }
  return (
    <Frame
      brand="行远旅行"
      accent="#087d86"
      page={page}
      navigate={setPage}
      tabs={[
        ["home", "旅行首页"],
        ["routes", "车次查询"],
        ["bookings", "我的订单"],
        ["passengers", "常用旅客"],
      ]}
    >
      <main className="product-main">
        <Notice api={api} />
        {page === "home" ? (
          <>
            <section className="travel-hero">
              <span>JOURNEYS THAT STAY WITH YOU</span>
              <h1>下一站，去看看。</h1>
              <p>一段从容的旅程，从选好一张车票开始。</p>
              <div className="travel-search">
                <label>
                  出发城市<b>北京</b>
                </label>
                <span>⇄</span>
                <label>
                  到达城市<b>上海</b>
                </label>
                <label>
                  出发日期<b>2026-01-15 · 周四</b>
                </label>
                <button
                  className="product-primary"
                  onClick={() => setPage("routes")}
                >
                  查询车次
                </button>
              </div>
            </section>
            <div className="product-section">
              <h2>旅行服务</h2>
            </div>
            <div className="travel-services">
              <button onClick={() => setPage("passengers")}>
                <span>◎</span>
                <h3>常用旅客</h3>
                <p>核对姓名，出行更省心</p>
              </button>
              <button onClick={() => setPage("bookings")}>
                <span>▦</span>
                <h3>我的订单</h3>
                <p>查看预订与行程信息</p>
              </button>
              <button onClick={() => setPage("routes")}>
                <span>⇆</span>
                <h3>高铁出行</h3>
                <p>比较时间、票价与换乘</p>
              </button>
            </div>
          </>
        ) : page === "passengers" ? (
          <>
            <PageHead
              eyebrow="PASSENGERS"
              title="常用旅客"
              description="填写与旅客资料一致的姓名，并按要求保存显示格式。"
            />
            <section className="travel-passenger">
              <div className="product-avatar">
                {s.source.surname.slice(0, 1)}
              </div>
              <h2>
                {s.source.surname} {s.source.given_name}
              </h2>
              <dl>
                <dt>姓 / Surname</dt>
                <dd>{s.source.surname}</dd>
                <dt>名 / Given name</dt>
                <dd>{s.source.given_name}</dd>
              </dl>
              <label>
                旅客显示姓名
                <input value={text} onChange={(e) => setText(e.target.value)} />
              </label>
              <button
                className="product-primary"
                disabled={api.busy || s.task_id !== 44}
                onClick={() => api.mutate("save", "target", text)}
              >
                保存旅客
              </button>
              {s.outputs.target && (
                <p className="product-ok">已保存：{s.outputs.target}</p>
              )}
            </section>
          </>
        ) : page === "bookings" ? (
          <>
            <PageHead eyebrow="MY TRIPS" title="我的订单" />
            {d.artifacts
              .filter((a: any) => a.kind === "booking")
              .map((a: any, i: number) => (
                <article className="travel-ticket" key={i}>
                  <h2>{d.objects[a.target].name}</h2>
                  <p>北京南 → 上海虹桥 · 2026-01-15</p>
                  <strong>¥{a.price}</strong>
                  <span className="product-ok">预订成功</span>
                </article>
              ))}
            {!d.artifacts.length && (
              <div className="product-empty">
                还没有订单。选择合适的车次，开始安排旅程。
                <button onClick={() => setPage("routes")}>查询车次 →</button>
              </div>
            )}
          </>
        ) : page === "details" && active ? (
          <>
            <button className="product-back" onClick={() => setPage("routes")}>
              ← 返回车次列表
            </button>
            <PageHead
              eyebrow="ITINERARY"
              title={active.name}
              description="2026-01-15 · 二等座"
            />
            <section className="travel-ticket">
              <div className="travel-stations">
                <div>
                  <b>{time(active.departure)}</b>
                  <span>北京南</span>
                </div>
                <div>
                  <small>
                    {active.duration} 分钟 · 换乘 {active.transfers} 次
                  </small>
                  <div className="travel-line">───────── →</div>
                </div>
                <div>
                  <b>
                    {time(active.departure + Math.floor(active.duration / 10))}
                  </b>
                  <span>上海虹桥</span>
                </div>
              </div>
              <h2>¥{active.price}</h2>
              {s.task_id === 47 && <Classify item={active} api={api} />}
              <button
                className="product-primary"
                disabled={api.busy || ![51, 54].includes(s.task_id)}
                onClick={() =>
                  s.task_id === 54
                    ? api.mutate("action", active.id, "确认预订")
                    : api.mutate("select", "", "", [active.id])
                }
              >
                {s.task_id === 51 ? "选择此行程" : "确认预订"}
              </button>
              {s.selection.includes(active.id) && (
                <p className="product-ok">✓ 已选择此行程</p>
              )}
              {d.artifacts.some((a: any) => a.target === active.id) && (
                <p className="product-ok">✓ 预订成功，可在我的订单查看</p>
              )}
            </section>
          </>
        ) : (
          <>
            <PageHead
              eyebrow="TRAIN SEARCH"
              title="北京 → 上海"
              description="2026-01-15 · 共 6 个行程方案"
              action={
                <input
                  placeholder="搜索车次"
                  value={query}
                  onChange={(e) => setQuery(e.target.value)}
                />
              }
            />
            <div className="travel-results-head">
              车次 / 出发与到达 <span>耗时与换乘</span>
              <span>票价</span>
            </div>
            {rows
              .filter((x: any) => x.name.includes(query))
              .map((item: any) => (
                <article
                  className="travel-result"
                  key={item.id}
                  data-object-id={item.id}
                >
                  <div>
                    <button
                      className="product-text-link"
                      onClick={() => open(item.id)}
                    >
                      <b>{item.name}</b>
                    </button>
                    <p>
                      {time(item.departure)} 北京南 <span>→</span> 上海虹桥
                    </p>
                  </div>
                  <div>
                    <b>{item.duration} 分钟</b>
                    <small>
                      {item.transfers === 0
                        ? "直达"
                        : `换乘 ${item.transfers} 次`}
                    </small>
                  </div>
                  <div>
                    <strong>¥{item.price}</strong>
                    <small>二等座 · 有票</small>
                  </div>
                  <div>
                    {s.task_id === 47 ? (
                      <Classify item={item} api={api} />
                    ) : (
                      <button
                        className="product-primary"
                        onClick={() => open(item.id)}
                      >
                        查看行程
                      </button>
                    )}
                  </div>
                </article>
              ))}
          </>
        )}
      </main>
    </Frame>
  );
}
