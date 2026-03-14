const byId = (id) => document.getElementById(id);

const els = {
  runBadge: byId("runBadge"),
  heroText: byId("heroText"),
  statusUrl: byId("statusUrl"),
  rootDir: byId("rootDir"),
  dataDir: byId("dataDir"),
  runningValue: byId("runningValue"),
  pidValue: byId("pidValue"),
  platformValue: byId("platformValue"),
  versionValue: byId("versionValue"),
  pairedValue: byId("pairedValue"),
  ownerValue: byId("ownerValue"),
  connectorIdValue: byId("connectorIdValue"),
  platformUrlValue: byId("platformUrlValue"),
  heartbeatAtValue: byId("heartbeatAtValue"),
  heartbeatErrorValue: byId("heartbeatErrorValue"),
  codexValue: byId("codexValue"),
  llmValue: byId("llmValue"),
  logOutput: byId("logOutput"),
  startBtn: byId("startBtn"),
  stopBtn: byId("stopBtn"),
  statusBtn: byId("statusBtn"),
  logsBtn: byId("logsBtn"),
  dataBtn: byId("dataBtn"),
  rootBtn: byId("rootBtn"),
  clearLogBtn: byId("clearLogBtn")
};

function appendLog(text) {
  els.logOutput.textContent += text;
  els.logOutput.scrollTop = els.logOutput.scrollHeight;
}

function setRunBadge(running) {
  els.runBadge.textContent = running ? "运行中" : "未启动";
  els.runBadge.className = `pill ${running ? "pill--ok" : "pill--idle"}`;
  els.runningValue.textContent = running ? "是" : "否";
}

function updateStatus(payload) {
  const health = payload.health || {};
  const pairing = payload.pairing || {};
  setRunBadge(Boolean(payload.running));
  els.statusUrl.textContent = payload.statusUrl || "http://127.0.0.1:3931";
  els.rootDir.textContent = payload.rootDir || "-";
  els.dataDir.textContent = payload.dataDir || "-";
  els.pidValue.textContent = payload.launcherPid || "-";
  els.platformValue.textContent = health.platform || "-";
  els.versionValue.textContent = health.connector_version || "-";
  els.pairedValue.textContent = pairing.paired ? "已配对" : "未配对";
  els.ownerValue.textContent = pairing.owner_username || "-";
  els.connectorIdValue.textContent = pairing.connector_id || "-";
  els.platformUrlValue.textContent = pairing.platform_url || "-";
  els.heartbeatAtValue.textContent = pairing.last_heartbeat_at || "-";
  els.heartbeatErrorValue.textContent = pairing.last_heartbeat_error || "无";
  els.codexValue.textContent = health.codex_available ? "已检测到" : "未检测到";
  els.llmValue.textContent = health.llm_bridge_enabled ? "已配置" : "未配置";
  if (payload.errors && payload.errors.length) {
    els.heroText.textContent = `状态探测异常：${payload.errors.join(" | ")}`;
  } else if (pairing.last_pairing_error) {
    els.heroText.textContent = `最近配对异常：${pairing.last_pairing_error}`;
  } else {
    els.heroText.textContent = "适合普通用户的一键启动和状态查看界面。";
  }
}

window.connectorDesktop.onStatusUpdate(updateStatus);
window.connectorDesktop.onRuntimeLog((payload) => appendLog(payload.line || ""));
window.connectorDesktop.onRuntimeLogBatch((payload) => appendLog(payload.text || ""));
window.connectorDesktop.onLauncherState((payload) => {
  setRunBadge(Boolean(payload.running));
  if (payload.error) {
    appendLog(`\n[desktop] ${payload.error}\n`);
  }
});

els.startBtn.addEventListener("click", async () => {
  appendLog("\n[desktop] 正在启动连接器...\n");
  await window.connectorDesktop.startLauncher();
});

els.stopBtn.addEventListener("click", async () => {
  appendLog("\n[desktop] 正在停止连接器...\n");
  await window.connectorDesktop.stopLauncher();
});

els.statusBtn.addEventListener("click", async () => {
  await window.connectorDesktop.openStatusPage();
});

els.logsBtn.addEventListener("click", async () => {
  await window.connectorDesktop.openLogDir();
});

els.dataBtn.addEventListener("click", async () => {
  await window.connectorDesktop.openDataDir();
});

els.rootBtn.addEventListener("click", async () => {
  await window.connectorDesktop.openRootDir();
});

els.clearLogBtn.addEventListener("click", () => {
  els.logOutput.textContent = "";
});

window.addEventListener("DOMContentLoaded", async () => {
  const initial = await window.connectorDesktop.getInitialState();
  updateStatus(initial);
});
