import { useEffect, useRef, useState } from "react";

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
    root = useRef<HTMLDivElement>(null);
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
        <div role="listbox" aria-label={label} className="label-options">
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
