import {useState} from 'react';
import type {ProductAPI} from './kit';
import './worksets.css';

export function useWorksets(api:ProductAPI) {
  const [scopeId,setScopeId]=useState(''),[filter,setFilter]=useState('');
  const scopes=api.s.scopes||[],scope=scopes.find((x:any)=>x.id===scopeId);
  const visible=(item:any)=>!api.s.v2_worksets||((!scopeId||item.scope_id===scopeId)&&(!filter||Object.keys(scope?.filters||{}).every(k=>item[k]===filter)));
  return {scope,scopeId,filter,visible,change:(id:string)=>{setScopeId(id);setFilter('')},setFilter};
}
export function WorksetBar({api,view}:{api:ProductAPI;view:ReturnType<typeof useWorksets>}) {
  if(!api.s.v2_worksets)return null;
  const {s,d}=api,scope=view.scope,field=Object.keys(scope?.filters||{})[0];
  const values=field?Array.from(new Set<string>(s.items.filter((x:any)=>x.scope_id===scope.id).map((x:any)=>String(x[field])))):[];
  const requested=s.scopes.filter((x:any)=>x.requested);
  const rows=s.items.map((x:any)=>d.objects[x.id]).filter(view.visible);
  const snapshot=[26,47,48].includes(s.task_id);
  return <section className="workset-bar" aria-label="资料筛选">
    <div className="workset-brief"><b>本次整理</b><span>{requested.map((x:any)=>x.name).join('、')}{field&&` · ${scope.filter_label}：${scope.filters[field]}`}{s.task_id===57&&` · 提醒渠道：${s.source.notification_channel}`}</span></div>
    <p className="workset-identity">{s.task_id===49 ? `金额单位为整数元；备注长度阈值 ${s.source.text_threshold} 个字符（包含标点和空格）。` : s.public_parameters}</p>
    <div className="workset-filters"><label>{s.scopes[0].kind}<select aria-label={s.scopes[0].kind} value={view.scopeId} onChange={e=>view.change(e.target.value)}><option value="">全部</option>{s.scopes.map((x:any)=><option key={x.id} value={x.id}>{x.name}</option>)}</select></label>
      {field&&<label>{scope.filter_label}<select aria-label={scope.filter_label} value={view.filter} onChange={e=>view.setFilter(e.target.value)}><option value="">全部</option>{values.map(v=><option key={v}>{v}</option>)}</select></label>}
      <span>{rows.length} 项 · 已标注 {rows.filter((x:any)=>x.label).length} 项</span>
      {snapshot&&<button className="product-primary" disabled={api.busy||!scope} onClick={()=>api.mutate('workset.collect',scope.id,'',rows.filter((x:any)=>x.label===s.options[0]).map((x:any)=>x.id))}>保存{scope?.collection||s.scopes[0].collection}</button>}
    </div>
    {snapshot&&scope&&<div className="workset-summary" role="status">已保存 {d.collections['scope:'+scope.id]?.length||0} 项：{(d.collections['scope:'+scope.id]||[]).map((id:string)=>d.objects[id].name+' ('+d.objects[id].record_code+')').join('、')||'暂无'}</div>}
  </section>;
}
export function WorksetIdentity({item}:{item:any}) {
  return item.scope_id?<p className="workset-identity">{item.scope_name} · 编号 {item.record_code}{item.specification&&` · ${item.specification}`}{item.period&&` · ${item.period}`}{item.travel_date&&` · ${item.travel_date}`}</p>:null;
}
export function CollectToWorkset({api,item,label}:{api:ProductAPI;item:any;label:string}) {
  const [destination,setDestination]=useState(item.scope_id||'');
  if(!api.s.v2_worksets)return null;
  return <section className="workset-collect"><label>保存位置<select aria-label="保存位置" value={destination} onChange={e=>setDestination(e.target.value)}>{api.s.scopes.map((x:any)=><option key={x.id} value={x.id}>{x.name} · {x.collection}</option>)}</select></label><button className="product-primary" disabled={api.busy||!destination} onClick={()=>api.mutate('workset.collect',destination,'',[item.id])}>{label}</button><p role="status">{api.d.collections['scope:'+destination]?.includes(item.id)?'✓ 此记录已保存到所选位置':''}</p></section>;
}
export function SavedWorksets({api}:{api:ProductAPI}) {
  if(!api.s.v2_worksets)return null;
  return <section className="saved-worksets" aria-label="已保存的集合">{api.s.scopes.filter((x:any)=>x.collection&&x.requested).map((scope:any)=><article key={scope.id}><h2>{scope.name} · {scope.collection}</h2>{(api.d.collections['scope:'+scope.id]||[]).map((id:string)=><p key={id}>{api.d.objects[id].name} · {api.d.objects[id].record_code}</p>)}{!(api.d.collections['scope:'+scope.id]||[]).length&&<p>尚未添加</p>}</article>)}</section>;
}
export function ReminderChannel({api,item}:{api:ProductAPI;item:any}) {
  if(!api.s.v2_worksets||api.s.task_id!==57)return null;
  return <label className="workset-channel">通知渠道<select aria-label={'通知渠道 '+item.record_code} value={item.reminder_channel} disabled={api.busy} onChange={e=>api.mutate('reminder.channel',item.id,e.target.value)}>{['短信','站内信','电子邮件'].map(v=><option key={v}>{v}</option>)}</select></label>;
}
