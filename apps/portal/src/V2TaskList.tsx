import {useEffect,useState} from 'react';
import {flushSync} from 'react-dom';
import {nativeApplicationUrl} from './nativeApplicationUrl';
import {HumanRecording} from './HumanRecording';

export function V2TaskList({token,onBusy}:{token:string;onBusy:(value:boolean)=>void}) {
  const [tasks,setTasks]=useState<any[]>([]),[selected,setSelected]=useState<any>(null);
  const [variant,setVariant]=useState('A'),[query,setQuery]=useState(''),[difficulty,setDifficulty]=useState('all');
  const [runs,setRuns]=useState<Record<string,any>>({}),[busy,setBusy]=useState(false),[error,setError]=useState('');
  const [capture,setCapture]=useState<MediaStream|null>(null),[recording,setRecording]=useState(false);
  const [privateView,setPrivateView]=useState(false);
  const runKey=(mode:string)=>`${selected?.id}-${variant}-${mode}`;
  const demo=runs[runKey('demo')],evaluation=runs[runKey('eval')];
  useEffect(()=>{onBusy(busy||recording);return()=>onBusy(false)},[busy,recording,onBusy]);
  async function call(path:string,body?:any){const r=await fetch(path,{method:body===undefined?'GET':'POST',headers:{Authorization:`Bearer ${token}`,'Content-Type':'application/json'},body:body===undefined?undefined:JSON.stringify(body)});const v=await r.json();if(!r.ok)throw Error(typeof v.detail==='string'?v.detail:JSON.stringify(v.detail));return v}
  useEffect(()=>{call('/v2/tasks').then(v=>setTasks(v.tasks)).catch(e=>setError(String(e)))},[token]);
  useEffect(()=>{if(!recording||!demo)return;const interval=setInterval(()=>{call(`/v1/runs/${demo.id}`).then(value=>setRuns(s=>({...s,[runKey('demo')]:value}))).catch(()=>{})},1500);return()=>clearInterval(interval)},[recording,demo?.id]);
  async function prepare(mode:string,reset=false){const old=runs[runKey(mode)];const r=old&&reset?await call(`/v1/runs/${old.id}/reset`,{}):old&&!old.result&&old.status==='ready'?old:await call('/v1/runs',{suite:'v2',task_id:selected.id,variant,seed:mode==='demo'?0:10001,mode,runtime:'browser',interaction:'human',teaching:mode==='demo'});setRuns(s=>({...s,[runKey(mode)]:r}));return r}
  async function open(mode:string){const tab=window.open('about:blank','_blank');if(!tab){setError('请允许本站打开应用标签页');return}tab.opener=null;setBusy(true);setError('');let stream:MediaStream|null=null;try{
    if(mode==='demo'){flushSync(()=>setPrivateView(true));stream=await navigator.mediaDevices.getDisplayMedia({video:{frameRate:30},audio:false})}
    const r=await prepare(mode);tab.location.replace(nativeApplicationUrl(r.application_url));tab.focus();if(stream)setCapture(stream);
  }catch(e){stream?.getTracks().forEach(t=>t.stop());tab.close();setError(String(e));setPrivateView(false)}finally{setBusy(false)}}
  async function reset(mode:string){setBusy(true);setError('');try{await prepare(mode,true)}catch(e){setError(String(e))}finally{setBusy(false)}}
  async function check(){setBusy(true);setError('');try{const result=await call(`/v2/tasks/${selected.id}/eval`,{run_id:evaluation.id});setRuns(s=>({...s,[runKey('eval')]:{...evaluation,result,status:'completed'}}))}catch(e){setError(String(e))}finally{setBusy(false)}}
  const shown=tasks.filter(t=>(difficulty==='all'||t.difficulty===difficulty)&&`${String(t.id).padStart(3,'0')} ${t.title} ${t.assignment}`.includes(query));
  const locked=busy||recording,ready=selected?.status==='application-ready';
  return <><div className="toolbar"><input aria-label="搜索 v2 任务" placeholder="搜索任务或工作内容" value={query} onChange={e=>setQuery(e.target.value)}/><select aria-label="执行难度" value={difficulty} onChange={e=>setDifficulty(e.target.value)}><option value="all">全部难度</option><option value="low">低</option><option value="medium">中</option><option value="hard">高</option></select><span>{shown.length} 个任务</span></div>
    {error&&<p role="alert" className="error">{error}</p>}
    <div className="recorder-layout"><section className="panel task-list"><table><thead><tr><th>任务</th><th>难度</th></tr></thead><tbody>{shown.map(t=><tr key={t.id} aria-selected={selected?.id===t.id}><td><button disabled={locked} onClick={()=>{setSelected(t);setPrivateView(false);setCapture(null);setError('')}}>{String(t.id).padStart(3,'0')} {t.title}</button></td><td>{{low:'低',medium:'中',hard:'高'}[t.difficulty as string]}</td></tr>)}</tbody></table></section>
    <section className="panel task-detail">{selected?<><h2>{selected.title}</h2>{!privateView&&<><div className="variant-buttons">{['A','B','C'].map(v=><button key={v} disabled={locked} aria-pressed={variant===v} onClick={()=>setVariant(v)}>版本 {v}</button>)}</div><div className="rule"><b>录制者规则</b><p>{selected.variants[variant]}</p></div><h3>录制示范</h3><p>{selected.demo.instructions}</p><h3>执行任务的目的</h3><p>{selected.assignment}</p><h3>需要完成的工作</h3><p>{selected.inference.instructions}</p><h3>最终交付</h3><p>{selected.delivery}</p></>}
      {!ready&&<p>此执行环境正在实现，尚未开放试用。</p>}
      <div className="actions"><button disabled={locked||!ready} onClick={()=>reset('demo')}>重置示范</button><button disabled={locked||!ready} onClick={()=>open('demo')}>开始录制</button><button disabled={locked||!ready} onClick={()=>open('eval')}>打开执行环境</button><button disabled={locked||!ready} onClick={()=>reset('eval')}>重置执行环境</button></div>
      {demo&&<HumanRecording key={`${demo.id}-${demo.epoch}`} run={demo} token={token} onUpdate={r=>setRuns(s=>({...s,[runKey('demo')]:r}))} onBusy={setRecording} initialStream={capture} compact/>}
      {privateView&&!locked&&<button onClick={()=>setPrivateView(false)}>已停止录制，查看任务说明</button>}
      {evaluation&&<><button disabled={locked||!!evaluation.result} onClick={check}>检查最终交付</button>{evaluation.result&&<div role="status"><h3>{evaluation.result.success?'交付检查通过':'交付尚未完成'}</h3><p>完成度 {Math.round(evaluation.result.completion*100)}%</p><p>{evaluation.result.violations.join('、')}</p></div>}</>}
    </>:<p>选择任务，查看工作目的、教学规则与最终交付。</p>}</section></div></>;
}
