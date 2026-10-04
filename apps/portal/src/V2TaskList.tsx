import {useEffect,useRef,useState} from 'react';
import {flushSync} from 'react-dom';
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
  const tabs=useRef<Record<string,Window|null>>({});
  const runKey=(value:Mode)=>`${selected?.id}-${variant}-${value}`;
  const demo=runs[runKey('demo')],current=runs[runKey(mode)];
  useEffect(()=>{onBusy(busy||recording);return()=>onBusy(false)},[busy,recording,onBusy]);
  async function call(path:string,body?:any){const r=await fetch(path,{method:body===undefined?'GET':'POST',headers:{Authorization:`Bearer ${token}`,'Content-Type':'application/json'},body:body===undefined?undefined:JSON.stringify(body)});const v=await r.json();if(!r.ok)throw Error(typeof v.detail==='string'?v.detail:JSON.stringify(v.detail));return v}
  useEffect(()=>{call('/v2/tasks').then(v=>setTasks(v.tasks)).catch(e=>setError(String(e)))},[token]);
  useEffect(()=>{if(!recording||!demo)return;const key=runKey('demo');const interval=setInterval(()=>{call(`/v1/runs/${demo.id}`).then(value=>setRuns(s=>({...s,[key]:value}))).catch(()=>{})},1500);return()=>clearInterval(interval)},[recording,demo?.id]);
  async function prepare(value:Mode,reset=false){
    const key=runKey(value),old=runs[key];
    const r=old&&reset?await call(`/v1/runs/${old.id}/reset`,{}):old&&!old.result&&old.status==='ready'?old:await call('/v1/runs',{suite:'v2',task_id:selected.id,variant,seed:value==='demo'?0:10001,mode:value,runtime:'browser',interaction:'human',teaching:value==='demo'});
    setRuns(s=>({...s,[key]:r}));return r;
  }
  async function open(value:Mode,record=false){
    const tab=window.open('about:blank','_blank');if(!tab){setError('请允许本站打开应用标签页');return}
    tab.opener=null;setBusy(true);setError('');setNotice('');let stream:MediaStream|null=null;
    try{
      if(record){
        if(!navigator.mediaDevices?.getDisplayMedia||typeof MediaRecorder==='undefined')throw Error('此浏览器不支持内置录制，请使用 Chrome 或 Edge；预览环境不受影响。');
        flushSync(()=>setPrivateView(true));
        stream=await navigator.mediaDevices.getDisplayMedia({video:{frameRate:30},audio:false});
      }
      // A recording always starts from the initial homepage, even after a preview.
      const r=await prepare(value,record);tabs.current[runKey(value)]=tab;
      tab.location.replace(nativeApplicationUrl(r.application_url));tab.focus();
      if(stream){setRecordingRun(r.id);setCapture(stream)}
      else setNotice(value==='demo'?'示范环境已在新标签页打开，不会录屏。':'执行环境已在新标签页打开。完成后可回到这里检查交付。');
    }catch(e){stream?.getTracks().forEach(t=>t.stop());tab.close();setError(String(e));setPrivateView(false)}finally{setBusy(false)}
  }
  async function reset(value:Mode){
    setBusy(true);setError('');setNotice('');
    try{const r=await prepare(value,true);const tab=tabs.current[runKey(value)];if(tab&&!tab.closed)tab.location.replace(nativeApplicationUrl(r.application_url));if(value==='demo'){setCapture(null);setRecordingRun(null)}setNotice(`${value==='demo'?'示范':'执行'}环境已恢复初态${tab&&!tab.closed?'，应用标签页已更新':''}。`)}catch(e){setError(String(e))}finally{setBusy(false)}
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
    <div className="v2-toolbar"><input aria-label="搜索 v2 任务" placeholder="搜索编号、任务或平台" value={query} onChange={e=>setQuery(e.target.value)}/><select aria-label="执行难度" value={difficulty} onChange={e=>setDifficulty(e.target.value)}><option value="all">全部难度</option><option value="low">低 · 单次应用规则</option><option value="medium">中 · 多次应用规则</option><option value="hard">高 · 完整业务流程</option></select><select aria-label="筛选平台" value={platform} onChange={e=>setPlatform(e.target.value)}><option value="all">全部平台</option>{platforms.map(p=><option key={p}>{p}</option>)}</select><span>{shown.length} / {tasks.length} 题</span></div>
    {error&&<p role="alert" className="error">{error}</p>}
    <div className="v2-layout"><section className="v2-list" aria-label="任务列表"><table><thead><tr>{sortHeading('id','任务序号')}{sortHeading('difficulty','难度')}{sortHeading('platform','平台')}</tr></thead><tbody>{shown.map(t=><tr key={t.id} aria-selected={selected?.id===t.id}><td><button aria-label={`${String(t.id).padStart(3,'0')} ${t.title}`} disabled={locked} onClick={()=>{setSelected(t);setPrivateView(false);setCapture(null);setError('');setNotice('')}}><span className="v2-task-number">{String(t.id).padStart(3,'0')}</span><span>{t.title}</span></button></td><td><span className={`v2-level v2-level-${t.difficulty}`}>{difficultyLabel[t.difficulty]}</span></td><td className="v2-platform">{platformName(t)}</td></tr>)}</tbody></table>{!shown.length&&<p className="v2-empty">没有匹配的任务，请调整搜索或筛选条件。</p>}</section>
    <section className="v2-detail" aria-label="任务详情">{selected?<>
      <header className="v2-card-header"><div className="v2-card-meta"><span>任务 {String(selected.id).padStart(3,'0')}</span><span>{platformName(selected)}</span><span className={`v2-level v2-level-${selected.difficulty}`}>{difficultyLabel[selected.difficulty]}难度</span></div><h2>{selected.title}</h2>{!privateView&&<p>{selected.assignment}</p>}</header>
      {!privateView&&<><div className="v2-version-row"><span>规则版本</span><div className="v2-versions">{['A','B','C'].map(v=><button key={v} disabled={locked} aria-pressed={variant===v} onClick={()=>{setVariant(v);setError('');setNotice('')}}>版本 {v}</button>)}</div></div>
        <div className="v2-mode-tabs" role="tablist" aria-label="任务环境"><button id="v2-demo-tab" role="tab" aria-controls="v2-mode-content" aria-selected={mode==='demo'} disabled={locked} onClick={()=>{setMode('demo');setNotice('')}}>示范 · demo</button><button id="v2-eval-tab" role="tab" aria-controls="v2-mode-content" aria-selected={mode==='eval'} disabled={locked} onClick={()=>{setMode('eval');setNotice('')}}>执行 · inference</button></div>
        <div id="v2-mode-content" role="tabpanel" aria-labelledby={mode==='demo'?'v2-demo-tab':'v2-eval-tab'} className="v2-mode-content">
          {mode==='demo'?<><div className="v2-rule"><span>版本 {variant} · 本次要示范的规则</span><p>{selected.variants[variant]}</p>{explanation&&<div className="v2-rule-explanation">{Array.isArray(explanation)?explanation.join('；'):String(explanation)}</div>}</div><h3>录制时依次完成</h3><ol className="v2-steps">{steps.map((step:any,i:number)=><li key={i}>{String(step)}</li>)}</ol><p className="v2-hint">先预览、试操作，再正式录制。示范只教清楚规则；完整工作流程在执行环境中验证。</p></>:<><h3>需要完成的工作</h3><p className="v2-instructions">{selected.inference.instructions}</p>{executionSteps.length>0&&<ol className="v2-steps">{executionSteps.map((step:string,i:number)=><li key={i}>{step}</li>)}</ol>}<div className="v2-delivery"><span>最终交付</span><p>{selected.delivery}</p></div><p className="v2-hint">执行环境使用独立数据，不影响示范练习。这里可以直接进入应用，手动验证整条工作流程。</p><details className="v2-difficulty-note"><summary>为什么是{difficultyLabel[selected.difficulty]}难度</summary><p>{selected.difficulty_basis||({low:'依据规则完成一次有意义的操作。',medium:'在同一业务目标下，多次独立应用规则。',hard:'完成有前后依赖的业务流程，其中关键步骤必须正确应用视频规则。'} as Record<string,string>)[selected.difficulty]}</p></details></>}
        </div>
      </>}
      {!ready&&<p className="v2-hint">此执行环境正在实现，尚未开放试用。</p>}
      {!privateView&&<div className="v2-actions"><button className="v2-primary" disabled={locked||!ready} onClick={()=>open(mode)}>{busy?'正在准备…':mode==='demo'?'预览示范环境':'打开执行环境'}<span aria-hidden="true"> ↗</span></button><button disabled={locked||!ready} onClick={()=>reset(mode)}>{mode==='demo'?'重置示范':'重置执行环境'}</button>{current&&<button disabled={locked||!ready||!!current.result} onClick={check}>{mode==='demo'?'检查示范结果':'检查最终交付'}</button>}</div>}
      {mode==='eval'&&current&&!privateView&&<p className="v2-hint">最终检查会提交本次结果；如需修改后重试，请重置执行环境。</p>}{notice&&!privateView&&<p className="v2-notice" role="status">{notice}</p>}
      {!privateView&&current?.result&&<div className={`v2-result ${current.result.success?'v2-result-pass':''}`} role="status"><b>{current.result.success?'检查通过':'尚未完成'}</b><span>完成度 {Math.round((current.result.completion||0)*100)}%</span>{current.result.violations?.length>0&&<p>{current.result.violations.join('；')}</p>}</div>}
      {mode==='demo'&&!privateView&&<div className="v2-record-start"><div><b>准备好录制了？</b><p>从初始首页重新开始，选择应用标签页或窗口。</p></div><button disabled={locked||!ready} onClick={()=>open('demo',true)}>开始录制</button></div>}
      {privateView&&<p className="v2-notice">录制期间已隐藏规则与任务说明。请在应用中操作；录制控件在此页面。</p>}
      {demo&&recordingRun===demo.id&&<HumanRecording key={`${demo.id}-${demo.epoch}`} run={demo} token={token} onUpdate={r=>setRuns(s=>({...s,[runKey('demo')]:r}))} onBusy={setRecording} initialStream={capture} compact/>}
      {privateView&&!locked&&<button onClick={()=>setPrivateView(false)}>已停止录制，查看任务说明</button>}
    </>:<div className="v2-welcome"><span className="v2-welcome-icon" aria-hidden="true">↗</span><h2>选择一项任务</h2><p>查看清晰的示范步骤，或直接进入执行环境验证工作流程。</p><div><b>示范环境</b><span>预览规则、练习、录制</span></div><div><b>执行环境</b><span>实际操作、检查最终交付</span></div></div>}</section></div>
  </section>;
}
