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
    const batch = envelope.state?.work_batch;
    if (batch && !document.getElementById('vic-work-batch')) {
      const bar = document.createElement('nav');
      bar.id = 'vic-work-batch';
      bar.setAttribute('aria-label', '本批工作清单');
      Object.assign(bar.style, {position:'fixed',bottom:'12px',right:'16px',zIndex:'2147483000',display:'flex',flexWrap:'wrap',alignItems:'center',gap:'9px',padding:'9px 12px',background:'#ffffff',border:'1px solid #dfe4e2',borderRadius:'10px',boxShadow:'0 2px 10px #172d1912',font:'13px system-ui',color:'#293d34',maxWidth:'min(670px,92vw)'});
      const label = document.createElement('span');
      label.textContent = envelope.state.task_id >= 66 ? '训练清单' : '工作清单';
      label.title = batch.title;
      const buttons = batch.units.map((unit,index) => {
        const button = document.createElement('button');
        button.type = 'button';
        button.textContent = String(index+1);
        button.title = unit.title;
        button.setAttribute('aria-label', `打开第${index+1}项：${unit.title}`);
        button.setAttribute('aria-pressed', String(unit.id === batch.active));
        Object.assign(button.style,{minWidth:'32px',padding:'7px',border:'1px solid #d4ddd7',borderRadius:'6px',background:unit.id===batch.active?'#245d4c':'#fff',color:unit.id===batch.active?'#fff':'#293d34',cursor:'pointer'});
        button.onclick = () => openItem(unit.id);
        return button;
      });
      const current = document.createElement('span');
      current.textContent = batch.units.find(unit=>unit.id===batch.active)?.title || '';
      Object.assign(current.style,{maxWidth:'min(280px,40vw)',overflow:'hidden',textOverflow:'ellipsis',whiteSpace:'nowrap'});
      const status = document.createElement('span');
      status.setAttribute('role','status');
      status.textContent = '保存后切换，可返回修改';
      status.style.color = '#637268';
      async function openItem(target) {
        if (target === batch.active) return;
        buttons.forEach(button=>button.disabled=true);
        status.textContent = '正在打开…';
        try {
          const response = await fetch('/api/runs/' + run + '/commands', {method:'POST',headers,body:JSON.stringify({epoch:envelope.epoch,action_id:crypto.randomUUID(),op:'batch.open',target,value:'',ids:[]})});
          const result = await response.json();
          if (!response.ok) throw Error(typeof result.detail === 'string' ? result.detail : '无法打开，请重试');
          if (envelope.state.task_id === 66 || envelope.state.task_id === 67) {
            const authorization = await fetch('/native/gomoku/' + run + '/authorize', {method:'POST',headers});
            if (!authorization.ok) throw Error('棋盘已保存，但暂时无法刷新，请重新打开应用');
          }
          // Reopen the ordinary app home, not a teaching interstitial. Every
          // work item's saved state remains accessible through this navigator.
          const match = location.pathname.match(/^\/native\/(chat|music|news|code|gomoku)\/([a-f0-9]{32})/);
          const destination = match ? `/native/${match[1]}/${run}${match[1] === 'news' ? '' : '/'}` : location.pathname;
          history.replaceState(null, '', destination + '#' + token);
          location.reload();
        } catch (error) {
          status.textContent = error.message || '切换失败，请重试';
          status.style.color = '#a62b28';
          buttons.forEach(button=>button.disabled=false);
        }
      };
      bar.append(label,...buttons,current,status);
      document.body.append(bar);
      const reserve = () => document.documentElement.style.setProperty('--vic-lesson-bottom-inset', `${Math.ceil(bar.getBoundingClientRect().height) + 12}px`);
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
    const clipboardHelp = document.createElement('details');
    const clipboardInput = document.createElement('textarea');
    if (envelope.state?.task_id === 43) {
      const summary = document.createElement('summary');
      summary.textContent = '剪贴板读取失败？手动粘贴核验';
      const explanation = document.createElement('p');
      explanation.textContent = '每次复制会覆盖剪贴板，各文件的复制操作已分别记录。这里只粘贴最后一次复制的完整正文，无需拼接；粘贴后再点击完成练习。';
      clipboardInput.setAttribute('aria-label', '最后复制的正文');
      clipboardInput.rows = 3;
      Object.assign(clipboardInput.style, {width:'100%',boxSizing:'border-box'});
      clipboardHelp.append(summary, explanation, clipboardInput);
    }
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
        if (envelope.state?.task_id === 43) {
          const latest = await fetch('/api/runs/' + run,{headers,signal:controller.signal});
          if (!latest.ok) throw Error('无法读取保存状态，请重试。');
          const snapshot = await latest.json();
          if (snapshot.state?.domain?.clipboard_history?.length) {
            if (clipboardInput.value) payload.clipboard = clipboardInput.value;
            else try {payload.clipboard = await navigator.clipboard.readText();}
            catch {
              clipboardHelp.open = true;
              clipboardInput.focus();
              throw Error('浏览器未允许读取剪贴板。请在下方粘贴最后复制的完整正文，再点击完成练习。');
            }
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
          clipboardHelp.hidden = true;
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
        if (clipboardHelp.childNodes.length) clipboardHelp.open = true;
        message.style.color = '#a62b28';
        message.textContent = error.name === 'AbortError' ? '连接超时，请重试；已经完成的练习会保留。' : error.message || '暂时无法继续，请重试。';
        button.disabled = false;
      } finally { clearTimeout(timeout); }
    };
    bar.append(status, button, message);
    if (clipboardHelp.childNodes.length && !lesson.finished) bar.append(clipboardHelp);
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
