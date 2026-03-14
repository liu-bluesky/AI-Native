"use strict";

const http = require("node:http");
const fs = require("node:fs");
const fsp = require("node:fs/promises");
const net = require("node:net");
const path = require("node:path");
const os = require("node:os");
const crypto = require("node:crypto");
const { spawn, spawnSync } = require("node:child_process");

const CONNECTOR_VERSION = "0.2.0";
const DEFAULT_HOST = "127.0.0.1";
const DEFAULT_PORT = 3931;
const ROOT_DIR = path.resolve(process.env.LOCAL_CONNECTOR_APP_ROOT || __dirname);
const DATA_DIR = path.resolve(process.env.LOCAL_CONNECTOR_DATA_DIR || ROOT_DIR);
const STATE_FILE = path.join(DATA_DIR, ".connector-state.json");
const nativePtyModule = loadNativePtyModule();

const execProcesses = new Map();
const ptySessions = new Map();
let httpServer = null;
let shuttingDown = false;

let heartbeatTimer = null;
let runtimeHost = process.env.LOCAL_CONNECTOR_HOST || DEFAULT_HOST;
let runtimePort = Number.parseInt(process.env.LOCAL_CONNECTOR_PORT || String(DEFAULT_PORT), 10) || DEFAULT_PORT;

class HttpError extends Error {
  constructor(statusCode, message) {
    super(message);
    this.statusCode = statusCode;
  }
}

class AsyncEventQueue {
  constructor() {
    this.items = [];
    this.waiters = [];
  }

  push(value) {
    if (this.waiters.length > 0) {
      const resolve = this.waiters.shift();
      resolve(value);
      return;
    }
    this.items.push(value);
  }

  next() {
    if (this.items.length > 0) {
      return Promise.resolve(this.items.shift());
    }
    return new Promise((resolve) => {
      this.waiters.push(resolve);
    });
  }
}

function loadNativePtyModule() {
  const candidates = [
    path.join(ROOT_DIR, "vendor", "@homebridge", "node-pty-prebuilt-multiarch"),
    path.join(ROOT_DIR, "vendor", "node-pty"),
    "@homebridge/node-pty-prebuilt-multiarch",
    "node-pty"
  ];
  for (const candidate of candidates) {
    try {
      return {
        packageName: candidate,
        api: require(candidate)
      };
    } catch (_error) {
      // try next
    }
  }
  return null;
}

function splitEnvList(name) {
  const raw = String(process.env[name] || "").trim();
  if (!raw) {
    return [];
  }
  return raw.split(",").map((item) => item.trim()).filter(Boolean);
}

function loadState() {
  try {
    if (!fs.existsSync(STATE_FILE)) {
      return {};
    }
    return JSON.parse(fs.readFileSync(STATE_FILE, "utf8"));
  } catch (_error) {
    return {};
  }
}

function saveState(payload) {
  fs.mkdirSync(path.dirname(STATE_FILE), { recursive: true });
  fs.writeFileSync(STATE_FILE, `${JSON.stringify(payload, null, 2)}\n`, "utf8");
}

function updateState(patch) {
  const state = loadState();
  const nextState = { ...state, ...patch };
  saveState(nextState);
  return nextState;
}

function platformUrl() {
  const state = loadState();
  return String(process.env.LOCAL_CONNECTOR_PLATFORM_URL || state.platform_url || "")
    .trim()
    .replace(/\/+$/, "");
}

function pairCode() {
  return String(process.env.LOCAL_CONNECTOR_PAIR_CODE || "").trim();
}

function normalizePlatformUrl(value) {
  return String(value || "").trim().replace(/\/+$/, "");
}

function connectorName() {
  const configured = String(process.env.LOCAL_CONNECTOR_NAME || "").trim();
  if (configured) {
    return configured;
  }
  return `${os.hostname()} Connector`;
}

function advertisedUrl() {
  return String(process.env.LOCAL_CONNECTOR_ADVERTISED_URL || "").trim() || runtimeBaseUrl();
}

function heartbeatIntervalSec() {
  const parsed = Number.parseInt(String(process.env.LOCAL_CONNECTOR_HEARTBEAT_SEC || "").trim(), 10);
  if (!Number.isFinite(parsed)) {
    return 20;
  }
  return Math.max(10, Math.min(parsed, 120));
}

function platformLabel() {
  if (process.platform === "darwin") {
    return "macos";
  }
  if (process.platform === "win32") {
    return "windows";
  }
  return process.platform;
}

function runtimeBaseUrl() {
  return `http://${runtimeHost}:${runtimePort}`;
}

function llmBaseUrl() {
  return String(process.env.LOCAL_CONNECTOR_LLM_BASE_URL || "").trim().replace(/\/+$/, "");
}

function llmDefaultModel() {
  return String(process.env.LOCAL_CONNECTOR_LLM_DEFAULT_MODEL || "").trim();
}

function llmModels() {
  const configured = splitEnvList("LOCAL_CONNECTOR_LLM_MODELS");
  if (configured.length > 0) {
    return configured;
  }
  const fallback = llmDefaultModel();
  return fallback ? [fallback] : [];
}

function llmHeaders() {
  const headers = { "Content-Type": "application/json" };
  const apiKey = String(process.env.LOCAL_CONNECTOR_LLM_API_KEY || "").trim();
  if (apiKey) {
    headers.Authorization = `Bearer ${apiKey}`;
  }
  return headers;
}

function expandUser(rawPath) {
  const raw = String(rawPath || "").trim();
  if (!raw) {
    return "";
  }
  if (raw === "~") {
    return os.homedir();
  }
  if (raw.startsWith("~/") || raw.startsWith("~\\")) {
    return path.join(os.homedir(), raw.slice(2));
  }
  return raw;
}

function normalizeAbsolutePath(rawPath) {
  return path.resolve(expandUser(rawPath));
}

function isWithinPath(targetPath, rootPath) {
  const normalizedTarget = path.resolve(targetPath);
  const normalizedRoot = path.resolve(rootPath);
  const targetValue = process.platform === "win32" ? normalizedTarget.toLowerCase() : normalizedTarget;
  const rootValue = process.platform === "win32" ? normalizedRoot.toLowerCase() : normalizedRoot;
  const relative = path.relative(rootValue, targetValue);
  return relative === "" || (!relative.startsWith("..") && !path.isAbsolute(relative));
}

async function pathExists(targetPath) {
  try {
    await fsp.access(targetPath);
    return true;
  } catch (_error) {
    return false;
  }
}

