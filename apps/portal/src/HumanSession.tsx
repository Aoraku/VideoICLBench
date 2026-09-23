import { useState } from 'react';
import {HumanRecording} from './HumanRecording';

export type HumanRun = {id:string;task_id:number;variant:string;mode:string;runtime:string;status:string;epoch:number;result:any;interaction?:string;application_url?:string;workspace_url?:string;rule?:string};
export function HumanSession({run,token,onUpdate}:{run:HumanRun;token:string;onUpdate:(r:HumanRun)=>void}) {
  const [busy,setBusy]=useState(false),[error,setError]=useState(''),[clipboard,setClipboard]=useState(''),[recordingBusy,setRecordingBusy]=useState(false);
  const base=`/v1/runs/${run.id}`;
  async function operation(op:string) {
    setBusy(true);setError('');
    try {
      const r=await fetch(base+'/'+op,{method:'POST',headers:{Authorization:`Bearer ${token}`,'Content-Type':'application/json'},body:op==='evaluate'?JSON.stringify(run.task_id===43&&run.variant==='B'?{clipboard}:{}):undefined});
      const data=await r.json();if(!r.ok)throw Error(typeof data.detail==='string'?data.detail:JSON.stringify(data.detail));
      onUpdate(op==='reset'?{...data,rule:run.rule}:{...run,status:'completed',result:data});
    }catch(e){setError(String(e))}finally{setBusy(false)}
  }
  return <>
    <div className="session-heading"><div><h2>任务 {run.task_id} · 版本 {run.variant}</h2><span className="muted">独立应用 · {run.id.slice(0,8)} · 第 {run.epoch+1} 轮</span></div><div className="actions"><button disabled={busy||recordingBusy} onClick={()=>operation('reset')}>重置环境</button><button className="primary" disabled={busy||recordingBusy||!!run.result} onClick={()=>operation('evaluate')}>结束并评测</button></div></div>
    {run.rule&&<div className="rule inline-rule"><b>录制者规则卡</b><span>{run.rule}{run.task_id===45&&<small style={{display:"block"}}>数量与商品名紧邻，不额外插入空格。</small>}</span></div>}
    {error&&<p className="error" role="alert">{error}</p>}
    <section className="panel direct-launch"><span className="eyebrow">{run.result?'任务已结束':run.status==='recorded'?'录像已保存，等待评测':'应用已准备好'}</span><h2>在独立页面中使用应用</h2><p>打开后从应用首页开始，使用浏览器中的鼠标、输入法、菜单和快捷键完成任务。</p>
      {!run.result&&run.status!=='recorded'&&run.application_url&&<a className="direct-open" href={run.application_url} target="_blank" rel="noopener noreferrer">打开独立应用 ↗</a>}
      <p className="muted">完成后回到此页评测。重置会清空本轮操作；重置后请关闭旧应用页，从这里重新打开。</p>
      {run.mode==='demo'&&<p>录制请从新标签页的应用工作台开始，包含首页、导航和实际操作。</p>}
    </section>
    {run.task_id===43&&run.variant==='B'&&!run.result&&<section className="panel results"><label>粘贴剪贴板内容以核验复制结果<textarea value={clipboard} onChange={e=>setClipboard(e.target.value)} rows={5}/></label><p className="muted">在应用完成复制后，使用粘贴快捷键把实际内容粘贴到这里。人工核验结果会注明此证据来源。</p></section>}
    {run.mode==='demo'&&<HumanRecording run={run} token={token} onUpdate={onUpdate} onBusy={setRecordingBusy}/>}
    {run.result&&<section className="panel results"><h2>{run.result.success?'✓ 任务通过':'任务未通过'} <span className="badge">人工试用评测</span></h2><p>子目标完成度 {Math.round(run.result.completion*100)}%</p>{run.result.checks.map((c:any)=><div key={c.id}>{c.passed?'✓':'×'} {c.id}</div>)}{run.result.violations.map((v:string)=><p className="error" key={v}>{v}</p>)}</section>}
  </>;
}
