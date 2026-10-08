/** Keep a failed launch visible so a service error never looks like a crash. */
export function applicationLaunchError(tab:Window|null,error:unknown):string {
  const message=error instanceof Error?error.message:String(error);
  if(tab&&!tab.closed){
    try{
      tab.document.title='应用暂未打开';
      tab.document.body.textContent=`应用暂未打开：${message}\n\n请返回任务卡重试。已经上传的录像会保留。`;
      tab.document.body.style.cssText='font:18px/1.7 system-ui;padding:40px;white-space:pre-wrap;color:#18392f';
    }catch{/* A successfully navigated cross-origin application remains open. */}
  }
  return message;
}
export async function applicationResponse(response:Response){
  const data=await response.json().catch(()=>null);
  if(!response.ok)throw Error(typeof data?.detail==='string'?data.detail:`服务暂时无法处理请求（HTTP ${response.status}），请稍后重试。`);
  if(data===null)throw Error('服务返回了无法读取的内容，请稍后重试。');
  return data;
}
