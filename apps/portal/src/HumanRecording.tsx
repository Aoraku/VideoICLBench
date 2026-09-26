import {useEffect,useRef,useState} from 'react';
import type {HumanRun} from './HumanSession';
export function HumanRecording({run,token,onUpdate,onBusy,initialStream,compact=false}:{run:HumanRun;token:string;onUpdate:(r:HumanRun)=>void;onBusy:(b:boolean)=>void;initialStream?:MediaStream|null;compact?:boolean}) {
  const [status,setStatus]=useState('idle'),[error,setError]=useState(''),[video,setVideo]=useState(''),[local,setLocal]=useState<Blob|null>(null),[localUrl,setLocalUrl]=useState(''),[reviewer,setReviewer]=useState(''),[note,setNote]=useState(''),[approved,setApproved]=useState(false);
  const recorder=useRef<MediaRecorder|null>(null),stream=useRef<MediaStream|null>(null),mounted=useRef(true),base=`/v1/runs/${run.id}/recordings`;
  const deadline=useRef<ReturnType<typeof setTimeout>|null>(null);
  function busy(value:boolean){onBusy(value)}
  const startedStream=useRef<MediaStream|null>(null);
  useEffect(()=>{if(initialStream&&startedStream.current!==initialStream){startedStream.current=initialStream;begin(initialStream)}},[initialStream]);
  useEffect(()=>{mounted.current=true;return()=>{mounted.current=false;if(deadline.current)clearTimeout(deadline.current);stream.current?.getTracks().forEach(t=>t.stop())}},[]);
  useEffect(()=>{if(run.status==='recorded'||run.result)void loadVideo()},[]);
  useEffect(()=>()=>{if(video)URL.revokeObjectURL(video)},[video]);
  useEffect(()=>{if(!local)return;const url=URL.createObjectURL(local);setLocalUrl(url);return()=>URL.revokeObjectURL(url)},[local]);
  useEffect(()=>{if(status!=='recording'&&status!=='uploading')return;const warn=(e:BeforeUnloadEvent)=>{e.preventDefault();e.returnValue=''};window.addEventListener('beforeunload',warn);return()=>window.removeEventListener('beforeunload',warn)},[status]);
  async function loadVideo(){const r=await fetch(base+'/video',{headers:{Authorization:`Bearer ${token}`}});if(r.ok){setVideo(URL.createObjectURL(await r.blob()));setStatus('recorded')}}
  async function upload(blob:Blob){
    setLocal(blob);setStatus('uploading');setError('');busy(true);
    try{
      const r=await fetch(`${base}/upload?epoch=${run.epoch}`,{method:'POST',headers:{Authorization:`Bearer ${token}`,'Content-Type':blob.type.split(';')[0]||'video/webm'},body:blob});
      const d=await r.json();if(!r.ok)throw Error(d.detail||'录像保存失败');
      await loadVideo();onUpdate({...run,status:'recorded'});
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
      recording.onerror=()=>{setError('录制中断，请保留本地录像后重试。');busy(false)};
      stream.current.getVideoTracks()[0].onended=()=>{if(recording.state==='recording')recording.stop()};
      recorder.current=recording;recording.start(1000);setStatus('recording');busy(true);
      deadline.current=setTimeout(()=>{if(recording.state==='recording')recording.stop()},15*60*1000);
    }catch(e){stream.current?.getTracks().forEach(t=>t.stop());setError(e instanceof Error&&e.name==='NotAllowedError'?'未开始录制。需要在浏览器的分享窗口中选择应用标签页或窗口。':String(e));busy(false)}
  }
  async function review(){
    setError('');busy(true);
    try{const r=await fetch(base+'/review',{method:'POST',headers:{Authorization:`Bearer ${token}`,'Content-Type':'application/json'},body:JSON.stringify({approved:true,reviewer,note})});const d=await r.json();if(!r.ok)throw Error(d.detail);setApproved(true)}catch(e){setError(String(e))}finally{busy(false)}
  }
  return <section className={compact?'recording-controls':'panel results'}><h2>{status==='recording'?'● 正在录制':video?'录像已保存':'录像'}</h2><p>录制包含应用首页、导航和任务操作。完成后回到此任务卡结束录制，录像会自动保存并检查任务结果。</p>
    {!video&&!run.result&&<div className="actions">{(!compact||status==='recording'||status==='uploading')&&<button disabled={status==='uploading'} className={status==='recording'?'danger':'primary'} onClick={()=>status==='recording'?recorder.current?.stop():start()}>{status==='recording'?'结束并保存录像':status==='uploading'?'正在保存录像…':'开始屏幕录制'}</button>}<label className="recording-upload">或选择录像文件<input type="file" accept="video/webm,video/mp4,.webm,.mp4" disabled={status==='recording'||status==='uploading'} onChange={e=>{const f=e.target.files?.[0];if(f)void upload(f.type?f:new Blob([f],{type:f.name.endsWith('.mp4')?'video/mp4':'video/webm'}))}}/></label></div>}
    <p className="muted">最长 15 分钟，文件不超过 150 MB。录制仅包含你选择的画面；首页与导航是否完整需要人工审核。</p>
    {error&&<p className="error" role="alert">{error}</p>}
    {localUrl&&<p><a href={localUrl} download={`task-${run.task_id}-${run.id.slice(0,8)}.${local?.type==='video/mp4'?'mp4':'webm'}`}>下载原始录像</a>{status==='idle'&&local&&<button onClick={()=>upload(local)}>重试保存录像</button>}</p>}
    {video&&<><video src={video} controls/><details><summary>审核录像</summary><label>审核人<input value={reviewer} onChange={e=>setReviewer(e.target.value)}/></label><label>录制检查备注<textarea value={note} onChange={e=>setNote(e.target.value)} placeholder="确认首页、导航与任务过程完整。"/></label><button disabled={!reviewer||!run.result?.success||approved} onClick={review}>{approved?'已审核通过':'确认录像完整并审核通过'}</button></details></>}
  </section>;
}
