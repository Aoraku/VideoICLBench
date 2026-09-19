import React from "react";
import { LabelMenu } from "../LabelMenu";
export type ProductAPI = {
  s: any;
  d: any;
  busy: boolean;
  notice: string;
  mutate: (
    op: string,
    target?: string,
    value?: string,
    ids?: string[],
  ) => Promise<boolean>;
};
export function Frame({
  brand,
  accent,
  page,
  navigate,
  tabs,
  children,
  tools,
}: {
  brand: string;
  accent: string;
  page: string;
  navigate: (p: string) => void;
  tabs: [string, string][];
  children: React.ReactNode;
  tools?: React.ReactNode;
}) {
  return (
    <div
      className="product"
      style={{ "--product-accent": accent } as React.CSSProperties}
    >
      <aside className="product-nav">
        <button className="product-brand" onClick={() => navigate("home")}>
          <b>{brand.slice(0, 1)}</b>
          {brand}
        </button>
        <div className="product-space">
          个人工作区 <span>⌄</span>
        </div>
        <nav>
          {tabs.map(([id, label]) => (
            <button
              key={id}
              className={page === id ? "active" : ""}
              onClick={() => navigate(id)}
            >
              <span>
                {(
                  {
                    home: "◫",
                    library: "▤",
                    drafts: "▧",
                    published: "◉",
                    tags: "◇",
                    models: "◈",
                    prompts: "▤",
                    documents: "▥",
                    routes: "⇆",
                    passengers: "◎",
                    bookings: "▦",
                    products: "▦",
                    cart: "▣",
                    favorites: "♡",
                    accounts: "▤",
                    transactions: "⇄",
                    transfer: "↗",
                    contacts: "◎",
                    reminders: "◷",
                    watchlist: "▷",
                    history: "◷",
                    queue: "≡",
                  } as any
                )[id] || "·"}
              </span>
              {label}
            </button>
          ))}
        </nav>
        <footer>
          <div className="product-avatar">予</div>
          <div>
            周予安<small>个人账户</small>
          </div>
        </footer>
      </aside>
      <div className="product-content">
        <header className="product-topbar">
          <span>{tabs.find((t) => t[0] === page)?.[1] || "详情"}</span>
          <div>
            {tools}
            <span className="product-online">● 已同步</span>
          </div>
        </header>
        {children}
      </div>
    </div>
  );
}
export function PageHead({
  eyebrow,
  title,
  description,
  action,
}: {
  eyebrow?: string;
  title: string;
  description?: string;
  action?: React.ReactNode;
}) {
  return (
    <div className="product-page-head">
      <div>
        <span className="product-eyebrow">{eyebrow}</span>
        <h1>{title}</h1>
        {description && <p>{description}</p>}
      </div>
      {action}
    </div>
  );
}
export function Notice({ api }: { api: ProductAPI }) {
  return api.notice ? (
    <div className="product-notice" role="status">
      {api.notice}
    </div>
  ) : null;
}
export function Tags({ item, api }: { item: any; api: ProductAPI }) {
  const obj = api.d.objects[item.id];
  return (
    <div className="product-tags">
      {item.tags?.map((t: string) => (
        <span key={t}>{t}</span>
      ))}
      {obj.label && <b>{obj.label}</b>}
      {obj.starred && <b>已收藏</b>}
      {obj.published && <b>已发布</b>}
    </div>
  );
}
export function Classify({ item, api }: { item: any; api: ProductAPI }) {
  return (
    <LabelMenu
      label={`分类 ${item.name}`}
      value={api.d.objects[item.id].label}
      options={api.s.options}
      disabled={api.busy}
      onChange={(value) => {
        void api.mutate("label", item.id, value);
      }}
    />
  );
}
export function DataRows({
  items,
  columns,
  renderActions,
  open,
}: {
  items: any[];
  columns: [string, string, (v: any) => React.ReactNode][];
  renderActions?: (v: any) => React.ReactNode;
  open?: (id: string) => void;
}) {
  return (
    <table className="product-table">
      <thead>
        <tr>
          {columns.map(([k, title]) => (
            <th key={k}>{title}</th>
          ))}
          {renderActions && <th>操作</th>}
        </tr>
      </thead>
      <tbody>
        {items.map((item) => (
          <tr key={item.id} data-object-id={item.id}>
            {columns.map(([k, , render], index) => (
              <td key={k}>
                {index === 0 && open ? (
                  <button
                    className="product-text-link"
                    onClick={() => open(item.id)}
                  >
                    {render(item)}
                  </button>
                ) : (
                  render(item)
                )}
              </td>
            ))}
            {renderActions && <td>{renderActions(item)}</td>}
          </tr>
        ))}
      </tbody>
    </table>
  );
}
export const dateOf = (item: any) =>
  `2026-01-${String(15 - (item.age_days || 0)).padStart(2, "0")}`;
export const minutes = (seconds: number) =>
  `${Math.floor(seconds / 60)}:${String(seconds % 60).padStart(2, "0")}`;
