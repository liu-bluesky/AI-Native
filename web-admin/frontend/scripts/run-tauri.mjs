import { execFileSync, spawn } from "node:child_process";
import { existsSync } from "node:fs";
import { homedir } from "node:os";
import { delimiter, resolve } from "node:path";

const cargoBin = resolve(homedir(), ".cargo", "bin");
const tauriCli = resolve(process.cwd(), "node_modules", "@tauri-apps", "cli", "tauri.js");

function findVsDevCmd() {
  if (process.platform !== "win32") {
    return null;
  }
  const root = process.env["ProgramFiles(x86)"] || "C:\\Program Files (x86)";
  for (const edition of ["BuildTools", "Community", "Professional", "Enterprise"]) {
    const candidate = resolve(root, "Microsoft Visual Studio", "2022", edition, "Common7", "Tools", "VsDevCmd.bat");
    if (existsSync(candidate)) {
      return candidate;
    }
  }
  return null;
}

function loadVsEnvironment() {
  const devCmd = findVsDevCmd();
  if (!devCmd) {
    return {};
  }
  const output = execFileSync(
    "cmd.exe",
    ["/d", "/c", "call", devCmd, "-arch=x64", "-host_arch=x64", "&&", "set"],
    { encoding: "utf8", windowsHide: true },
  );
  const environment = {};
  for (const line of output.split(/\r?\n/)) {
    const separator = line.indexOf("=");
    if (separator > 0) {
      environment[line.slice(0, separator)] = line.slice(separator + 1);
    }
  }
  return environment;
}

const visualStudioEnvironment = loadVsEnvironment();
const pathEntries = [cargoBin, visualStudioEnvironment.PATH, process.env.PATH].filter(Boolean);
const child = spawn(process.execPath, [tauriCli, ...process.argv.slice(2)], {
  cwd: process.cwd(),
  env: {
    ...process.env,
    ...visualStudioEnvironment,
    PATH: pathEntries.join(delimiter),
  },
  stdio: "inherit",
});

child.on("error", (error) => {
  console.error(`Failed to start Tauri CLI: ${error.message}`);
  process.exitCode = 1;
});

child.on("exit", (code, signal) => {
  if (signal) {
    process.kill(process.pid, signal);
    return;
  }
  process.exitCode = code ?? 1;
});