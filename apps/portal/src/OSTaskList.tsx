import {useEffect,useRef,useState} from 'react';

type Case={id:string;title:string;app:string;family:string;difficulty:string;task:string};
type Run={id:string;application_url:string;result?:{success:boolean;agent_steps:number;optimal_steps:number}};
const families:Record<string,string>={selection:'选择',selection_set:'多选',mapping:'动作映射',ordering:'排序',state_machine:'状态机',recovery:'恢复',cross_app:'跨应用'};
export function OSTaskList({token}:{token:string}){
  const [cases,setCases]=useState<Case[]>([]),[selected,setSelected]=useState<Case|null>(null),[variant,setVariant]=useState('A');
  const [query,setQuery]=useState(''),[error,setError]=useState(''),[busy,setBusy]=useState(false),[video,setVideo]=useState('');
  const [runs,setRuns]=useState<Record<string,Run>>({});
  const tab=useRef<Window|null>(null),key=`${selected?.id}-${variant}`,run=runs[key];
  async function api(path:string,method='GET',body?:unknown){
    const r=await fetch(path,{method,headers:{Authorization:`Bearer ${token}`,'Content-Type':'application/json'},body:body===undefined?undefined:JSON.stringify(body)});
    if(!r.ok){const e=await r.json();throw Error(typeof e.detail==='string'?e.detail:'OS 服务请求失败')}
    return r.json();
  }
  useEffect(()=>{api('/os-api/cases').then(d=>setCases(d.cases)).catch(e=>setError(String(e)))},[token]);
  useEffect(()=>{
    setVideo('');setError('');if(!selected)return;let alive=true,url='';const controller=new AbortController();
    fetch(`/os-api/cases/${selected.id}/demo?variant=${variant}`,{headers:{Authorization:`Bearer ${token}`},signal:controller.signal})
      .then(async r=>{if(!r.ok)throw Error('示范视频暂不可用');return r.blob()})
      .then(blob=>{url=URL.createObjectURL(blob);if(alive)setVideo(url);else URL.revokeObjectURL(url)})
      .catch(e=>{if(alive)setError(String(e))});
    return()=>{alive=false;controller.abort();if(url)URL.revokeObjectURL(url)};
  },[selected?.id,variant,token]);
  async function prepare(){return api('/os-api/runs','POST',{case_id:selected!.id,variant,interaction:'human',seed:20261005})}
  async function open(reset=false){
    if(!selected)return;setError('');setBusy(true);
    const win=window.open('about:blank','_blank');if(win)win.opener=null;
    try{
      if(!win)throw Error('请允许本站打开应用标签页。');
      const next=reset||!run||run.result?await prepare():run;
      setRuns(s=>({...s,[key]:next}));win.location.replace(next.application_url);tab.current=win;
    }catch(e){win?.close();setError(String(e))}finally{setBusy(false)}
  }
  async function evaluate(){
    if(!run)return;setBusy(true);setError('');
    try{const result=await api(`/os-api/runs/${run.id}/eval`,'POST',{});setRuns(s=>({...s,[key]:{...run,result}}))}
    catch(e){setError(String(e))}finally{setBusy(false)}
  }
  const shown=cases.filter(c=>`${c.id} ${c.title} ${c.app} ${c.family}`.toLowerCase().includes(query.toLowerCase()));
  return <section aria-label="OS 任务"><div className="toolbar"><input aria-label="搜索 OS 任务" placeholder="搜索 OS 题号、任务或应用…" value={query} onChange={e=>setQuery(e.target.value)}/><span className="muted">{shown.length} 个任务 · 108 个配套示范 · OS-ICL 1.0.0</span></div>
    {error&&<p className="error" role="alert">{error}</p>}
    <div className="recorder-layout"><section className="panel task-list"><table><thead><tr><th>任务</th><th>应用 / 难度</th></tr></thead><tbody>{shown.map(c=><tr key={c.id} tabIndex={0} aria-selected={selected?.id===c.id} className={selected?.id===c.id?'selected':''} onClick={()=>!busy&&setSelected(c)} onKeyDown={e=>e.key==='Enter'&&!busy&&setSelected(c)}><td><span className="task-id">{c.id}</span>{c.title}<small style={{display:'block'}}>{families[c.family]||c.family}</small></td><td>{c.app}<br/>{c.difficulty}</td></tr>)}</tbody></table></section>
    <section className="panel recorder-card">{selected?<><p className="eyebrow">{selected.id}</p><h2>{selected.title}</h2><div className="segmented">{'ABC'.split('').map(v=><button key={v} disabled={busy} aria-pressed={variant===v} className={variant===v?'chosen':''} onClick={()=>setVariant(v)}>版本 {v}</button>)}</div><h3>示范视频</h3><p>从视频学习规则，再在新的资料上执行。示范和执行初态不同。</p>{video?<video key={video} controls preload="metadata" src={video} style={{width:'100%',borderRadius:12}} aria-label="OS 规则示范"/>:<p>正在载入视频…</p>}<h3>执行任务</h3><p>{selected.task}</p><div className="actions"><button className="primary" disabled={busy} onClick={()=>open()}>打开执行环境</button><button disabled={busy} onClick={()=>open(true)}>重置并打开</button><button disabled={busy||!run||!!run.result} onClick={evaluate}>检查最终结果</button></div><p className="muted">直接进入原版 OS 应用。完成后点击应用里的 Finish and evaluate，或回到这里检查结果。重置会创建独立环境。</p>{run?.result&&<p role="status" className="recording-result"><b>{run.result.success?'success · 通过':'fail · 未通过'}</b> · 已记录 {run.result.agent_steps} 步</p>}{run&&<small className="muted">运行编号：{run.id}</small>}</>:<div className="empty"><h2>选择一个 OS 任务</h2><p>观看同事提供的示范，然后直接进入 OS 应用。</p></div>}</section></div>
  </section>;
}
