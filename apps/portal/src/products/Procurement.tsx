import {useState} from 'react';
import {Frame, PageHead, Notice, DataRows, type ProductAPI} from './kit';
import './procurement.css';

export function Procurement({api}:{api:ProductAPI}) {
  const w=api.s.world;
  const [requestId,setRequestId]=useState(new URLSearchParams(location.search).get('request')||'');
  const [page,setPage]=useState(requestId?'requests':'home'), [department,setDepartment]=useState(w.departments[0].id);
  const [active,setActive]=useState(''), [sku,setSku]=useState(w.products[0].id);
  const [quantity,setQuantity]=useState(1), [note,setNote]=useState(''), [address,setAddress]=useState('');
  const [query,setQuery]=useState('');
  const order=w.orders[active];
  const dep=(id:string)=>w.departments.find((d:any)=>d.id===id);
  const product=(id:string)=>w.products.find((p:any)=>p.id===id);
  const command=(op:string,target:string,data:any={})=>api.mutate(op,target,JSON.stringify(data));
  function navigate(next:string){setRequestId('');setPage(next);}
  function open(id:string){setActive(id);setAddress(w.orders[id].address);setPage('editor');setNote('');setQuantity(1)}
  function editLine(id:string){setSku(id);setQuantity(order.lines[id].quantity);setNote(order.lines[id].note)}
  return <div className="procurement"><Frame brand="VIC Shop" accent="#e66a30" page={page} navigate={navigate}
    tabs={[["home","采购首页"],["requests","采购申请"],["products","商品目录"],["contacts","部门通讯录"],["orders","订单草稿"]]}
    tools={<a href={api.applicationLink?.('im')}>团队采购消息 →</a>}>
    <main className="product-main"><Notice api={api}/>
    {page==='home'&&<><PageHead eyebrow="采购工作台" title="把同事需要的用品准备好" description="申请、商品与订单在这里统一管理。"/>
      <section className="product-card"><h2>本次采购要求</h2><p>{w.brief}</p><button className="product-primary" onClick={()=>setPage('requests')}>查看采购申请</button></section>
      <div className="product-grid"><section className="product-card"><h3>采购申请</h3><p>{w.requests.length} 份申请与更正</p><button onClick={()=>setPage('requests')}>查看申请</button></section><section className="product-card"><h3>订单草稿</h3><p>{Object.keys(w.orders).length} 张订单</p><button onClick={()=>setPage('orders')}>管理订单</button></section><section className="product-card"><h3>收货地址</h3><p>三个部门的联系人与地址</p><button onClick={()=>setPage('contacts')}>查看通讯录</button></section></div></>}
    {page==='requests'&&<><PageHead title="采购申请" description="同一申请编号采用最高版本，追加申请单独累计。"/>
      <p>原始申请与更正单由各部门联系人在团队消息中提交。<a href={api.applicationLink?.('im')}>查看来源消息 →</a></p>
      {requestId&&<p>正在查看申请 {requestId}。<button onClick={()=>{setRequestId('');setQuery('');}}>查看全部采购申请</button></p>}
      <label>筛选部门<select value={query} onChange={e=>setQuery(e.target.value)}><option value="">全部部门</option>{w.departments.map((d:any)=><option key={d.id} value={d.id}>{d.name}</option>)}</select></label>
      <div className="product-grid">{w.requests.filter((r:any)=>(!query||r.department===query)&&(!requestId||r.id===requestId)).map((r:any)=><section className="product-card" data-purchase-request={r.id} key={r.id}><h2>{r.number} · 第 {r.revision} 版</h2><p>{r.id} · {dep(r.department).name} · {r.date}</p><DataRows items={r.lines.map((l:any)=>({...l,id:l.sku}))} columns={[["name","商品",l=>product(l.sku).name],["id","商品编号",l=>l.sku],["spec","规格",l=>product(l.sku).spec],["quantity","数量",l=>l.quantity]]}/></section>)}</div></>}
    {page==='products'&&<><PageHead title="商品目录" description="同名商品可能具有不同规格，请核对商品编号。"/><DataRows items={w.products} columns={[["name","商品",p=>p.name],["id","商品编号",p=>p.id],["spec","规格",p=>p.spec],["price","单价",p=>`¥${p.price}`],["stock","库存",p=>p.stock]]}/></>}
    {page==='contacts'&&<><PageHead title="部门通讯录"/><DataRows items={w.departments} columns={[["name","部门",d=>d.name],["contact","采购联系人",d=>d.contact],["address","收货地址与联系人",d=>d.address]]}/></>}
    {page==='orders'&&<><PageHead title="订单草稿" description="为每个部门准备一张订单，编辑完成后保存草稿。"/>
      <section className="product-card"><label>采购部门<select value={department} onChange={e=>setDepartment(e.target.value)}>{w.departments.map((d:any)=><option key={d.id} value={d.id}>{d.name}</option>)}</select></label><button disabled={api.busy} onClick={()=>command('order.create','',{department})}>新建订单</button></section>
      <DataRows items={Object.values(w.orders)} columns={[["id","订单编号",o=>o.id],["department","部门",o=>dep(o.department).name],["lines","商品行数",o=>Object.keys(o.lines).length],["status","状态",o=>o.status==='saved'?'已保存':'编辑中']]} open={open} renderActions={o=><><button disabled={api.busy} onClick={()=>open(o.id)}>编辑订单 {o.id}</button><button disabled={api.busy} onClick={()=>command('order.delete',o.id)}>删除订单 {o.id}</button></>}/></>}
    {page==='editor'&&order&&<><PageHead title={`${order.id} · ${dep(order.department).name}`} description="填写地址和商品，保存后可返回订单列表复查。"/><button onClick={()=>setPage('orders')}>返回订单列表</button>
      <section className="product-card"><label>收货地址<input value={address} onChange={e=>setAddress(e.target.value)} /></label><button disabled={api.busy} onClick={()=>command('order.address',active,{address})}>保存地址</button><p>已存地址：{order.address||'尚未填写'}</p></section>
      <section className="product-card"><h2>添加或修改商品</h2><label>商品与规格<select value={sku} onChange={e=>{setSku(e.target.value);setNote('');setQuantity(1)}}>{w.products.map((p:any)=><option key={p.id} value={p.id}>{p.name} · {p.spec} · {p.id}</option>)}</select></label><label>数量<input type="number" min="1" value={quantity} onChange={e=>setQuantity(Number(e.target.value))}/></label><label>商品备注<input value={note} onChange={e=>setNote(e.target.value)}/></label><button className="product-primary" disabled={api.busy} onClick={()=>command('order.line',active,{sku,quantity,note})}>保存商品行</button></section>
      <DataRows items={Object.entries(order.lines).map(([id,line])=>({id,...line as any}))} columns={[["name","商品",l=>product(l.id).name],["spec","规格",l=>product(l.id).spec],["quantity","数量",l=>l.quantity],["note","备注",l=>l.note],["total","小计",l=>`¥${product(l.id).price*l.quantity}`]]} renderActions={l=><><button disabled={api.busy} onClick={()=>editLine(l.id)}>编辑商品 {l.id}</button><button disabled={api.busy} onClick={()=>command('order.remove',active,{sku:l.id})}>移除商品 {l.id}</button></>}/>
      <p>订单合计：¥{Object.entries(order.lines).reduce((sum:number,[id,line]:any)=>sum+product(id).price*line.quantity,0)}</p><button className="product-primary" disabled={api.busy} onClick={()=>command('order.save',active)}>保存订单草稿</button><p>{order.status==='saved'?'此订单已保存':'修改后请保存订单草稿'}</p></>}
    </main></Frame></div>;
}
