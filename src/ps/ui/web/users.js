"use strict";

const ui = {
  form: document.getElementById("search-form"), input: document.getElementById("search-input"),
  body: document.getElementById("users-table-body"), empty: document.getElementById("empty-state"),
  count: document.getElementById("record-count"), detailBody: document.getElementById("detail-body"),
  photo: document.getElementById("detail-photo"), initial: document.getElementById("detail-initial"),
  name: document.getElementById("detail-name"), id: document.getElementById("detail-id"),
  time: document.getElementById("detail-time"), remove: document.getElementById("delete-user"),
  refresh: document.getElementById("refresh-users"),
};

let users = [];
let selectedId = "";
let query = "";

function escapeHtml(value) {
  return String(value).replace(/[&<>"']/g, (character) => ({
    "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;",
  })[character]);
}

function formatTime(value) {
  if (!value) return "—";
  const parsed = new Date(value);
  return Number.isNaN(parsed.getTime()) ? String(value) : parsed.toLocaleString("zh-CN", { hour12: false });
}

function visibleUsers() {
  const term = query.trim().toLocaleLowerCase("zh-CN");
  return term ? users.filter((user) => user.id.toLowerCase().includes(term) || user.name.toLocaleLowerCase("zh-CN").includes(term)) : users;
}

function avatarMarkup(user) {
  return user.photo ? `<img src="${escapeHtml(user.photo)}" alt="" loading="lazy">` : `<span aria-hidden="true">${escapeHtml(user.name.charAt(0) || "用")}</span>`;
}

function renderDetail() {
  const user = users.find((item) => item.id === selectedId);
  ui.detailBody.hidden = !user;
  ui.remove.disabled = !user;
  if (!user) return;
  ui.name.textContent = user.name;
  ui.id.textContent = user.id;
  ui.time.textContent = formatTime(user.registeredAt);
  ui.initial.textContent = user.name.charAt(0) || "用";
  ui.initial.hidden = Boolean(user.photo);
  ui.photo.hidden = !user.photo;
  if (user.photo) ui.photo.src = user.photo;
}

function render() {
  const shown = visibleUsers();
  ui.body.innerHTML = shown.map((user) => `
    <tr data-user-id="${escapeHtml(user.id)}" tabindex="0" class="${user.id === selectedId ? "is-selected" : ""}" aria-selected="${user.id === selectedId}">
      <td>${escapeHtml(user.id)}</td><td><span class="table-avatar">${avatarMarkup(user)}</span><strong>${escapeHtml(user.name)}</strong></td>
      <td><span class="voice-ok">✓</span> 已录入</td><td>${escapeHtml(formatTime(user.registeredAt))}</td>
    </tr>`).join("");
  ui.empty.hidden = shown.length !== 0;
  ui.count.textContent = `共 ${users.length} 条记录`;
  ui.body.querySelectorAll("tr").forEach((row) => {
    const select = () => { selectedId = row.dataset.userId; render(); };
    row.addEventListener("click", select);
    row.addEventListener("keydown", (event) => { if (event.key === "Enter" || event.key === " ") { event.preventDefault(); select(); } });
  });
  renderDetail();
}

async function refreshUsers() {
  ui.refresh.disabled = true;
  try {
    const response = await fetch("/api/users", { cache: "no-store" });
    const payload = await response.json().catch(() => ({}));
    if (!response.ok) throw new Error(payload.error || `HTTP ${response.status}`);
    users = Array.isArray(payload.users) ? payload.users : [];
    if (!users.some((user) => user.id === selectedId)) selectedId = users[0]?.id || "";
    render();
  } catch (error) {
    users = [];
    selectedId = "";
    render();
    ui.empty.hidden = false;
    ui.empty.textContent = `无法读取板端用户：${error.message}`;
  } finally {
    ui.refresh.disabled = false;
  }
}

ui.form.addEventListener("submit", (event) => { event.preventDefault(); query = ui.input.value; render(); });
ui.input.addEventListener("search", () => { query = ui.input.value; render(); });
ui.remove.addEventListener("click", async () => {
  const user = users.find((item) => item.id === selectedId);
  if (!user) return;
  const confirmed = window.confirm(
    `确定要删除以下用户吗？\n\n用户编号：${user.id}\n姓名：${user.name}\n\n声纹数据将移入可恢复回收目录。`
  );
  if (!confirmed) return;
  ui.remove.disabled = true;
  try {
    const response = await fetch("/api/users/delete", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ id: user.id }),
    });
    const payload = await response.json().catch(() => ({}));
    if (!response.ok) throw new Error(payload.error || `HTTP ${response.status}`);
    window.alert(`用户 ${user.id}（${user.name}）已移入可恢复回收目录。`);
    selectedId = "";
    await refreshUsers();
  } catch (error) {
    window.alert(`删除失败：${error.message}`);
    ui.remove.disabled = false;
  }
});
ui.refresh.addEventListener("click", refreshUsers);
refreshUsers();
