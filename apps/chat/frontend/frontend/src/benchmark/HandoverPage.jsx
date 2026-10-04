import {useEffect,useState} from 'react';
import {Link} from 'react-router-dom';
import {business,command,workspaceLink} from './bridge.js';
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
    <section className="communication-panel"><h2>Studio 项目文档</h2><p>将 Chat 中处理的消息整理成可追溯的交接清单，保存文档后在这里发送。</p><a className="wxBtn" href={workspaceLink('studio')}>编制或查看交接文档 ↗</a><button className="wxBtn" onClick={load}>刷新文档</button>
      {w.documents['handover-001']?<pre style={{whiteSpace:'pre-wrap',lineHeight:1.8}}>{w.documents['handover-001'].body}</pre>:<p>尚未保存交接文档。</p>}
      {Object.values(doc.rows).map(row=><p key={row.message}><Link to={row.link}>{row.task_number} · 打开原消息</Link><span> · {row.status}</span></p>)}
      <footer><label>交接给<select aria-label="交接单收件人" value={recipient} disabled={doc.sent||busy} onChange={e=>setRecipient(e.target.value)}>{w.conversations.map(c=><option key={c.id} value={c.user_id}>{c.name}</option>)}</select></label><button className="wxBtn wxBtn--primary" disabled={busy||doc.sent||!w.documents['handover-001']} onClick={()=>save('handover.send','',{recipient:Number(recipient)})}>{busy?'保存中…':doc.sent?'交接单已发送':'发送交接单'}</button></footer>
      {doc.sent&&<p role="status">交接文件已保存在收件会话中。<Link to={'/chat?open='+w.documents['handover-001'].recipient}>查看已发送文件</Link></p>}
    </section>
  </main>;
}
