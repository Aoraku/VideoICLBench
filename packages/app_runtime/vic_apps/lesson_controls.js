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
    if (envelope.state?.rule_target && !document.getElementById('vic-single-review')) {
      const review = document.createElement('aside');
      review.id = 'vic-single-review';
      review.setAttribute('aria-label', '本次核验对象');
      Object.assign(review.style, {position:'fixed',bottom:'12px',right:'16px',zIndex:'2147483000',padding:'14px 18px',background:'#fff',border:'1px solid #ccd5d0',borderRadius:'12px',boxShadow:'0 3px 18px #0002',font:'14px system-ui',color:'#18392f',maxWidth:'min(460px,85vw)'});
      const instruction = document.createElement('p');
      instruction.textContent = envelope.state.review_instructions;
      instruction.style.margin = '0 0 10px';
      const confirm = document.createElement('button');
      confirm.textContent = '确认本条核验';
      Object.assign(confirm.style,{padding:'8px 16px',border:'0',borderRadius:'8px',background:'#256953',color:'#fff',cursor:'pointer'});
      const status = document.createElement('span');
      status.setAttribute('role','status');
      status.style.marginLeft = '10px';
      if (envelope.state.reviewed_target) status.textContent = '核验记录已保存';
      confirm.onclick = async () => {
        confirm.disabled = true;
        try {
          const response = await fetch('/api/runs/' + run + '/commands', {method:'POST',headers,body:JSON.stringify({epoch:envelope.epoch,action_id:crypto.randomUUID(),op:'review.confirm',target:envelope.state.rule_target,value:'',ids:[]})});
          const result = await response.json();
          if (!response.ok) throw Error(typeof result.detail === 'string' ? result.detail : '保存失败，请重试');
          status.textContent = '核验记录已保存';
        } catch (error) {status.textContent = error.message || '保存失败，请重试';}
        finally {confirm.disabled = false;}
      };
      review.append(instruction,confirm,status);
      document.body.append(review);
      const reserve = () => document.documentElement.style.setProperty('--vic-lesson-bottom-inset', `${Math.ceil(review.getBoundingClientRect().height) + 12}px`);
      reserve();
      new ResizeObserver(reserve).observe(review);
    }
    const lesson = envelope.lesson;
    if (!lesson || document.getElementById('vic-lesson-controls')) return;
    const bar = document.createElement('aside');
    bar.id = 'vic-lesson-controls';
    bar.setAttribute('aria-label', '连续练习');
    Object.assign(bar.style, {position:'fixed',bottom:'12px',right:'16px',zIndex:'2147483000',display:'flex',flexWrap:'wrap',alignItems:'center',gap:'12px',padding:'10px 14px',background:'#fff',border:'1px solid #ccd5d0',borderRadius:'12px',boxShadow:'0 3px 18px #0002',font:'14px system-ui',color:'#18392f',maxWidth:'min(620px,90vw)'});
    const status = document.createElement('span');
    status.textContent = `练习 ${lesson.index + 1} / ${lesson.total}`;
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
      message.textContent = '示范练习已保存，可返回任务卡检查结果。';
    }
    button.onclick = async () => {
      button.disabled = true;
      message.textContent = '正在保存本组操作…';
      message.style.color = '#18392f';
      const controller = new AbortController();
      const timeout = setTimeout(() => controller.abort(), 30000);
      try {
        const payload = {epoch:envelope.epoch,index:lesson.index};
        if (envelope.state?.task_id === 43) {
          const latest = await fetch('/api/runs/' + run,{headers,signal:controller.signal});
          if (!latest.ok) throw Error('无法读取保存状态，请重试。');
          const snapshot = await latest.json();
          if (snapshot.state?.domain?.clipboard_history?.length) {
            try {payload.clipboard = await navigator.clipboard.readText();}
            catch {throw Error('请允许读取刚复制的内容，再点击完成练习。');}
          }
        }
        const response = await fetch('/api/runs/' + run + '/lesson/next', {
          method:'POST',headers,signal:controller.signal,body:JSON.stringify(payload),
        });
        const data = await response.json();
        if (!response.ok) throw Error(typeof data.detail === 'string' ? data.detail : '暂时无法继续，请重试。');
        if (data.lesson.finished) {
          status.textContent = `已完成 ${data.lesson.total} 组练习`;
          button.hidden = true;
          message.textContent = '示范练习已完成，请返回任务卡检查结果；正在录制时请结束录制。';
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
