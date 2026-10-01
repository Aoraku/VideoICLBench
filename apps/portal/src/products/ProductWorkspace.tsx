import { useEffect, useRef, useState } from "react";
import { Blog } from "./Blog";
import { Studio } from "./Studio";
import { Travel } from "./Travel";
import { Shop } from "./Shop";
import { ShopProjects } from "./ShopProjects";
import { Bank } from "./Bank";
import { Media } from "./Media";
import { Games } from "./Games";
import { TravelProjects } from "./TravelProjects";
import { Screening } from "./Screening";
import { StudioProjects } from "./StudioProjects";
import { Publishing } from "./Publishing";
import { Editorial } from "./Editorial";
import { Procurement } from "./Procurement";
import type { ProductAPI } from "./kit";
import "./products.css";
export function ProductWorkspace({
  module,
  id,
}: {
  module: string;
  id: string;
}) {
  const key = `vic-product:${id}`,
    token = useRef(location.hash.slice(1) || sessionStorage.getItem(key) || ""),
    [data, setData] = useState<any>(null),
    [busy, setBusy] = useState(false),
    [notice, setNotice] = useState(""),
    pending = useRef(false);
  async function request(method = "GET", body?: any) {
    const r = await fetch(
      `/api/runs/${id}${method === "POST" ? "/commands" : ""}`,
      {
        method,
        headers: {
          Authorization: `Bearer ${token.current}`,
          "Content-Type": "application/json",
        },
        body: body ? JSON.stringify(body) : undefined,
      },
    );
    const result = await r.json();
    if (!r.ok)
      throw Error(
        typeof result.detail === "string"
          ? result.detail
          : "操作未完成，请重试",
      );
    return result;
  }
  useEffect(() => {
    sessionStorage.setItem(key, token.current);
    void request()
      .then(setData)
      .catch((e) => setNotice(String(e)));
  }, []);
  async function mutate(
    op: string,
    target = "",
    value = "",
    ids: string[] = [],
  ) {
    if (pending.current) return false;
    pending.current = true;
    setBusy(true);
    try {
      const next = await request("POST", {
        epoch: data.epoch,
        action_id: crypto.randomUUID(),
        op,
        target,
        value,
        ids,
      });
      setData(next);
      setNotice(
        op === "label"
          ? `分类已保存：${value || "未分类"}`
          : op === "order"
            ? "顺序已保存"
            : op === "save"
              ? "内容已保存"
              : op === "action"
                ? (value === "检查" ? "检查已完成" : `${value}成功`)
                : "操作已保存",
      );
      return true;
    } catch (e) {
      setNotice(String(e));
      return false;
    } finally {
      pending.current = false;
      setBusy(false);
    }
  }
  if (!data)
    return (
      <div className="product-loading">
        <h1>正在打开应用</h1>
        <p>{notice || "正在载入你的个人工作区…"}</p>
      </div>
    );
  const Component = data.state.workflow === 'shop_projects' && module==='shop' ? ShopProjects : data.state.workflow === 'travel_projects' && module==='travel' ? TravelProjects : data.state.workflow === 'screening' ? Screening : data.state.workflow === 'studio_projects' && module === 'studio' ? StudioProjects : data.state.workflow === 'publishing' && module === 'blog' ? Publishing : data.state.workflow === 'editorial_projects' && module === 'blog' ? Editorial : data.state.workflow === 'procurement' ? Procurement : (
    {
      blog: Blog,
      studio: Studio,
      travel: Travel,
      shop: Shop,
      bank: Bank,
      media: Media,
      games: Games,
    } as Record<string, React.ComponentType<{ api: ProductAPI }>>
  )[module];
  if (!Component || (data.state.app !== module && !data.state.linked_apps?.includes(module)))
    return <p role="alert">应用与会话不匹配</p>;
  return (
    <Component
      api={{ s: data.state, d: data.state.domain, busy, notice, mutate, clearNotice: () => setNotice(""),
             downloadFile: async (fileId, name) => {
               const response = await fetch(`/api/runs/${id}/files/${encodeURIComponent(fileId)}`, {headers:{Authorization:`Bearer ${token.current}`}});
               if(!response.ok) throw Error('文件无法下载');
               const url = URL.createObjectURL(await response.blob()), anchor=document.createElement('a');
               anchor.href=url;anchor.download=name;anchor.click();setTimeout(()=>URL.revokeObjectURL(url),1000);
             },
             applicationLink: (app, query = {}) => {
               const path = app === 'im' ? '/native-assets/im/' : app === 'news' ? `/native/news/${id}` : `/native/product/${app}/${id}`;
               if(app==='im') query={...query,run:id};
               const search = new URLSearchParams(query).toString();
               return `${path}${search ? '?'+search : ''}#${token.current}`;
             },
             mediaUrl: target => `/api/runs/${id}/media/${encodeURIComponent(target)}` }}
    />
  );
}
