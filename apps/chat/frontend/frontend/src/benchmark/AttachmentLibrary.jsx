import { useState } from "react";
import { command, currentBusiness } from "./bridge.js";
export default function AttachmentLibrary({ open, onClose }) {
  const [selected, setSelected] = useState(""),
    [error, setError] = useState(""),
    [sent, setSent] = useState(false);
  const state = currentBusiness();
  if (!open || !state) return null;
  return (
    <div
      style={{
        position: "fixed",
        inset: 0,
        background: "#20304455",
        zIndex: 9000,
        display: "grid",
        placeItems: "center",
      }}
    >
      <section
        style={{
          width: 740,
          maxHeight: 860,
          overflowY: "auto",
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
          <button onClick={onClose} aria-label="关闭文件窗口">
            ×
          </button>
        </header>
        <p style={{ color: "#8290a3", fontSize: 13 }}>林若宁 · 共享文件</p>
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
                setSent(false);
              }}
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
              <span>{selected === item.id ? "✓" : ""}</span>
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
          <span style={{ fontSize: 13, color: "#718295" }}>
            {sent
              ? "✓ 附件已发送至林若宁"
              : selected
                ? "已选中 1 个文件"
                : "选择需要发送的文件"}
          </span>
          <button
            className="primary"
            disabled={!selected}
            onClick={async () => {
              try {
                await command("select", "", "", [selected]);
                setSent(true);
                setError("");
              } catch (e) {
                setError(e.message);
              }
            }}
          >
            发送给林若宁
          </button>
        </footer>
      </section>
    </div>
  );
}
