/* Native OJ text areas retain literal indentation, including real tab bytes. */
(() => {
  let leaveEditor = null;
  const isEditor = el => el instanceof HTMLTextAreaElement && !el.disabled && !el.readOnly &&
    (el.getAttribute('aria-label') === '编辑源代码' || /^编辑 .+\.(py|cpp|c|js|ts|java)$/.test(el.getAttribute('aria-label') || ''));
  document.addEventListener('keydown', event => {
    const el = event.target;
    if (!isEditor(el)) return;
    if (event.key === 'Escape') { leaveEditor = el; return; }
    if (event.key !== 'Tab' || event.ctrlKey || event.metaKey || event.altKey) { leaveEditor = null; return; }
    if (leaveEditor === el) { leaveEditor = null; return; }
    event.preventDefault();
    event.stopImmediatePropagation();
    const value = el.value, start = el.selectionStart, end = el.selectionEnd;
    let next, a, b;
    if (!event.shiftKey && start === end) {
      next = value.slice(0, start) + '\t' + value.slice(end); a = b = start + 1;
    } else {
      const first = start === 0 ? 0 : value.lastIndexOf('\n', start - 1) + 1;
      const tail = value.indexOf('\n', end > start && value[end - 1] === '\n' ? end - 1 : end);
      const last = tail === -1 ? value.length : tail;
      let delta = 0, firstDelta = 0;
      const block = value.slice(first, last).split('\n').map((line, i) => {
        const remove = event.shiftKey ? (line.match(/^(\t| {1,4})/)?.[0].length || 0) : 0;
        const change = event.shiftKey ? -remove : 1;
        delta += change; if (!i) firstDelta = change;
        return event.shiftKey ? line.slice(remove) : '\t' + line;
      }).join('\n');
      next = value.slice(0, first) + block + value.slice(last);
      a = Math.max(first, start + firstDelta); b = Math.max(a, end + delta);
    }
    // Use the native setter so React/Streamlit sees a real input change.
    Object.getOwnPropertyDescriptor(HTMLTextAreaElement.prototype, 'value').set.call(el, next);
    el.dispatchEvent(new Event('input', {bubbles: true}));
    el.setSelectionRange(a, b);
  }, true);
})();
