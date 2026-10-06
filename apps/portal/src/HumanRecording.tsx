import {useEffect,useRef,useState} from 'react';
import type {HumanRun} from './HumanSession';
export function HumanRecording({run,token,onUpdate,onBusy,initialStream,compact=false,onStarted}:{run:HumanRun;token:string;onUpdate:(r:HumanRun)=>void;onBusy:(b:boolean)=>void;initialStream?:MediaStream|null;compact?:boolean;onStarted?:()=>void}) {
  const [status,setStatus]=useState('idle'),[error,setError]=useState(''),[video,setVideo]=useState(''),[local,setLocal]=useState<Blob|null>(null),[localUrl,setLocalUrl]=useState(''),[reviewer,setReviewer]=useState(''),[note,setNote]=useState(''),[approved,setApproved]=useState(!!run.recording?.approved);
  const recorder=useRef<MediaRecorder|null>(null),stream=useRef<MediaStream|null>(null),mounted=useRef(true),base=`/v1/runs/${run.id}/recordings`;
  const videoRequest=useRef<AbortController|null>(null);
  const deadline=useRef<ReturnType<typeof setTimeout>|null>(null);
  function busy(value:boolean){onBusy(value)}
  const latestRun=useRef(run);latestRun.current=run;
  useEffect(()=>{if(run.lesson?.finished&&recorder.current?.state==='recording')recorder.current.stop()},[run.lesson?.finished]);
  const startedStream=useRef<MediaStream|null>(null);
  useEffect(()=>{if(initialStream&&startedStream.current!==initialStream){startedStream.current=initialStream;begin(initialStream)}},[initialStream]);
  useEffect(()=>{mounted.current=true;return()=>{mounted.current=false;videoRequest.current?.abort();if(deadline.current)clearTimeout(deadline.current);stream.current?.getTracks().forEach(t=>t.stop())}},[]);
  useEffect(()=>{if(run.recording||run.status==='recorded'||run.result){void loadVideo();void fetch(`${base}/metadata?epoch=${run.epoch}`,{headers:{Authorization:`Bearer ${token}`}}).then(async r=>{if(r.ok){const meta=await r.json();setApproved(!!meta.approved);setReviewer(meta.reviewer||'');setNote(meta.note||'')}}).catch(()=>setError('无法读取审核状态，请刷新重试'));if(!run.result&&!run.recording?.archived&&run.recording?.contract_current!==false)void checkResult()}},[]);
  useEffect(()=>()=>{if(video)URL.revokeObjectURL(video)},[video]);
  useEffect(()=>{if(!local)return;const url=URL.createObjectURL(local);setLocalUrl(url);return()=>URL.revokeObjectURL(url)},[local]);
  useEffect(()=>{if(status!=='recording'&&status!=='uploading')return;const warn=(e:BeforeUnloadEvent)=>{e.preventDefault();e.returnValue=''};window.addEventListener('beforeunload',warn);return()=>window.removeEventListener('beforeunload',warn)},[status]);
  async function loadVideo(){
    videoRequest.current?.abort();const controller=new AbortController();videoRequest.current=controller;
    try{const r=await fetch(`${base}/video?epoch=${run.epoch}`,{headers:{Authorization:`Bearer ${token}`},signal:controller.signal});if(r.ok){const blob=await r.blob();if(mounted.current){setVideo(URL.createObjectURL(blob));setStatus('recorded')}}else if(run.recording){setError('无法加载服务器录像，请刷新重试')}}catch(e){if(!controller.signal.aborted)setError('录像加载失败，请检查连接后刷新重试')}
  }
  async function checkResult(){
    busy(true);setError('');
    try{
      const response=await fetch(`/v1/runs/${run.id}/evaluate`,{method:'POST',headers:{Authorization:`Bearer ${token}`,'Content-Type':'application/json'},body:'{}'});
      const result=await response.json();if(!response.ok)throw Error(typeof result.detail==='string'?result.detail:'自动检查暂未完成，请重试');
      onUpdate({...latestRun.current,status:'completed',result});
    }catch(e){setError(String(e))}finally{busy(false)}
  }
  async function upload(blob:Blob){
    setLocal(blob);setStatus('uploading');setError('');busy(true);
    try{
      const r=await fetch(`${base}/upload?epoch=${run.epoch}`,{method:'POST',headers:{Authorization:`Bearer ${token}`,'Content-Type':blob.type.split(';')[0]||'video/webm'},body:blob});
      const d=await r.json();if(!r.ok)throw Error(d.detail||'录像保存失败');
      await loadVideo();onUpdate({...latestRun.current,status:'recorded',recording:{...d,available:true,contract_current:true}});await checkResult();
    }catch(e){setError(String(e));setStatus('idle')}finally{busy(false)}
  }
  async function start(){
    setError('');
    if(!navigator.mediaDevices?.getDisplayMedia||typeof MediaRecorder==='undefined'){setError('此浏览器不支持屏幕录制。请在 Chrome / Edge 中打开工作台，或上传已有的 WebM / MP4 录像。');return}
    try{
      const capture=await navigator.mediaDevices.getDisplayMedia({video:{frameRate:30},audio:false});
      begin(capture);
    }catch(e){stream.current?.getTracks().forEach(t=>t.stop());setError(e instanceof Error&&e.name==='NotAllowedError'?'未开始录制。需要在浏览器的分享窗口中选择应用标签页或窗口。':String(e));busy(false)}
  }
  function begin(capture:MediaStream){
    try{
      stream.current=capture;
      if(!mounted.current){stream.current.getTracks().forEach(t=>t.stop());return}
      const mime=['video/webm;codecs=vp8','video/webm','video/mp4'].find(x=>MediaRecorder.isTypeSupported(x));
      const recording=new MediaRecorder(stream.current,mime?{mimeType:mime}:undefined),chunks:BlobPart[]=[];
      let size=0;
      recording.ondataavailable=e=>{if(e.data.size){chunks.push(e.data);size+=e.data.size;if(size>150*1024*1024&&recording.state==='recording')recording.stop()}};
      recording.onstop=()=>{if(deadline.current)clearTimeout(deadline.current);stream.current?.getTracks().forEach(t=>t.stop());if(mounted.current)void upload(new Blob(chunks,{type:recording.mimeType.split(';')[0]}))};
      recording.onerror=()=>{stream.current?.getTracks().forEach(t=>t.stop());if(recording.state==='recording')recording.stop();setError('录制中断，请保留本地录像后重试。');busy(false)};
      stream.current.getVideoTracks()[0].onended=()=>{if(recording.state==='recording')recording.stop()};
      recorder.current=recording;recording.start(1000);setStatus('recording');busy(true);onStarted?.();
      deadline.current=setTimeout(()=>{if(recording.state==='recording')recording.stop()},30*60*1000);
    }catch(e){stream.current?.getTracks().forEach(t=>t.stop());setError(e instanceof Error&&e.name==='NotAllowedError'?'未开始录制。需要在浏览器的分享窗口中选择应用标签页或窗口。':String(e));busy(false)}
  }
  async function review(){
    setError('');busy(true);
    try{const r=await fetch(base+'/review',{method:'POST',headers:{Authorization:`Bearer ${token}`,'Content-Type':'application/json'},body:JSON.stringify({approved:true,reviewer,note})});const d=await r.json();if(!r.ok)throw Error(d.detail);setApproved(true);onUpdate({...latestRun.current,recording:{...d,available:true,contract_current:true}})}catch(e){setError(String(e))}finally{busy(false)}
  }
  return <section className={compact?'recording-controls':'panel results'}><h2>{status==='recording'?'● 正在录制':video?(approved?'已完成录制 · 审核通过':'录像已上传 · 待审核'):'录像'}</h2><p>录制包含应用首页、导航和任务操作。{run.lesson && run.lesson.total>1?`请连续完成 ${run.lesson.total} 组练习，最后点击应用内“完成练习”；内置录屏会自动结束、保存并检查任务结果。`:'完成后回到此任务卡结束录制，录像会自动保存并检查任务结果。'}</p>
    {!video&&!run.result&&<div className="actions">{<button disabled={status==='uploading'} className={status==='recording'?'danger':'primary'} onClick={()=>status==='recording'?recorder.current?.stop():start()}>{status==='recording'?'结束并保存录像':status==='uploading'?'正在保存录像…':'选择应用画面并开始录制'}</button>}<label className="recording-upload">或选择录像文件<input type="file" accept="video/webm,video/mp4,.webm,.mp4" disabled={status==='recording'||status==='uploading'} onChange={e=>{const f=e.target.files?.[0];if(f)void upload(f.type?f:new Blob([f],{type:f.name.endsWith('.mp4')?'video/mp4':'video/webm'}))}}/></label></div>}
    <p className="muted">停止录制后会自动上传；审核通过后才可用于 inference。WebM / MP4 均可导入，服务器统一保存 MP4。最长 30 分钟，文件不超过 150 MB。录制仅包含你选择的画面；首页与导航是否完整需要人工审核。</p>
    {error&&<p className="error" role="alert">{error}</p>}
    {localUrl&&<p><a href={localUrl} download={`task-${run.task_id}-${run.id.slice(0,8)}.${local?.type==='video/mp4'?'mp4':'webm'}`}>下载原始录像</a>{status==='idle'&&local&&<button onClick={()=>upload(local)}>重试保存录像</button>}</p>}
    {video&&<><p><a href={video} download={`task-${run.task_id}-${run.variant}-${run.id.slice(0,8)}-${run.epoch}.mp4`}>下载服务器录像（MP4）</a></p>{run.recording?.archived&&<p>这是保留的历史录像，可回放和下载。</p>}{run.recording?.contract_current===false&&<p>该录像对应较早的任务规则，保留供查看，不用于当前规则的 inference。</p>}<section aria-label="自动检查结果" role="status"><h3>任务结果自动检查</h3>{run.result?<><p>{run.result.success?'✓ 检查通过':'尚未完成'} · 完成度 {Math.round(run.result.completion*100)}%</p>{!run.result.success&&<p>请核对全部示范组是否完成；需要重录时重置示范环境。录像已经上传保存，审核通过后才能用于 inference。</p>}</>:<><p>录像已上传，等待任务结果检查。检查通过后可提交人工审核。</p><button disabled={run.recording?.archived||run.recording?.contract_current===false} onClick={checkResult}>检查任务结果</button></>}</section><video src={video} controls/>{!run.recording?.archived&&run.recording?.contract_current!==false&&<details open><summary>审核录像</summary><label>审核人<input value={reviewer} onChange={e=>setReviewer(e.target.value)}/></label><label>录制检查备注<textarea value={note} onChange={e=>setNote(e.target.value)} placeholder="确认首页、导航与任务过程完整。"/></label><button disabled={!reviewer.trim()||!run.result?.success||approved} onClick={review}>{approved?'已审核通过':'确认录像完整并审核通过'}</button>{!run.result?.success&&<p>审核尚不可提交：需要先通过上方的任务结果检查。</p>}{approved&&<p role="status">录像与审核结果已保存到后端，可用于匹配本题规则版本的 inference。</p>}</details>}</>}
  </section>;
}
