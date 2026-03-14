const { app, BrowserWindow, ipcMain, shell, dialog } = require("electron");
const path = require("node:path");
const fs = require("node:fs");
const { spawn } = require("node:child_process");
const http = require("node:http");

let mainWindow = null;
let launcherProcess = null;
let statusTimer = null;
let launching = false;
let lastLogSize = 0;
let stoppingPromise = null;
let quitting = false;

function appRoot() {
  return app.isPackaged
    ? path.join(process.resourcesPath, "connector")
    : path.resolve(__dirname, "../..");
}

function dataRoot() {
  return path.join(app.getPath("userData"), "connector-runtime");
}

function logDir() {
  return path.join(dataRoot(), "logs");
}

function bootstrapLog() {
  return path.join(logDir(), "bootstrap.log");
}

function connectorLog() {
  return path.join(logDir(), "connector.log");
}

function stateFile() {
  return path.join(dataRoot(), ".connector-state.json");
}

function readConnectorState() {
  try {
    if (!fs.existsSync(stateFile())) {
      return {};
    }
    return JSON.parse(fs.readFileSync(stateFile(), "utf8"));
  } catch (_error) {
    return {};
  }
}

function resolveStatusUrl() {
  const state = readConnectorState();
  return String(
    state.runtime_url ||
      `http://${process.env.LOCAL_CONNECTOR_HOST || "127.0.0.1"}:${process.env.LOCAL_CONNECTOR_PORT || "3931"}`
  ).trim();
}

function ensureWindow() {
  if (mainWindow && !mainWindow.isDestroyed()) return mainWindow;
  mainWindow = new BrowserWindow({
    width: 1180,
    height: 820,
    minWidth: 1024,
    minHeight: 700,
    backgroundColor: "#edf3fb",
    title: "Local Connector",
    webPreferences: {
      preload: path.join(__dirname, "preload.js"),
      contextIsolation: true,
      nodeIntegration: false
    }
  });
  mainWindow.loadFile(path.join(__dirname, "index.html"));
  mainWindow.on("closed", () => {
    mainWindow = null;
  });
  return mainWindow;
}

function sendToRenderer(channel, payload) {
  if (!mainWindow || mainWindow.isDestroyed()) return;
  mainWindow.webContents.send(channel, payload);
}

function appendRuntimeLog(line) {
  sendToRenderer("runtime-log", { line });
}

function wait(ms) {
  return new Promise((resolve) => {
    setTimeout(resolve, ms);
  });
}

function startStatusPolling() {
  stopStatusPolling();
  statusTimer = setInterval(async () => {
    const payload = await collectStatus();
    sendToRenderer("status-update", payload);
    streamLogTail();
  }, 4000);
}

function stopStatusPolling() {
  if (statusTimer) {
    clearInterval(statusTimer);
    statusTimer = null;
  }
}

function requestJson(urlPath, baseUrl = resolveStatusUrl()) {
  return new Promise((resolve, reject) => {
    const req = http.get(`${baseUrl}${urlPath}`, (res) => {
      let raw = "";
      res.setEncoding("utf8");
      res.on("data", (chunk) => {
        raw += chunk;
      });
      res.on("end", () => {
        try {
          resolve(JSON.parse(raw || "{}"));
        } catch (error) {
          reject(error);
        }
      });
    });
    req.on("error", reject);
    req.setTimeout(1500, () => {
      req.destroy(new Error("timeout"));
    });
  });
}

function requestRaw(method, urlPath, baseUrl = resolveStatusUrl()) {
  return new Promise((resolve, reject) => {
    const req = http.request(`${baseUrl}${urlPath}`, { method }, (res) => {
      let raw = "";
      res.setEncoding("utf8");
      res.on("data", (chunk) => {
        raw += chunk;
      });
      res.on("end", () => {
        resolve({
          statusCode: res.statusCode || 0,
          body: raw
        });
      });
    });
    req.on("error", reject);
    req.setTimeout(2000, () => {
      req.destroy(new Error("timeout"));
    });
    req.end();
  });
}

async function collectStatus() {
  const statusUrl = resolveStatusUrl();
  const result = {
    running: Boolean(launcherProcess),
    launcherPid: launcherProcess?.pid || null,
    statusUrl,
    rootDir: appRoot(),
    dataDir: dataRoot(),
    bootstrapLog: bootstrapLog(),
    connectorLog: connectorLog(),
    health: null,
    pairing: null,
    errors: []
  };
  try {
    result.health = await requestJson("/health", statusUrl);
  } catch (error) {
    result.errors.push(`health: ${error.message}`);
  }
  try {
    result.pairing = await requestJson("/pairing/state", statusUrl);
  } catch (error) {
    result.errors.push(`pairing: ${error.message}`);
  }
  return result;
}

function streamLogTail() {
  const targetLog = connectorLog();
  if (!fs.existsSync(targetLog)) return;
  const stat = fs.statSync(targetLog);
  if (stat.size < lastLogSize) {
    lastLogSize = 0;
  }
  if (stat.size === lastLogSize) return;
  const fd = fs.openSync(targetLog, "r");
  try {
    const length = stat.size - lastLogSize;
    const buffer = Buffer.alloc(length);
    fs.readSync(fd, buffer, 0, length, lastLogSize);
    lastLogSize = stat.size;
    const text = buffer.toString("utf8");
    if (text) {
      sendToRenderer("runtime-log-batch", { text });
    }
  } finally {
    fs.closeSync(fd);
  }
}