async function probeWorkspaceAccess(workspacePath, sandboxMode = "workspace-write") {
  const raw = String(workspacePath || "").trim();
  const mode = String(sandboxMode || "workspace-write").trim() || "workspace-write";
  if (!raw) {
    return {
      configured: false,
      exists: false,
      is_dir: false,
      read_ok: false,
      write_ok: false,
      sandbox_mode: mode,
      reason: "workspace_path is empty"
    };
  }
  const workspace = normalizeAbsolutePath(raw);
  if (!(await pathExists(workspace))) {
    return {
      configured: true,
      exists: false,
      is_dir: false,
      read_ok: false,
      write_ok: false,
      sandbox_mode: mode,
      reason: `workspace does not exist: ${workspace}`
    };
  }
  const stat = await fsp.stat(workspace);
  if (!stat.isDirectory()) {
    return {
      configured: true,
      exists: true,
      is_dir: false,
      read_ok: false,
      write_ok: false,
      sandbox_mode: mode,
      reason: `workspace is not a directory: ${workspace}`
    };
  }
  const result = {
    configured: true,
    exists: true,
    is_dir: true,
    read_ok: true,
    write_ok: false,
    sandbox_mode: mode,
    path: workspace,
    reason: ""
  };
  if (mode !== "workspace-write") {
    result.reason = "current mode is read-only";
    return result;
  }
  const probeFile = path.join(workspace, `.write-probe-${crypto.randomUUID().replace(/-/g, "")}.tmp`);
  try {
    await fsp.writeFile(probeFile, "ok", "utf8");
    await fsp.rm(probeFile, { force: true });
    result.write_ok = true;
    return result;
  } catch (error) {
    result.reason = error instanceof Error ? error.message : String(error);
    return result;
  }
}

function createTimeoutSignal(timeoutMs) {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(new Error("timeout")), timeoutMs);
  return {
    signal: controller.signal,
    clear() {
      clearTimeout(timer);
    }
  };
}

async function fetchJson(url, options = {}) {
  const timeout = createTimeoutSignal(options.timeoutMs || 20000);
  try {
    const response = await fetch(url, {
      method: options.method || "GET",
      headers: options.headers,
      body: options.body,
      signal: timeout.signal
    });
    const text = await response.text();
    let payload = {};
    if (text) {
      try {
        payload = JSON.parse(text);
      } catch (_error) {
        payload = text;
      }
    }
    if (!response.ok) {
      const message = typeof payload === "string"
        ? payload
        : String(payload?.detail || payload?.message || JSON.stringify(payload) || "");
      const error = new Error(message || `HTTP ${response.status}`);
      error.statusCode = response.status;
      throw error;
    }
    return payload;
  } finally {
    timeout.clear();
  }
}

function connectorIdentityState() {
  const state = loadState();
  return {
    connectorId: String(state.connector_id || "").trim(),
    connectorToken: String(state.connector_token || "").trim(),
    platformUrl: normalizePlatformUrl(state.platform_url || platformUrl())
  };
}

function pickDirectoryViaNativeDialog(initialPath = "", title = "选择本地工作区目录") {
  const normalizedTitle = String(title || "选择本地工作区目录").trim() || "选择本地工作区目录";
  const rawInitialPath = String(initialPath || "").trim();
  const expandedInitial = rawInitialPath ? normalizeAbsolutePath(rawInitialPath) : "";
  let initialDir = "";
  if (expandedInitial && fs.existsSync(expandedInitial) && fs.statSync(expandedInitial).isDirectory()) {
    initialDir = expandedInitial;
  } else if (expandedInitial) {
    initialDir = path.dirname(expandedInitial);
  }

  if (process.platform === "darwin") {
    const args = ["-e"];
    if (initialDir && fs.existsSync(initialDir)) {
      args.push(
        `set chosenFolder to choose folder with prompt "${normalizedTitle.replace(/"/g, "\\\"")}" default location POSIX file "${initialDir.replace(/"/g, "\\\"")}"`
      );
    } else {
      args.push(`set chosenFolder to choose folder with prompt "${normalizedTitle.replace(/"/g, "\\\"")}"`);
    }
    args.push("-e", "POSIX path of chosenFolder");
    const result = spawnSync("osascript", args, { encoding: "utf8" });
    const message = String(result.stderr || result.stdout || "").trim();
    if (result.status !== 0) {
      if (message.includes("User canceled") || message.includes("(-128)")) {
        return "";
      }
      throw new Error(message || "macOS 原生目录选择失败");
    }
    return String(result.stdout || "").trim().replace(/\/+$/, "");
  }

  if (process.platform === "win32") {
    const command = [
      "Add-Type -AssemblyName System.Windows.Forms;",
      "$dialog = New-Object System.Windows.Forms.FolderBrowserDialog;",
      `$dialog.Description = "${normalizedTitle.replace(/"/g, "\\\"")}";`
    ];
    if (initialDir && fs.existsSync(initialDir)) {
      command.push(`$dialog.SelectedPath = "${initialDir.replace(/"/g, "\\\"")}";`);
    }
    command.push('if ($dialog.ShowDialog() -eq [System.Windows.Forms.DialogResult]::OK) { [Console]::Write($dialog.SelectedPath) }');
    const result = spawnSync("powershell", ["-NoProfile", "-Command", command.join(" ")], { encoding: "utf8" });
    const message = String(result.stderr || result.stdout || "").trim();
    if (result.status !== 0) {
      throw new Error(message || "Windows 原生目录选择失败");
    }
    return String(result.stdout || "").trim();
  }

  const zenityArgs = ["--file-selection", "--directory", `--title=${normalizedTitle}`];
  if (initialDir && fs.existsSync(initialDir)) {
    zenityArgs.push(`--filename=${initialDir}${path.sep}`);
  }
  const zenity = spawnSync("zenity", zenityArgs, { encoding: "utf8" });
  if (zenity.status === 0) {
    return String(zenity.stdout || "").trim();
  }
  if (zenity.status === 1) {
    return "";
  }

  const kdialogArgs = ["--getexistingdirectory"];
  if (initialDir && fs.existsSync(initialDir)) {
    kdialogArgs.push(initialDir);
  }
  kdialogArgs.push("--title", normalizedTitle);
  const kdialog = spawnSync("kdialog", kdialogArgs, { encoding: "utf8" });
  if (kdialog.status === 0) {
    return String(kdialog.stdout || "").trim();
  }
  if (kdialog.status === 1) {
    return "";
  }

  throw new Error("当前本机环境不支持原生目录选择器，或连接器运行在无桌面界面的 headless 模式");
}

async function consumeWorkspacePickSession(platformUrlValue, sessionId, sessionToken, connectorToken) {
  return fetchJson(`${normalizePlatformUrl(platformUrlValue)}/api/local-connectors/workspace-pick/consume`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      "X-Connector-Token": connectorToken
    },
    body: JSON.stringify({
      session_id: sessionId,
      session_token: sessionToken
    }),
    timeoutMs: 20000
  });
}

async function handleWorkspacePick(reqBody) {
  const sessionId = String(reqBody.session_id || "").trim();
  const sessionToken = String(reqBody.session_token || "").trim();
  const requestPlatformUrl = normalizePlatformUrl(reqBody.platform_url);
  const title = String(reqBody.title || "选择本地工作区目录").trim() || "选择本地工作区目录";
  const initialPath = String(reqBody.initial_path || "").trim();
  const identity = connectorIdentityState();
  if (!identity.connectorId || !identity.connectorToken || !identity.platformUrl) {
    throw new HttpError(409, "当前本地连接器尚未完成配对，无法选择目录");
  }
  if (!sessionId || !sessionToken || !requestPlatformUrl) {
    throw new HttpError(400, "platform_url, session_id and session_token are required");
  }
  if (identity.platformUrl !== requestPlatformUrl) {
    throw new HttpError(403, "workspace pick platform mismatch");
  }
  await consumeWorkspacePickSession(requestPlatformUrl, sessionId, sessionToken, identity.connectorToken);
  const selectedPath = pickDirectoryViaNativeDialog(initialPath, title);
  return {
    ok: true,
    cancelled: !selectedPath,
    path: selectedPath,
    connector_id: identity.connectorId
  };
}

