import {useEffect,useRef,useState} from 'react';
import {flushSync} from 'react-dom';

type Case={id:string;title:string;app:string;difficulty:string;task:string;rules:Record<string,string>;demo_description:string;demo_instruction:string;demo_groups:number;demo_examples:Record<string,{seed:number;instruction:string;steps:Record<string,unknown>[]}[]>;recording_status:Record<string,string>};
type Recording={approved:boolean;reviewer?:string;note?:string;id:string};
type Run={id:string;application_url:string;mode:string;lesson?:{index:number;total:number;finished:boolean};recording?:Recording;public_task:{assignment:string}};
type Take={run_id:string;label:string;url:string;approved:boolean;historical:boolean};
const LEVEL:Record<string,string>={easy:'Easy · 批量应用',medium:'Medium · 单应用长程',hard:'Hard · 跨应用长程'};
export function OSTaskList({token,onBusy}:{token:string;onBusy:(value:boolean)=>void}){
 const [cases,setCases]=useState<Case[]>([]),[selected,setSelected]=useState<Case|null>(null),[variant,setVariant]=useState('A');
 const [query,setQuery]=useState(''),[error,setError]=useState(''),[busy,setBusy]=useState(false),[privateView,setPrivateView]=useState(false);
 const [run,setRun]=useState<Run|null>(null),[result,setResult]=useState<any>(null),[takes,setTakes]=useState<Take[]>([]),[refresh,setRefresh]=useState(0);
 const [capture,setCapture]=useState<MediaStream|null>(null),[recordingBusy,setRecordingBusy]=useState(false),[inference,setInference]=useState<Run|null>(null);
 const windowRef=useRef<Window|null>(null),runRef=useRef(run);runRef.current=run;
 const locked=busy||recordingBusy,storageKey=`os-demo-human-1:${selected?.id}:${variant}`;
 async function api(path:string,method='GET',body?:unknown){const r=await fetch(path,{method,headers:{Authorization:`Bearer ${token}`,'Content-Type':'application/json'},body:body===undefined?undefined:JSON.stringify(body)});const d=await r.json();if(!r.ok)throw Error(typeof d.detail==='string'?d.detail:'OS 请求失败');return d}
 async function prepare(){return api('/os-api/runs','POST',{case_id:selected!.id,variant,mode:'demo'}) as Promise<Run>}
 function update(next:Run){setRun(next);localStorage.setItem(storageKey,next.id)}
 useEffect(()=>{onBusy(locked);return()=>onBusy(false)},[locked]);
 useEffect(()=>{let live=true;api('/os-api/cases').then(d=>{if(live)setCases(d.cases)}).catch(e=>setError(String(e)));return()=>{live=false}},[token,refresh]);
 useEffect(()=>{
  let live=true;setRun(null);setResult(null);setInference(null);setError('');setCapture(null);setPrivateView(false);setTakes([]);if(!selected)return;
  setBusy(true);
  (async()=>{const d=await api(`/os-api/cases/${selected.id}/demos?variant=${variant}`);if(!live)return;setTakes(d.videos);
    const saved=localStorage.getItem(storageKey)||[...d.videos].reverse().find((t:Take)=>!t.historical)?.run_id;
    let next:Run;try{next=saved?await api(`/os-api/runs/${saved}`):await prepare()}catch{next=await prepare()}
    if(live)update(next);
  })().catch(e=>{if(live)setError(String(e))}).finally(()=>{if(live)setBusy(false)});
  return()=>{live=false};
 },[selected?.id,variant,token]);
 useEffect(()=>{if(!run||!recordingBusy)return;let live=true;const id=run.id;const timer=setInterval(()=>{api(`/os-api/runs/${id}`).then(r=>{if(live)setRun(old=>({...r,recording:r.recording||old?.recording}))}).catch(e=>{if(live)setError(String(e))})},2000);return()=>{live=false;clearInterval(timer)}},[run?.id,recordingBusy]);
 async function reset(){setBusy(true);setError('');try{const next=await prepare();update(next);setResult(null);setCapture(null);setPrivateView(false);if(windowRef.current&&!windowRef.current.closed)windowRef.current.location.replace(next.application_url)}catch(e){setError(String(e))}finally{setBusy(false)}}
 function preview(){if(!run)return;const win=window.open(run.application_url,'_blank');if(win){win.opener=null;windowRef.current=win}else setError('请允许打开应用标签页')}
 async function start(){
  if(!run||!selected)return;
  if(!navigator.mediaDevices?.getDisplayMedia||typeof MediaRecorder==='undefined'){setError('请使用 Chrome / Edge 的 localhost 或 HTTPS 页面录制，也可上传人工录制的 WebM / MP4。');return}
  flushSync(()=>{setPrivateView(true);setBusy(true);setError('')});
  const win=window.open(run.application_url,'_blank');if(!win){setError('请允许打开应用标签页');setBusy(false);setPrivateView(false);return}win.opener=null;windowRef.current=win;
  const access=navigator.mediaDevices.getDisplayMedia({video:{frameRate:30},audio:false}).then(stream=>({stream,error:''})).catch(e=>({stream:null,error:String(e)}));
  let stream:MediaStream|null=null;
  try{const next=await prepare();if(win.closed)throw Error('应用页已关闭');win.location.replace(next.application_url);update(next);setResult(null);
    const response=await access;stream=response.stream;if(!stream)throw Error('未授权录屏。应用环境已打开，可重试或上传系统录屏。');if(win.closed)throw Error('应用页已关闭');setCapture(stream);win.focus();
  }catch(e){stream?.getTracks().forEach(t=>t.stop());void access.then(r=>r.stream?.getTracks().forEach(t=>t.stop()));setError(String(e));setPrivateView(false)}finally{setBusy(false)}
 }
 async function check(){if(!run)return;setBusy(true);try{setResult(await api(`/os-api/runs/${run.id}/check`,'POST',{}))}catch(e){setError(String(e))}finally{setBusy(false)}}
 async function saved(next:Run){update(next);setRefresh(n=>n+1);const d=await api(`/os-api/cases/${selected!.id}/demos?variant=${variant}`);setTakes(d.videos);await check()}
 async function openInference(){const win=window.open('about:blank','_blank');if(!win){setError('请允许打开应用标签页');return}win.opener=null;win.document.body.textContent='正在准备执行桌面…';setBusy(true);try{const next=await api('/os-api/runs','POST',{case_id:selected!.id,variant,mode:'eval',seed:4201});setInference(next);win.location.replace(next.application_url)}catch(e){win.close();setError(String(e))}finally{setBusy(false)}}
 const shown=cases.filter(c=>`${c.id} ${c.title} ${c.app}`.toLowerCase().includes(query.toLowerCase()));
 return <section aria-label="OS 任务"><div className="toolbar"><input aria-label="搜索 OS 任务" placeholder="搜索题号、任务或应用" value={query} onChange={e=>setQuery(e.target.value)}/><span>36 题 · Easy / Medium / Hard 各 12 题</span></div>{error&&<p className="error" role="alert">{error}</p>}
 <div className="recorder-layout"><section className="panel task-list"><table><thead><tr><th>任务</th><th>难度 / 录像</th></tr></thead><tbody>{shown.map(c=><tr key={c.id} tabIndex={locked?-1:0} aria-selected={selected?.id===c.id} className={selected?.id===c.id?'selected':''} onClick={()=>!locked&&setSelected(c)} onKeyDown={e=>e.key==='Enter'&&!locked&&setSelected(c)}><td><small>{c.id}</small><br/>{c.title}</td><td>{LEVEL[c.difficulty]}<small style={{display:'block'}}>{'ABC'.split('').map(v=>`${v} ${c.recording_status[v]}`).join(' · ')}</small></td></tr>)}</tbody></table></section>
 <section className="panel recorder-card">{selected?<><p className="eyebrow">{selected.id} · {selected.app}</p><h2>{selected.title}</h2><div className="segmented">{'ABC'.split('').map(v=><button key={v} disabled={locked} aria-pressed={variant===v} className={variant===v?'chosen':''} onClick={()=>setVariant(v)}>版本 {v}</button>)}</div>
 {!privateView?<><h3>版本 {variant} · 录制者规则卡</h3><p>{selected.rules[variant]}</p><h3>Demo 录什么</h3><p>{selected.demo_description}</p><p className="muted">{selected.demo_groups===1?'在一个示范桌面内完成多个对象的同规则操作。':`连续完成 ${selected.demo_groups} 组局部示例，应用右下角可切下一组；一段视频始终使用同一版本。`}从桌面首页进入应用，展示输入、操作与保存结果；不要录完整 inference 流程。</p><details><summary>逐组录制说明与预期保存内容（仅录制者可见）</summary>{selected.demo_examples[variant].map((g,i)=><section key={g.seed}><h4>第 {i+1} 组</h4><p>{g.instruction}</p><ol>{g.steps.map((s,j)=><li key={j}><strong>{({rename:'重命名',copy:'复制',move:'移动',write:'编辑并保存',setting:'设置',process:'设置进程状态',device:'设置连接状态','print-control':'设置打印队列状态','export-log':'导出日志','create-job':'创建作业','run-job':'运行作业','update-job':'更新作业',delete:'删除工作副本',probe:'验证'} as Record<string,string>)[String(s.op)]||String(s.op)}</strong><p style={{whiteSpace:'pre-wrap',overflowWrap:'anywhere'}}>{Object.entries(s).filter(([k])=>k!=='op').map(([k,v])=>`${({target:'对象',name:'名称',parent:'目标目录',content:'保存内容',key:'设置项',value:'值',input:'输入',output:'输出',dependency:'依赖',trigger:'触发',status:'状态',kind:'类型',start:'起始',end:'截止',connected:'连接'} as Record<string,string>)[k]||k}：${String(v)}`).join('\n')}</p></li>)}</ol></section>)}</details></>:<p>规则卡已隐藏。仅录制 OS 应用标签页；完成所有局部示例后回到这里保存和审核。</p>}
 <div className="actions"><button disabled={locked||!run} onClick={preview}>预览示范环境 ↗</button><button disabled={locked} onClick={reset}>重置示范</button><button disabled={locked||!run} onClick={check}>检查示范结果</button><button className="primary" disabled={locked||!run} onClick={start}>开始录制</button></div>
 {result&&<p role="status">{result.success?'✓ 示范检查通过':'尚未全部完成'}{result.total!==undefined&&` · 已通过 ${result.passed}/${result.total} 组`}</p>}
 {run&&<OSRecording key={run.id} run={run} token={token} capture={capture} onBusy={setRecordingBusy} onSaved={saved}/>}
 {takes.length>0&&<details><summary>服务器录像 · {takes.length} 份</summary>{takes.map(t=><p key={t.url}>{t.label}{t.historical?' · 历史设计':''} <button disabled={locked} onClick={async()=>{try{update(await api(`/os-api/runs/${t.run_id}`));setCapture(null)}catch(e){setError(String(e))}}}>回放 / 审核</button></p>)}</details>}
 {!privateView&&<><h3>Inference 执行什么</h3><p>{selected.task}</p><p className="muted">{LEVEL[selected.difficulty]}。一个独立且持续的桌面；应用之间共享文件、设置和作业结果。</p><button disabled={locked} onClick={openInference}>打开独立 inference 环境 ↗</button>{inference&&<p>{inference.public_task.assignment}</p>}</>}
 </>:<p className="empty">选择任务，查看 A/B/C 方法和人工录制要求。</p>}</section></div></section>
}

