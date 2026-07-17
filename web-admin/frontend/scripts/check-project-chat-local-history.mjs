import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const scriptDir = dirname(fileURLToPath(import.meta.url));
const projectChatPath = resolve(
  scriptDir,
  "../src/views/projects/ProjectChat.vue",
);
const storagePath = resolve(
  scriptDir,
  "../src/modules/project-chat/services/projectChatStorage.js",
);
const runtimeStoragePath = resolve(
  scriptDir,
  "../src/modules/project-chat/services/projectChatRuntimeStorage.js",
);
const nativeBridgePath = resolve(
  scriptDir,
  "../src/utils/native-desktop-bridge.js",
);
const sqliteStorePath = resolve(
  scriptDir,
  "../src-tauri/src/project_chat_store.rs",
);
const projectChatSource = readFileSync(projectChatPath, "utf8");
const storageSource = readFileSync(storagePath, "utf8");
const runtimeStorageSource = readFileSync(runtimeStoragePath, "utf8");
const nativeBridgeSource = readFileSync(nativeBridgePath, "utf8");
const sqliteStoreSource = readFileSync(sqliteStorePath, "utf8");

for (const [label, endpointPattern] of [
  ["/chat/sessions", /\/chat\/sessions/],
  ["/chat/runtime", /\/chat\/runtime/],
  ["/chat/history", /\/chat\/history`/],
]) {
  assert.doesNotMatch(
    projectChatSource,
    endpointPattern,
    `project chat must not use remote conversation endpoint ${label}`,
  );
}

assert.ok(
  (projectChatSource.match(/persist_history:\s*false/g) || []).length >= 2,
  "normal and interaction chat requests must disable server history persistence",
);
assert.match(
  storageSource,
  /listNativeProjectChatSessions/,
  "desktop session metadata must be read from SQLite",
);
assert.match(
  storageSource,
  /replaceNativeProjectChatSessions/,
  "desktop session metadata must be written to SQLite",
);
assert.doesNotMatch(
  storageSource,
  /project_chat\.local_sessions|localChatSessionsStorageKey/,
  "chat session metadata must not use localStorage",
);
assert.doesNotMatch(
  runtimeStorageSource,
  /localStorage|QuotaExceededError|本地存储空间不足/,
  "chat runtime must not use localStorage quota fallback",
);
assert.match(
  runtimeStorageSource,
  /writeNativeProjectChatRuntime/,
  "chat runtime must be written through the native SQLite bridge",
);
assert.match(
  nativeBridgeSource,
  /project_chat_write_runtime/,
  "native bridge must expose the SQLite runtime command",
);
assert.match(
  sqliteStoreSource,
  /project-chat\.sqlite3/,
  "desktop chat must use a dedicated SQLite database",
);
assert.match(
  sqliteStoreSource,
  /CREATE TABLE IF NOT EXISTS project_chat_sessions/,
  "SQLite schema must contain chat sessions",
);
assert.match(
  sqliteStoreSource,
  /CREATE TABLE IF NOT EXISTS project_chat_runtimes/,
  "SQLite schema must contain chat runtimes",
);

console.log("project chat local history checks passed");
