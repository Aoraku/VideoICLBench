import { useState } from "react";
import {useWorksets,WorksetBar,WorksetIdentity,CollectToWorkset,SavedWorksets,ReminderChannel} from './Worksets';
import {
  Frame,
  PageHead,
  Notice,
  Classify,
  DataRows,
  type ProductAPI,
} from "./kit";
const dateTime = (value: string) => value ? value.replace("T", " ").slice(0, 16) + " UTC" : "—";
const money = (n: number) =>
  n.toLocaleString("zh-CN", {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  });
export function Bank({ api }: { api: ProductAPI }) {
  const { s, d } = api,
    [page, setPage] = useState("home"),
    [selected, setSelected] = useState(""),
    [text, setText] = useState(s.outputs.target ?? ""),
    [query, setQuery] = useState("");
  const view=useWorksets(api);
  const rows = s.items.map((x: any) => d.objects[x.id]).filter(view.visible),
    active = d.objects[selected];
  const balance = (item: any) => d.balances[item.id] / 100;
  const transferred = (id: string) => d.ledger.some((x: any) => x.account === "self" && x.counterparty === id);
  function open(id: string) {
    setSelected(id);
    setPage([49, 53].includes(s.task_id) ? "transaction" : "account");
    if (s.task_id === 53 && !s.v2_worksets) void api.mutate("select", "", "", [id]);
  }
  return (
    <Frame
      brand="青禾账户"
      accent="#285ba5"
      page={page}
      navigate={setPage}
      tabs={[
        ["home", "账户总览"],
        ["accounts", "我的账户"],
        ["transactions", "交易明细"],
        ["transfer", "转账汇款"],
        ["reminders", "余额提醒"],
        ...(s.v2_worksets&&s.task_id===53?[["statements","对账单"] as [string,string]]:[]),
      ]}
      tools={<span className="bank-sandbox">模拟账户 · 不连接真实资金</span>}
    >
      <main className="product-main">
        <Notice api={api} />
        {!['account','transaction','confirm'].includes(page)&&<WorksetBar api={api} view={view}/>}
        {page === "home" ? (
          <>
            <PageHead
              eyebrow="GOOD MORNING, YUAN"
              title="你好，周予安"
              description="在一个地方，了解账户的每一笔收支。"
            />
            <div className="bank-overview">
              <section className="bank-balance">
                <span>可用余额（元）</span>
                <h1>¥{money(d.balances.self / 100)}</h1>
                <p>青禾储蓄账户 · 尾号 0826</p>
                <div>
                  <button onClick={() => setPage("transfer")}>
                    转账汇款 ↗
                  </button>
                  <button onClick={() => setPage("transactions")}>
                    查看明细 →
                  </button>
                </div>
              </section>
              <section className="bank-summary">
                <h3>账户服务</h3>
                <button onClick={() => setPage("accounts")}>
                  我的账户 <b>{rows.length} 个 →</b>
                </button>
                <button onClick={() => setPage("reminders")}>
                  余额提醒{" "}
                  <b>{rows.filter((x: any) => x.reminder).length} 已开启 →</b>
                </button>
                <button onClick={() => setPage("transactions")}>
                  收支记录 <b>查看 →</b>
                </button>
              </section>
            </div>
            <div className="product-section">
              <h2>常用账户</h2>
              <button onClick={() => setPage("accounts")}>管理账户 →</button>
            </div>
            <div className="bank-cards">
              {rows.slice(0, 3).map((x: any) => (
                <button key={x.id} onClick={() => open(x.id)}>
                  <small>QINGHE · SAVINGS</small>
                  <h3>{x.name}</h3>
                  <span>•••• {x.account.slice(-4)}</span>
                  <strong>¥{money(balance(x))}</strong>
                </button>
              ))}
            </div>
          </>
        ) : page === "statements" ? <><PageHead title="月度对账单"/><SavedWorksets api={api}/>{d.artifacts.filter((a:any)=>a.kind==='statement_voucher').map((a:any)=><article key={a.statement} className="bank-receipt"><b>{a.number}</b><span>账户 {a.account} · {dateTime(a.occurred_at)}</span><strong>¥{money(a.amount)}</strong></article>)}</> : page === "transfer" ? (
          <>
            <PageHead
              eyebrow="TRANSFER"
              title="转账汇款"
              description="核对收款账户与金额，再确认转账。"
            />
            {s.task_id === 46 ? (
              <section className="bank-form">
                <h2>转账备注</h2>
                <dl>
                  <dt>收款账户</dt>
                  <dd>{s.source.text}</dd>
                  <dt>收款人</dt>
                  <dd>{s.source.recipient}</dd>
                </dl>
                <label>
                  备注
                  <input
                    value={text}
                    onChange={(e) => setText(e.target.value)}
                  />
                </label>
                <button
                  className="product-primary"
                  disabled={api.busy}
                  onClick={() => api.mutate("save", "target", text)}
                >
                  保存转账备注
                </button>
                {s.outputs.target && (
                  <p className="product-ok">已保存：{s.outputs.target}</p>
                )}
              </section>
            ) : (
              <>
                <DataRows
                  items={rows}
                  columns={[
                    ["name", "收款人", (x) => x.name],
                    ["account", "收款账户", (x) => x.account],
                    ["amount", "待转金额", (x) => `¥${money(x.amount)}`],
                  ]}
                  renderActions={(x) => (
                    <button
                      className="product-primary"
                      disabled={api.busy || s.task_id !== 56 || transferred(x.id)}
                      onClick={() => {
                        setSelected(x.id);
                        setPage("confirm");
                      }}
                    >
                      {transferred(x.id) ? "✓ 已转账" : "核对并转账"}
                    </button>
                  )}
                />
                <div className="product-section">
                  <h2>转账回执</h2>
                </div>
                {d.ledger
                  .filter((x: any) => x.account === "self")
                  .map((x: any) => (
                    <div className="bank-receipt" key={x.transfer}>
                      <span>✓ 转账成功 · {x.transfer}</span>
                      <b>{d.objects[x.counterparty].name}</b>
                      <strong>¥{money(-x.cents / 100)}</strong>
                    </div>
                  ))}
              </>
            )}
          </>
        ) : page === "confirm" && active ? (
          <>
            <button
              className="product-back"
              onClick={() => setPage("transfer")}
            >
              ← 转账汇款
            </button>
            <PageHead title="确认转账信息" />
            <section className="bank-form">
              <dl>
                <dt>收款人</dt>
                <dd>{active.name}</dd>
                <dt>收款账户</dt>
                <dd>{active.account}</dd>
                <dt>转账金额</dt>
                <dd>¥{money(active.amount)}</dd>
              </dl>
              <button
                className="product-primary"
                disabled={
                  api.busy ||
                  transferred(active.id)
                }
                onClick={() => api.mutate("action", active.id, "转账")}
              >
                {transferred(active.id)
                  ? "✓ 转账成功"
                  : "确认转账"}
              </button>
            </section>
          </>
        ) : page === "transaction" && active ? (
          <>
            <button
              className="product-back"
              onClick={() => setPage("transactions")}
            >
              ← 交易明细
            </button>
            <PageHead title="交易详情" />
            <WorksetIdentity item={active}/>
            <section className="bank-form">
              <div className="bank-transaction-amount">
                ¥{money(active.amount)}
              </div>
              <dl>
                <dt>交易对象</dt>
                <dd>{active.name}</dd>
                <dt>交易备注</dt>
                <dd>{active.text}</dd>
                {s.task_id === 49 && <><dt>备注字符数</dt><dd>{Array.from(active.text).length}</dd></>}
                <dt>交易时间</dt>
                <dd>
                  {dateTime(active.created_at)}
                </dd>
                <dt>账户</dt>
                <dd>{active.account}</dd>
                <dt>状态</dt>
                <dd>已完成</dd>
              </dl>
              {s.task_id === 49 && <Classify item={active} api={api} />}
              {s.task_id===53&&<CollectToWorkset key={active.id} api={api} item={active} label="保存到对账单"/>}
            </section>
          </>
        ) : page === "account" && active ? (
          <>
            <button
              className="product-back"
              onClick={() => setPage("accounts")}
            >
              ← 我的账户
            </button>
            <PageHead
              title={active.name}
              description={`账户 ${active.account}`}
            />
            <section className="bank-form">
              <span>账户余额</span>
              <WorksetIdentity item={active}/>
              <h1>¥{money(balance(active))}</h1>
              <p>最近 30 天交易笔数：{active.transactions}</p>
              <p>{s.source.transaction_window.start} 至 {s.source.transaction_window.end}</p>
              <p>
                开户日期：
                {active.opened_at}
              </p>
              <h3>最近两笔交易</h3>
              <DataRows items={active.recent_transactions} columns={[
                ["occurred_at", "交易时间", (x) => dateTime(x.occurred_at)],
                ["amount", "金额", (x) => `¥${money(x.amount)}`],
              ]} />
              {active.transaction_history&&<details><summary>展开近 30 天全部 {active.transaction_history.length} 笔交易</summary><DataRows items={active.transaction_history.map((x:any)=>({...x,name:x.id}))} columns={[
                ['id','流水编号',x=>x.id],['occurred_at','交易时间',x=>dateTime(x.occurred_at)],['amount','金额',x=>`¥${money(x.amount)}`],
              ]}/></details>}
              {s.task_id === 50 && <Classify item={active} api={api} />}{" "}
              <ReminderChannel api={api} item={active}/>
              {s.task_id === 57 && (
                <button
                  className="product-primary"
                  disabled={api.busy || active.reminder}
                  onClick={() => api.mutate("action", active.id, "开启提醒")}
                >
                  {active.reminder ? "✓ 提醒已开启" : "开启余额提醒"}
                </button>
              )}
            </section>
          </>
        ) : page === "transactions" ? (
          <>
            <PageHead
              eyebrow="TRANSACTIONS"
              title="交易明细"
              description="查看交易金额、备注与明细。"
              action={
                <input
                  placeholder="搜索交易备注"
                  value={query}
                  onChange={(e) => setQuery(e.target.value)}
                />
              }
            />
            <DataRows
              items={rows.filter((x: any) => (x.name + x.text).includes(query))}
              open={[49,53].includes(s.task_id) ? undefined : open}
              columns={[
                ["name", "交易对象", (x) => <>{x.name}<WorksetIdentity item={x}/></>],
                ["text", "备注", (x) => <span>{x.text}{s.task_id === 49 && <small style={{display:"block"}}>{Array.from(x.text).length} 个字符</small>}</span>],
                ["time", "交易时间", (x) => dateTime(x.created_at)],
                ["amount", "金额", (x) => `¥${money(x.amount)}`],
              ]}
              renderActions={(x) =>
                s.task_id === 49 ? (
                  <Classify item={x} api={api} />
                ) : s.task_id === 53 ? (
                  s.v2_worksets ? <CollectToWorkset key={x.id} api={api} item={x} label="保存到对账单"/> : <button disabled={api.busy} onClick={()=>api.mutate("select","","",[x.id])}>{s.selection.includes(x.id)?"✓ 已选择":"选择这笔交易"}</button>
                ) : (
                  <button onClick={() => open(x.id)}>查看明细 →</button>
                )
              }
            />
          </>
        ) : (
          <>
            <PageHead
              eyebrow="ACCOUNTS"
              title={page === "reminders" ? "余额提醒" : "我的账户"}
              description={`交易统计区间：${s.source.transaction_window.start} 至 ${s.source.transaction_window.end}`}
            />
            <DataRows
              items={rows}
              open={[49,53].includes(s.task_id) ? undefined : open}
              columns={[
                ["name", "账户名称", (x) => <>{x.name}<WorksetIdentity item={x}/></>],
                ["account", "账号", (x) => x.account],
                ["balance", "余额", (x) => `¥${money(balance(x))}`],
                ["transactions", "最近30天交易笔数", (x) => x.transactions],
                [
                  "date",
                  "最近两笔交易",
                  (x) => <span>{x.recent_transactions.map((tx: any) => <span key={tx.occurred_at} style={{display:"block"}}>{dateTime(tx.occurred_at)}</span>)}</span>,
                ],
              ]}
              renderActions={(x) =>
                s.task_id === 50 ? (
                  <Classify item={x} api={api} />
                ) : s.task_id === 57 ? (
                  <><ReminderChannel api={api} item={x}/><button
                    disabled={api.busy || x.reminder}
                    onClick={() => api.mutate("action", x.id, "开启提醒")}
                  >
                    {x.reminder ? "✓ 已开启" : "开启提醒"}
                  </button></>
                ) : (
                  <button onClick={() => open(x.id)}>详情 →</button>
                )
              }
            />
          </>
        )}
      </main>
    </Frame>
  );
}
