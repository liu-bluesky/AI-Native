"use strict";

const fs = require("node:fs");
const path = require("node:path");
const http = require("node:http");
const net = require("node:net");
const { spawn } = require("node:child_process");

const ROOT_DIR = path.resolve(process.env.LOCAL_CONNECTOR_APP_ROOT || __dirname);
const DATA_DIR = path.resolve(process.env.LOCAL_CONNECTOR_DATA_DIR || ROOT_DIR);
const LOG_DIR = path.join(DATA_DIR, "logs");
const BOOTSTRAP_LOG = path.join(LOG_DIR, "bootstrap.log");
const CONNECTOR_LOG = path.join(LOG_DIR, "connector.log");
const STATE_FILE = path.join(DATA_DIR, ".connector-state.json");
const DEFAULT_HOST = process.env.LOCAL_CONNECTOR_HOST || "127.0.0.1";
const DEFAULT_PORT = String(process.env.LOCAL_CONNECTOR_PORT || "3931");
const PRIMARY_VENDOR_PTY_DIR = path.join(ROOT_DIR, "vendor", "@homebridge", "node-pty-prebuilt-multiarch");
const FALLBACK_VENDOR_PTY_DIR = path.join(ROOT_DIR, "vendor", "node-pty");
const PRIMARY_PTY_PACKAGE_DIR = path.join(ROOT_DIR, "node_modules", "@homebridge", "node-pty-prebuilt-multiarch");
const FALLBACK_PTY_PACKAGE_DIR = path.join(ROOT_DIR, "node_modules", "node-pty");
const AUTO_INSTALL_DISABLED = String(process.env.LOCAL_CONNECTOR_DISABLE_AUTO_INSTALL || "").trim() === "1";
let activeServerProcess = null;

function ensureDir(dirPath) {
  fs.mkdirSync(dirPath, { recursive: true });
}

function appendLog(filePath, text) {
  ensureDir(path.dirname(filePath));
  fs.appendFileSync(filePath, text, "utf8");
}

function printStep(message) {
  console.log(`[launcher] ${message}`);
}

function npmCommand() {
  return process.platform === "win32" ? "npm.cmd" : "npm";
}

function ensureNodeRuntime() {
  const major = Number.parseInt(String(process.versions.node || "0").split(".")[0], 10) || 0;
  if (major < 18) {
    throw new Error(`Node.js 版本过低，当前为 ${process.versions.node}，请安装 Node.js 18 或更高版本`);
  }
}

function hasRuntimeDependencies() {
  return (
    fs.existsSync(PRIMARY_VENDOR_PTY_DIR) ||
    fs.existsSync(FALLBACK_VENDOR_PTY_DIR) ||
    fs.existsSync(PRIMARY_PTY_PACKAGE_DIR) ||
    fs.existsSync(FALLBACK_PTY_PACKAGE_DIR)
  );
}

async function runChecked(command, args, options = {}) {
  appendLog(BOOTSTRAP_LOG, `\n$ ${[command, ...args].join(" ")}\n`);
  const child = spawn(command, args, {
    cwd: ROOT_DIR,
    env: {
      ...process.env,
      LOCAL_CONNECTOR_APP_ROOT: ROOT_DIR,
      LOCAL_CONNECTOR_DATA_DIR: DATA_DIR,
      npm_config_update_notifier: "false",
      ...(options.env || {})
    },
    stdio: ["ignore", "pipe", "pipe"]
  });
  child.stdout.setEncoding("utf8");
  child.stderr.setEncoding("utf8");
  child.stdout.on("data", (chunk) => {
    const text = String(chunk || "");
    process.stdout.write(text);
    appendLog(BOOTSTRAP_LOG, text);
  });
  child.stderr.on("data", (chunk) => {
    const text = String(chunk || "");
    process.stderr.write(text);
    appendLog(BOOTSTRAP_LOG, text);
  });
  const exitCode = await new Promise((resolve, reject) => {
    child.once("error", reject);
    child.once("exit", (code) => resolve(code ?? 0));
  });
  if (exitCode !== 0) {
    throw new Error(`command failed with exit code ${exitCode}: ${[command, ...args].join(" ")}`);
  }
}

