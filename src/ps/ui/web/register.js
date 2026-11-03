"use strict";

const ui = {
  name: document.getElementById("person-name-input"),
  id: document.getElementById("person-id-input"),
  photoInput: document.getElementById("photo-input"),
  photo: document.getElementById("photo-preview"),
  placeholder: document.getElementById("avatar-placeholder"),
  start: document.getElementById("start-enrollment"),
  finish: document.getElementById("finish-enrollment"),
  status: document.getElementById("capture-status"),
  count: document.getElementById("sample-count"),
  offline: document.getElementById("enrollment-offline"),
  samples: Array.from(document.querySelectorAll(".sample-item")),
};

let lastRevision = -1;
let enrollmentBusy = false;

function updateStartAvailability() {
  const ready = ui.name.value.trim() && ui.id.value.trim();
  ui.start.disabled = !ready || enrollmentBusy;
  if (ready && ui.status.textContent === "填写人员信息后开始录入") ui.status.textContent = "可以开始录入";
}

function renderEnrollment(state) {
  enrollmentBusy = state.status === "recording" || state.status === "processing";
  if (state.name && !ui.name.value) ui.name.value = state.name;
  if (state.id && !ui.id.value) ui.id.value = state.id;
  const sampleCount = Math.max(0, Math.min(3, Number(state.samples) || 0));
  ui.count.textContent = String(sampleCount);
  ui.samples.forEach((item, index) => {
    const done = index < sampleCount;
    item.classList.toggle("is-done", done);
    item.querySelector("span").textContent = done ? "已录入" : "未录入";
  });

  if (state.status === "recording") ui.status.textContent = state.message || `正在录入第 ${sampleCount + 1} 段声纹`;
  else if (state.status === "processing") ui.status.textContent = state.message || "正在生成声纹模板";
  else if (state.status === "complete" || sampleCount >= 3) ui.status.textContent = state.message || "声纹录入完成";
  else if (state.status === "fault") ui.status.textContent = state.message || "录入失败，请重试";

  const complete = state.status === "complete" || sampleCount >= 3;
  ui.finish.setAttribute("aria-disabled", String(!complete));
  if (state.status === "fault" || state.status === "complete" || state.status === "idle") {
    enrollmentBusy = false;
  }
  updateStartAvailability();
}

async function postEnrollment(patch) {
  const response = await fetch("/api/enrollment/start", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(patch),
  });
  if (!response.ok) throw new Error(`HTTP ${response.status}`);
  return response.json();
}

ui.name.addEventListener("input", updateStartAvailability);
ui.id.addEventListener("input", updateStartAvailability);

ui.photoInput.addEventListener("change", () => {
  const [file] = ui.photoInput.files;
  if (!file) return;
  const reader = new FileReader();
  reader.onload = () => {
    ui.photo.src = String(reader.result);
    ui.photo.hidden = false;
    ui.placeholder.hidden = true;
  };
  reader.readAsDataURL(file);
});

ui.start.addEventListener("click", async () => {
  enrollmentBusy = true;
  ui.start.disabled = true;
  try {
    const state = await postEnrollment({
      name: ui.name.value.trim(),
      id: ui.id.value.trim(),
    });
    ui.status.textContent = state.accepted ? "录入任务已启动" : "无法启动录入";
    ui.offline.hidden = true;
  } catch (error) {
    enrollmentBusy = false;
    ui.offline.hidden = false;
    ui.status.textContent = "无法启动录入";
  } finally {
    // Polling will restore availability when the job completes or fails.
  }
});

async function pollEnrollment() {
  try {
    const response = await fetch("/api/enrollment", { cache: "no-store" });
    if (!response.ok) throw new Error(`HTTP ${response.status}`);
    const state = await response.json();
    ui.offline.hidden = true;
    if (state.revision !== lastRevision) {
      lastRevision = state.revision;
      renderEnrollment(state);
    }
  } catch (error) {
    ui.offline.hidden = false;
  } finally {
    window.setTimeout(pollEnrollment, 700);
  }
}

updateStartAvailability();
pollEnrollment();