function OSRecording({run,token,capture,onBusy,onSaved}:{run:Run;token:string;capture:MediaStream|null;onBusy:(b:boolean)=>void;onSaved:(r:Run)=>void}){
 const [state,setState]=useState('idle'),[error,setError]=useState(''),[local,setLocal]=useState<Blob|null>(null),[localURL,setLocalURL]=useState(''),[video,setVideo]=useState('');
 const [reviewer,setReviewer]=useState(run.recording?.reviewer||''),[note,setNote]=useState(run.recording?.note||'');
 const recorder=useRef<MediaRecorder|null>(null),active=useRef<MediaStream|null>(null),started=useRef<MediaStream|null>(null),mounted=useRef(true),timer=useRef<ReturnType<typeof setTimeout>|null>(null);
 const latest=useRef(run);latest.current=run;const base=`/os-api/runs/${run.id}/recordings`;
 useEffect(()=>{mounted.current=true;return()=>{mounted.current=false;if(timer.current)clearTimeout(timer.current);active.current?.getTracks().forEach(t=>t.stop())}},[]);
 useEffect(()=>{if(!local)return;const url=URL.createObjectURL(local);setLocalURL(url);return()=>URL.revokeObjectURL(url)},[local]);
 useEffect(()=>{if(!run.recording)return;let live=true,url='';const c=new AbortController();fetch(base+'/video',{headers:{Authorization:`Bearer ${token}`},signal:c.signal}).then(async r=>{if(!r.ok)throw Error('服务器录像加载失败');return r.blob()}).then(b=>{url=URL.createObjectURL(b);if(live)setVideo(url);else URL.revokeObjectURL(url)}).catch(e=>{if(live)setError(String(e))});return()=>{live=false;c.abort();if(url)URL.revokeObjectURL(url)}},[run.recording?.id]);
 useEffect(()=>{if(run.lesson?.finished&&recorder.current?.state==='recording')recorder.current.stop()},[run.lesson?.finished]);
 useEffect(()=>{if(!capture||started.current===capture)return;started.current=capture;active.current=capture;
   try{const mime=['video/webm;codecs=vp8','video/webm','video/mp4'].find(m=>MediaRecorder.isTypeSupported(m));const r=new MediaRecorder(capture,mime?{mimeType:mime}:undefined);recorder.current=r;const chunks:BlobPart[]=[];let size=0;
    r.ondataavailable=e=>{if(e.data.size){chunks.push(e.data);size+=e.data.size;if(size>150*1024*1024&&r.state==='recording')r.stop()}};
    r.onstop=()=>{if(timer.current)clearTimeout(timer.current);capture.getTracks().forEach(t=>t.stop());if(mounted.current)void upload(new Blob(chunks,{type:r.mimeType.split(';')[0]}))};
    r.onerror=()=>{setError('录制中断，请保留本地文件后重试。');if(r.state==='recording')r.stop();capture.getTracks().forEach(t=>t.stop());onBusy(false)};
    capture.getVideoTracks()[0].onended=()=>{if(r.state==='recording')r.stop()};r.start(1000);setState('recording');onBusy(true);timer.current=setTimeout(()=>{if(r.state==='recording')r.stop()},30*60*1000);
   }catch(e){capture.getTracks().forEach(t=>t.stop());setError(String(e));onBusy(false)}
 },[capture]);
 useEffect(()=>{if(!['recording','uploading'].includes(state))return;const warn=(e:BeforeUnloadEvent)=>{e.preventDefault();e.returnValue=''};window.addEventListener('beforeunload',warn);return()=>window.removeEventListener('beforeunload',warn)},[state]);
 async function upload(blob:Blob){setLocal(blob);setState('uploading');setError('');onBusy(true);try{const r=await fetch(base+'/upload',{method:'POST',headers:{Authorization:`Bearer ${token}`,'Content-Type':blob.type.split(';')[0]||'video/webm'},body:blob});const d=await r.json();if(!r.ok)throw Error(d.detail);await onSaved({...latest.current,recording:d});setState('saved')}catch(e){setError(String(e));setState('failed')}finally{onBusy(false)}}
 async function review(){setError('');onBusy(true);try{const r=await fetch(base+'/review',{method:'POST',headers:{Authorization:`Bearer ${token}`,'Content-Type':'application/json'},body:JSON.stringify({reviewer,note})});const d=await r.json();if(!r.ok)throw Error(d.detail);await onSaved({...latest.current,recording:d})}catch(e){setError(String(e))}finally{onBusy(false)}}
 return <section className="recording-controls"><h3>{state==='recording'?'● 正在录制':state==='uploading'?'正在上传录像…':run.recording?.approved?'已完成录制 · 审核通过':run.recording?'录像已上传 · 待审核':'人工录像'}</h3>
 {state==='recording'?<button className="danger" onClick={()=>recorder.current?.stop()}>结束并保存录像</button>:<label>上传本次示范的人工录屏（WebM / MP4）<input type="file" accept="video/webm,video/mp4,.webm,.mp4" disabled={state==='uploading'} onChange={e=>{const f=e.target.files?.[0];if(f)void upload(new Blob([f],{type:f.name.endsWith('.mp4')?'video/mp4':'video/webm'}))}}/></label>}
 <p className="muted">仅捕获你选择的画面。停止后自动上传，最长 30 分钟、150 MB。自动检查验证操作结果；人工审核确认视频清晰、覆盖全部局部示例且由人操作。</p>
 {error&&<p className="error" role="alert">{error}</p>}{localURL&&<p><a href={localURL} download={`OS-demo-${run.id}.${local?.type==='video/mp4'?'mp4':'webm'}`}>下载原始录像</a>{state==='failed'&&local&&<button onClick={()=>upload(local)}>重试上传</button>}</p>}
 {video&&<><video src={video} controls style={{width:'100%'}}/><a href={video} download={`OS-demo-${run.id}.mp4`}>下载服务器 MP4</a><label>审核人<input value={reviewer} onChange={e=>setReviewer(e.target.value)}/></label><label>录制检查备注<textarea value={note} onChange={e=>setNote(e.target.value)} placeholder="确认人工操作、输入和结果清晰、全部示例使用同一方法。"/></label><button disabled={!reviewer.trim()||!!run.recording?.approved||state==='uploading'} onClick={review}>{run.recording?.approved?'已审核通过':'确认人工录像完整并审核通过'}</button><p>审核要求本次所有示范组自动检查通过。审核结果与录像持久保存，回到任务卡仍可查看。</p></>}
 </section>
}
