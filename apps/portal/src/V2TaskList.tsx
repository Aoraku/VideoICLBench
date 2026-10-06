import {useEffect,useRef,useState} from 'react';
import {nativeApplicationUrl} from './nativeApplicationUrl';
import {HumanRecording} from './HumanRecording';
import './v2-task-list.css';

type Mode='demo'|'eval';
type Sort='id'|'difficulty'|'platform';
const difficultyLabel:Record<string,string>={low:'低',medium:'中',hard:'高'};
const difficultyRank:Record<string,number>={low:0,medium:1,hard:2};
const platformName=(task:any)=>(task.platforms?.length?task.platforms:[task.app]).join(' · ');
function variantValue(value:any,variant:string){return value&&typeof value==='object'&&!Array.isArray(value)?value[variant]:value}

export function V2TaskList({token,onBusy}:{token:string;onBusy:(value:boolean)=>void}) {
  const [tasks,setTasks]=useState<any[]>([]),[selected,setSelected]=useState<any>(null);
  const [variant,setVariant]=useState('A'),[query,setQuery]=useState(''),[difficulty,setDifficulty]=useState('all');
  const [platform,setPlatform]=useState('all'),[sort,setSort]=useState<Sort>('id'),[ascending,setAscending]=useState(true),[mode,setMode]=useState<Mode>('demo');
  const [runs,setRuns]=useState<Record<string,any>>({}),[busy,setBusy]=useState(false),[error,setError]=useState(''),[notice,setNotice]=useState('');
  const [capture,setCapture]=useState<MediaStream|null>(null),[recording,setRecording]=useState(false);
  const [privateView,setPrivateView]=useState(false),[recordingRun,setRecordingRun]=useState<string|null>(null);
  const [library,setLibrary]=useState<any[]>([]),[take,setTake]=useState<string|null>(null);
  const tabs=useRef<Record<string,Window|null>>({});
  const runKey=(value:Mode)=>`${selected?.id}-${variant}-${value}`;
  const demo=runs[runKey('demo')],current=runs[runKey(mode)];
  useEffect(()=>{onBusy(busy||recording);return()=>onBusy(false)},[busy,recording,onBusy]);
  async function call(path:string,body?:any){const r=await fetch(path,{method:body===undefined?'GET':'POST',headers:{Authorization:`Bearer ${token}`,'Content-Type':'application/json'},body:body===undefined?undefined:JSON.stringify(body)});const v=await r.json();if(!r.ok)throw Error(typeof v.detail==='string'?v.detail:JSON.stringify(v.detail));return v}
  async function refreshRecordings(){try{setLibrary(await call('/v1/recordings'))}catch(e){setError(`读取录制记录失败：${String(e)}`)}}
  useEffect(()=>{void refreshRecordings();const refresh=()=>{if(!document.hidden)void refreshRecordings()};window.addEventListener('focus',refresh);document.addEventListener('visibilitychange',refresh);return()=>{window.removeEventListener('focus',refresh);document.removeEventListener('visibilitychange',refresh)}},[token]);
  useEffect(()=>{call('/v2/tasks').then(v=>setTasks(v.tasks)).catch(e=>setError(String(e)))},[token]);
  useEffect(()=>{if(!recording||!demo)return;const key=runKey('demo');const interval=setInterval(()=>{call(`/v1/runs/${demo.id}`).then(value=>setRuns(s=>({...s,[key]:value}))).catch(()=>{})},1500);return()=>clearInterval(interval)},[recording,demo?.id]);
  async function prepare(value:Mode,reset=false){
    const key=runKey(value),old=runs[key];
    const saved=old&&(old.recording||library.some(x=>x.id===old.id&&x.epoch===old.epoch));
    const r=old&&reset&&!saved?await call(`/v1/runs/${old.id}/reset`,{}):old&&!saved&&!old.result&&old.status==='ready'&&!reset?old:await call('/v1/runs',{suite:'v2',task_id:selected.id,variant,seed:value==='demo'?0:10001,mode:value,runtime:'browser',interaction:'human',teaching:value==='demo'});
    setRuns(s=>({...s,[key]:r}));return r;
  }
  async function open(value:Mode,record=false){
    const tab=window.open('about:blank','_blank');if(!tab){setError('请允许本站打开应用标签页');return}
    tab.document.title='正在准备应用';tab.document.body.textContent='正在准备应用首页，请稍候。录制画面将在任务卡中选择。';window.focus();tab.opener=null;setBusy(true);setError('');setNotice('');
    try{
      // A recording always starts from the initial homepage, even after a preview.
      const r=await prepare(value,record);tabs.current[runKey(value)]=tab;
      tab.location.replace(nativeApplicationUrl(r.application_url));
      if(record){setTake(null);setRecordingRun(r.id);setCapture(null);setPrivateView(true);window.focus()}
      else tab.focus();
      if(record)setNotice('应用首页已准备好。点击“选择应用画面并开始录制”，在浏览器分享窗口中选择刚打开的应用标签页。');
      else setNotice(value==='demo'?'示范环境已在新标签页打开，不会录屏。':'执行环境已在新标签页打开。完成后可回到这里检查交付。');
    }catch(e){tab.close();setError(String(e));setPrivateView(false)}finally{setBusy(false)}
  }
  async function reset(value:Mode){
    setBusy(true);setError('');setNotice('');
    try{const r=await prepare(value,true);const tab=tabs.current[runKey(value)];if(tab&&!tab.closed){const next=new URL(nativeApplicationUrl(r.application_url),location.href);next.searchParams.set('vic_reset',String(r.epoch));tab.location.replace(next.toString())}if(value==='demo'){setCapture(null);setRecordingRun(null)}setNotice(`${value==='demo'?'示范':'执行'}环境已恢复初态${tab&&!tab.closed?'，应用标签页已更新':''}。`)}catch(e){setError(String(e))}finally{setBusy(false)}
  }
  async function check(){
    if(!current)return;setBusy(true);setError('');setNotice('');
    try{if(mode==='demo'){const fresh=await call(`/v1/runs/${current.id}`);if(fresh.lesson&&!fresh.lesson.finished)throw Error('请先在应用中完成全部示范练习，再检查结果。');}const result=await call(`/v2/tasks/${selected.id}/eval`,{run_id:current.id});setRuns(s=>({...s,[runKey(mode)]:{...current,result,status:'completed'}}))}catch(e){setError(String(e))}finally{setBusy(false)}
  }
  function chooseSort(value:Sort){if(sort===value)setAscending(v=>!v);else{setSort(value);setAscending(true)}}
  const platforms=[...new Set<string>(tasks.flatMap(t=>t.platforms?.length?t.platforms:[t.app]))].sort((a,b)=>a.localeCompare(b));
  const shown=tasks.filter(t=>(difficulty==='all'||t.difficulty===difficulty)&&(platform==='all'||(t.platforms||[t.app]).includes(platform))&&`${String(t.id).padStart(3,'0')} ${t.title} ${t.assignment} ${platformName(t)}`.toLowerCase().includes(query.trim().toLowerCase())).sort((a,b)=>{
    const comparison=sort==='difficulty'?difficultyRank[a.difficulty]-difficultyRank[b.difficulty]:sort==='platform'?platformName(a).localeCompare(platformName(b)):a.id-b.id;
    return (comparison||a.id-b.id)*(ascending?1:-1);
  });
  const recordings=library.filter(r=>r.task_id===selected?.id&&r.variant===variant&&r.manifest?.suite==='v2');
  const savedTake=recordings.find(r=>`${r.id}:${r.epoch}`===take)||recordings[0];
  const recordingToShow=demo&&recordingRun===demo.id?demo:savedTake;
  const recordingLabel=(r:any)=>!r.recording?.available?'录像文件缺失':r.recording?.contract_current===false?'历史规则录像':r.recording?.archived?'历史轮次录像':r.recording?.status==='rejected'?'已上传 · 审核未通过':r.recording?.approved?'已完成录制 · 审核通过':'已上传 · 待审核';
  function updateRecording(r:any){if(!r.recording?.archived)setRuns(s=>({...s,[`${r.task_id}-${r.variant}-demo`]:r}));void refreshRecordings()}
  function badges(id:number){return ['A','B','C'].map(v=>{const matches=library.filter(r=>r.task_id===id&&r.variant===v&&r.manifest?.suite==='v2');const r=matches.find(r=>r.recording?.approved&&r.recording?.contract_current)||matches[0];return r?`${v}：${recordingLabel(r)}`:''}).filter(Boolean).join('；')}
  const locked=busy||recording,ready=selected?.status==='application-ready';
  const explanation=selected&&variantValue(selected.rule_explanations||selected.demo?.rule_explanations,variant);
  const customSteps=selected&&variantValue(selected.recording_steps||selected.demo?.recording_steps,variant);
  const steps=Array.isArray(customSteps)?customSteps:customSteps?[customSteps]:selected?[
    '从应用默认首页进入任务页面，保留查找与导航过程。',
    selected.demo.instructions,
    `对照版本 ${variant} 的规则完成操作，并展示保存后的实际结果。`,
    '完成当前组后点击“下一组”；演示全部练习后点击“完成练习”。',
  ]:[];
  const executionSteps=(selected?.inference?.steps||[]).filter((step:string)=>step!==selected.inference.instructions&&!step.startsWith('完成边界：'));
  const sortHeading=(value:Sort,label:string)=><th aria-sort={sort===value?(ascending?'ascending':'descending'):'none'}><button onClick={()=>chooseSort(value)}>{label}<span aria-hidden="true">{sort===value?(ascending?' ↑':' ↓'):' ↕'}</span></button></th>;
  return <section className="v2-workspace" aria-label="v2 任务工作台">
    <div className="v2-toolbar"><input aria-label="搜索 v2 任务" placeholder="搜索编号、任务或平台" value={query} onChange={e=>setQuery(e.target.value)}/><select aria-label="执行难度" value={difficulty} onChange={e=>setDifficulty(e.target.value)}><option value="all">全部难度</option><option value="low">低 · 多次应用规则</option><option value="medium">中 · 完整长程任务</option><option value="hard">高 · 跨平台长程任务</option></select><select aria-label="筛选平台" value={platform} onChange={e=>setPlatform(e.target.value)}><option value="all">全部平台</option>{platforms.map(p=><option key={p}>{p}</option>)}</select><span>{shown.length} / {tasks.length} 题</span></div>
    {error&&<p role="alert" className="error">{error}</p>}
    <div className="v2-layout"><section className="v2-list" aria-label="任务列表"><table><thead><tr>{sortHeading('id','任务序号')}{sortHeading('difficulty','难度')}{sortHeading('platform','平台')}</tr></thead><tbody>{shown.map(t=><tr key={t.id} aria-selected={selected?.id===t.id}><td><button aria-label={`${String(t.id).padStart(3,'0')} ${t.title}`} disabled={locked} onClick={()=>{setSelected(t);setTake(null);setRecordingRun(null);setPrivateView(false);setCapture(null);setError('');setNotice('')}}><span className="v2-task-number">{String(t.id).padStart(3,'0')}</span><span>{t.title}{badges(t.id)&&<small className="recording-badge">{badges(t.id)}</small>}</span></button></td><td><span className={`v2-level v2-level-${t.difficulty}`}>{difficultyLabel[t.difficulty]}</span></td><td className="v2-platform">{platformName(t)}</td></tr>)}</tbody></table>{!shown.length&&<p className="v2-empty">没有匹配的任务，请调整搜索或筛选条件。</p>}</section>
    <section className="v2-detail" aria-label="任务详情">{selected?<>
      <header className="v2-card-header"><div className="v2-card-meta"><span>任务 {String(selected.id).padStart(3,'0')}</span><span>{mode==='demo'?platformName({platforms:selected.demo.platforms||[selected.app]}):platformName(selected)}</span><span className={`v2-level v2-level-${selected.difficulty}`}>执行难度：{difficultyLabel[selected.difficulty]}</span></div><h2>{mode==='demo'?(selected.demo.title||selected.title):selected.title}</h2>{!privateView&&<p>{mode==='demo'?(selected.demo.objective||'展示本版本规则的输入、操作与结果。'):selected.assignment}</p>}</header>
      {!privateView&&<><div className="v2-version-row"><span>规则版本</span><div className="v2-versions">{['A','B','C'].map(v=><button key={v} disabled={locked} aria-pressed={variant===v} onClick={()=>{setVariant(v);setTake(null);setRecordingRun(null);setError('');setNotice('')}}>版本 {v}</button>)}</div></div>
        <div className="v2-mode-tabs" role="tablist" aria-label="任务环境"><button id="v2-demo-tab" role="tab" aria-controls="v2-mode-content" aria-selected={mode==='demo'} disabled={locked} onClick={()=>{setMode('demo');setNotice('')}}>示范 · demo</button><button id="v2-eval-tab" role="tab" aria-controls="v2-mode-content" aria-selected={mode==='eval'} disabled={locked} onClick={()=>{setMode('eval');setNotice('')}}>执行 · inference</button></div>
        <div id="v2-mode-content" role="tabpanel" aria-labelledby={mode==='demo'?'v2-demo-tab':'v2-eval-tab'} className="v2-mode-content">
          {mode==='demo'?<><div className="v2-rule"><span>版本 {variant} · 本次要示范的规则</span><p>{selected.variants[variant]}</p>{selected.id===16&&variant==='C'&&<p>固定回复正文：<strong>{selected.recording_parameters?.fixed_reply||'已确认'}</strong>（不含引号，不加标点或换行）。对每条包含“收到”的消息只回复一次。</p>}{explanation&&<div className="v2-rule-explanation">{Array.isArray(explanation)?explanation.join('；'):String(explanation)}</div>}</div><h3>录制时依次完成</h3><ol className="v2-steps">{steps.map((step:any,i:number)=><li key={i}>{String(step)}</li>)}</ol><div className="v2-delivery" aria-label="示范完成标准"><span>示范完成标准</span>{selected.demo.completion_checks?.length>0?<ul>{selected.demo.completion_checks.map((item:string,i:number)=><li key={i}>{item}</li>)}</ul>:<p>完成全部规则示例，清楚展示每组输入、操作和保存后的结果。</p>}</div><p className="v2-hint">示范范围：从首页进入规则操作页，完成本题示例。完整业务流程仅属于执行环境。</p></>:<><h3>需要完成的工作</h3><p className="v2-instructions">{selected.inference.instructions}</p>{executionSteps.length>0&&<ol className="v2-steps">{executionSteps.map((step:string,i:number)=><li key={i}>{step}</li>)}</ol>}<div className="v2-delivery" aria-label="执行完成标准"><span>最终交付</span><p>{selected.delivery}</p>{selected.inference.completion_checks?.length>0&&<ul>{selected.inference.completion_checks.map((item:string,i:number)=><li key={i}>{item}</li>)}</ul>}</div><p className="v2-hint">执行环境使用独立数据，不影响示范练习。这里可以直接进入应用，手动验证整条工作流程。</p><details className="v2-difficulty-note"><summary>为什么是{difficultyLabel[selected.difficulty]}难度</summary><p>{selected.difficulty_basis||({low:'对一批新对象或多个独立局面反复应用视频规则，完成整批工作。',medium:'围绕明确交付目标完成资料核对、规则处理、成果编制与交付；后续阶段依赖前序真实结果。',hard:'在多个真实应用及业务模块之间查找和关联资料，处理相互依赖的工作，再向正确对象交付可追溯成果。'} as Record<string,string>)[selected.difficulty]}</p></details></>}
        </div>
      </>}
      {!ready&&<p className="v2-hint">此执行环境正在实现，尚未开放试用。</p>}
      {!privateView&&<div className="v2-actions"><button className="v2-primary" disabled={locked||!ready} onClick={()=>open(mode)}>{busy?'正在准备…':mode==='demo'?'预览示范环境':'打开执行环境'}<span aria-hidden="true"> ↗</span></button><button disabled={locked||!ready} onClick={()=>reset(mode)}>{mode==='demo'?'重置示范':'重置执行环境'}</button>{current&&<button disabled={locked||!ready||!!current.result} onClick={check}>{mode==='demo'?'检查示范结果':'检查最终交付'}</button>}</div>}
      {mode==='eval'&&current&&!privateView&&<p className="v2-hint">最终检查会提交本次结果；如需修改后重试，请重置执行环境。</p>}{notice&&!privateView&&<p className="v2-notice" role="status">{notice}</p>}
      {!privateView&&current?.result&&<div className={`v2-result ${current.result.success?'v2-result-pass':''}`} role="status"><b>{current.result.success?'检查通过':'尚未完成'}</b><span>完成度 {Math.round((current.result.completion||0)*100)}%</span>{current.result.violations?.length>0&&<p>{current.result.violations.join('；')}</p>}</div>}
      {mode==='demo'&&!privateView&&recordings.length>0&&<section className="recording-library" aria-label="本版本录制记录"><h3>本版本录制记录 · {recordings.length} 份</h3><p>录像和审核状态保存在服务器，切换题目或刷新后仍可查看。重新录制保留已有录像。</p>{recordings.map(r=><button key={`${r.id}:${r.epoch}`} disabled={locked} aria-pressed={recordingToShow?.id===r.id&&recordingToShow?.epoch===r.epoch} onClick={()=>{setTake(`${r.id}:${r.epoch}`);setRecordingRun(null)}}>{recordingLabel(r)} · {new Date(r.created_at).toLocaleString()} · {r.recording.reviewer||'尚未审核'} · {r.id.slice(0,8)} / {r.epoch+1}</button>)}</section>}
      {mode==='demo'&&!privateView&&<div className="v2-record-start"><div><b>准备好录制了？</b><p>从初始首页重新开始，选择应用标签页或窗口。</p></div><button disabled={locked||!ready} onClick={()=>open('demo',true)}>{recordings.length?'重新录制（保留已有录像）':'开始录制'}</button></div>}
      {privateView&&!demo?.result&&demo?.status!=="recorded"&&<p className="v2-notice">应用首页已在新标签页准备好。请点击下方“选择应用画面并开始录制”，选择应用标签页并允许分享；录制开始后会切换到应用。任务说明已隐藏，避免录入规则文字。</p>}
      {mode==='demo'&&recordingToShow&&<HumanRecording key={`${recordingToShow.id}-${recordingToShow.epoch}`} run={recordingToShow} token={token} onUpdate={updateRecording} onBusy={setRecording} initialStream={capture} onStarted={()=>tabs.current[runKey('demo')]?.focus()} compact/>}
      {privateView&&!locked&&<button onClick={()=>setPrivateView(false)}>返回任务说明</button>}
    </>:<div className="v2-welcome"><span className="v2-welcome-icon" aria-hidden="true">↗</span><h2>选择一项任务</h2><p>查看清晰的示范步骤，或直接进入执行环境验证工作流程。</p><div><b>示范环境</b><span>预览规则、练习、录制</span></div><div><b>执行环境</b><span>实际操作、检查最终交付</span></div></div>}</section></div>
  </section>;
}
