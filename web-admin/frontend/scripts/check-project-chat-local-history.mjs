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
const nativeStorePath = resolve(
  scriptDir,
  "../src-tauri/src/project_chat_store.rs",
);
const projectChatSource = readFileSync(projectChatPath, "utf8");
const storageSource = readFileSync(storagePath, "utf8");
const runtimeStorageSource = readFileSync(runtimeStoragePath, "utf8");
const nativeBridgeSource = readFileSync(nativeBridgePath, "utf8");
const nativeStoreSource = readFileSync(nativeStorePath, "utf8");
const activeNativeStoreSource = nativeStoreSource.split("#[cfg(test)]")[0];

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
  "desktop session metadata must be read through the native JSON store",
);
assert.match(
  storageSource,
  /replaceNativeProjectChatSessions/,
  "desktop session metadata must be merged into the same JSON session file",
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
  "chat runtime must be written through the native JSON bridge",
);
assert.match(
  nativeBridgeSource,
  /project_chat_write_runtime/,
  "native bridge must expose the JSON runtime command",
);
assert.match(
  nativeStoreSource,
  /JSON_STORE_DIRECTORY[^\n]*project-chat-data/,
  "desktop chat must use a dedicated JSON data directory",
);
assert.match(
  nativeStoreSource,
  /build_json_envelope/,
  "session metadata and runtime must share one JSON envelope",
);
assert.match(
  nativeStoreSource,
  /build_session_from_runtime/,
  "session lists must be derived from runtime messages",
);
assert.match(
  nativeStoreSource,
  /OpenFlags::SQLITE_OPEN_READ_ONLY[\s\S]*migrate_legacy_sqlite_project/,
  "legacy SQLite data must only be opened read-only for one-time migration",
);
assert.doesNotMatch(
  activeNativeStoreSource,
  /CREATE TABLE IF NOT EXISTS|INSERT INTO project_chat_|DELETE FROM project_chat_|UPDATE project_chat_/,
  "active chat storage must not create or mutate SQLite tables",
);
assert.match(
  projectChatSource,
  /function setProjectChatSessionsMemoryCache/,
  "session reads must have a memory-only cache path",
);
const fetchChatSessionsSource = projectChatSource.match(
  /async function fetchChatSessions\([\s\S]*?\n\}/,
)?.[0] || "";
assert.ok(fetchChatSessionsSource, "project chat must define fetchChatSessions");
assert.doesNotMatch(
  fetchChatSessionsSource,
  /setProjectChatSessionsCache\(/,
  "session reads and load failures must not overwrite JSON session metadata",
);

console.log("project chat local history checks passed");
