import { useRef, useState } from "react";
import { command, currentBusiness } from "./bridge.js";
export default function AttachmentLibrary({ open, onClose }) {
  const [selected, setSelected] = useState(""),
    [error, setError] = useState(""),
    [busy, setBusy] = useState(false);
  const sending = useRef(false);
  const state = currentBusiness();
  if (!open || !state) return null;
  const sentIds = new Set(state.domain.messages.filter(m => m.sender === "self" && m.attachment).map(m => m.attachment));
  const sent = sentIds.has(selected);
  return (
    <div
      style={{
        position: "fixed",
        inset: 0,
        background: "#20304455",
        zIndex: 9000,
        display: "grid",
        placeItems: "center",
        padding: "16px 16px calc(16px + var(--vic-lesson-bottom-inset, 0px))",
      }}
    >
      <section
        role="dialog"
        aria-modal="true"
        aria-label="聊天文件"
        style={{
          width: "min(740px, 100%)",
          maxHeight: "calc(100dvh - 32px - var(--vic-lesson-bottom-inset, 0px))",
          boxSizing: "border-box",
          display: "flex",
          flexDirection: "column",
          background: "#fff",
          borderRadius: 20,
          padding: 32,
          boxShadow: "0 20px 70px #132a4933",
        }}
      >
        <header
          style={{
            display: "flex",
            justifyContent: "space-between",
            alignItems: "center",
          }}
        >
          <h2 style={{ fontSize: 20 }}>聊天文件</h2>
          <button onClick={onClose} disabled={busy} aria-label="关闭文件窗口">
            ×
          </button>
        </header>
        <p style={{ color: "#8290a3", fontSize: 13 }}>林若宁 · 共享文件</p>
        <div style={{ overflowY: "auto", minHeight: 0 }}>
        <div
          style={{
            border: "1px solid #e5ebf2",
            borderRadius: 12,
            overflow: "hidden",
          }}
        >
          {state.items.map((item) => (
            <button
              key={item.id}
              onClick={() => {
                setSelected(item.id);
                setError("");
              }}
              disabled={busy}
              aria-pressed={selected === item.id}
              style={{
                display: "flex",
                alignItems: "center",
                width: "100%",
                padding: "17px 20px",
                gap: 20,
                border: 0,
                borderBottom: "1px solid #edf1f7",
                background: selected === item.id ? "#edf5ff" : "white",
                textAlign: "left",
              }}
            >
              <span style={{ fontSize: 27, color: "#65a6e6" }}>▤</span>
              <span style={{ flex: 1 }}>
                {item.name}
                <small
                  style={{ display: "block", color: "#8c98a8", marginTop: 4 }}
                >
                  来自共享资料 · {item.size} 字节
                </small>
              </span>
              <span>{sentIds.has(item.id) ? "已发送" : selected === item.id ? "✓" : ""}</span>
            </button>
          ))}
        </div>
        {selected && (
          <details style={{ marginTop: 15 }}>
            <summary
              style={{ cursor: "pointer", color: "#718295", fontSize: 13 }}
            >
              预览所选文件
            </summary>
            <pre
              style={{
                maxHeight: 130,
                overflow: "auto",
                whiteSpace: "pre-wrap",
                fontSize: 12,
              }}
            >
              {state.items.find((item) => item.id === selected)?.file_text}
            </pre>
          </details>
        )}
        </div>
        {error && (
          <p role="alert" style={{ color: "#c44" }}>
            {error}
          </p>
        )}
        <footer
          style={{
            display: "flex",
            alignItems: "center",
            justifyContent: "space-between",
            marginTop: 24,
          }}
        >
          <span role="status" style={{ fontSize: 13, color: "#718295" }}>
            {sent
              ? "✓ 附件已发送至林若宁"
              : selected
                ? "已选中 1 个文件"
                : "选择需要发送的文件"}
          </span>
          <button
            className="primary"
            disabled={!selected || busy || sent}
            onClick={async () => {
              if (sending.current || sent) return;
              sending.current = true;
              setBusy(true);
              try {
                await command("select", "", "", [selected]);
                setError("");
              } catch (e) {
                setError(e.message);
              } finally {
                sending.current = false;
                setBusy(false);
              }
            }}
          >
            {busy ? "发送中…" : sent ? "已发送给林若宁" : "发送给林若宁"}
          </button>
        </footer>
      </section>
    </div>
  );
}
