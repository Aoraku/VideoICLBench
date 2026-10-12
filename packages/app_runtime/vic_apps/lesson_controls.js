/* A recorder's neutral progress control. Private rules never enter this script. */
(() => {
  const route = location.pathname.match(/^\/native\/(?:product\/[a-z]+|[a-z]+)\/([a-f0-9]{32})(?:\/|$)/);
  const isIM = location.pathname.startsWith('/native-assets/im/');
  const run = route?.[1] || (isIM ? new URLSearchParams(location.search).get('run') || sessionStorage.getItem('vic-im-run') : '');
  if (!run || !/^[a-f0-9]{32}$/.test(run)) return;
  const key = 'vic-lesson:' + run;
  const token = location.hash.slice(1) || sessionStorage.getItem(key);
  if (!token) return;
  sessionStorage.setItem(key, token);
  const headers = {Authorization:'Bearer ' + token, 'Content-Type':'application/json'};
  async function setup() {
    let envelope;
    try {
      const response = await fetch('/api/runs/' + run, {headers});
      if (!response.ok) return;
      envelope = await response.json();
    } catch { return; }
    const apps = [...new Set([envelope.state?.app,...(envelope.state?.linked_apps || [])])].filter(Boolean);
    if (!envelope.lesson && apps.length > 1 && !document.getElementById('vic-app-switcher')) {
      const bar = document.createElement('nav');bar.id='vic-app-switcher';bar.setAttribute('aria-label','应用切换');
      Object.assign(bar.style,{position:'fixed',bottom:'12px',right:'16px',zIndex:'2147483000',display:'flex',gap:'10px',padding:'10px 14px',background:'#fff',border:'1px solid #dfe4e2',borderRadius:'10px',boxShadow:'0 2px 10px #172d1912',font:'13px system-ui'});
      const names={chat:'VIC Chat',im:'VIC IM',music:'VIC Music',news:'VIC News',code:'VIC Code',blog:'墨记',studio:'Studio',media:'映集',travel:'行远旅行',shop:'拾物商城',bank:'青禾账户'};
      for (const app of apps) {
        const a=document.createElement('a');a.textContent=names[app]||app;
        const path=app==='im'?'/native-assets/im/?run='+run:['chat','music','news','code','gomoku'].includes(app)?'/native/'+app+'/'+run+(app==='news'?'':'/'):'/native/product/'+app+'/'+run;
        a.href=path+'#'+token;a.style.color='#245d4c';bar.append(a);
      }
      document.body.append(bar);
      const reserve=()=>document.documentElement.style.setProperty('--vic-lesson-bottom-inset',`${Math.ceil(bar.getBoundingClientRect().height)+12}px`);
      reserve();new ResizeObserver(reserve).observe(bar);
    }
    if (envelope.state?.workset_delivery) {
      try {
        if (!window.VICWorksetWorkspace) await new Promise((resolve,reject) => {
          const script=document.createElement('script');script.src='/workset-workspace.js';
          script.onload=resolve;script.onerror=reject;document.head.append(script);
        });
        window.VICWorksetWorkspace.mount({run,headers,envelope});
      } catch (error) { console.error('业务资料未加载，请刷新应用', error); }
    }
    const lesson = envelope.lesson;
    if (!lesson || document.getElementById('vic-lesson-controls')) return;
    const bar = document.createElement('aside');
    bar.id = 'vic-lesson-controls';
    bar.setAttribute('aria-label', '连续练习');
    Object.assign(bar.style, {position:'fixed',bottom:'12px',right:'16px',zIndex:'2147483000',display:'flex',flexWrap:'wrap',alignItems:'center',gap:'12px',padding:'10px 14px',background:'#fff',border:'1px solid #ccd5d0',borderRadius:'12px',boxShadow:'0 3px 18px #0002',font:'14px system-ui',color:'#18392f',maxWidth:'min(620px,90vw)'});
    const status = document.createElement('span');
    status.textContent = `练习 ${lesson.index + 1} / ${lesson.total} · 已通过 ${lesson.completed || 0} 组`;
    const button = document.createElement('button');
    button.textContent = lesson.index + 1 === lesson.total ? '完成练习' : '下一组';
    Object.assign(button.style,{padding:'8px 16px',border:'0',borderRadius:'8px',background:'#256953',color:'#fff',cursor:'pointer',whiteSpace:'nowrap'});
    const message = document.createElement('span');
    message.setAttribute('role','status');
    message.setAttribute('aria-live','polite');
    Object.assign(message.style, {maxWidth:'min(440px,65vw)',whiteSpace:'normal'});
    if (lesson.finished) {
      status.textContent = `已完成 ${lesson.total} 组练习`;
      button.hidden = true;
      message.textContent = '自动检查：全部示例通过（100%）。录像上传后可在任务卡审核。';
    }
    button.onclick = async () => {
      button.disabled = true;
      message.textContent = '正在保存本组操作…';
      message.style.color = '#18392f';
      const controller = new AbortController();
      const timeout = setTimeout(() => controller.abort(), 30000);
      try {
        const payload = {epoch:envelope.epoch,index:lesson.index};
        const response = await fetch('/api/runs/' + run + '/lesson/next', {
          method:'POST',headers,signal:controller.signal,body:JSON.stringify(payload),
        });
        const data = await response.json();
        if (!response.ok) throw Error(typeof data.detail === 'string' ? data.detail : '暂时无法继续，请重试。');
        if (data.lesson.finished) {
          status.textContent = `已完成 ${data.lesson.total} 组练习`;
          button.hidden = true;
          message.textContent = '自动检查：全部示例通过（100%）。请返回任务卡查看录像上传与审核结果。';
          return;
        }
        // Navigation stays in this tab so tab capture remains continuous.
        const next = new URL(data.application_url, location.origin);
        if (next.pathname === location.pathname && next.search === location.search) {
          // A fragment-only change does not reload Streamlit or refresh its
          // cookie. Commit the new credential before reopening this document.
          history.replaceState(null, '', next.href);
          location.reload();
        } else location.replace(data.application_url);
      } catch (error) {
        message.style.color = '#a62b28';
        message.textContent = error.name === 'AbortError' ? '连接超时，请重试；已经完成的练习会保留。' : error.message || '暂时无法继续，请重试。';
        button.disabled = false;
      } finally { clearTimeout(timeout); }
    };
    bar.append(status, button, message);
    document.body.append(bar);
    // Sticky application actions can reserve the control's actual height,
    // including wrapped status messages and viewport changes.
    const reserveSpace = () => document.documentElement.style.setProperty(
      '--vic-lesson-bottom-inset', `${Math.ceil(bar.getBoundingClientRect().height) + 12}px`);
    reserveSpace();
    new ResizeObserver(reserveSpace).observe(bar);
  }
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded',setup,{once:true});
  else void setup();
})();
