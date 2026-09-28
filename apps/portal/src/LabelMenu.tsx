import { useEffect, useLayoutEffect, useRef, useState } from "react";

// DOM menus remain visible in Chromium screenshots; OS select popups do not.
export function LabelMenu({
  label,
  value,
  options,
  disabled,
  onChange,
}: {
  label: string;
  value: string;
  options: string[];
  disabled: boolean;
  onChange: (value: string) => void;
}) {
  const [open, setOpen] = useState(false),
    [above, setAbove] = useState(false),
    [maxHeight, setMaxHeight] = useState(320),
    menu = useRef<HTMLDivElement>(null),
    root = useRef<HTMLDivElement>(null);
  useLayoutEffect(() => {
    if (!open) return;
    const place = () => {
      if (!root.current || !menu.current) return;
      const anchor = root.current.getBoundingClientRect();
      const controls = document.getElementById("vic-lesson-controls")?.getBoundingClientRect();
      const bottom = controls && anchor.right > controls.left && anchor.left < controls.right
        ? Math.min(innerHeight, controls.top) : innerHeight;
      const below = Math.max(0, bottom - anchor.bottom - 14);
      const top = Math.max(0, anchor.top - 14);
      const flip = below < menu.current.scrollHeight && top > below;
      setAbove(flip);
      setMaxHeight(Math.min(320, flip ? top : below));
    };
    place();
    window.addEventListener("resize", place);
    window.addEventListener("scroll", place, true);
    return () => {
      window.removeEventListener("resize", place);
      window.removeEventListener("scroll", place, true);
    };
  }, [open]);
  useEffect(() => {
    const close = (e: PointerEvent) => {
      if (!root.current?.contains(e.target as Node)) setOpen(false);
    };
    document.addEventListener("pointerdown", close);
    return () => document.removeEventListener("pointerdown", close);
  }, []);
  return (
    <div
      ref={root}
      className="label-menu"
      onKeyDown={(e) => {
        if (e.key === "Escape") setOpen(false);
      }}
    >
      <button
        type="button"
        aria-label={label}
        aria-haspopup="listbox"
        aria-expanded={open}
        disabled={disabled}
        onClick={() => setOpen(!open)}
      >
        {value || "未标注"} <span aria-hidden>⌄</span>
      </button>
      {open && (
        <div ref={menu} role="listbox" aria-label={label} className="label-options"
          style={{ top: above ? "auto" : "calc(100% + 6px)", bottom: above ? "calc(100% + 6px)" : "auto", maxHeight, overflowY: "auto" }}>
          {["", ...options].map((option) => (
            <button
              type="button"
              role="option"
              aria-selected={option === value}
              key={option}
              onClick={() => {
                setOpen(false);
                onChange(option);
              }}
            >
              <span
                className="label-swatch"
                style={{
                  background:
                    (
                      {
                        蓝色: "#3478db",
                        红色: "#df5454",
                        绿色: "#2c9c6a",
                      } as Record<string, string>
                    )[option] || "#b1bac6",
                }}
              />
              {option || "清除标签"}
              {option === value ? " ✓" : ""}
            </button>
          ))}
        </div>
      )}
    </div>
  );
}