function llmEndpoint() {
  const baseUrl = llmBaseUrl();
  if (!baseUrl) {
    throw new HttpError(400, "LOCAL_CONNECTOR_LLM_BASE_URL is not configured");
  }
  return `${baseUrl}/chat/completions`;
}

function listChildDirs(rootPath) {
  try {
    return fs.readdirSync(rootPath, { withFileTypes: true })
      .filter((entry) => entry && entry.isDirectory())
      .map((entry) => path.join(rootPath, entry.name));
  } catch (_error) {
    return [];
  }
}

function existingDir(dirPath) {
  if (!dirPath) {
    return "";
  }
  try {
    const stat = fs.statSync(dirPath);
    return stat.isDirectory() ? dirPath : "";
  } catch (_error) {
    return "";
  }
}

function candidateExecutableDirs() {
  const dirs = [];
  const push = (dirPath) => {
    const normalized = existingDir(dirPath);
    if (normalized) {
      dirs.push(normalized);
    }
  };
  const home = os.homedir();
  if (process.platform === "darwin" || process.platform === "linux") {
    push("/opt/homebrew/bin");
    push("/usr/local/bin");
    push("/usr/bin");
    push(path.join(home, ".local", "bin"));
    push(path.join(home, ".npm-global", "bin"));
    push(path.join(home, ".volta", "bin"));
    push(path.join(home, ".asdf", "shims"));
    push(path.join(home, ".nvm", "current", "bin"));
    for (const versionDir of listChildDirs(path.join(home, ".nvm", "versions", "node"))) {
      push(path.join(versionDir, "bin"));
    }
    for (const versionDir of listChildDirs(path.join(home, ".fnm", "node-versions"))) {
      push(path.join(versionDir, "installation", "bin"));
    }
    return dirs;
  }

  if (process.platform === "win32") {
    const userProfile = String(process.env.USERPROFILE || home || "").trim();
    const appData = String(process.env.APPDATA || path.join(userProfile, "AppData", "Roaming")).trim();
    const localAppData = String(process.env.LOCALAPPDATA || path.join(userProfile, "AppData", "Local")).trim();
    const programFiles = String(process.env.ProgramFiles || "C:\\Program Files").trim();
    const programFilesX86 = String(process.env["ProgramFiles(x86)"] || "C:\\Program Files (x86)").trim();
    const programData = String(process.env.ProgramData || "C:\\ProgramData").trim();
    const nvmHome = String(process.env.NVM_HOME || "").trim();
    const nvmSymlink = String(process.env.NVM_SYMLINK || "").trim();
    const scoopRoot = String(process.env.SCOOP || path.join(userProfile, "scoop")).trim();
    const chocolateyRoot = String(process.env.ChocolateyInstall || path.join(programData, "chocolatey")).trim();

    push(path.join(appData, "npm"));
    push(path.join(localAppData, "Programs", "nodejs"));
    push(path.join(programFiles, "nodejs"));
    push(path.join(programFilesX86, "nodejs"));
    push(path.join(userProfile, ".volta", "bin"));
    push(path.join(userProfile, ".asdf", "shims"));
    push(path.join(scoopRoot, "shims"));
    push(path.join(chocolateyRoot, "bin"));
    push(nvmSymlink);
    push(nvmHome);
    for (const versionDir of listChildDirs(nvmHome)) {
      push(versionDir);
    }
    return dirs;
  }

  return dirs;
}

function augmentProcessPath() {
  const currentPath = String(process.env.PATH || "").trim();
  const existing = new Set(
    currentPath.split(path.delimiter)
      .map((item) => item.trim())
      .filter(Boolean)
      .map((item) => (process.platform === "win32" ? item.toLowerCase() : item))
  );
  const extras = [];
  for (const dirPath of candidateExecutableDirs()) {
    const key = process.platform === "win32" ? dirPath.toLowerCase() : dirPath;
    if (existing.has(key)) {
      continue;
    }
    existing.add(key);
    extras.push(dirPath);
  }
  if (extras.length === 0) {
    return currentPath;
  }
  const nextPath = [...extras, currentPath].filter(Boolean).join(path.delimiter);
  process.env.PATH = nextPath;
  return nextPath;
}

function findExecutable(commandName) {
  const pathValue = String(process.env.PATH || "");
  const dirs = pathValue.split(path.delimiter).filter(Boolean);
  const extensions = process.platform === "win32"
    ? String(process.env.PATHEXT || ".EXE;.CMD;.BAT;.COM")
      .split(";")
      .map((item) => item.trim())
      .filter(Boolean)
    : [""];
  for (const dirPath of dirs) {
    if (process.platform === "win32") {
      for (const ext of extensions) {
        const candidate = path.join(dirPath, `${commandName}${ext}`);
        if (fs.existsSync(candidate)) {
          return candidate;
        }
      }
      const directCandidate = path.join(dirPath, commandName);
      if (fs.existsSync(directCandidate)) {
        return directCandidate;
      }
      continue;
    }
    const candidate = path.join(dirPath, commandName);
    try {
      fs.accessSync(candidate, fs.constants.X_OK);
      return candidate;
    } catch (_error) {
      // continue
    }
  }
  return "";
}

augmentProcessPath();

async function healthPayload() {
  const codexPath = findExecutable("codex");
  const claudePath = findExecutable("claude");
  const geminiPath = findExecutable("gemini");
  return {
    ok: true,
    connector_version: CONNECTOR_VERSION,
    platform: process.platform === "win32" ? "nt" : "posix",
    codex_available: Boolean(codexPath),
    codex_path: codexPath,
    claude_available: Boolean(claudePath),
    claude_path: claudePath,
    gemini_available: Boolean(geminiPath),
    gemini_path: geminiPath,
    pty_native_available: Boolean(nativePtyModule),
    pty_provider: nativePtyModule ? nativePtyModule.packageName : "",
    llm_bridge_enabled: Boolean(llmBaseUrl()),
    runtime_url: runtimeBaseUrl()
  };
}

async function manifestPayload() {
  return {
    name: "local-connector",
    version: CONNECTOR_VERSION,
    capabilities: {
      workspace: true,
      exec_stream: true,
      pty: true,
      pty_native: Boolean(nativePtyModule),
      local_llm_bridge: true
    },
    llm: {
      base_url_configured: Boolean(llmBaseUrl()),
      models: llmModels(),
      default_model: llmDefaultModel()
    },
    platforms: ["macos", "windows"]
  };
}

function pairingStatePayload() {
  const state = loadState();
  return {
    paired: Boolean(String(state.connector_id || "").trim() && String(state.connector_token || "").trim()),
    platform_url: String(state.platform_url || "").trim(),
    connector_id: String(state.connector_id || "").trim(),
    connector_name: connectorName(),
    advertised_url: advertisedUrl(),
    runtime_url: String(state.runtime_url || runtimeBaseUrl()).trim(),
    runtime_port: Number.parseInt(String(state.runtime_port || runtimePort), 10) || runtimePort,
    owner_username: String(state.owner_username || "").trim(),
    heartbeat_interval_sec: Number.parseInt(String(state.heartbeat_interval_sec || heartbeatIntervalSec()), 10) || heartbeatIntervalSec(),
    data_dir: DATA_DIR,
    last_pairing_error: String(state.last_pairing_error || "").trim(),
    last_heartbeat_at: String(state.last_heartbeat_at || "").trim(),
    last_heartbeat_error: String(state.last_heartbeat_error || "").trim(),
    heartbeat_ok: Boolean(state.heartbeat_ok)
  };
}

