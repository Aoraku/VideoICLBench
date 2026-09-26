/** Bypass the launchpad while retaining per-run credentials and the native homepage. */
export function nativeApplicationUrl(entry:string):string {
  const url=new URL(entry);
  const match=url.pathname.match(/^\/apps\/([a-z]+)\/([a-f0-9]+)\/?$/);
  if(!match)throw Error('应用入口格式不正确，请重新准备环境。');
  const [,module,id]=match;
  if(['media','blog','studio','travel','shop','bank','games'].includes(module))url.pathname=`/native/product/${module}/${id}`;
  else if(module==='im'){url.pathname='/native-assets/im/';url.searchParams.set('run',id)}
  else url.pathname=`/native/${module}/${id}${['chat','music','code','gomoku'].includes(module)?'/':''}`;
  return url.href;
}
