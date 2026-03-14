"use strict";

const fs = require("node:fs");
const path = require("node:path");

const DESKTOP_ROOT = path.resolve(__dirname, "..");
const CONNECTOR_ROOT = path.resolve(DESKTOP_ROOT, "..");
const RUNTIME_ROOT = path.join(DESKTOP_ROOT, "runtime", "connector");

function ensureDir(targetPath) {
  fs.mkdirSync(targetPath, { recursive: true });
}

function resetDir(targetPath) {
  fs.rmSync(targetPath, { recursive: true, force: true });
  ensureDir(targetPath);
}

function copyPath(sourcePath, targetPath) {
  const stat = fs.statSync(sourcePath);
  if (stat.isDirectory()) {
    fs.cpSync(sourcePath, targetPath, {
      recursive: true,
      force: true,
      dereference: true,
      filter: (src) => {
        const name = path.basename(src);
        return ![".DS_Store", ".connector-state.json"].includes(name);
      }
    });
    return;
  }
  ensureDir(path.dirname(targetPath));
  fs.copyFileSync(sourcePath, targetPath);
}

function main() {
  const copies = [
    "launcher.js",
    "connector_server.js",
    "package.json",
    ".env.example",
    ".gitignore",
    "scripts"
  ];

  resetDir(RUNTIME_ROOT);
  for (const relativePath of copies) {
    const sourcePath = path.join(CONNECTOR_ROOT, relativePath);
    if (!fs.existsSync(sourcePath)) {
      continue;
    }
    const targetPath = path.join(RUNTIME_ROOT, relativePath);
    copyPath(sourcePath, targetPath);
  }
  copyPath(
    path.join(CONNECTOR_ROOT, "node_modules", "@homebridge", "node-pty-prebuilt-multiarch"),
    path.join(RUNTIME_ROOT, "vendor", "@homebridge", "node-pty-prebuilt-multiarch"),
  );
  console.log(`runtime prepared: ${RUNTIME_ROOT}`);
}

main();
