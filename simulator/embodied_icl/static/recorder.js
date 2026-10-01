// Record actual browser pixels. No task state or simulation coordinates are accessed.
let recStream, screenRecorder, uploadChain=Promise.resolve(), seq=0, localChunks=[]; 
const recStatus=document.getElementById('screen-status');
document.getElementById('screen-start').onclick=async()=>{
 try{
  recStream=await navigator.mediaDevices.getDisplayMedia({video:{frameRate:15},audio:false,preferCurrentTab:true,selfBrowserSurface:'include'});
  const mime=['video/webm;codecs=vp9','video/webm;codecs=vp8','video/mp4'].find(x=>MediaRecorder.isTypeSupported(x));
  screenRecorder=new MediaRecorder(recStream,{mimeType:mime,videoBitsPerSecond:3000000});localChunks=[];
  screenRecorder.ondataavailable=e=>{if(e.data.size)localChunks.push(e.data);};
  screenRecorder.onstop=()=>{recStream.getTracks().forEach(t=>t.stop());const blob=new Blob(localChunks,{type:mime});const link=document.createElement('a');link.href=URL.createObjectURL(blob);link.download='VideoICL_webpage_part2.'+(mime.includes('mp4')?'mp4':'webm');link.textContent='下载续录视频';document.querySelector('.screenbar').appendChild(link);link.click();recStatus.textContent='网页续录已导出';};
  screenRecorder.start(2000);recStatus.textContent='● 正在录制网页';document.getElementById('screen-start').disabled=true;document.getElementById('screen-stop').disabled=false;
 }catch(e){recStatus.textContent='录屏未启动：'+e.message;}
};
document.getElementById('screen-stop').onclick=()=>{if(screenRecorder&&screenRecorder.state!=='inactive'){screenRecorder.stop();document.getElementById('screen-stop').disabled=true;recStatus.textContent='保存录屏中…';}};
document.addEventListener('pointerdown',e=>{const ring=document.createElement('div');ring.className='click-ring';ring.style.left=e.clientX+'px';ring.style.top=e.clientY+'px';document.body.appendChild(ring);setTimeout(()=>ring.remove(),900);},true);
