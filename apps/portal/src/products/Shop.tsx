import { useState } from "react";
import {
  Frame,
  PageHead,
  Notice,
  Classify,
  Tags,
  type ProductAPI,
} from "./kit";
function ProductArt({ item, index }: { item: any; index: number }) {
  index = Math.max(
    0,
    [
      "帆布通勤背包",
      "不锈钢保温杯",
      "便携机械键盘",
      "桌面阅读灯",
      "旅行收纳包",
      "无线静音鼠标",
    ].indexOf(item.name),
  );
  return (
    <div className={`shop-art shop-art-${index % 6}`}>
      <svg viewBox="0 0 240 190" aria-label={item.name} role="img">
        {index % 6 === 0 ? (
          <>
            <path
              d="M82 65V50a38 38 0 0176 0v15"
              fill="none"
              stroke="currentColor"
              strokeWidth="9"
            />
            <rect
              x="62"
              y="60"
              width="115"
              height="112"
              rx="20"
              fill="currentColor"
            />
            <rect
              x="80"
              y="110"
              width="80"
              height="48"
              rx="8"
              fill="#ffffff44"
            />
            <path d="M83 78h71" stroke="#fff8" strokeWidth="3" />
          </>
        ) : index % 6 === 1 ? (
          <>
            <rect
              x="90"
              y="35"
              width="64"
              height="137"
              rx="15"
              fill="currentColor"
            />
            <rect x="92" y="24" width="60" height="24" rx="8" fill="#2b3239" />
            <path d="M102 59v89" stroke="#fff7" strokeWidth="7" />
          </>
        ) : index % 6 === 2 ? (
          <>
            <rect
              x="22"
              y="55"
              width="198"
              height="96"
              rx="12"
              fill="currentColor"
            />
            {Array.from({ length: 30 }, (_, i) => (
              <rect
                key={i}
                x={33 + (i % 10) * 18}
                y={66 + Math.floor(i / 10) * 22}
                width="14"
                height="17"
                rx="3"
                fill="#fff9"
              />
            ))}
            <rect x="70" y="132" width="100" height="10" rx="3" fill="#fff9" />
          </>
        ) : index % 6 === 3 ? (
          <>
            <path
              d="M119 153V91l36-42"
              fill="none"
              stroke="currentColor"
              strokeWidth="9"
            />
            <path d="M116 30l68 30-8 18-68-30z" fill="currentColor" />
            <ellipse cx="120" cy="160" rx="47" ry="10" fill="currentColor" />
          </>
        ) : index % 6 === 4 ? (
          <>
            <rect
              x="48"
              y="55"
              width="144"
              height="105"
              rx="28"
              fill="currentColor"
            />
            <path d="M58 78h124M91 55v105" stroke="#fff8" strokeWidth="3" />
            <rect x="157" y="75" width="9" height="21" rx="2" fill="#ddd" />
          </>
        ) : (
          <>
            <path
              d="M79 74a42 42 0 0184 0v45a42 42 0 01-84 0z"
              fill="currentColor"
            />
            <path d="M121 35v53" stroke="#fff8" strokeWidth="3" />
            <rect x="117" y="51" width="8" height="24" rx="4" fill="#fff9" />
          </>
        )}
      </svg>
    </div>
  );
}
export function Shop({ api }: { api: ProductAPI }) {
  const { s, d } = api,
    [page, setPage] = useState("home"),
    [selected, setSelected] = useState(""),
    [query, setQuery] = useState(""),
    [text, setText] = useState(s.outputs.target ?? "");
  const rows = s.items.map((x: any) => d.objects[x.id]),
    active = d.objects[selected];
  function open(id: string) {
    setSelected(id);
    setPage("detail");
  }
  const list =
    page === "cart"
      ? rows.filter((x: any) => d.collections.cart.includes(x.id))
      : page === "favorites"
        ? rows.filter((x: any) => d.collections.favorites.includes(x.id))
        : rows;
  const cartAction = (item: any) => (
    <div className="product-actions">
      {s.task_id === 55 && (
        <>
          <button
            className="product-primary"
            disabled={api.busy}
            onClick={() => api.mutate("action", item.id, "加入购物车")}
          >
            {"加入购物车"}
          </button>
          <button
            disabled={api.busy}
            onClick={() => api.mutate("action", item.id, "移出购物车")}
          >
            移出购物车
          </button>
          <button
            disabled={api.busy || item.starred}
            onClick={() => api.mutate("action", item.id, "收藏")}
          >
            {item.starred ? "♥ 已收藏" : "♡ 收藏"}
          </button>
        </>
      )}
      {s.task_id === 52 && (
        <button
          className="product-primary"
          disabled={api.busy}
          onClick={() => api.mutate("select", "", "", [item.id])}
        >
          {s.selection.includes(item.id) ? "✓ 已选购" : "选择此商品"}
        </button>
      )}
    </div>
  );
  return (
    <Frame
      brand="拾物商店"
      accent="#a04e35"
      page={page}
      navigate={setPage}
      tabs={[
        ["home", "发现好物"],
        ["products", "所有商品"],
        ["cart", `购物车 · ${d.collections.cart.length}`],
        ["favorites", "我的收藏"],
      ]}
      tools={
        <input
          placeholder="搜索商品"
          value={query}
          onChange={(e) => {
            setQuery(e.target.value);
            setPage("products");
          }}
        />
      }
    >
      <main className="product-main">
        <Notice api={api} />
        {page === "home" ? (
          <>
            <section className="shop-hero">
              <div>
                <span>EVERYDAY, WELL MADE.</span>
                <h1>
                  让日常，
                  <br />
                  多一点称心。
                </h1>
                <p>为通勤、工作与生活挑选实用好物。</p>
                <button
                  className="product-primary"
                  onClick={() => setPage("products")}
                >
                  逛逛本期精选 →
                </button>
              </div>
              <ProductArt item={rows[0]} index={0} />
            </section>
            <div className="product-section">
              <h2>本期精选</h2>
              <button onClick={() => setPage("products")}>查看全部 →</button>
            </div>
          </>
        ) : null}
        {page === "detail" && active ? (
          <>
            <button
              className="product-back"
              onClick={() => setPage("products")}
            >
              ← 所有商品
            </button>
            <div className="shop-detail">
              <ProductArt
                item={active}
                index={s.items.findIndex((x: any) => x.id === selected)}
              />
              <section>
                <span className="product-eyebrow">EVERYDAY ESSENTIALS</span>
                <h1>{active.name}</h1>
                <p>{active.text}</p>
                <strong className="shop-price">¥{active.price}.00</strong>
                <div className="shop-metrics">
                  <span>综合评分 {active.rating}/100</span>
                  <span>{active.comments} 条评价</span>
                  <span>已售 {active.sales}</span>
                  <span>库存 {active.stock}</span>
                </div>
                <Tags item={active} api={api} />
                {s.task_id === 48 && <Classify item={active} api={api} />}{" "}
                {cartAction(active)}
                {s.task_id === 45 && (
                  <section className="shop-note">
                    <h3>订单备注</h3>
                    <p>
                      商品：{s.source.text} · 数量：{s.source.quantity}
                    </p>
                    <label>
                      备注内容
                      <textarea
                        value={text}
                        onChange={(e) => setText(e.target.value)}
                        rows={3}
                      />
                    </label>
                    <button
                      className="product-primary"
                      disabled={api.busy}
                      onClick={() => api.mutate("save", "target", text)}
                    >
                      保存备注
                    </button>
                    {s.outputs.target && (
                      <p className="product-ok">已保存：{s.outputs.target}</p>
                    )}
                  </section>
                )}
              </section>
            </div>
          </>
        ) : (
          <>
            {page !== "home" && (
              <PageHead
                eyebrow="COLLECTION"
                title={
                  page === "cart"
                    ? "购物车"
                    : page === "favorites"
                      ? "我的收藏"
                      : "所有商品"
                }
                description={`${list.length} 件好物`}
              />
            )}
            <div className="shop-grid">
              {list
                .filter((x: any) => x.name.includes(query))
                .map((item: any) => (
                  <article
                    className="shop-card"
                    key={item.id}
                    data-object-id={item.id}
                  >
                    <button
                      className="shop-image-link"
                      onClick={() => open(item.id)}
                    >
                      <ProductArt
                        item={item}
                        index={s.items.findIndex((x: any) => x.id === item.id)}
                      />
                    </button>
                    <div>
                      <small>{item.tags.join(" · ") || "日用精选"}</small>
                      <button
                        className="product-text-link"
                        onClick={() => open(item.id)}
                      >
                        <h2>{item.name}</h2>
                      </button>
                      <p>
                        <strong>¥{item.price}.00</strong>
                        <span>
                          {item.rating}/100 · {item.comments} 条评价
                        </span>
                      </p>
                      <p className="product-muted">
                        已售 {item.sales} · 库存 {item.stock}
                      </p>
                      {s.task_id === 48 && <Classify item={item} api={api} />}{" "}
                      {cartAction(item)}
                    </div>
                  </article>
                ))}
            </div>
            {list.length === 0 && (
              <div className="product-empty">
                这里还没有商品。
                <button onClick={() => setPage("products")}>继续逛逛 →</button>
              </div>
            )}
          </>
        )}
      </main>
    </Frame>
  );
}
