import {useEffect,useState} from 'react';
import {business,nativeRun,currentScope,setCurrentScope} from './bridge.js';

export default function WorkspaceBar(){
  const [state,setState]=useState(null),[scope,setScope]=useState(currentScope);
  useEffect(()=>{
    if(!nativeRun)return;
    let active=true;
    const refresh=()=>business().then(r=>{if(active)setState(r.state)}).catch(()=>{});
    refresh();window.addEventListener('vic-chat-updated',refresh);
    return()=>{active=false;window.removeEventListener('vic-chat-updated',refresh)};
  },[]);
  if(!state?.v2_worksets)return null;
  const chosen=state.scopes.find(s=>s.id===scope);
  return <section className="workspace-bar" aria-label="工作范围" style={{padding:'12px 20px',borderBottom:'1px solid #dde5e1',background:'#f7faf8',flexShrink:0}}>
    <div style={{display:'flex',gap:16,alignItems:'center'}}>
      <label>{state.scopes[0].kind} <select aria-label={state.scopes[0].kind} value={scope} onChange={e=>{setScope(e.target.value);setCurrentScope(e.target.value)}} style={{padding:'6px 12px',border:'1px solid #c7d5ce',borderRadius:6,background:'white'}}>
        <option value="">全部资料</option>{state.scopes.map(s=><option key={s.id} value={s.id}>{s.name}</option>)}
      </select></label>
      <span style={{fontSize:13,color:'#456257'}}>本次范围：{state.scopes.filter(s=>s.requested).map(s=>s.name).join('、')}</span>
    </div>
    <p style={{fontSize:12,margin:'7px 0 0',color:'#53635c'}}>{state.public_parameters}</p>
    {chosen?.notification&&<p aria-label="部门通知" style={{fontSize:13,margin:'8px 0 0',whiteSpace:'pre-wrap'}}>{chosen.notification}</p>}
  </section>;
}
