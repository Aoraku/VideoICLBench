import {useEffect,useState} from 'react';
import {command,currentBusiness} from './bridge.js';
import './communications.css';

export default function ProjectFiles({open,conversation,onClose}) {
  const [library,setLibrary]=useState(''),[selected,setSelected]=useState(''),[recipient,setRecipient]=useState(''),[request,setRequest]=useState('');
  const [busy,setBusy]=useState(false),[error,setError]=useState(''),[,refresh]=useState(0);
  const state=currentBusiness();
  useEffect(()=>{if(open){setLibrary(state.world.projects.some(p=>p.conversation===Number(conversation))?String(conversation):'');setSelected('');setError('');}},[open,conversation]);
  if(!open)return null;
  const w=state.world,file=state.domain.files[selected],sent=state.domain.messages.some(m=>m.reference===request);
  return <div className="communication-overlay"><section className="communication-dialog" role="dialog" aria-label="项目聊天文件" aria-modal="true">
    <header><div><small>共享资料</small><h2>聊天文件</h2></div><button className="wxBtn" onClick={onClose} disabled={busy} aria-label="关闭文件窗口">关闭</button></header>
    <label>来源会话 <select aria-label="来源会话" value={library} onChange={e=>{setLibrary(e.target.value);setSelected('')}}><option value="">全部项目资料</option>{w.projects.map(p=><option key={p.id} value={p.conversation}>{p.id} · {p.name} · 项目资料</option>)}</select></label>
    <div className="communication-file-list">{state.items.filter(item=>!library||item.conversation===Number(library)).map(item=><button className="communication-file" data-file-id={item.id} key={item.id} aria-pressed={selected===item.id} onClick={()=>setSelected(item.id)}><span className="communication-file-icon">▤</span><span><strong>{item.name}</strong><small>{item.project} · {item.file_type} · {item.version} · {item.size} 字节</small><small>文件编号 {item.record_code}</small></span><span>{selected===item.id?'✓':''}</span></button>)}</div>
    {file&&<details><summary>预览所选文件</summary><pre>{state.items.find(i=>i.id===selected).file_text}</pre></details>}
    <footer><div className="communication-fields"><label>发送给<select aria-label="附件收件人" value={recipient} onChange={e=>setRecipient(e.target.value)}><option value="">选择联系人</option>{w.conversations.map(c=><option key={c.id} value={c.user_id}>{c.name}</option>)}</select></label><label>关联原请求<select aria-label="关联原请求" value={request} onChange={e=>setRequest(e.target.value)}><option value="">选择请求编号</option>{w.requests.map(r=><option key={r.id} value={r.id}>{r.id} · {r.project}</option>)}</select></label></div>
      {error&&<p role="alert">{error}</p>}{sent&&<p role="status">此请求已有附件回复，可回到收件会话核对。</p>}
      <button className="wxBtn wxBtn--primary" disabled={!file||!recipient||!request||busy||sent} onClick={async()=>{setBusy(true);try{await command('file.send','',JSON.stringify({file:selected,recipient:Number(recipient),request}));setError('');refresh(n=>n+1)}catch(e){setError(e.message)}finally{setBusy(false)}}}>{busy?'发送中…':'发送附件'}</button>
    </footer>
  </section></div>;
}
