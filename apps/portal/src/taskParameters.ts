/** Public task inputs shared by recorder cards and ordinary application pages. */
export function taskParameters(id:number, source:any):string {
  if(id===22)return `播放量阈值：${source.threshold} 次。时长按秒计，4 分钟为 240 秒。`;
  if(id===38)return `正文长度阈值：${source.threshold} 个字符；包含标点和空格，不包含标题。`;
  if(id===49)return `备注长度阈值：${source.text_threshold} 个字符；包含标点和空格。金额单位为元。`;
  if(id===57)return `余额阈值：${source.threshold} 元。日期比较采用 UTC。`;
  return '';
}