function statusPageHtml() {
  return `<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>Local Connector 状态</title>
  <style>
    :root {
      color-scheme: light;
      --bg: #f3f6fb;
      --card: #ffffff;
      --text: #152033;
      --muted: #5f6b7a;
      --ok: #0f9d58;
      --warn: #d97706;
      --err: #dc2626;
      --border: #d9e2f0;
      --shadow: 0 12px 30px rgba(21, 32, 51, 0.08);
    }
    body { margin: 0; padding: 24px; background: linear-gradient(180deg, #eef4ff 0%, var(--bg) 100%); color: var(--text); font: 14px/1.6 "Segoe UI", "PingFang SC", "Microsoft YaHei", sans-serif; }
    .shell { max-width: 980px; margin: 0 auto; }
    .hero { margin-bottom: 18px; }
    .hero h1 { margin: 0 0 6px; font-size: 28px; }
    .hero p { margin: 0; color: var(--muted); }
    .grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(260px, 1fr)); gap: 16px; }
    .card { background: var(--card); border: 1px solid var(--border); border-radius: 18px; padding: 18px; box-shadow: var(--shadow); }
    .card h2 { margin: 0 0 12px; font-size: 16px; }
    .status { display: inline-flex; align-items: center; gap: 8px; padding: 6px 10px; border-radius: 999px; font-weight: 600; background: #eef7ff; }
    .status.ok { color: var(--ok); background: #edf9f1; }
    .status.warn { color: var(--warn); background: #fff7ed; }
    .status.err { color: var(--err); background: #fef2f2; }
    .kv { display: grid; grid-template-columns: 110px 1fr; gap: 8px 12px; }
    .kv dt { color: var(--muted); }
    .kv dd { margin: 0; word-break: break-all; }
    .actions { display: flex; flex-wrap: wrap; gap: 10px; margin-top: 16px; }
    button { border: 0; border-radius: 12px; padding: 10px 14px; background: #1d4ed8; color: #fff; cursor: pointer; font: inherit; }
    button.secondary { background: #e5edf9; color: var(--text); }
    pre { margin: 0; padding: 12px; border-radius: 12px; background: #0f172a; color: #e2e8f0; overflow: auto; white-space: pre-wrap; word-break: break-word; }
  </style>
</head>
<body>
  <div class="shell">
    <div class="hero">
      <h1>Local Connector 状态</h1>
      <p>这个页面运行在用户自己的电脑上，用来确认连接器是否启动、是否已配对、是否持续在线。</p>
    </div>
    <div class="grid">
      <section class="card">
        <h2>运行状态</h2>
        <div id="run-status" class="status">加载中</div>
        <dl class="kv" style="margin-top: 12px">
          <dt>本地地址</dt><dd id="runtime-url">-</dd>
          <dt>系统平台</dt><dd id="platform">-</dd>
          <dt>版本</dt><dd id="version">-</dd>
          <dt>本地模型桥接</dt><dd id="llm">-</dd>
        </dl>
      </section>
      <section class="card">
        <h2>平台配对</h2>
        <div id="pair-status" class="status">加载中</div>
        <dl class="kv" style="margin-top: 12px">
          <dt>平台地址</dt><dd id="platform-url">-</dd>
          <dt>连接器 ID</dt><dd id="connector-id">-</dd>
          <dt>设备名称</dt><dd id="connector-name">-</dd>
          <dt>所属用户</dt><dd id="owner-username">-</dd>
        </dl>
      </section>
      <section class="card">
        <h2>心跳状态</h2>
        <div id="heartbeat-status" class="status">加载中</div>
        <dl class="kv" style="margin-top: 12px">
          <dt>上次成功</dt><dd id="last-heartbeat-at">-</dd>
          <dt>心跳间隔</dt><dd id="heartbeat-interval">-</dd>
          <dt>数据目录</dt><dd id="data-dir">-</dd>
          <dt>最近错误</dt><dd id="last-heartbeat-error">-</dd>
        </dl>
      </section>
      <section class="card">
        <h2>本机 CLI</h2>
        <dl class="kv">
          <dt>Codex</dt><dd id="codex-cli">-</dd>
          <dt>Claude</dt><dd id="claude-cli">-</dd>
          <dt>Gemini</dt><dd id="gemini-cli">-</dd>
        </dl>
      </section>
      <section class="card" style="grid-column: 1 / -1">
        <h2>错误与排查</h2>
        <pre id="troubleshooting">加载中...</pre>
        <div class="actions">
          <button onclick="refreshAll()">立即刷新</button>
          <button class="secondary" onclick="window.location.reload()">重载页面</button>
        </div>
      </section>
    </div>
  </div>
  <script>
    function setStatus(id, text, cls) {
      const el = document.getElementById(id);
      el.textContent = text;
      el.className = "status " + (cls || "");
    }
    function setText(id, value) {
      document.getElementById(id).textContent = value || "-";
    }
    async function refreshAll() {
      try {
        const [healthResp, pairingResp] = await Promise.all([
          fetch("/health", { cache: "no-store" }),
          fetch("/pairing/state", { cache: "no-store" }),
        ]);
        const health = await healthResp.json();
        const pairing = await pairingResp.json();
        setStatus("run-status", health.ok ? "服务已启动" : "服务异常", health.ok ? "ok" : "err");
        setStatus("pair-status", pairing.paired ? "已配对" : "未配对", pairing.paired ? "ok" : "warn");
        setStatus("heartbeat-status", pairing.heartbeat_ok ? "心跳正常" : (pairing.paired ? "等待心跳" : "尚未配对"), pairing.heartbeat_ok ? "ok" : (pairing.paired ? "warn" : ""));
        setText("runtime-url", health.runtime_url);
        setText("platform", health.platform);
        setText("version", health.connector_version);
        setText("llm", health.llm_bridge_enabled ? "已配置" : "未配置");
        setText("platform-url", pairing.platform_url);
        setText("connector-id", pairing.connector_id);
        setText("connector-name", pairing.connector_name);
        setText("owner-username", pairing.owner_username);
        setText("last-heartbeat-at", pairing.last_heartbeat_at);
        setText("heartbeat-interval", pairing.heartbeat_interval_sec ? pairing.heartbeat_interval_sec + " 秒" : "-");
        setText("data-dir", pairing.data_dir);
        setText("last-heartbeat-error", pairing.last_heartbeat_error || "无");
        setText("codex-cli", health.codex_available ? ("已检测到: " + (health.codex_path || "codex")) : "未检测到");
        setText("claude-cli", health.claude_available ? ("已检测到: " + (health.claude_path || "claude")) : "未检测到");
        setText("gemini-cli", health.gemini_available ? ("已检测到: " + (health.gemini_path || "gemini")) : "未检测到");
        const troubleshooting = [
          "如果窗口一闪而过，请重新双击启动脚本，并查看同目录 logs/bootstrap.log 与 logs/connector.log。",
          health.pty_native_available ? ("真实终端: 已启用 " + (health.pty_provider || "")) : "真实终端: 未安装原生 PTY 依赖，当前将降级为普通进程镜像。",
          pairing.last_pairing_error ? ("配对错误: " + pairing.last_pairing_error) : "配对错误: 无",
          pairing.last_heartbeat_error ? ("心跳错误: " + pairing.last_heartbeat_error) : "心跳错误: 无",
        ].join("\\n");
        document.getElementById("troubleshooting").textContent = troubleshooting;
      } catch (error) {
        setStatus("run-status", "状态读取失败", "err");
        document.getElementById("troubleshooting").textContent = String(error);
      }
    }
    refreshAll();
    setInterval(refreshAll, 5000);
  </script>
</body>
</html>`;
}

