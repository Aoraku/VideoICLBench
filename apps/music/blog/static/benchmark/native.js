const run = location.pathname.match(/^\/native\/music\/([a-f0-9]{32})/)?.[1];
const token = sessionStorage.getItem(`vic-music:${run}`) || "";
let state = JSON.parse(document.querySelector("#music-state").textContent);
let busy = false;
async function command(op, target = "", value = "", ids = []) {
  if (busy) return;
  busy = true;
  try {
    const current = await fetch(`/api/runs/${run}`, {
      headers: { Authorization: `Bearer ${token}` },
    }).then((r) => r.json());
    const r = await fetch(`/api/runs/${run}/commands`, {
      method: "POST",
      headers: {
        Authorization: `Bearer ${token}`,
        "Content-Type": "application/json",
      },
      body: JSON.stringify({
        op,
        target,
        value,
        ids,
        epoch: current.epoch,
        action_id: crypto.randomUUID(),
      }),
    });
    const data = await r.json();
    if (!r.ok) throw Error(data.detail);
    state = data.state;
    document
      .querySelectorAll(".music-status")
      .forEach((el) => (el.textContent = "✓ 已保存"));
    return true;
  } catch (e) {
    document
      .querySelectorAll(".music-status")
      .forEach((el) => (el.textContent = e.message));
    return false;
  } finally {
    busy = false;
  }
}
document.querySelector("#editName")?.addEventListener("click", () => {
  document.querySelector("#nameForm").hidden = false;
});
document.querySelector("#nameForm")?.addEventListener("submit", async (e) => {
  e.preventDefault();
  if (await command("save", "target", new FormData(e.target).get("name")))
    location.reload();
});
document.querySelector("#newPlaylist")?.addEventListener("click", () => {
  document.querySelector("#playlistForm").hidden = false;
});
document
  .querySelector("#playlistForm")
  ?.addEventListener("submit", async (e) => {
    e.preventDefault();
    if (await command("save", "target", new FormData(e.target).get("name")))
      location.reload();
  });
document.querySelectorAll("[data-label-open]").forEach(
  (button) =>
    (button.onclick = () => {
      const menu = button.nextElementSibling;
      document.querySelectorAll(".music-options").forEach((m) => {
        if (m !== menu) m.hidden = true;
      });
      menu.hidden = !menu.hidden;
    }),
);
document.querySelectorAll("[data-label]").forEach(
  (button) =>
    (button.onclick = async () => {
      if (await command("label", button.dataset.target, button.dataset.label)) {
        button.parentElement.hidden = true;
        button.parentElement.previousElementSibling.textContent =
          (button.dataset.label || "分类") + " ▾";
      }
    }),
);
document.querySelectorAll("[data-add]").forEach((button) => {
  if (state.domain.collections["list-a"]?.includes(button.dataset.add)) {
    button.textContent = "✓ 已加入";
    button.disabled = true;
  }
  button.onclick = async () => {
    if (await command("action", button.dataset.add, "加入列表甲")) {
      button.textContent = "✓ 已加入";
      button.disabled = true;
    }
  };
});
document.querySelectorAll("[data-play]").forEach(
  (button) =>
    (button.onclick = async () => {
      if (await command("select", "", "", [button.dataset.play]))
        button.textContent = "✓ 已选择歌曲";
    }),
);
document.querySelectorAll("[data-move]").forEach(
  (button) =>
    (button.onclick = async () => {
      const ids = [...state.domain.orders.main],
        i = ids.indexOf(button.dataset.target),
        j = i + Number(button.dataset.move);
      if (j < 0 || j >= ids.length) return;
      [ids[i], ids[j]] = [ids[j], ids[i]];
      if (await command("order", "", "", ids)) location.reload();
    }),
);
