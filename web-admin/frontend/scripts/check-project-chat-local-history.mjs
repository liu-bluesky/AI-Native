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

assert.match(
  projectChatSource,
  /api\.get\([\s\S]*?\/projects\/\$\{encodeURIComponent\(projectId\)\}\/chat\/sessions/,
  "project chat must restore the authoritative remote session list",
);
assert.match(
  projectChatSource,
  /api\.get\([\s\S]*?\/projects\/\$\{encodeURIComponent\(projectId\)\}\/chat\/history/,
  "project chat must restore the authoritative remote history",
);

assert.match(
  projectChatSource,
  /async function sendProjectChatRequest\([\s\S]*?persistHistory = false[\s\S]*?persist_history: Boolean\(persistHistory\)/,
  "normal project chat requests must disable server history persistence by default",
);
assert.match(
  projectChatSource,
  /type: "interaction_submit"[\s\S]*?persist_history: false/,
  "interaction chat requests must disable server history persistence",
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
  /fn runtime_activity_updated_at\([\s\S]*?runtime_message_activity[\s\S]*?existing_session_activity/,
  "runtime-only persistence must preserve the existing conversation activity timestamp",
);
assert.match(
  nativeStoreSource,
  /session_stable_position_at\(right\)[\s\S]*?session_stable_position_at\(left\)[\s\S]*?value_text\(left, &\["id"\]\)/,
  "native session listing must use deterministic creation ordering with an id tie-breaker",
);
assert.match(
  nativeStoreSource,
  /OpenFlags::SQLITE_OPEN_READ_ONLY[\s\S]*migrate_legacy_sqlite_project/,
  "legacy SQLite data must only be opened read-only for one-time migration",
);
assert.match(
  nativeStoreSource,
  /fn migrate_legacy_sqlite_project_paths[\s\S]*?if !legacy_path\.exists\(\)[\s\S]*?if !marker\.exists\(\)/,
  "legacy migration must reconcile SQLite rows even when a previous marker exists",
);
assert.match(
  activeNativeStoreSource,
  /CREATE TABLE IF NOT EXISTS desktop_project_chat_sessions[\s\S]*CREATE TABLE IF NOT EXISTS desktop_project_chat_runtimes/,
  "active desktop chat storage must use the canonical local SQLite tables",
);
assert.match(
  projectChatSource,
  /function setProjectChatSessionsMemoryCache/,
  "session reads must have a memory-only cache path",
);
assert.match(
  projectChatSource,
  /function syncLocalChatSessionMetadata[\s\S]*?messageActivityChanged[\s\S]*?updated_at: messageActivityChanged \? now : current\.updated_at[\s\S]*?sortChatSessionsByStablePosition/,
  "message updates must not move a conversation from its stable sidebar position",
);
assert.match(
  projectChatSource,
  /function normalizeVisibleChatSessions[\s\S]*?sortChatSessionsByStablePosition/,
  "loaded conversation lists must use the same stable creation ordering as live updates",
);
assert.match(
  projectChatSource,
  /sortChatSessionsByStablePosition/,
  "project chat must keep sidebar positions independent from message activity",
);
const fetchChatSessionsSource = projectChatSource.match(
  /async function fetchChatSessions\([\s\S]*?\n\}/,
)?.[0] || "";
assert.ok(fetchChatSessionsSource, "project chat must define fetchChatSessions");
assert.match(
  fetchChatSessionsSource,
  /remoteSessions[\s\S]*?storedSessions[\s\S]*?mergedSessions/,
  "remote and local session metadata must be merged instead of replacing the remote source",
);

const fetchChatHistorySource = projectChatSource.slice(
  projectChatSource.indexOf("async function fetchChatHistory("),
  projectChatSource.indexOf("async function loadOlderMessages("),
);
assert.ok(fetchChatHistorySource, "project chat must define fetchChatHistory");
assert.match(
  projectChatSource,
  /function persistCurrentChatRuntimeBeforeSessionSwitch[\s\S]*?onlyIfDirty: true/,
  "switching conversations must only flush a dirty runtime snapshot",
);
assert.match(
  projectChatSource,
  /const dirtyChatRuntimeSessionKeys = new Set\(\)[\s\S]*?function markChatRuntimeDirty/,
  "chat runtime persistence must track dirty sessions explicitly",
);
assert.match(
  fetchChatHistorySource,
  /getCachedChatRuntime[\s\S]*?getRememberedChatSessionMessages[\s\S]*?chatHistoryLoading\.value = true/,
  "revisited conversations must render cached rows while revalidating remote history",
);
assert.match(
  projectChatSource,
  /async function applyChatMessagesWithoutPersisting[\s\S]*?chatRuntimePersistenceSuppressionDepth/,
  "hydrating history must suppress runtime persistence watchers",
);
assert.match(
  projectChatSource,
  /watch\(\s*messages,[\s\S]*?chatRuntimePersistenceSuppressionDepth > 0[\s\S]*?schedulePersistChatRuntime/,
  "message hydration must not be treated as a new runtime mutation",
);
assert.doesNotMatch(
  fetchChatHistorySource,
  /await restoreInteractiveChatRuntime\(/,
  "interactive runtime recovery must not block history rendering",
);
assert.match(
  fetchChatHistorySource,
  /void restoreInteractiveChatRuntime\([\s\S]*?\.catch\(/,
  "interactive runtime recovery must continue safely in the background",
);

console.log("project chat local history checks passed");
