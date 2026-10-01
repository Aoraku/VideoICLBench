import {useEffect,useState} from 'react';
import {Link} from 'react-router-dom';
import {business,command} from './bridge.js';
import './communications.css';

export default function HandoverPage(){
  const [state,setState]=useState(null),[project,setProject]=useState(''),[batch,setBatch]=useState(''),[recipient,setRecipient]=useState('2'),[busy,setBusy]=useState(false),[error,setError]=useState('');
  const load=()=>business().then(r=>setState(r.state)).catch(e=>setError(e.message));
  useEffect(()=>{load()},[]);
  if(!state)return <p style={{padding:32}}>正在打开交接单…</p>;
  if(state.workflow!=='communications'||state.task_id!==13)return <p style={{padding:32}}>此工作区没有交接单。<Link to="/chat">返回会话</Link></p>;
  const w=state.world,doc=w.handover;
  const save=async(op,target='',data={})=>{setBusy(true);try{setState(await command(op,target,JSON.stringify(data)));setError('')}catch(e){setError(e.message)}finally{setBusy(false)}};
  const link=item=>`/chat?open=${item.conversation}&msg=${item.message_id}`;
  return <main className="communication-workspace"><header><div><small>客户支持 / 班次交接</small><h1>{doc.title}</h1><p>记录本班处理结果，让接班人能够打开原消息继续跟进。</p></div><Link className="wxBtn" to="/chat">返回会话</Link></header>
    {error&&<p role="alert">{error}</p>}
    <div className="handover-layout"><section className="communication-panel"><h2>原消息</h2><div className="communication-fields"><label>项目<select aria-label="消息项目" value={project} onChange={e=>setProject(e.target.value)}><option value="">全部项目</option>{w.projects.map(p=><option key={p.id} value={p.id}>{p.name}</option>)}<option value="P-999">其他项目</option></select></label><label>批次<select aria-label="消息批次" value={batch} onChange={e=>setBatch(e.target.value)}><option value="">全部批次</option><option>晚班-0115</option><option>早班-0115</option></select></label></div>
      {state.items.filter(x=>(!project||x.project===project)&&(!batch||x.batch===batch)).map(item=>{const obj=state.domain.objects[item.id];const statuses=[obj.archived?'已归档':'',obj.starred?'已收藏':'',state.domain.messages.some(m=>m.reference===item.id)?'已转发':''].filter(Boolean);return <article className="handover-source" key={item.id} data-message-id={item.id}><Link to={link(item)}>{item.record_code} · {item.project_name}</Link><p>{item.text}</p><small>当前记录：{statuses.join('、')||'待处理'}</small><button className="wxBtn" disabled={busy||doc.sent||!!doc.rows[item.id]} onClick={()=>save('handover.line',item.id,{status:'待处理'})}>加入交接单</button></article>})}
    </section><section className="communication-panel"><header><h2>交付清单</h2><span>{Object.keys(doc.rows).length} 项</span></header>
      {!Object.keys(doc.rows).length&&<div className="handover-empty">从原消息中添加本班需要交接的事项，再核对处理结果。</div>}
      {Object.values(doc.rows).map(row=><article className="handover-entry" key={row.message} data-delivery-id={row.message}><Link to={row.link}>{row.task_number} · 打开原消息</Link><div className="communication-fields"><label>处理结果<select aria-label={'处理结果 '+row.task_number} disabled={busy||doc.sent} value={row.status} onChange={e=>save('handover.line',row.message,{status:e.target.value})}>{['待处理','已转发','已收藏','已归档'].map(s=><option key={s}>{s}</option>)}</select></label><button className="wxBtn" disabled={busy||doc.sent} onClick={()=>save('handover.remove',row.message)}>移除 {row.task_number}</button></div></article>)}
      <footer><label>交接给<select aria-label="交接单收件人" value={recipient} disabled={doc.sent||busy} onChange={e=>setRecipient(e.target.value)}>{w.conversations.map(c=><option key={c.id} value={c.user_id}>{c.name}</option>)}</select></label><button className="wxBtn wxBtn--primary" disabled={busy||doc.sent||!Object.keys(doc.rows).length} onClick={()=>save('handover.send','',{recipient:Number(recipient)})}>{busy?'保存中…':doc.sent?'交接单已发送':'发送交接单'}</button></footer>
      {doc.sent&&<p role="status">交接文件已保存在收件会话中。<Link to={'/chat?open='+w.documents['handover-001'].recipient}>查看已发送文件</Link></p>}
    </section></div>
  </main>;
}