function sendJson(res, statusCode, payload) {
  const body = JSON.stringify(payload);
  res.writeHead(statusCode, {
    "Content-Type": "application/json; charset=utf-8",
    "Cache-Control": "no-store",
    "Access-Control-Allow-Origin": "*",
    "Access-Control-Allow-Methods": "GET,POST,OPTIONS",
    "Access-Control-Allow-Headers": "Content-Type"
  });
  res.end(body);
}

function sendHtml(res, statusCode, html) {
  res.writeHead(statusCode, {
    "Content-Type": "text/html; charset=utf-8",
    "Cache-Control": "no-store",
    "Access-Control-Allow-Origin": "*",
    "Access-Control-Allow-Methods": "GET,POST,OPTIONS",
    "Access-Control-Allow-Headers": "Content-Type"
  });
  res.end(html);
}

function sendNdjsonHeaders(res) {
  res.writeHead(200, {
    "Content-Type": "application/x-ndjson; charset=utf-8",
    "Cache-Control": "no-store",
    Connection: "keep-alive",
    "Access-Control-Allow-Origin": "*",
    "Access-Control-Allow-Methods": "GET,POST,OPTIONS",
    "Access-Control-Allow-Headers": "Content-Type"
  });
}

function writeNdjson(res, payload) {
  res.write(`${JSON.stringify(payload)}\n`);
}

function sendError(res, statusCode, message) {
  sendJson(res, statusCode, { detail: message });
}

function readJsonBody(req) {
  return new Promise((resolve, reject) => {
    let raw = "";
    req.setEncoding("utf8");
    req.on("data", (chunk) => {
      raw += chunk;
      if (raw.length > 10 * 1024 * 1024) {
        reject(new HttpError(413, "request body too large"));
        req.destroy();
      }
    });
    req.on("end", () => {
      if (!raw.trim()) {
        resolve({});
        return;
      }
      try {
        resolve(JSON.parse(raw));
      } catch (_error) {
        reject(new HttpError(400, "invalid json body"));
      }
    });
    req.on("error", reject);
  });
}

function createLinePump(stream, type, onEvent) {
  let buffer = "";
  stream.setEncoding("utf8");
  stream.on("data", (chunk) => {
    buffer += String(chunk || "");
    while (true) {
      const index = buffer.indexOf("\n");
      if (index < 0) {
        break;
      }
      const line = buffer.slice(0, index + 1);
      buffer = buffer.slice(index + 1);
      onEvent({ type, data: line });
    }
  });
  return () => {
    if (buffer) {
      onEvent({ type, data: buffer });
      buffer = "";
    }
  };
}

function terminateChild(child) {
  if (!child || child.exitCode !== null || child.killed) {
    return;
  }
  try {
    child.kill();
  } catch (_error) {
    // ignore
  }
}

async function handleLlmChat(reqBody) {
  const endpoint = llmEndpoint();
  let model = String(reqBody.model || llmDefaultModel() || "").trim();
  if (!model) {
    const configured = llmModels();
    model = configured[0] || "";
  }
  if (!model) {
    throw new HttpError(400, "No local model is configured");
  }
  const payload = await fetchJson(endpoint, {
    method: "POST",
    headers: llmHeaders(),
    body: JSON.stringify({
      model,
      messages: Array.isArray(reqBody.messages) ? reqBody.messages : [],
      temperature: Number(reqBody.temperature || 0),
      stream: false,
      ...(reqBody.max_tokens !== undefined && reqBody.max_tokens !== null
        ? { max_tokens: Number(reqBody.max_tokens) }
        : {})
    }),
    timeoutMs: 120000
  }).catch((error) => {
    if (error instanceof HttpError) {
      throw error;
    }
    const statusCode = error && error.statusCode ? Number(error.statusCode) : 500;
    throw new HttpError(statusCode, `Local LLM bridge failed: ${error instanceof Error ? error.message : String(error)}`);
  });
  const choices = Array.isArray(payload && payload.choices) ? payload.choices : [];
  const first = choices[0] && typeof choices[0] === "object" ? choices[0] : {};
  const message = first && typeof first.message === "object" ? first.message : {};
  return {
    content: String(message.content || "").trim(),
    model,
    raw: payload
  };
}

async function materializeWorkspace(reqBody) {
  const access = await probeWorkspaceAccess(reqBody.workspace_path, reqBody.sandbox_mode);
  access.source = "local_connector";
  const workspaceRoot = normalizeAbsolutePath(reqBody.workspace_path || "");
  const result = {
    ok: false,
    workspace_access: access,
    files: [],
    copies: []
  };
  if (!access.configured || !access.exists || !access.is_dir) {
    result.reason = String(access.reason || "workspace unavailable");
    return result;
  }
  if (reqBody.sandbox_mode === "workspace-write" && !access.write_ok) {
    result.reason = String(access.reason || "workspace is not writable");
    return result;
  }

  const fileResults = [];
  for (const item of Array.isArray(reqBody.files) ? reqBody.files : []) {
    const rawPath = String(item && item.path ? item.path : "").trim();
    const targetPath = normalizeAbsolutePath(rawPath);
    const entry = { path: targetPath, written: false };
    try {
      if (!path.isAbsolute(rawPath)) {
        throw new Error("path must be absolute");
      }
      if (!isWithinPath(targetPath, workspaceRoot)) {
        throw new Error("path must stay within workspace");
      }
      await fsp.mkdir(path.dirname(targetPath), { recursive: true });
      await fsp.writeFile(targetPath, String(item && item.content ? item.content : ""), "utf8");
      entry.written = true;
    } catch (error) {
      entry.error = error instanceof Error ? error.message : String(error);
    }
    fileResults.push(entry);
  }

  const copyResults = [];
  for (const item of Array.isArray(reqBody.copies) ? reqBody.copies : []) {
    const rawSourcePath = String(item && item.source_path ? item.source_path : "").trim();
    const rawTargetPath = String(item && item.target_path ? item.target_path : "").trim();
    const sourcePath = normalizeAbsolutePath(rawSourcePath);
    const targetPath = normalizeAbsolutePath(rawTargetPath);
    const entry = { source_path: sourcePath, target_path: targetPath, written: false };
    try {
      const sourceStat = await fsp.stat(sourcePath).catch(() => null);
      if (!sourceStat || !sourceStat.isFile()) {
        throw new Error(`source file not found: ${sourcePath}`);
      }
      if (!path.isAbsolute(rawTargetPath)) {
        throw new Error("target_path must be absolute");
      }
      if (!isWithinPath(targetPath, workspaceRoot)) {
        throw new Error("target_path must stay within workspace");
      }
      await fsp.mkdir(path.dirname(targetPath), { recursive: true });
      const content = await fsp.readFile(sourcePath, "utf8");
      await fsp.writeFile(targetPath, content, "utf8");
      entry.written = true;
    } catch (error) {
      entry.error = error instanceof Error ? error.message : String(error);
    }
    copyResults.push(entry);
  }

  result.ok = [...fileResults, ...copyResults].every((item) => item.written);
  result.files = fileResults;
  result.copies = copyResults;
  return result;
}

