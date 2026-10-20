// Render choices inside the page so tab capture includes the entire selection.
// Native selects remain the form values and change-event targets.
let visiblePicker = null;
function closeVisiblePicker(focus = false) {
  if (!visiblePicker) return;
  const {menu, trigger} = visiblePicker;
  menu.remove();
  trigger.setAttribute('aria-expanded', 'false');
  if (focus && trigger.isConnected) trigger.focus();
  visiblePicker = null;
}
document.addEventListener('pointerdown', event => {
  if (visiblePicker && !visiblePicker.menu.contains(event.target) && !visiblePicker.trigger.contains(event.target))
    closeVisiblePicker();
}, true);
window.addEventListener('resize', () => closeVisiblePicker());

function installVisibleSelects() {
  closeVisiblePicker();
  root.querySelectorAll('select').forEach((select, index) => {
    if (select.dataset.visiblePicker) return;
    select.dataset.visiblePicker = 'true';
    const label = select.getAttribute('aria-label') ||
      select.closest('label')?.childNodes[0]?.textContent?.trim() || select.name || 'Choose';
    const trigger = document.createElement('button');
    trigger.type = 'button';
    trigger.className = 'visible-select';
    trigger.setAttribute('role', 'combobox');
    trigger.setAttribute('aria-label', label);
    trigger.setAttribute('aria-haspopup', 'listbox');
    trigger.setAttribute('aria-expanded', 'false');
    trigger.setAttribute('aria-controls', 'visible-options-' + index);
    trigger.disabled = select.disabled;
    trigger.textContent = select.selectedOptions[0]?.textContent || 'Choose…';
    select.hidden = true;
    select.after(trigger);

    function show() {
      if (visiblePicker?.trigger === trigger) { closeVisiblePicker(true); return; }
      closeVisiblePicker();
      const menu = document.createElement('div');
      menu.id = 'visible-options-' + index;
      menu.className = 'visible-options';
      menu.setAttribute('role', 'listbox');
      menu.setAttribute('aria-label', label);
      const buttons = [];
      function choose(option) {
        select.value = option.value;
        trigger.textContent = option.textContent;
        closeVisiblePicker(true);
        select.dispatchEvent(new Event('change', {bubbles: true}));
      }
      for (const option of select.options) {
        const button = document.createElement('button');
        button.type = 'button';
        button.setAttribute('role', 'option');
        button.setAttribute('aria-selected', String(option.selected));
        button.textContent = option.textContent;
        button.disabled = option.disabled;
        button.addEventListener('click', event => {event.stopPropagation(); choose(option);});
        menu.append(button);
        if (!option.disabled) buttons.push(button);
      }
      menu.addEventListener('keydown', event => {
        const position = buttons.indexOf(document.activeElement);
        if (['ArrowDown','ArrowUp','Home','End'].includes(event.key)) {
          event.preventDefault(); event.stopPropagation();
          const next = event.key === 'Home' ? 0 : event.key === 'End' ? buttons.length - 1 :
            (position + (event.key === 'ArrowDown' ? 1 : -1) + buttons.length) % buttons.length;
          buttons[next]?.focus();
        } else if (event.key === 'Escape') {
          event.preventDefault(); event.stopPropagation(); closeVisiblePicker(true);
        } else if (event.key === 'Tab') closeVisiblePicker(true);
      });
      document.body.append(menu);
      const box = trigger.getBoundingClientRect();
      const width = Math.min(Math.max(box.width, 320), innerWidth - 24);
      menu.style.width = width + 'px';
      menu.style.left = Math.max(12, Math.min(box.left, innerWidth - width - 12)) + 'px';
      const below = innerHeight - box.bottom - 12, above = box.top - 12;
      menu.style.maxHeight = Math.min(320, Math.max(below, above)) + 'px';
      if (below >= Math.min(menu.scrollHeight, 320) || below >= above) menu.style.top = box.bottom + 4 + 'px';
      else menu.style.bottom = innerHeight - box.top + 4 + 'px';
      visiblePicker = {menu, trigger};
      trigger.setAttribute('aria-expanded', 'true');
      (buttons.find(button => button.getAttribute('aria-selected') === 'true') || buttons[0])?.focus();
    }
    trigger.addEventListener('click', event => {event.stopPropagation(); show();});
    trigger.addEventListener('keydown', event => {
      if (['ArrowDown','ArrowUp','Enter',' '].includes(event.key)) {
        event.preventDefault(); event.stopPropagation(); show();
      }
    });
  });
}
