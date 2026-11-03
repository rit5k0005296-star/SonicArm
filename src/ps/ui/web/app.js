"use strict";

const elements = {
  body: document.body,
  systemStatus: document.getElementById("system-status-text"),
  mode: document.getElementById("mode-label"),
  photo: document.getElementById("identity-photo"),
  photoPlaceholder: document.getElementById("portrait-placeholder"),
  placeholderText: document.getElementById("placeholder-text"),
  personName: document.getElementById("person-name"),
  personId: document.getElementById("person-id"),
  scoreNumber: document.getElementById("score-number"),
  scoreTrack: document.getElementById("score-track"),
  scoreFill: document.getElementById("score-fill"),
  verificationState: document.getElementById("verification-state"),
  voiceprintBanner: document.getElementById("voiceprint-banner"),
  thresholdSlider: document.getElementById("threshold-slider"),
  thresholdNumber: document.getElementById("threshold-number"),
  commandValue: document.getElementById("command-value"),
  armState: document.getElementById("arm-state"),
  armMessage: document.getElementById("task-message"),
  updatedTime: document.getElementById("updated-time"),
  offlineNotice: document.getElementById("offline-notice"),
  startRecognition: document.getElementById("start-recognition"),
};

const phaseText = {
  idle: { system: "系统就绪", identity: "等待识别", placeholder: "等待识别" },
  listening: { system: "正在识别", identity: "识别中", placeholder: "识别中" },
  matched: { system: "身份已确认", identity: "匹配成功", placeholder: "身份已确认" },
  denied: { system: "身份未通过", identity: "匹配失败", placeholder: "未知人员" },
  executing: { system: "机械臂运行中", identity: "匹配成功", placeholder: "身份已确认" },
  completed: { system: "任务已完成", identity: "匹配成功", placeholder: "身份已确认" },
  fault: { system: "系统异常", identity: "识别异常", placeholder: "状态异常" },
};

let lastRevision = -1;
let failedPolls = 0;
let currentPhoto = "";
let thresholdEditing = false;
let thresholdSaveTimer = null;
let recognitionRequested = false;
let recognitionObservedBusy = false;

function clamp(value, min, max) {
  return Math.min(max, Math.max(min, value));
}

function showThreshold(percent) {
  const value = Math.round(clamp(percent, 0, 100));
  elements.thresholdSlider.value = String(value);
  elements.thresholdSlider.style.setProperty("--threshold-fill", `${value}%`);
  elements.thresholdNumber.textContent = `${value}%`;
}

async function persistThreshold(percent) {
  try {
    const response = await fetch("/api/state", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ identity: { threshold: clamp(percent, 0, 100) / 100 } }),
    });
    if (!response.ok) throw new Error(`HTTP ${response.status}`);
    elements.offlineNotice.hidden = true;
  } catch (error) {
    elements.offlineNotice.hidden = false;
  }
}

function queueThresholdSave(percent) {
  window.clearTimeout(thresholdSaveTimer);
  thresholdSaveTimer = window.setTimeout(() => persistThreshold(percent), 120);
}

function setPhoto(phase, photoPath) {
  const reveal = ["matched", "executing", "completed"].includes(phase);
  const photo = reveal && typeof photoPath === "string" ? photoPath.trim() : "";

  if (!photo) {
    elements.photo.hidden = true;
    elements.photoPlaceholder.hidden = false;
    currentPhoto = "";
    return;
  }

  if (photo === currentPhoto && !elements.photo.hidden) {
    return;
  }

  currentPhoto = photo;
  elements.photo.hidden = true;
  elements.photoPlaceholder.hidden = false;
  elements.placeholderText.textContent = "照片加载中";
  elements.photo.onload = () => {
    elements.photo.hidden = false;
    elements.photoPlaceholder.hidden = true;
  };
  elements.photo.onerror = () => {
    elements.photo.hidden = true;
    elements.photoPlaceholder.hidden = false;
    elements.placeholderText.textContent = "照片不可用";
  };
  elements.photo.src = photo;
}

function renderIdentity(phase, identity) {
  const showIdentity = ["matched", "executing", "completed"].includes(phase);
  const scoreValid = typeof identity.score === "number" && Number.isFinite(identity.score);
  const score = scoreValid ? clamp(identity.score, 0, 1) : 0;

  elements.placeholderText.textContent = phaseText[phase].placeholder;
  elements.personName.textContent = showIdentity
    ? identity.name || "已注册用户"
    : phase === "denied"
      ? "未知人员"
      : phase === "listening"
        ? "正在识别"
        : "尚未确认身份";
  elements.personId.textContent = showIdentity && identity.id ? `用户编号：${identity.id}` : "用户编号：—";
  elements.scoreNumber.textContent = scoreValid ? `${(score * 100).toFixed(1)}%` : "—";
  elements.scoreFill.style.width = `${score * 100}%`;
  elements.scoreTrack.setAttribute("aria-valuenow", String(Math.round(score * 100)));
  if (!thresholdEditing) {
    const threshold = typeof identity.threshold === "number" && Number.isFinite(identity.threshold)
      ? identity.threshold
      : 0.67;
    showThreshold(threshold * 100);
  }
  elements.verificationState.textContent = {
    idle: "等待声纹输入",
    listening: "正在校验声纹",
    matched: "声纹校验通过",
    denied: "声纹校验未通过",
    executing: "声纹校验通过",
    completed: "声纹校验通过",
    fault: "声纹校验异常",
  }[phase];
  const defaultBanner = {
    idle: "等待声纹识别程序返回结果",
    listening: "正在等待声纹识别结果",
    matched: "声纹识别已通过",
    denied: "声纹识别未通过",
    executing: "声纹识别已通过",
    completed: "声纹识别已通过",
    fault: "声纹识别程序状态异常",
  }[phase];
  elements.voiceprintBanner.textContent = defaultBanner;
  setPhoto(phase, identity.photo);
}

