/** Recorder cards show the rule parameters; demonstration applications do not. */
export function taskParameters(id:number, source:any, state?:any):string {
  if(state && state.seed < 1000)return '';
  if(id===22)return `播放量阈值：${source.threshold} 次。时长按秒计，4 分钟为 240 秒。`;
  if(id===38)return `正文长度阈值：${source.threshold} 个字符；包含标点和空格，不包含标题。`;
  if(id===49)return `备注长度阈值：${source.text_threshold} 个字符；包含标点和空格。金额单位为元。`;
  if(id===57)return `余额阈值：${source.threshold} 元。日期比较采用 UTC。`;
  // Hard workflows carry request-specific parameters in their business documents.
  if(state?.world && [42,54,55,56].includes(id))return '';
  if(id===42)return `指定字符：小写“${source.letter}”。`;
  if(id===54)return `价格阈值：${source.threshold} 元。`;
  if(id===55)return `指定标签：${source.tag}。`;
  if(id===56)return `指定字母：小写“${source.letter}”；金额阈值：${source.threshold} 元。`;
  return '';
}