function createExecStream(res, reqBody, req) {
  const cmd = Array.isArray(reqBody.cmd) ? reqBody.cmd.map((item) => String(item || "")) : [];
  if (cmd.length === 0 || !cmd[0]) {
    throw new HttpError(400, "cmd is required");
  }
  const execId = `exec-${crypto.randomUUID().replace(/-/g, "").slice(0, 12)}`;
  let finished = false;
  let child;
  try {
    child = spawn(cmd[0], cmd.slice(1), {
      cwd: String(reqBody.cwd || "").trim() || process.cwd(),
      env: { ...process.env, ...(reqBody.env && typeof reqBody.env === "object" ? reqBody.env : {}) },
      stdio: ["ignore", "pipe", "pipe"]
    });
  } catch (error) {
    throw new HttpError(400, error instanceof Error ? error.message : String(error));
  }
  sendNdjsonHeaders(res);
  execProcesses.set(execId, child);
  writeNdjson(res, { type: "started", exec_id: execId });

  const flushStdout = createLinePump(child.stdout, "stdout", (event) => {
    if (!finished) {
      writeNdjson(res, event);
    }
  });
  const flushStderr = createLinePump(child.stderr, "stderr", (event) => {
    if (!finished) {
      writeNdjson(res, event);
    }
  });

  const cleanup = () => {
    execProcesses.delete(execId);
  };

  const finish = (returncode) => {
    if (finished) {
      return;
    }
    finished = true;
    flushStdout();
    flushStderr();
    writeNdjson(res, { type: "exit", exec_id: execId, returncode });
    res.end();
    cleanup();
  };

  child.on("error", (error) => {
    if (!finished) {
      writeNdjson(res, { type: "stderr", data: `${error.message}\n` });
    }
    finish(-1);
  });

  child.on("close", (code) => {
    finish(Number.isInteger(code) ? code : -1);
  });

  req.on("close", () => {
    if (!finished) {
      terminateChild(child);
      cleanup();
    }
  });
}

function createPtySession(reqBody) {
  const cmd = Array.isArray(reqBody.cmd) ? reqBody.cmd.map((item) => String(item || "")) : [];
  if (cmd.length === 0 || !cmd[0]) {
    throw new HttpError(400, "cmd is required");
  }
  const sessionId = `pty-${crypto.randomUUID().replace(/-/g, "").slice(0, 12)}`;
  const queue = new AsyncEventQueue();
  const cwd = String(reqBody.cwd || "").trim() || process.cwd();
  const env = { ...process.env, ...(reqBody.env && typeof reqBody.env === "object" ? reqBody.env : {}) };
  if (nativePtyModule) {
    let nativeProcess;
    try {
      nativeProcess = nativePtyModule.api.spawn(cmd[0], cmd.slice(1), {
        name: String(reqBody.term_name || "xterm-256color"),
        cols: Number(reqBody.cols || 120),
        rows: Number(reqBody.rows || 32),
        cwd,
        env
      });
    } catch (error) {
      throw new HttpError(400, error instanceof Error ? error.message : String(error));
    }
    const session = {
      id: sessionId,
      process: nativeProcess,
      queue,
      ended: false,
      mode: "native"
    };
    nativeProcess.onData((data) => {
      queue.push({ type: "chunk", data: String(data || "") });
    });
    nativeProcess.onExit((event) => {
      if (!session.ended) {
        session.ended = true;
        queue.push({ type: "exit", returncode: Number.isInteger(event?.exitCode) ? event.exitCode : 0 });
      }
    });
    ptySessions.set(sessionId, session);
    return sessionId;
  }
  let child;
  try {
    child = spawn(cmd[0], cmd.slice(1), {
      cwd,
      env,
      stdio: ["pipe", "pipe", "pipe"]
    });
  } catch (error) {
    throw new HttpError(400, error instanceof Error ? error.message : String(error));
  }
  const session = {
    id: sessionId,
    process: child,
    queue,
    ended: false,
    mode: "fallback"
  };
  child.stdout.setEncoding("utf8");
  child.stderr.setEncoding("utf8");
  child.stdout.on("data", (chunk) => {
    queue.push({ type: "chunk", data: String(chunk || "") });
  });
  child.stderr.on("data", (chunk) => {
    queue.push({ type: "chunk", data: String(chunk || "") });
  });
  child.on("close", (code) => {
    if (!session.ended) {
      session.ended = true;
      queue.push({ type: "exit", returncode: Number.isInteger(code) ? code : -1 });
    }
  });
  child.on("error", (error) => {
    queue.push({ type: "chunk", data: `${error.message}\n` });
    if (!session.ended) {
      session.ended = true;
      queue.push({ type: "exit", returncode: -1 });
    }
  });
  ptySessions.set(sessionId, session);
  return sessionId;
}

function closePtySession(sessionId) {
  const session = ptySessions.get(sessionId);
  if (!session) {
    return { ok: false, reason: "not_found" };
  }
  ptySessions.delete(sessionId);
  if (session.mode === "native") {
    try {
      session.process.kill();
    } catch (_error) {
      // ignore
    }
  } else if (session.process.exitCode === null && !session.process.killed) {
    terminateChild(session.process);
  }
  if (!session.ended) {
    session.ended = true;
    session.queue.push({
      type: "exit",
      returncode: session.mode === "native" ? 0 : (session.process.exitCode ?? -1)
    });
  }
  return { ok: true };
}

async function streamPtySession(req, res, sessionId) {
  const session = ptySessions.get(sessionId);
  if (!session) {
    throw new HttpError(404, "session not found");
  }
  sendNdjsonHeaders(res);
  let closed = false;
  req.on("close", () => {
    closed = true;
    closePtySession(sessionId);
  });
  while (!closed) {
    const event = await session.queue.next();
    if (closed) {
      break;
    }
    writeNdjson(res, event);
    if (event && event.type === "exit") {
      ptySessions.delete(sessionId);
      break;
    }
  }
  if (!res.writableEnded) {
    res.end();
  }
}