async function ensureDependencies() {
  if (hasRuntimeDependencies()) {
    return;
  }
  if (AUTO_INSTALL_DISABLED) {
    throw new Error("桌面安装包缺少运行依赖，请重新打包安装版，不应在用户电脑上执行 npm install");
  }
  printStep("首次启动，正在安装 Node 运行依赖，这一步会稍慢一些...");
  printStep("依赖安装完成后会自动启用真实终端能力。");
  await runChecked(npmCommand(), ["install", "--omit=dev"]);
}

function wait(ms) {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

function httpGetJson(url) {
  return new Promise((resolve, reject) => {
    const req = http.get(url, (res) => {
      let raw = "";
      res.setEncoding("utf8");
      res.on("data", (chunk) => {
        raw += chunk;
      });
      res.on("end", () => {
        if (res.statusCode !== 200) {
          reject(new Error(`HTTP ${res.statusCode || 0}`));
          return;
        }
        try {
          resolve(JSON.parse(raw || "{}"));
        } catch (error) {
          reject(error);
        }
      });
    });
    req.on("error", reject);
    req.setTimeout(1500, () => req.destroy(new Error("timeout")));
  });
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

function resolveRuntimeUrl(host, port) {
  const state = loadState();
  return String(state.runtime_url || `http://${host}:${port}`).trim();
}

function checkPortAvailable(host, port) {
  return new Promise((resolve) => {
    const server = net.createServer();
    server.once("error", () => resolve(false));
    server.once("listening", () => {
      server.close(() => resolve(true));
    });
    server.listen(port, host);
  });
}

async function resolveLaunchPort(host, preferredPort) {
  const parsedPreferred = Number.parseInt(String(preferredPort || DEFAULT_PORT), 10) || 3931;
  if (await checkPortAvailable(host, parsedPreferred)) {
    return parsedPreferred;
  }
  for (let offset = 1; offset <= 20; offset += 1) {
    const candidate = parsedPreferred + offset;
    if (await checkPortAvailable(host, candidate)) {
      return candidate;
    }
  }
  return 0;
}

function openUrl(targetUrl) {
  try {
    if (process.platform === "win32") {
      const child = spawn("cmd", ["/c", "start", "", targetUrl], {
        detached: true,
        stdio: "ignore"
      });
      child.unref();
      return;
    }
    if (process.platform === "darwin") {
      const child = spawn("open", [targetUrl], {
        detached: true,
        stdio: "ignore"
      });
      child.unref();
      return;
    }
    const child = spawn("xdg-open", [targetUrl], {
      detached: true,
      stdio: "ignore"
    });
    child.unref();
  } catch (_error) {
    // ignore opener failures
  }
}

async function waitAndOpenStatusPage(statusUrl) {
  for (let index = 0; index < 40; index += 1) {
    const runtimeUrl = resolveRuntimeUrl(
      new URL(statusUrl).hostname,
      new URL(statusUrl).port || "3931"
    );
    try {
      const payload = await httpGetJson(`${runtimeUrl}/health`);
      if (payload && payload.ok) {
        openUrl(runtimeUrl);
        return;
      }
    } catch (_error) {
      // ignore until timeout
    }
    await wait(500);
  }
}

async function runServer() {
  const host = String(process.env.LOCAL_CONNECTOR_HOST || DEFAULT_HOST || "127.0.0.1");
  const preferredPort = String(process.env.LOCAL_CONNECTOR_PORT || DEFAULT_PORT || "3931");
  const resolvedPort = await resolveLaunchPort(host, preferredPort);
  if (!resolvedPort) {
    throw new Error(`未找到可用端口。默认端口 ${preferredPort} 已占用，连续 20 个备用端口也不可用`);
  }
  if (String(resolvedPort) !== String(preferredPort)) {
    printStep(`检测到 ${host}:${preferredPort} 已被占用，自动切换到 ${host}:${resolvedPort}`);
  }
  const port = String(resolvedPort);
  const statusUrl = `http://${host}:${port}`;
  const env = {
    ...process.env,
    LOCAL_CONNECTOR_APP_ROOT: ROOT_DIR,
    LOCAL_CONNECTOR_DATA_DIR: DATA_DIR,
    LOCAL_CONNECTOR_HOST: host,
    LOCAL_CONNECTOR_PORT: port
  };

  ensureDir(LOG_DIR);
  printStep(`本地状态页: ${statusUrl}`);
  printStep(`启动日志: ${CONNECTOR_LOG}`);
  printStep("当前版本为 Node 连接器，无需 Python 虚拟环境。");
  printStep("连接器启动后会自动打开本地状态页，用来查看配对和在线状态。");

  appendLog(CONNECTOR_LOG, `\n=== Local Connector Start ===\n${new Date().toISOString()}\n`);
  void waitAndOpenStatusPage(statusUrl);

  const child = spawn(process.execPath, [path.join(ROOT_DIR, "connector_server.js"), "--host", host, "--port", port], {
    cwd: ROOT_DIR,
    env,
    stdio: ["ignore", "pipe", "pipe"]
  });

  child.stdout.setEncoding("utf8");
  child.stderr.setEncoding("utf8");
  child.stdout.on("data", (chunk) => {
    const text = String(chunk || "");
    process.stdout.write(text);
    appendLog(CONNECTOR_LOG, text);
  });
  child.stderr.on("data", (chunk) => {
    const text = String(chunk || "");
    process.stderr.write(text);
    appendLog(CONNECTOR_LOG, text);
  });

  activeServerProcess = child;
  return child;
}

function stopServerProcess() {
  const child = activeServerProcess;
  activeServerProcess = null;
  if (!child || child.exitCode !== null || child.killed) {
    return;
  }
  try {
    child.kill("SIGTERM");
  } catch (_error) {
    // ignore
  }
}

async function main() {
  console.log("Local Connector Launcher");
  console.log("========================");
  console.log(`程序目录: ${ROOT_DIR}`);
  console.log(`数据目录: ${DATA_DIR}`);
  console.log(`Bootstrap 日志: ${BOOTSTRAP_LOG}`);
  try {
    ensureDir(DATA_DIR);
    ensureDir(LOG_DIR);
    appendLog(BOOTSTRAP_LOG, `\n=== Launcher Start ===\n${new Date().toISOString()}\n`);
    ensureNodeRuntime();
    printStep(`Node.js 运行时已就绪: ${process.versions.node}`);
    await ensureDependencies();
    printStep("正在启动连接器服务...");
    const child = await runServer();
    const exitCode = await new Promise((resolve, reject) => {
      child.once("error", reject);
      child.once("exit", (code) => {
        if (activeServerProcess === child) {
          activeServerProcess = null;
        }
        resolve(code ?? 0);
      });
    });
    if (exitCode !== 0) {
      throw new Error(`连接器服务异常退出，退出码 ${exitCode}`);
    }
    return 0;
  } catch (error) {
    const message = error instanceof Error ? error.message : String(error);
    console.error(`\n[launcher] 启动失败: ${message}`);
    console.error(`[launcher] 请查看日志: ${BOOTSTRAP_LOG}`);
    appendLog(BOOTSTRAP_LOG, `[launcher] 启动失败: ${message}\n`);
    return 1;
  }
}

void main().then((code) => {
  process.exitCode = code;
});

process.on("SIGINT", () => {
  stopServerProcess();
});

process.on("SIGTERM", () => {
  stopServerProcess();
});

process.on("exit", () => {
  stopServerProcess();
});