function startLauncher() {
  if (launcherProcess || launching) return;
  launching = true;
  fs.mkdirSync(logDir(), { recursive: true });
  lastLogSize = 0;
  const env = {
    ...process.env,
    ELECTRON_RUN_AS_NODE: "1",
    LOCAL_CONNECTOR_DISABLE_AUTO_INSTALL: "1",
    LOCAL_CONNECTOR_APP_ROOT: appRoot(),
    LOCAL_CONNECTOR_DATA_DIR: dataRoot(),
    LOCAL_CONNECTOR_HOST: process.env.LOCAL_CONNECTOR_HOST || "127.0.0.1",
    LOCAL_CONNECTOR_PORT: process.env.LOCAL_CONNECTOR_PORT || "3931"
  };
  launcherProcess = spawn(process.execPath, [path.join(appRoot(), "launcher.js")], {
    cwd: appRoot(),
    env,
    stdio: ["ignore", "pipe", "pipe"]
  });
  launcherProcess.stdout.setEncoding("utf8");
  launcherProcess.stderr.setEncoding("utf8");
  launcherProcess.stdout.on("data", (chunk) => appendRuntimeLog(String(chunk || "")));
  launcherProcess.stderr.on("data", (chunk) => appendRuntimeLog(String(chunk || "")));
  launcherProcess.on("exit", (code, signal) => {
    appendRuntimeLog(`\n[desktop] launcher exited. code=${code ?? "null"} signal=${signal ?? "null"}\n`);
    launcherProcess = null;
    launching = false;
    sendToRenderer("launcher-state", { running: false, code, signal });
  });
  launcherProcess.on("spawn", () => {
    launching = false;
    sendToRenderer("launcher-state", { running: true, pid: launcherProcess?.pid || null });
  });
  launcherProcess.on("error", (error) => {
    appendRuntimeLog(`\n[desktop] 启动失败: ${error.message}\n`);
    launcherProcess = null;
    launching = false;
    sendToRenderer("launcher-state", { running: false, error: error.message });
  });
}

function stopLauncher() {
  const statusUrl = resolveStatusUrl();
  void requestRaw("POST", "/runtime/stop", statusUrl).catch(() => null);
  if (!launcherProcess) return false;
  const killed = launcherProcess.kill(process.platform === "win32" ? undefined : "SIGTERM");
  return killed;
}

async function waitForConnectorStop(statusUrl, timeoutMs = 4000) {
  const startedAt = Date.now();
  while (Date.now() - startedAt < timeoutMs) {
    try {
      await requestJson("/health", statusUrl);
    } catch (_error) {
      return true;
    }
    await wait(250);
  }
  return false;
}

async function waitForLauncherExit(timeoutMs = 3000) {
  const startedAt = Date.now();
  while (Date.now() - startedAt < timeoutMs) {
    if (!launcherProcess) {
      return true;
    }
    await wait(200);
  }
  return !launcherProcess;
}

async function stopLauncherGracefully() {
  if (stoppingPromise) {
    return stoppingPromise;
  }
  stoppingPromise = (async () => {
    const statusUrl = resolveStatusUrl();
    try {
      await requestRaw("POST", "/runtime/stop", statusUrl);
    } catch (_error) {
      // ignore; fall back to killing launcher below
    }

    await waitForConnectorStop(statusUrl, 3500);

    const child = launcherProcess;
    if (child && child.exitCode === null && !child.killed) {
      try {
        child.kill(process.platform === "win32" ? undefined : "SIGTERM");
      } catch (_error) {
        // ignore
      }
    }

    await waitForLauncherExit(3000);
    sendToRenderer("launcher-state", { running: false });
    return { ok: true };
  })().finally(() => {
    stoppingPromise = null;
  });
  return stoppingPromise;
}

ipcMain.handle("desktop:get-initial-state", async () => collectStatus());
ipcMain.handle("desktop:start-launcher", async () => {
  startLauncher();
  return { ok: true };
});
ipcMain.handle("desktop:stop-launcher", async () => stopLauncherGracefully());
ipcMain.handle("desktop:open-status-page", async () => {
  await shell.openExternal(resolveStatusUrl());
  return { ok: true };
});
ipcMain.handle("desktop:open-log-dir", async () => {
  fs.mkdirSync(logDir(), { recursive: true });
  await shell.openPath(logDir());
  return { ok: true };
});
ipcMain.handle("desktop:open-root-dir", async () => {
  await shell.openPath(appRoot());
  return { ok: true };
});
ipcMain.handle("desktop:open-data-dir", async () => {
  fs.mkdirSync(dataRoot(), { recursive: true });
  await shell.openPath(dataRoot());
  return { ok: true };
});
ipcMain.handle("desktop:pick-workspace", async () => {
  const win = ensureWindow();
  const result = await dialog.showOpenDialog(win, {
    title: "选择本地工作区目录",
    properties: ["openDirectory"]
  });
  return {
    canceled: result.canceled,
    path: result.canceled ? "" : (result.filePaths[0] || "")
  };
});

app.whenReady().then(async () => {
  ensureWindow();
  startStatusPolling();
  sendToRenderer("status-update", await collectStatus());
});

app.on("window-all-closed", () => {
  app.quit();
});

app.on("before-quit", (event) => {
  if (quitting) {
    return;
  }
  event.preventDefault();
  quitting = true;
  stopStatusPolling();
  void stopLauncherGracefully().finally(() => {
    app.quit();
  });
});
