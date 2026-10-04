import {useEffect, useId, useRef, useState} from 'react';
import {createPortal} from 'react-dom';

// DOM-rendered options: screenshot coordinates and mouse hit testing share one surface.
export default function VisualSelect({label, value, options, onChange}) {
  const button = useRef(null), menu = useRef(null), id = useId();
  const [open, setOpen] = useState(false), [active, setActive] = useState(0), [position, setPosition] = useState({});
  const selected = Math.max(0, options.findIndex(o => String(o.value) === String(value)));
  const choose = index => {onChange(String(options[index].value)); setOpen(false); button.current?.focus();};
  const show = () => {
    const rect = button.current.getBoundingClientRect();
    const height = Math.min(options.length * 38 + 8, 350);
    const above = window.innerHeight - rect.bottom < height && rect.top > height;
    setPosition({left: Math.max(8, Math.min(rect.left, window.innerWidth - Math.max(260, rect.width) - 8)),
      width: Math.max(260, rect.width), ...(above ? {bottom: window.innerHeight - rect.top + 4} : {top: rect.bottom + 4})});
    setActive(selected); setOpen(true);
  };
  useEffect(() => {
    if (!open) return;
    const outside = e => {if (!button.current?.contains(e.target) && !menu.current?.contains(e.target)) setOpen(false);};
    const resize = () => setOpen(false);
    document.addEventListener('pointerdown', outside);
    window.addEventListener('resize', resize);
    return () => {document.removeEventListener('pointerdown', outside); window.removeEventListener('resize', resize);};
  }, [open]);
  useEffect(() => {if (open) menu.current?.children[active]?.scrollIntoView({block:'nearest'});}, [active, open]);
  return <>
    <button ref={button} type="button" className="communication-select" role="combobox" aria-label={label}
      aria-expanded={open} aria-controls={id} aria-haspopup="listbox" aria-activedescendant={open ? `${id}-${active}` : undefined}
      onClick={e => {e.preventDefault(); open ? setOpen(false) : show();}}
      onKeyDown={e => {
        if (e.key === 'Escape' || e.key === 'Tab') {setOpen(false); return;}
        if (['ArrowDown','ArrowUp','Enter',' '].includes(e.key)) {
          e.preventDefault();
          if (!open) {show(); return;}
          if (e.key === 'Enter' || e.key === ' ') choose(active);
          else setActive(i => Math.max(0, Math.min(options.length - 1, i + (e.key === 'ArrowDown' ? 1 : -1))));
        }
      }}><span>{options[selected]?.label}</span><span aria-hidden="true">▾</span></button>
    {open && createPortal(<div ref={menu} id={id} className="communication-select-menu" role="listbox" aria-label={label} style={position}>
      {options.map((option,index) => <button type="button" role="option" tabIndex={-1} id={`${id}-${index}`} key={option.value}
        aria-selected={String(option.value) === String(value)} className={index === active ? 'active' : ''}
        onMouseEnter={() => setActive(index)} onClick={e => {e.preventDefault(); e.stopPropagation(); choose(index);}}>{option.label}</button>)}
    </div>, document.body)}
  </>;
}