function formatLocalTimestamp() {
  const date = new Date();
  const pad = (value) => String(value).padStart(2, "0");
  return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())} ${pad(date.getHours())}:${pad(date.getMinutes())}:${pad(date.getSeconds())}`;
}

async function activatePairing(options = {}) {
  const state = loadState();
  const normalizedPlatformUrl = normalizePlatformUrl(options.platform_url || platformUrl());
  const normalizedPairCode = String(options.pair_code || pairCode()).trim();
  if (
    normalizedPlatformUrl &&
    String(state.platform_url || "").trim().replace(/\/+$/, "") === normalizedPlatformUrl &&
    String(state.connector_id || "").trim() &&
    String(state.connector_token || "").trim()
  ) {
    return false;
  }
  if (!normalizedPlatformUrl || !normalizedPairCode) {
    return false;
  }
  const body = {
    pair_code: normalizedPairCode,
    connector_name: connectorName(),
    platform: platformLabel(),
    app_version: CONNECTOR_VERSION,
    advertised_url: advertisedUrl(),
    manifest: await manifestPayload(),
    health: await healthPayload()
  };
  const payload = await fetchJson(`${normalizedPlatformUrl}/api/local-connectors/pair/activate`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
    timeoutMs: 20000
  });
  const nextState = {
    ...state,
    platform_url: normalizedPlatformUrl,
    connector_id: String(payload.connector_id || "").trim(),
    connector_token: String(payload.connector_token || "").trim(),
    owner_username: String(payload.owner_username || "").trim(),
    heartbeat_interval_sec: Number.parseInt(String(payload.heartbeat_interval_sec || heartbeatIntervalSec()), 10) || heartbeatIntervalSec(),
    last_pairing_error: "",
    paired_at: formatLocalTimestamp()
  };
  saveState(nextState);
  console.log(`[local-connector] paired with platform as ${nextState.connector_id}`);
  return true;
}

async function connectPairingFromBrowser(reqBody) {
  const normalizedPlatformUrl = normalizePlatformUrl(reqBody.platform_url);
  const normalizedPairCode = String(reqBody.pair_code || "").trim();
  if (!normalizedPlatformUrl || !normalizedPairCode) {
    throw new HttpError(400, "platform_url and pair_code are required");
  }
  try {
    await activatePairing({
      platform_url: normalizedPlatformUrl,
      pair_code: normalizedPairCode
    });
  } catch (error) {
    const message = error instanceof Error ? error.message : String(error);
    updateState({ last_pairing_error: message });
    throw error;
  }
  const state = loadState();
  if (String(state.connector_id || "").trim() && String(state.connector_token || "").trim()) {
    startHeartbeatLoop();
  }
  return {
    ok: true,
    pairing: pairingStatePayload()
  };
}

async function sendHeartbeatOnce() {
  const state = loadState();
  const normalizedPlatformUrl = String(state.platform_url || platformUrl() || "").trim().replace(/\/+$/, "");
  const connectorId = String(state.connector_id || "").trim();
  const connectorToken = String(state.connector_token || "").trim();
  if (!normalizedPlatformUrl || !connectorId || !connectorToken) {
    return;
  }
  await fetchJson(`${normalizedPlatformUrl}/api/local-connectors/${connectorId}/heartbeat`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      "X-Connector-Token": connectorToken
    },
    body: JSON.stringify({
      advertised_url: advertisedUrl(),
      manifest: await manifestPayload(),
      health: await healthPayload(),
      status: "online",
      last_error: ""
    }),
    timeoutMs: 20000
  });
  updateState({
    heartbeat_ok: true,
    last_heartbeat_at: formatLocalTimestamp(),
    last_heartbeat_error: ""
  });
}

function startHeartbeatLoop() {
  if (heartbeatTimer) {
    return;
  }
  const tick = async () => {
    try {
      await sendHeartbeatOnce();
    } catch (error) {
      const message = error instanceof Error ? error.message : String(error);
      updateState({
        heartbeat_ok: false,
        last_heartbeat_error: message
      });
      console.log(`[local-connector] heartbeat failed: ${message}`);
    } finally {
      const state = loadState();
      const interval = Number.parseInt(String(state.heartbeat_interval_sec || heartbeatIntervalSec()), 10) || heartbeatIntervalSec();
      heartbeatTimer = setTimeout(tick, Math.max(10, Math.min(interval, 120)) * 1000);
    }
  };
  heartbeatTimer = setTimeout(tick, 0);
}

function stopHeartbeatLoop() {
  if (!heartbeatTimer) {
    return;
  }
  clearTimeout(heartbeatTimer);
  heartbeatTimer = null;
}

function terminateChild(child) {
  if (!child) {
    return;
  }
  try {
    child.kill("SIGTERM");
  } catch (_error) {
    // ignore
  }
}

async function shutdown(server = httpServer) {
  if (shuttingDown) {
    return;
  }
  shuttingDown = true;
  stopHeartbeatLoop();
  for (const child of execProcesses.values()) {
    terminateChild(child);
  }
  execProcesses.clear();
  for (const [sessionId, session] of ptySessions.entries()) {
    try {
      closePtySession(sessionId);
    } catch (_error) {
      // ignore
    }
  }
  if (!server) {
    process.exit(0);
    return;
  }
  await new Promise((resolve) => {
    server.close(() => resolve());
  });
  process.exit(0);
}

async function bootstrapPairing() {
  try {
    await activatePairing();
  } catch (error) {
    const message = error instanceof Error ? error.message : String(error);
    updateState({ last_pairing_error: message });
    console.log(`[local-connector] pairing skipped/failed: ${message}`);
  }
  const state = loadState();
  if (String(state.connector_id || "").trim() && String(state.connector_token || "").trim()) {
    startHeartbeatLoop();
  }
}

async function routeRequest(req, res) {
  const requestUrl = new URL(req.url || "/", runtimeBaseUrl());
  const pathname = requestUrl.pathname;
  const method = String(req.method || "GET").toUpperCase();

  if (method === "OPTIONS") {
    res.writeHead(204, {
      "Cache-Control": "no-store",
      "Access-Control-Allow-Origin": "*",
      "Access-Control-Allow-Methods": "GET,POST,OPTIONS",
      "Access-Control-Allow-Headers": "Content-Type"
    });
    res.end();
    return;
  }
  if (method === "GET" && pathname === "/health") {
    sendJson(res, 200, await healthPayload());
    return;
  }
  if (method === "GET" && pathname === "/manifest") {
    sendJson(res, 200, await manifestPayload());
    return;
  }
  if (method === "GET" && pathname === "/pairing/state") {
    sendJson(res, 200, pairingStatePayload());
    return;
  }
  if (method === "POST" && pathname === "/pairing/connect") {
    const body = await readJsonBody(req);
    sendJson(res, 200, await connectPairingFromBrowser(body));
    return;
  }
  if (method === "POST" && pathname === "/runtime/stop") {
    sendJson(res, 200, { ok: true, status: "stopping" });
    setTimeout(() => {
      void shutdown();
    }, 10);
    return;
  }
  if (method === "GET" && pathname === "/") {
    sendHtml(res, 200, statusPageHtml());
    return;
  }
  if (method === "GET" && pathname === "/llm/models") {
    sendJson(res, 200, {
      enabled: Boolean(llmBaseUrl()),
      base_url: llmBaseUrl(),
      default_model: llmDefaultModel(),
      models: llmModels()
    });
    return;
  }
  if (method === "POST" && pathname === "/llm/chat/completions") {
    const body = await readJsonBody(req);
    sendJson(res, 200, await handleLlmChat(body));
    return;
  }
  if (method === "POST" && pathname === "/probe-workspace") {
    const body = await readJsonBody(req);
    const payload = await probeWorkspaceAccess(body.workspace_path, body.sandbox_mode);
    payload.source = "local_connector";
    sendJson(res, 200, payload);
    return;
  }
  if (method === "POST" && pathname === "/workspace/materialize") {
    const body = await readJsonBody(req);
    sendJson(res, 200, await materializeWorkspace(body));
    return;
  }
  if (method === "POST" && pathname === "/workspace/pick") {
    const body = await readJsonBody(req);
    sendJson(res, 200, await handleWorkspacePick(body));
    return;
  }
  if (method === "POST" && pathname === "/exec/stream") {
    const body = await readJsonBody(req);
    createExecStream(res, body, req);
    return;
  }
  const execCancelMatch = pathname.match(/^\/exec\/cancel\/([^/]+)$/);
  if (method === "POST" && execCancelMatch) {
    const execId = decodeURIComponent(execCancelMatch[1]);
    const child = execProcesses.get(execId);
    if (!child || child.exitCode !== null) {
      sendJson(res, 200, { ok: false, reason: "not_running" });
      return;
    }
    terminateChild(child);
    sendJson(res, 200, { ok: true });
    return;
  }
  if (method === "POST" && pathname === "/pty/open") {
    const body = await readJsonBody(req);
    sendJson(res, 200, {
      session_id: createPtySession(body),
      native: Boolean(nativePtyModule)
    });
    return;
  }
  const ptyStreamMatch = pathname.match(/^\/pty\/stream\/([^/]+)$/);
  if (method === "GET" && ptyStreamMatch) {
    await streamPtySession(req, res, decodeURIComponent(ptyStreamMatch[1]));
    return;
  }
  const ptyInputMatch = pathname.match(/^\/pty\/input\/([^/]+)$/);
  if (method === "POST" && ptyInputMatch) {
    const sessionId = decodeURIComponent(ptyInputMatch[1]);
    const session = ptySessions.get(sessionId);
    if (!session) {
      throw new HttpError(404, "session not running");
    }
    const body = await readJsonBody(req);
    if (session.mode === "native") {
      session.process.write(String(body.content || ""));
    } else {
      if (session.process.exitCode !== null || session.process.stdin.destroyed) {
        throw new HttpError(404, "session not running");
      }
      session.process.stdin.write(String(body.content || ""), "utf8");
    }
    sendJson(res, 200, { ok: true });
    return;
  }
  const ptyCloseMatch = pathname.match(/^\/pty\/close\/([^/]+)$/);
  if (method === "POST" && ptyCloseMatch) {
    sendJson(res, 200, closePtySession(decodeURIComponent(ptyCloseMatch[1])));
    return;
  }

  sendError(res, 404, "Not found");
}

function parseArgs(argv) {
  const parsed = {
    host: process.env.LOCAL_CONNECTOR_HOST || DEFAULT_HOST,
    port: Number.parseInt(process.env.LOCAL_CONNECTOR_PORT || String(DEFAULT_PORT), 10) || DEFAULT_PORT
  };
  for (let index = 0; index < argv.length; index += 1) {
    const value = argv[index];
    if (value === "--host" && argv[index + 1]) {
      parsed.host = argv[index + 1];
      index += 1;
      continue;
    }
    if (value === "--port" && argv[index + 1]) {
      const portValue = Number.parseInt(argv[index + 1], 10);
      if (Number.isFinite(portValue) && portValue > 0) {
        parsed.port = portValue;
      }
      index += 1;
    }
  }
  return parsed;
}

function canRetryOnPortConflict() {
  const raw = String(process.env.LOCAL_CONNECTOR_ALLOW_PORT_FALLBACK || "1").trim().toLowerCase();
  return !["0", "false", "no", "off"].includes(raw);
}

function listenOnce(server, host, port) {
  return new Promise((resolve, reject) => {
    const cleanup = () => {
      server.off("error", onError);
      server.off("listening", onListening);
    };
    const onError = (error) => {
      cleanup();
      reject(error);
    };
    const onListening = () => {
      cleanup();
      resolve();
    };
    server.once("error", onError);
    server.once("listening", onListening);
    server.listen(port, host);
  });
}

async function findAvailablePort(host, preferredPort) {
  const tried = new Set();
  const candidates = [];
  const preferred = Number.parseInt(String(preferredPort || DEFAULT_PORT), 10) || DEFAULT_PORT;
  candidates.push(preferred);
  for (let offset = 1; offset <= 20; offset += 1) {
    candidates.push(preferred + offset);
  }
  for (const candidate of candidates) {
    if (tried.has(candidate)) {
      continue;
    }
    tried.add(candidate);
    const available = await new Promise((resolve) => {
      const probe = net.createServer();
      probe.once("error", () => {
        resolve(false);
      });
      probe.once("listening", () => {
        probe.close(() => resolve(true));
      });
      probe.listen(candidate, host);
    });
    if (available) {
      return candidate;
    }
  }
  return 0;
}

async function shutdown(server) {
  stopHeartbeatLoop();
  for (const child of execProcesses.values()) {
    terminateChild(child);
  }
  execProcesses.clear();
  for (const sessionId of [...ptySessions.keys()]) {
    closePtySession(sessionId);
  }
  await new Promise((resolve) => {
    server.close(() => resolve());
  });
}

async function main() {
  const args = parseArgs(process.argv.slice(2));
  runtimeHost = String(args.host || DEFAULT_HOST);
  runtimePort = Number.parseInt(String(args.port || DEFAULT_PORT), 10) || DEFAULT_PORT;

  const server = http.createServer((req, res) => {
    void routeRequest(req, res).catch((error) => {
      if (res.writableEnded) {
        return;
      }
      const statusCode = error instanceof HttpError
        ? error.statusCode
        : Number(error && error.statusCode) || 500;
      const message = error instanceof Error ? error.message : String(error);
      sendError(res, statusCode, message);
    });
  });
  httpServer = server;
  try {
    await listenOnce(server, runtimeHost, runtimePort);
  } catch (error) {
    const code = error && error.code ? String(error.code) : "";
    if (code === "EADDRINUSE" && canRetryOnPortConflict()) {
      const fallbackPort = await findAvailablePort(runtimeHost, runtimePort);
      if (!fallbackPort) {
        console.error(`[local-connector] 启动失败：${runtimeBaseUrl()} 已被占用，且未找到可用备用端口`);
        process.exit(1);
        return;
      }
      console.warn(`[local-connector] ${runtimeBaseUrl()} 已被占用，自动切换到 http://${runtimeHost}:${fallbackPort}`);
      runtimePort = fallbackPort;
      await listenOnce(server, runtimeHost, runtimePort);
    } else if (code === "EADDRINUSE") {
      console.error(`[local-connector] 启动失败：${runtimeBaseUrl()} 已被占用`);
      process.exit(1);
      return;
    } else if (code === "EACCES" || code === "EPERM") {
      console.error(`[local-connector] 启动失败：没有权限监听 ${runtimeBaseUrl()}`);
      process.exit(1);
      return;
    } else {
      console.error(`[local-connector] 启动失败：${error instanceof Error ? error.message : String(error)}`);
      process.exit(1);
      return;
    }
  }

  updateState({
    runtime_host: runtimeHost,
    runtime_port: runtimePort,
    runtime_url: runtimeBaseUrl()
  });
  console.log(`[local-connector] listening on ${runtimeBaseUrl()}`);
  void bootstrapPairing();

  process.on("SIGINT", () => {
    void shutdown(server);
  });
  process.on("SIGTERM", () => {
    void shutdown(server);
  });
}

void main();
