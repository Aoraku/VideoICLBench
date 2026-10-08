import {applicationLaunchError,applicationResponse} from './applicationLaunchError';
import {useEffect,useRef,useState} from 'react';
import {flushSync} from 'react-dom';
import {HumanRecording} from './HumanRecording';
import type {HumanRun} from './HumanSession';
import {recordingSteps} from './recordingGuide';
import {nativeApplicationUrl} from './nativeApplicationUrl';
import {V2TaskList} from './V2TaskList';
import {OSTaskList} from './OSTaskList';
import './recorder.css';

type Task={id:number;title:string;app:string;status:string;variants:Record<string,string>};
const APPS:Record<string,string>={chat:'通讯 A',im:'通讯 B',music:'音乐',news:'新闻',code:'在线判题',media:'视频与信息流',blog:'博客',studio:'AI 工作台',travel:'旅游',shop:'购物',bank:'账户',gomoku:'五子棋',games:'游戏'};
async function api(path:string,token:string,method='GET',body?:unknown){
  const r=await fetch(path,{method,headers:{Authorization:`Bearer ${token}`,'Content-Type':'application/json'},body:body===undefined?undefined:JSON.stringify(body)});
  return applicationResponse(r);
}
export function RecorderPortal(){
  const [listVersion,setListVersion]=useState('v2');
  const [token,setToken]=useState(sessionStorage.getItem('vic-manager')||''),[entry,setEntry]=useState('');
  const [tasks,setTasks]=useState<Task[]>([]),[modules,setModules]=useState<string[]>([]),[error,setError]=useState('');
  const [query,setQuery]=useState(''),[filter,setFilter]=useState('all'),[selected,setSelected]=useState<Task|null>(null),[variant,setVariant]=useState('A');
  const [preview,setPreview]=useState<any>(null),[previewError,setPreviewError]=useState(''),[busy,setBusy]=useState(false),[recordingBusy,setRecordingBusy]=useState(false);
  const [sessions,setSessions]=useState<Record<string,HumanRun>>({}),[capture,setCapture]=useState<MediaStream|null>(null),[notice,setNotice]=useState(''),[clipboard,setClipboard]=useState('');
  const [privateCapture,setPrivateCapture]=useState(false);
  const [savedV1,setSavedV1]=useState<HumanRun[]>([]);
  const [history,setHistory]=useState<HumanRun[]|null>(null),[historyTake,setHistoryTake]=useState<HumanRun|null>(null);
  const appWindow=useRef<Window|null>(null),key=selected?`${selected.id}-${variant}`:'',run=sessions[key]||savedV1.find(r=>r.task_id===selected?.id&&r.variant===variant&&!r.recording?.archived),locked=busy||recordingBusy;
  const ready=!!selected&&selected.status==='application-ready'&&modules.includes(selected.app);
  useEffect(()=>{if(!token||listVersion!=='v1')return;let live=true;const refresh=()=>api('/v1/recordings',token).then(rows=>{if(live)setSavedV1(rows.filter((r:any)=>r.manifest?.suite!=='v2'))}).catch(e=>setError(String(e)));void refresh();window.addEventListener('focus',refresh);return()=>{live=false;window.removeEventListener('focus',refresh)}},[token,listVersion]);
  function v1Status(taskId:number){return ['A','B','C'].map(v=>{const r=savedV1.find(r=>r.task_id===taskId&&r.variant===v&&!r.recording?.archived);return r?`${v}：${r.recording?.contract_current===false?'历史规则录像':r.recording?.approved?'已完成录制':'已上传 · 待审核'}`:''}).filter(Boolean).join('；')}
  function update(r:HumanRun){setSessions(s=>({...s,[`${r.task_id}-${r.variant}`]:r}));if(r.recording)setSavedV1(rows=>[r,...rows.filter(item=>item.id!==r.id||item.epoch!==r.epoch)])}
  useEffect(()=>{if(!token)return;Promise.all([api('/v1/tasks',token),api('/v1/capabilities',token)]).then(([a,b])=>{setTasks(a.tasks);setModules(b.direct_application_modules||[])}).catch(e=>setError(String(e)))},[token]);
  useEffect(()=>{setPreview(null);setPreviewError('');setNotice('');setClipboard('');setCapture(null);if(!selected||selected.id>75)return;let current=true;api(`/v1/tasks/${selected.id}/recording-preview`,token).then(p=>{if(current)setPreview(p)}).catch(e=>{if(current)setPreviewError(String(e))});return()=>{current=false}},[selected?.id,token]);
  useEffect(()=>{if(!locked)return;const warn=(e:BeforeUnloadEvent)=>{e.preventDefault();e.returnValue=''};window.addEventListener('beforeunload',warn);return()=>window.removeEventListener('beforeunload',warn)},[locked]);
  useEffect(()=>{
    if(!privateCapture||!run?.lesson||run.lesson.total<2)return;
    const id=run.id;let live=true;
    const timer=setInterval(()=>{api(`/v1/runs/${id}`,token).then(value=>{if(live)update(value)}).catch(()=>{})},1500);
    return()=>{live=false;clearInterval(timer)};
  },[privateCapture,run?.id,token]);
  async function prepare(reset=false){
    if(!selected)throw Error('请先选择任务。');
    if(run?.lesson&&!reset&&['ready','running'].includes(run.status))return run;
    const next=run?.lesson&&reset&&!run.recording?await api(`/v1/runs/${run.id}/reset`,token,'POST'):await api('/v1/runs',token,'POST',{task_id:selected.id,variant,seed:0,mode:'demo',runtime:'browser',interaction:'human',teaching:true});
    const value={...next,rule:selected.variants[variant]};update(value);return value as HumanRun;
  }
  async function reset(){setBusy(true);setError('');try{appWindow.current?.close();appWindow.current=null;setCapture(null);await prepare(true);setNotice('环境已重置。点击“开始录制”将从应用首页进入。')}catch(e){setError(String(e))}finally{setBusy(false)}}
  async function start(){
    if(locked||!ready)return;
    // Commit the rule-free DOM before any screen-capture request can sample it.
    flushSync(()=>{setPrivateCapture(true);setBusy(true);setError('');setNotice('');setCapture(null)});
    // Reserve a tab during the click, so preparation cannot trigger popup blocking.
    const tab=window.open('about:blank','_blank');
    if(!tab){setError('浏览器拦截了应用标签页。请允许本站打开弹出式窗口后重试。');setBusy(false);setPrivateCapture(false);return}
    tab.opener=null;tab.document.title=`任务 ${selected!.id} · 录制应用`;appWindow.current=tab;
    // Request screen access during this same user gesture, not after the API request.
    const supported=!!navigator.mediaDevices?.getDisplayMedia&&typeof MediaRecorder!=='undefined';
    const streamPromise=supported?navigator.mediaDevices.getDisplayMedia({video:{frameRate:30},audio:false}).then(value=>({value,error:null})).catch(error=>({value:null,error})):Promise.resolve({value:null,error:null});
    let stream:MediaStream|null=null;
    try{
      const prepared=await prepare();
      if(!prepared.application_url)throw Error('应用入口暂不可用。');
      if(tab.closed)throw Error('应用标签页已关闭，请重新开始。');
      tab.location.replace(nativeApplicationUrl(prepared.application_url));
      const access=await streamPromise;stream=access.value;
      if(tab.closed){stream?.getTracks().forEach(t=>t.stop());throw Error('应用标签页已关闭，请重新开始。')}
      if(access.error){setNotice('应用已打开，但尚未录屏。请允许屏幕共享后重试，或使用系统录屏并上传视频。');return}
      if(stream){setCapture(stream);setRecordingBusy(true);setNotice(prepared.lesson && prepared.lesson.total>1 ? `正在录制。请从应用首页开始，连续完成 ${prepared.lesson.total} 组练习；最后点击应用内“完成练习”，录像会自动保存。` : '正在录制。请在应用首页开始操作，完成后回到此任务卡结束录制。')}
      else setNotice('应用已打开。此浏览器不支持内置录屏，请使用系统录屏，完成后在此卡上传视频；也可用 Chrome 或 Edge 打开本平台。');
      tab.focus();
    }catch(e){applicationLaunchError(tab,e);stream?.getTracks().forEach(t=>t.stop());void streamPromise.then(s=>s.value?.getTracks().forEach(t=>t.stop()));setError(String(e))}finally{setBusy(false)}
  }
  async function evaluate(r:HumanRun){
    setBusy(true);setError('');try{const result=await api(`/v1/runs/${r.id}/evaluate`,token,'POST',r.task_id===43&&r.variant==='B'?{clipboard}:{});update({...r,status:'completed',result})}catch(e){setError(String(e))}finally{setBusy(false)}
  }
  async function recorded(r:HumanRun){const current=await api(`/v1/runs/${r.id}`,token);update(current);setNotice('录像已保存，可以回放检查。');if(current.status==='recorded'&&!current.result&&!(current.task_id===43&&current.variant==='B'))void evaluate(current)}
  async function loadHistory(){try{setHistory(await api('/v1/recordings',token));setHistoryTake(null)}catch(e){setError(String(e))}}
  function openHistory(r:HumanRun){setHistoryTake(r)}
  function updateHistory(r:HumanRun){setHistoryTake(r);setHistory(rows=>rows?.map(item=>item.id===r.id&&item.epoch===r.epoch?r:item)||null)}

  if(!token)return <main className="login"><div className="brand"><span className="logo">V</span>VideoICL</div><h1>视频录制台</h1><p>输入访问密钥，选择任务开始录制。</p><form onSubmit={e=>{e.preventDefault();sessionStorage.setItem('vic-manager',entry);setToken(entry);setEntry('');setError('')}}><label>访问密钥<input type="password" value={entry} onChange={e=>setEntry(e.target.value)} required autoComplete="off"/></label><button className="primary">进入录制台</button></form>{error&&<p className="error" role="alert">{error}</p>}</main>;
  const shown=tasks.filter(t=>(filter==='all'||t.app===filter)&&`${t.id} ${t.title}`.toLowerCase().includes(query.toLowerCase()));
  return <main className="recorder-portal"><header className="recorder-header"><div><div className="brand"><span className="logo">V</span>VideoICL <span className="muted">视频录制台</span></div><h1>{listVersion==='v2'?'选择任务，预览环境或录制示范':'选择任务，录下完整操作'}</h1><p className="muted">{listVersion==='v2'?'示范与执行环境相互独立：先试操作，再录制或检查交付。':'阅读版本规则 → 开始录制 → 从应用首页完成任务'}</p></div><div className="actions"><button disabled={locked} onClick={()=>history?setHistory(null):loadHistory()}>{history?'返回任务列表':'录制记录'}</button><button disabled={locked} onClick={()=>{sessionStorage.removeItem('vic-manager');setToken('');setSessions({});setSelected(null);setHistory(null)}}>退出</button></div></header>
    {error&&<div className="error" role="alert">{error}<button onClick={()=>setError('')}>关闭</button></div>}
    <nav className="actions" aria-label="任务版本"><button disabled={locked} aria-pressed={listVersion==='v1'} onClick={()=>setListVersion('v1')}>v1 list</button><button disabled={locked} aria-pressed={listVersion==='v2'} onClick={()=>setListVersion('v2')}>v2 list</button><button disabled={locked} aria-pressed={listVersion==='os'} onClick={()=>setListVersion('os')}>OS · 36 题</button></nav>
    {history?<section className="panel" aria-label="全部录制记录"><h2>服务器录制记录 · {history.length} 份</h2><p>包括各题、各版本与历史轮次的已保存录像。选择一份查看、下载或审核。</p><table><thead><tr><th>任务</th><th>版本</th><th>录制状态</th><th/></tr></thead><tbody>{history.map(r=><tr key={`${r.id}:${r.epoch}`}><td>#{r.task_id} {tasks.find(t=>t.id===r.task_id)?.title}</td><td>{r.variant} · 第 {r.epoch+1} 轮</td><td>{r.recording?.contract_current===false?'历史规则录像':r.recording?.archived?'历史轮次录像':r.recording?.approved?'已完成录制 · 审核通过':'已上传 · 待审核'}{r.recording?.reviewer&&` · ${r.recording.reviewer}`}</td><td><button disabled={locked} onClick={()=>openHistory(r)}>查看</button></td></tr>)}</tbody></table>{!history.length&&<p className="empty">还没有已上传的录像。</p>}{historyTake&&<HumanRecording key={`${historyTake.id}-${historyTake.epoch}`} run={historyTake} token={token} onUpdate={updateHistory} onBusy={setRecordingBusy}/>}</section>:listVersion==='os'?<OSTaskList token={token}/>:listVersion==='v2'?<V2TaskList token={token} onBusy={setRecordingBusy}/>:<>
    <div className="toolbar"><input aria-label="搜索任务" placeholder="搜索任务名称或编号…" value={query} onChange={e=>setQuery(e.target.value)}/><select aria-label="应用筛选" value={filter} onChange={e=>setFilter(e.target.value)}><option value="all">全部应用</option>{Object.entries(APPS).map(([k,v])=><option key={k} value={k}>{v}</option>)}</select><span className="muted">{shown.length} 个任务</span></div>
    <div className="recorder-layout"><section className="panel task-list"><table><thead><tr><th>任务</th><th>应用</th></tr></thead><tbody>{shown.map(t=><tr key={t.id} tabIndex={locked?-1:0} aria-disabled={locked} aria-selected={selected?.id===t.id} className={selected?.id===t.id?'selected':''} onClick={()=>{if(!locked){setSelected(t);setError('')}}} onKeyDown={e=>{if(!locked&&e.key==='Enter')setSelected(t)}}><td><span className="task-id">{String(t.id).padStart(3,'0')}</span>{t.title}{v1Status(t.id)&&<small className="recording-badge">{v1Status(t.id)}</small>}</td><td><span className="muted">{APPS[t.app]||'暂未开放'}</span></td></tr>)}</tbody></table></section>
    <section className="panel recorder-card" aria-label="录制任务卡">{selected?<><p className="eyebrow">任务 {String(selected.id).padStart(3,'0')}</p><h2>{selected.title}</h2>{!privateCapture&&<><div className="segmented">{'ABC'.split('').map(v=><button key={v} disabled={locked} aria-pressed={variant===v} className={variant===v?'chosen':''} onClick={()=>{setVariant(v);setCapture(null);setNotice('');setClipboard('')}}>版本 {v}</button>)}</div>
      <div className="rule"><span>版本 {variant} 的规则</span><p>{selected.variants[variant]}</p>{selected.id===45&&<p>数量与商品名紧邻，不额外插入空格。</p>}</div>
      <div className="recording-instructions"><h3>录制中要完成的事情</h3>{preview&&preview.task_id===selected.id?<><ol>{recordingSteps(preview,variant,selected.variants[variant]).map((line,i)=><li key={i}>{line}</li>)}</ol>{preview.type==='T'&&![18,20,44].includes(selected.id)&&preview.source?.text&&<div className="recording-source"><b>{preview.episode_count>1?'第一组原始内容预览（其余各组在应用内查看）':'需要处理的原始内容'}</b><pre>{preview.source.text}</pre></div>}<p className="muted">从应用默认首页开始，保留找到目标页面的导航过程。{preview.type!=='T'&&(selected.id<66?'数值并列时按初始列表顺序处理。':selected.id===68?'合并次数或得分并列最优时，任选一个有效方向。':selected.id===69?'移动方向自行选择，在停止条件首次满足时停止。':'候选点并列时按行、列升序选择。')}</p></>:<p className="muted">{previewError|| (ready?'正在载入操作说明…':'此任务尚未开放录制。')}</p>}</div></>}
      {privateCapture&&<p className="recorder-notice">请在应用窗口完成操作。{run?.lesson&&run.lesson.total>1&&` 当前练习 ${run.lesson.index+1} / ${run.lesson.total}；每组完成后，在应用右下角继续下一组。`}</p>}
      <div className="recorder-start"><button disabled={locked||!ready} onClick={reset}>重置环境</button><button className="primary" disabled={locked||!ready||!preview||!!run?.result||run?.status==='recorded'} onClick={start}>{busy?'正在准备…':recordingBusy?'录制进行中':'● 开始录制'}</button></div>
      <p className="muted recording-hint">直接进入应用首页。内置录屏请选择应用标签页或所在窗口，并按上方说明完成全部练习。</p>
      {privateCapture&&!locked&&<button onClick={()=>setPrivateCapture(false)}>已停止所有录屏，返回任务说明</button>}
      {notice&&<p className="recorder-notice" role="status">{notice}</p>}
      {run&&<><HumanRecording key={`${run.id}-${run.epoch}`} run={run} token={token} onUpdate={recorded} onBusy={setRecordingBusy} initialStream={capture} compact/>{run.task_id===43&&run.variant==='B'&&!run.result&&<label>粘贴刚才复制的内容<textarea value={clipboard} onChange={e=>setClipboard(e.target.value)}/></label>}{run.status==='recorded'&&!run.result&&<button disabled={locked||(run.task_id===43&&run.variant==='B'&&!clipboard)} onClick={()=>evaluate(run)}>检查任务完成情况</button>}{run.result&&<div className="recording-result" role="status"><h3>{run.result.success?'✓ 任务完成':'任务未通过，请检查操作'}</h3><p>完成度 {Math.round(run.result.completion*100)}%。需要重录时点击“重置环境”。</p></div>}<details className="recording-details"><summary>问题反馈信息</summary><p>任务 {run.task_id} / 版本 {run.variant}<br/>记录编号 {run.id}<br/>第 {run.epoch+1} 次环境</p></details></>}
    </>:<div className="empty"><h2>选择一个任务</h2><p>阅读 A / B / C 的规则和操作说明，然后开始录制。</p></div>}</section></div></>}
  </main>;
}
