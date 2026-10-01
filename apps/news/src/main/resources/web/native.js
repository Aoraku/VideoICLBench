const match = location.pathname.match(/^\/native\/news\/([a-f0-9]{32})/);
if (match)
  start(match[1]).catch((e) => {
    document.querySelector("#news-app").textContent = "新闻服务暂不可用：" + e.message;
  });
async function start(id) {
  const key = `vic-news:${id}`,
    token = location.hash.slice(1) || sessionStorage.getItem(key) || "";
  sessionStorage.setItem(key, token);
  let state,
    epoch,
    page = "home",
    selected = "",
    query = "",
    scopeId = "",
    period = "",
    menu = "",
    busy = false,
    notice = "";
  const reading = new Set();
  const esc = (value) =>
    String(value ?? "").replace(
      /[&<>"']/g,
      (c) =>
        ({
          "&": "&amp;",
          "<": "&lt;",
          ">": "&gt;",
          '"': "&quot;",
          "'": "&#39;",
        })[c],
    );
  async function call(path = "", body) {
    const r = await fetch(`/api/runs/${id}${path}`, {
      method: body ? "POST" : "GET",
      headers: {
        Authorization: `Bearer ${token}`,
        "Content-Type": "application/json",
      },
      body: body ? JSON.stringify(body) : undefined,
    });
    const d = await r.json();
    if (!r.ok) throw Error(d.detail);
    state = d.state;
    epoch = d.epoch;
  }
  async function command(op, target = "", value = "", ids = []) {
    if (busy) return;
    busy = true;
    document.querySelectorAll("#news-app button").forEach((b) => (b.disabled = true));
    try {
      await call("/commands", {
        epoch,
        op,
        target,
        value,
        ids,
        action_id: crypto.randomUUID(),
      });
      notice = "已保存";
      menu = "";
    } catch (e) {
      notice = e.message;
    } finally {
      busy = false;
      render();
    }
  }
  await call();
  for (const articleId of state.domain.collections.reading_list || []) reading.add(articleId);
  history.replaceState({}, "", location.pathname);
  const names = {
    home: "首页",
    articles: "全部文章",
    reading: "阅读清单",
    favorites: "我的收藏",
    editor: "内容管理",
  };
  if(state.v2_worksets&&state.task_id===33){names.read='已读文章';names.hidden='隐藏文章'}
  const identity=item=>state.v2_worksets?`<p class="meta">${esc(item.scope_name)} · 文章编号 ${esc(item.record_code)} · ${esc(item.period)}</p>`:'';
  function scopeFilter(){
    if(!state.v2_worksets)return '';
    const kind=state.scopes[0].kind;
    return `<section class="news-scope" aria-label="资料筛选"><p><b>本次整理：</b>${state.scopes.filter(s=>s.requested).map(s=>esc(s.name)).join('、')}</p><p>${esc(state.public_parameters)}</p><form id="scopeFilter"><label>${esc(kind)}<select name="scope" aria-label="${esc(kind)}"><option value="">全部</option>${state.scopes.map(s=>`<option value="${s.id}" ${scopeId===s.id?'selected':''}>${esc(s.name)}</option>`).join('')}</select></label><label>发布月份<select name="period" aria-label="发布月份"><option value="">全部</option>${['2026-01','2025-12'].map(v=>`<option ${period===v?'selected':''}>${v}</option>`).join('')}</select></label><button type="submit">筛选文章</button></form></section>`;
  }
  const cover = (i) =>
    `<div class="news-cover cover-${i % 3}"><span>${["CITY JOURNAL", "WEEKLY REPORT", "CULTURE & LIFE"][i % 3]}</span><i></i><b>${["城 市 · 观 察", "公 共 · 生 活", "日 常 · 记 录"][i % 3]}</b></div>`;
  const publishedAt = (item) => esc(item.created_at.replace("T", " ").slice(0, 16)) + " UTC";
  function articleCard(item, i) {
    const obj = state.domain.objects[item.id];
    return `<article class="news-card" data-id="${item.id}">${cover(i)}<div class="news-card-body"><div class="meta">${esc(item.publisher)} · 发布于 ${publishedAt(item)}</div>${identity(item)}<button class="news-title" data-open="${item.id}">${esc(item.name)}</button><p>${esc(item.text)}</p><div class="news-card-footer"><span>${item.comments} 评论 · ${item.tag_count} 标签</span>${obj.read ? "<span>已读</span>" : ""}${state.domain.settings.reading_article?.includes(item.id) ? '<span class="news-chip">已选择阅读</span>' : ""}${obj.starred ? "<span>★ 已收藏</span>" : ""}${obj.label ? `<span class="news-chip">${esc(obj.label)}</span>` : ""}</div>${page === "articles" ? actions(item) : ""}</div></article>`;
  }
  function actions(item) {
    const obj = state.domain.objects[item.id];
    return `<div class="news-tools">${[23, 24].includes(state.task_id) ? `<div class="news-dropdown"><button data-menu="${item.id}" aria-haspopup="listbox" aria-expanded="${menu === item.id}">${obj.label ? esc(obj.label) : "设置分类"} ▾</button>${menu === item.id ? `<div class="news-options" role="listbox">${["", ...state.options].map((label) => `<button role="option" data-label="${esc(label)}" data-target="${item.id}">${esc(label || "清除分类")}</button>`).join("")}</div>` : ""}</div>` : ""}${state.task_id === 30 ? `<button data-reading="${item.id}">${reading.has(item.id) ? "✓ 已加入待选" : "加入阅读清单"}</button>` : ""}${state.task_id === 33 ? state.options.map((op) => { const done = (op === "已读" && obj.read) || (op === "收藏" && obj.starred); const label = op === "已读" ? (done ? "✓ 已读" : "标为已读") : (done ? "✓ 已收藏" : op); return `<button data-action="${esc(op)}" data-target="${item.id}" data-done="${done}" ${done ? "disabled" : ""}>${esc(label)}</button>`; }).join("") : ""}</div>`;
  }
  function render() {
    const all = state.items.filter((x) => page==='hidden'?state.domain.objects[x.id].hidden:!state.domain.objects[x.id].hidden),
      items = all.filter((x) => (x.name + " " + x.text).includes(query)&&(!scopeId||x.scope_id===scopeId)&&(!period||x.period===period)&&(page!=='read'||state.domain.objects[x.id].read)),
      obj = state.domain.objects[selected];
    document.querySelector("#news-app").innerHTML = `<header class="news-header"><a href="#" data-page="home" class="news-brand">VIC<span>NEWS</span></a><nav>${Object.entries(
      names,
    )
      .map(
        ([k, v]) =>
          `<button data-page="${k}" class="${page === k ? "active" : ""}">${v}</button>`,
      )
      .join(
        "",
      )}</nav><span class="news-account">周予安 · 编辑部</span></header><main class="news-main"><div class="news-breadcrumb">VIC News / ${names[page] || "文章详情"}</div>${notice ? `<div class="news-notice" role="status">${esc(notice)}</div>` : ""}
  ${scopeFilter()}${
    page === "home"
      ? `<section class="news-hero"><div><span class="news-overline">THE DAILY PERSPECTIVE</span><h1>在日常里，<br>看见城市的变化。</h1><p>关注公共生活，记录身边值得阅读的故事。</p><button data-page="articles">浏览全部文章 →</button></div>${cover(0)}</section><div class="news-section-title"><h2>编辑精选</h2><button data-page="articles">查看全部 →</button></div><div class="news-grid">${all.slice(0, 3).map(articleCard).join("")}</div>`
      : page === "detail" && obj
        ? `<article class="news-detail"><button data-page="articles" class="news-back">← 返回文章列表</button><div class="meta">${esc(obj.publisher)} · 发布于 ${publishedAt(obj)}</div>${state.domain.settings.reading_article?.includes(obj.id) ? '<p class="news-saved" role="status">✓ 已选择阅读</p>' : ""}<h1>${esc(obj.name)}</h1>${identity(obj)}<p class="news-deck">${esc(obj.text)}</p>${cover(state.items.findIndex((x) => x.id === selected))}<p>${esc(obj.text)}</p><p>报道围绕社区公共服务展开，结合实地观察与居民反馈，呈现日常生活中的具体需求。完整的后续安排将由相关服务机构通过公开渠道发布。</p>${actions(obj)}</article>`
        : page === "editor"
          ? `<section class="news-editor"><aside><h2>内容管理</h2><p>文章草稿</p><button data-edit="target">${esc(state.source.text)}</button></aside><form id="editorForm"><span class="news-overline">ARTICLE DRAFT</span><h1>编辑文章资料</h1><p>来源：${esc(state.source.publisher)} · 简称 ${esc(state.source.publisher_short)}</p><label>原始标题<div class="news-source">${esc(state.source.text)}</div></label>${state.task_id === 20 ? `<p>待整理标签：${state.source.tags.map(esc).join("、")}</p>` : ""}<label>${state.task_id === 20 ? "文章标签" : "文章标题"}<textarea name="text" rows="4">${esc(state.outputs.target ?? (state.task_id === 20 ? "" : state.source.text))}</textarea></label><button type="submit">保存草稿</button>${state.outputs.target !== undefined ? '<span class="news-saved">✓ 草稿已保存</span>' : ""}</form></section>`
          : `<div class="news-section-title"><div><span class="news-overline">YOUR READING DESK</span><h1>${names[page] || "全部文章"}</h1></div><form id="newsSearch"><input aria-label="搜索文章" name="q" value="${esc(query)}" placeholder="搜索标题或正文"><button>搜索</button></form></div><div class="news-grid">${(page === "reading" ? items.filter((x) => state.domain.collections.reading_list?.includes(x.id)) : page === "favorites" ? items.filter((x) => state.domain.collections.favorites?.includes(x.id)) : items).map(articleCard).join("") || '<div class="news-empty">这里还没有文章。前往全部文章浏览与整理。</div>'}</div>${state.task_id === 30 && page === "articles" ? `<div class="news-reading-save"><span>待加入 ${reading.size} 篇文章</span><button id="saveReading">保存阅读清单</button></div>` : ""}`
  }
  <footer class="news-footer">VIC News　·　阅读与记录</footer></main>`;
    document.querySelectorAll("[data-page]").forEach(
      (el) =>
        (el.onclick = (e) => {
          e.preventDefault();
          page = el.dataset.page;
          query = "";
          notice = "";
          menu = "";
          render();
          window.scrollTo(0, 0);
        }),
    );
    document.querySelector('#scopeFilter')?.addEventListener('submit',e=>{e.preventDefault();const form=new FormData(e.target);scopeId=form.get('scope');period=form.get('period');page='articles';menu='';render()});
    document.querySelectorAll("[data-open]").forEach(
      (el) =>
        (el.onclick = async () => {
          selected = el.dataset.open;
          page = "detail";
          if (state.task_id === 29) await command("select", "", "", [selected]);
          else render();
          window.scrollTo(0, 0);
        }),
    );
    document.querySelectorAll("[data-menu]").forEach(
      (el) =>
        (el.onclick = () => {
          menu = menu === el.dataset.menu ? "" : el.dataset.menu;
          render();
        }),
    );
    document
      .querySelectorAll("[data-label]")
      .forEach(
        (el) =>
          (el.onclick = () =>
            command("label", el.dataset.target, el.dataset.label)),
      );
    document
      .querySelectorAll("[data-action]")
      .forEach(
        (el) =>
          (el.onclick = () =>
            command("action", el.dataset.target, el.dataset.action)),
      );
    document.querySelectorAll("[data-reading]").forEach(
      (el) =>
        (el.onclick = () => {
          reading.has(el.dataset.reading)
            ? reading.delete(el.dataset.reading)
            : reading.add(el.dataset.reading);
          render();
        }),
    );
    const form = document.querySelector("#editorForm");
    if (form)
      form.onsubmit = (e) => {
        e.preventDefault();
        command("save", "target", new FormData(form).get("text"));
      };
    const search = document.querySelector("#newsSearch");
    if (search)
      search.onsubmit = (e) => {
        e.preventDefault();
        query = new FormData(search).get("q");
        render();
      };
    const save = document.querySelector("#saveReading");
    if (save) save.onclick = () => command("select", "", "", [...reading]);
    document.querySelectorAll("#news-app button").forEach((b) => (b.disabled = busy || b.dataset.done === "true"));
  }
  render();
}