function renderCommand(phase, command, headline) {
  let text = command.text ? command.text : "等待命令";
  if (phase === "denied") text = "未执行";
  if (phase === "listening") text = headline || "正在识别";
  if (phase === "fault" && !command.text) text = "识别失败";
  elements.commandValue.textContent = text;
}

function renderArm(phase, arm) {
  let state = "待机";
  if (phase === "executing") {
    state = {
      pickup: "夹取中",
      place: "移动 / 放置中",
      reset: "复位中",
    }[arm.step] || "运行中";
  } else if (phase === "completed") {
    state = "已完成";
  } else if (phase === "fault" && arm.status === "fault") {
    state = "异常";
  }
  elements.armState.textContent = state;
  elements.armMessage.textContent = arm.message || (state === "待机" ? "等待任务" : "");
}

function render(state) {
  const phase = phaseText[state.phase] ? state.phase : "fault";
  const identity = state.identity || {};
  const command = state.command || {};
  const arm = state.arm || {};

  elements.body.dataset.phase = phase;
  const recognitionRejected = phase === "denied" || (phase === "matched" && command.accepted === false);
  elements.body.dataset.recognitionRejected = String(recognitionRejected);
  elements.systemStatus.textContent = phaseText[phase].system;
  elements.mode.textContent = state.mode || "联调模式";
  renderIdentity(phase, identity);
  if ((phase === "listening" || phase === "fault") && state.message) {
    elements.voiceprintBanner.textContent = state.message;
  } else if (phase === "matched" && command.accepted === false) {
    elements.voiceprintBanner.textContent = "身份已通过，但命令识别未通过";
  }
  renderCommand(phase, command, state.headline);
  renderArm(phase, arm);

  const updated = state.updated_at ? new Date(state.updated_at) : new Date();
  elements.updatedTime.textContent = Number.isNaN(updated.getTime())
    ? "--:--:--"
    : updated.toLocaleTimeString("zh-CN", { hour12: false });

  if (state.phase === "listening") recognitionObservedBusy = true;
  if (recognitionObservedBusy && state.phase !== "listening") {
    recognitionRequested = false;
    recognitionObservedBusy = false;
  }
  const recognitionBusy = recognitionRequested || state.phase === "listening";
  elements.startRecognition.disabled = recognitionBusy;
  elements.startRecognition.textContent = recognitionBusy ? "识别中" : "开始识别";
}

async function pollState() {
  try {
    const response = await fetch("/api/state", { cache: "no-store" });
    if (!response.ok) throw new Error(`HTTP ${response.status}`);
    const state = await response.json();
    failedPolls = 0;
    elements.offlineNotice.hidden = true;
    if (state.revision !== lastRevision) {
      lastRevision = state.revision;
      render(state);
    }
  } catch (error) {
    failedPolls += 1;
    if (failedPolls >= 3) elements.offlineNotice.hidden = false;
  } finally {
    window.setTimeout(pollState, 700);
  }
}

pollState();

elements.thresholdSlider.addEventListener("input", (event) => {
  thresholdEditing = true;
  const percent = Number(event.currentTarget.value);
  showThreshold(percent);
  queueThresholdSave(percent);
});

elements.thresholdSlider.addEventListener("change", (event) => {
  thresholdEditing = false;
  window.clearTimeout(thresholdSaveTimer);
  persistThreshold(Number(event.currentTarget.value));
});

elements.startRecognition.addEventListener("click", async () => {
  recognitionRequested = true;
  elements.startRecognition.disabled = true;
  elements.startRecognition.textContent = "识别中";
  try {
    const response = await fetch("/api/recognition/start", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: "{}",
    });
    if (!response.ok) {
      const detail = await response.json().catch(() => ({}));
      throw new Error(detail.error || `HTTP ${response.status}`);
    }
  } catch (error) {
    recognitionRequested = false;
    elements.startRecognition.disabled = false;
    elements.startRecognition.textContent = "开始识别";
    elements.offlineNotice.hidden = false;
    elements.offlineNotice.textContent = `无法启动识别：${error.message}`;
  }
});
