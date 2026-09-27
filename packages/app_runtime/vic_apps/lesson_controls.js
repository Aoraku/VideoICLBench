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
    const lesson = envelope.lesson;
    if (!lesson || lesson.total < 2 || document.getElementById('vic-lesson-controls')) return;
    const bar = document.createElement('aside');
    bar.id = 'vic-lesson-controls';
    bar.setAttribute('aria-label', '连续练习');
    Object.assign(bar.style, {position:'fixed',bottom:'12px',right:'16px',zIndex:'2147483000',display:'flex',alignItems:'center',gap:'12px',padding:'10px 14px',background:'#fff',border:'1px solid #ccd5d0',borderRadius:'12px',boxShadow:'0 3px 18px #0002',font:'14px system-ui',color:'#18392f',maxWidth:'min(620px,90vw)'});
    const status = document.createElement('span');
    status.textContent = `练习 ${lesson.index + 1} / ${lesson.total}`;
    const button = document.createElement('button');
    button.textContent = lesson.index + 1 === lesson.total ? '完成练习' : '下一组';
    Object.assign(button.style,{padding:'8px 16px',border:'0',borderRadius:'8px',background:'#256953',color:'#fff',cursor:'pointer',whiteSpace:'nowrap'});
    const message = document.createElement('span');
    message.setAttribute('role','status');
    if (lesson.finished) {
      status.textContent = `已完成 ${lesson.total} 组练习`;
      button.hidden = true;
      message.textContent = '练习已保存，请在工作台查看录像。';
    }
    button.onclick = async () => {
      button.disabled = true;
      message.textContent = '正在保存本组操作…';
      try {
        const response = await fetch('/api/runs/' + run + '/lesson/next', {
          method:'POST',headers,body:JSON.stringify({epoch:envelope.epoch,index:lesson.index}),
        });
        const data = await response.json();
        if (!response.ok) throw Error(typeof data.detail === 'string' ? data.detail : '暂时无法继续，请重试。');
        if (data.lesson.finished) {
          status.textContent = `已完成 ${data.lesson.total} 组练习`;
          button.hidden = true;
          message.textContent = '录像将在工作台保存；外部录屏请手动结束并上传。';
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
        message.textContent = error.message || '暂时无法继续，请重试。';
        button.disabled = false;
      }
    };
    bar.append(status, button, message);
    document.body.append(bar);
  }
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded',setup,{once:true});
  else void setup();
})();
