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
const nativeListSessionsSource = nativeStoreSource.slice(
  nativeStoreSource.indexOf("fn list_canonical_sessions("),
  nativeStoreSource.indexOf("pub fn project_chat_upsert_session("),
);

assert.match(
  projectChatSource,
  /readLocalChatSessions\(/,
  "project chat must restore the local session list",
);
assert.match(
  projectChatSource,
  /readLocalPersistedChatRuntime\(/,
  "project chat must restore the local runtime history",
);

assert.doesNotMatch(
  projectChatSource,
  /api\.get\([\s\S]*?\/projects\/\$\{encodeURIComponent\(projectId\)\}\/chat\/(?:sessions|history)/,
  "project chat must not restore chat data from the removed backend endpoints",
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
  /upsertNativeProjectChatSession/,
  "desktop session metadata must be persisted one session at a time",
);
assert.doesNotMatch(
  storageSource,
  /replaceNativeProjectChatSessions/,
  "desktop session metadata must not replace the whole project session set",
);
assert.match(
  storageSource,
  /enqueueChatSessionStorageOperation/,
  "desktop session metadata and deletion must share one serialized queue",
);
assert.match(
  storageSource,
  /sessionProjectId !== normalizedProjectId/,
  "desktop session reads and writes must stay within the requested project",
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
  nativeBridgeSource,
  /project_chat_upsert_session/,
  "native bridge must expose single-session metadata upsert",
);
assert.match(
  runtimeStorageSource,
  /deleteLocalChatSession/,
  "runtime deletion must use the serialized local session deletion path",
);
assert.match(
  runtimeStorageSource,
  /isChatSessionDeleted[\s\S]*?writeNativeProjectChatRuntime/,
  "runtime writes must stop after a session has been deleted",
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
  nativeListSessionsSource,
  /WHERE username = \?1 AND project_id = \?2/,
  "native session listing must filter by project",
);
assert.match(
  nativeListSessionsSource,
  /query_map\(params!\[username, project_id\]/,
  "native session listing must bind the requested project",
);
assert.match(
  nativeStoreSource,
  /pub fn project_chat_list_all_sessions\([\s\S]*?list_canonical_sessions\(&app, &username, None\)/,
  "offline project discovery must have an explicit all-session listing command",
);
assert.match(
  nativeStoreSource,
  /fn normalized_session_project_id[\s\S]*?会话项目 ID 与请求项目 ID 不一致/,
  "native session writes must reject cross-project payloads",
);
assert.match(
  nativeStoreSource,
  /transaction\(\)[\s\S]*?DELETE FROM desktop_project_chat_sessions[\s\S]*?DELETE FROM desktop_project_chat_runtimes[\s\S]*?transaction\.commit/,
  "native session deletion must remove metadata and runtime atomically",
);
assert.match(
  nativeStoreSource,
  /fn runtime_activity_updated_at\([\s\S]*?runtime_message_activity[\s\S]*?existing_session_activity/,
  "runtime-only persistence must preserve the existing conversation activity timestamp",
);
assert.match(
  nativeStoreSource,
  /replace_messages[\s\S]*?merged\.insert\([\s\S]*?"messages"[\s\S]*?incoming_messages[\s\S]*?merged\.remove\("replace_messages"\)/,
  "authoritative message replacement must remove deleted messages without persisting the control flag",
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
  /function rememberCachedChatRuntime[\s\S]*?isChatSessionDeleted/,
  "deleted conversations must not re-enter the runtime cache",
);
assert.match(
  projectChatSource,
  /function buildPersistedChatRuntimePayload\([\s\S]*?replace_messages: true/,
  "chat runtime payloads must support an explicit authoritative message replacement",
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
  /const dirtyChatRuntimeSessionKeys = getProjectChatSessionDirtyKeys\(\)[\s\S]*?function markChatRuntimeDirty/,
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
const deleteChatSessionSource = projectChatSource.slice(
  projectChatSource.indexOf("async function deleteChatSession("),
  projectChatSource.indexOf("async function clearMessages("),
);
assert.match(
  deleteChatSessionSource,
  /markChatSessionDeleted\(projectId, chatSessionId\)[\s\S]*?clearPersistedChatRuntime\(projectId, chatSessionId\)[\s\S]*?removeChatSessionFromVisibleState\(projectId, chatSessionId\)/,
  "deleting one conversation must tombstone and delete only that session",
);
assert.doesNotMatch(
  deleteChatSessionSource,
  /setProjectChatSessionsCache\(/,
  "deleting one conversation must not replace the whole persisted session list",
);
const clearMessagesSource = projectChatSource.slice(
  projectChatSource.indexOf("async function clearMessages("),
  projectChatSource.indexOf("function isIntentOnlyReply("),
);
assert.doesNotMatch(
  clearMessagesSource,
  /setProjectChatSessionsCache\(/,
  "clearing one conversation must not replace the whole persisted session list",
);
assert.match(
  projectChatSource,
  /markChatSessionDeleted\(projectId, chatSessionId\)[\s\S]*?messages\.value = \[\]/,
  "clearing a conversation must tombstone before reactive runtime cleanup",
);
const deleteMessageSource = projectChatSource.slice(
  projectChatSource.indexOf("async function deleteMessageAt("),
  projectChatSource.indexOf("async function openInlineMessageEditor("),
);
assert.match(
  deleteMessageSource,
  /await persistCurrentChatRuntimeNow\([\s\S]*?replaceMessages: false[\s\S]*?deletedMessageIds/,
  "message deletion must await a tombstone-aware runtime write",
);
assert.match(
  deleteMessageSource,
  /if \(saved !== true\)[\s\S]*?messages\.value = previousMessages/,
  "message deletion must restore the visible state when persistence fails",
);
const deleteTargetSource = projectChatSource.slice(
  projectChatSource.indexOf("function resolveDeleteTarget("),
  projectChatSource.indexOf("function getDeleteActionTooltip("),
);
assert.match(
  deleteTargetSource,
  /mode: "round"[\s\S]*?startIndex[\s\S]*?endIndex[\s\S]*?messageIds/,
  "message deletion must target one conversation round",
);
const localDeleteSource = projectChatSource.slice(
  projectChatSource.indexOf("function applyDeleteTargetLocally("),
  projectChatSource.indexOf("function buildDeleteSuccessText("),
);
assert.doesNotMatch(
  localDeleteSource,
  /messages\.value\s*=\s*messages\.value\.slice\(0,\s*sliceIndex\)/,
  "message deletion must not truncate all following rounds",
);
assert.match(
  projectChatSource,
  /function persistedRuntimeDeletedMessageIds\([\s\S]*?function filterDeletedPersistedRows[\s\S]*?function applyPersistedChatRuntimeRows/,
  "history hydration must filter locally deleted message tombstones",
);
assert.match(
  projectChatSource,
  /readPersistedChatRuntime\([\s\S]*?rememberCachedChatRuntime[\s\S]*?fullRows/,
  "message mutations must refresh the runtime cache from the native merged snapshot",
);

console.log("project chat local history checks passed");
