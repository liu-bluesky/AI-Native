import {
  hasNativeDesktopBridge,
  listNativeLocalAiTasks,
  replaceNativeLocalAiTasks,
} from "@/utils/native-desktop-bridge.js";

const LOCAL_AI_TASKS_STORAGE_KEY = "desktop_local_ai_tasks";
export const LOCAL_AI_TASKS_UPDATED_EVENT = "desktop-local-ai-tasks-updated";

const ACTIVE_STATUSES = new Set([
  "queued",
  "running",
  "waiting_approval",
  "waiting_user",
  "reconnecting",
  "cancelling",
  "interrupted",
]);
const COMPLETED_TASK_RETENTION_MS = 7 * 24 * 60 * 60 * 1000;
const MAX_STORED_LOCAL_AI_TASKS = 100;
const LONG_RUNNING_TASK_KIND = "long_running";
const CHAT_TASK_KIND = "chat";
let tasksCache = null;
let nativeTaskWriteQueue = Promise.resolve();

function canUseWindow() {
  return typeof window !== "undefined";
}

function nowIso() {
  return new Date().toISOString();
}

function normalizeStatus(value) {
  const status = String(value || "queued").trim().toLowerCase();
  return [
    "queued",
    "running",
    "waiting_approval",
    "waiting_user",
    "reconnecting",
    "cancelling",
    "interrupted",
    "done",
    "failed",
    "cancelled",
  ].includes(status)
    ? status
    : "queued";
}

function normalizeTaskKind(input = {}) {
  const explicitKind = String(input.taskKind || input.task_kind || "")
    .trim()
    .toLowerCase();
  if (explicitKind === LONG_RUNNING_TASK_KIND) return LONG_RUNNING_TASK_KIND;
  if (explicitKind === CHAT_TASK_KIND) return CHAT_TASK_KIND;
  if (input.isLongTask === true || input.is_long_task === true) {
    return LONG_RUNNING_TASK_KIND;
  }
  const status = normalizeStatus(input.status);
  return input.recoverable === true || ACTIVE_STATUSES.has(status)
    ? LONG_RUNNING_TASK_KIND
    : CHAT_TASK_KIND;
}

function createTaskId(input = {}) {
  const explicitId = String(input.id || input.taskId || input.task_id || "").trim();
  if (explicitId) return explicitId;
  const projectId = String(input.projectId || input.project_id || "global").trim() || "global";
  const sessionId = String(input.chatSessionId || input.chat_session_id || "session").trim() || "session";
  const assistantMessageId = String(
    input.assistantMessageId || input.assistant_message_id || Date.now(),
  ).trim();
  return `local-ai:${projectId}:${sessionId}:${assistantMessageId}`;
}

function normalizeTask(input = {}) {
  const createdAt = String(input.createdAt || input.created_at || "").trim() || nowIso();
  return {
    id: createTaskId(input),
    projectId: String(input.projectId || input.project_id || "").trim(),
    projectName: String(input.projectName || input.project_name || "").trim(),
    chatSessionId: String(input.chatSessionId || input.chat_session_id || "").trim(),
    assistantMessageId: String(
      input.assistantMessageId || input.assistant_message_id || "",
    ).trim(),
    userMessageId: String(input.userMessageId || input.user_message_id || "").trim(),
    title: String(input.title || input.rootGoal || input.root_goal || "本地 AI 任务").trim().slice(0, 120),
    taskKind: normalizeTaskKind(input),
    status: normalizeStatus(input.status),
    currentStep: String(input.currentStep || input.current_step || "").trim().slice(0, 240),
    lastOutput: String(input.lastOutput || input.last_output || "").trim().slice(0, 2000),
    workspacePath: String(input.workspacePath || input.workspace_path || "").trim(),
    statePath: String(input.statePath || input.state_path || "").trim(),
    originWindowId: String(input.originWindowId || input.origin_window_id || "").trim(),
    recoverable: Boolean(input.recoverable),
    source: String(input.source || "tauri_liuagent_local_chat").trim(),
    createdAt,
    updatedAt: String(input.updatedAt || input.updated_at || "").trim() || createdAt,
    completedAt: String(input.completedAt || input.completed_at || "").trim(),
  };
}

function readLegacyTasks() {
  if (!canUseWindow()) return [];
  try {
    const parsed = JSON.parse(window.localStorage.getItem(LOCAL_AI_TASKS_STORAGE_KEY) || "[]");
    return Array.isArray(parsed) ? parsed.map((item) => normalizeTask(item)) : [];
  } catch {
    return [];
  }
}

function sortTasks(tasks) {
  return [...tasks].sort((left, right) => {
    const activeDelta = Number(isLocalAiTaskActive(right)) - Number(isLocalAiTaskActive(left));
    if (activeDelta) return activeDelta;
    return (new Date(right.updatedAt).getTime() || 0) - (new Date(left.updatedAt).getTime() || 0);
  });
}

function normalizeStoredTasks(tasks) {
  const retentionCutoff = Date.now() - COMPLETED_TASK_RETENTION_MS;
  return sortTasks(
    (Array.isArray(tasks) ? tasks : [])
      .map((item) => normalizeTask(item))
      .filter((task) => {
        if (!isLongRunningLocalAiTask(task)) return false;
        if (isLocalAiTaskActive(task)) return true;
        const updatedAt = new Date(task.updatedAt).getTime();
        return !Number.isFinite(updatedAt) || updatedAt >= retentionCutoff;
      }),
  ).slice(0, MAX_STORED_LOCAL_AI_TASKS);
}

function mergeStoredTasks(...taskLists) {
  const merged = new Map();
  for (const task of taskLists.flat()) {
    const normalized = normalizeTask(task);
    const existing = merged.get(normalized.id);
    if (!existing) {
      merged.set(normalized.id, normalized);
      continue;
    }
    const existingUpdatedAt = new Date(existing.updatedAt).getTime() || 0;
    const incomingUpdatedAt = new Date(normalized.updatedAt).getTime() || 0;
    if (incomingUpdatedAt >= existingUpdatedAt) {
      merged.set(normalized.id, normalized);
    }
  }
  return normalizeStoredTasks([...merged.values()]);
}

function emitTasksUpdated(tasks) {
  if (!canUseWindow()) return;
  window.dispatchEvent(new CustomEvent(LOCAL_AI_TASKS_UPDATED_EVENT, { detail: { tasks } }));
}

function removeLegacyTasks() {
  if (!canUseWindow()) return;
  try {
    window.localStorage.removeItem(LOCAL_AI_TASKS_STORAGE_KEY);
  } catch {}
}

function writeLegacyTasks(tasks) {
  if (!canUseWindow()) return;
  try {
    window.localStorage.setItem(LOCAL_AI_TASKS_STORAGE_KEY, JSON.stringify(tasks));
  } catch {}
}

function persistNativeTasks(tasks) {
  nativeTaskWriteQueue = nativeTaskWriteQueue
    .catch(() => undefined)
    .then(() => replaceNativeLocalAiTasks(tasks));
  return nativeTaskWriteQueue;
}

function readTasks() {
  if (tasksCache === null) {
    tasksCache = normalizeStoredTasks(readLegacyTasks());
  }
  return tasksCache;
}

function writeTasks(tasks) {
  const normalized = normalizeStoredTasks(tasks);
  tasksCache = normalized;
  emitTasksUpdated(normalized);
  if (hasNativeDesktopBridge()) {
    void persistNativeTasks(normalized)
      .then((saved) => {
        if (saved === true) removeLegacyTasks();
      })
      .catch(() => writeLegacyTasks(normalized));
  } else if (canUseWindow()) {
    writeLegacyTasks(normalized);
  }
  return normalized;
}

export async function hydrateLocalAiTasks() {
  const legacyTasks = readTasks();
  if (!hasNativeDesktopBridge()) return legacyTasks;
  try {
    const storedTasks = normalizeStoredTasks(await listNativeLocalAiTasks());
    const mergedTasks = mergeStoredTasks(storedTasks, readTasks());
    tasksCache = mergedTasks;
    const saved = await persistNativeTasks(mergedTasks);
    if (saved === true) removeLegacyTasks();
    emitTasksUpdated(mergedTasks);
    return mergedTasks;
  } catch {
    return legacyTasks;
  }
}

export function pruneStoredLocalAiTasks() {
  return writeTasks(readTasks());
}

export function listLocalAiTasks(options = {}) {
  const tasks = readTasks();
  return tasks.filter((task) => {
    if (options.longTaskOnly && !isLongRunningLocalAiTask(task)) return false;
    if (options.activeOnly && !isLocalAiTaskActive(task)) return false;
    return true;
  });
}

export function getLocalAiTask(taskId) {
  const id = String(taskId || "").trim();
  if (!id) return null;
  return readTasks().find((task) => task.id === id) || null;
}

export function isLocalAiTaskActive(task = {}) {
  return ACTIVE_STATUSES.has(normalizeStatus(task.status));
}

export function isLongRunningLocalAiTask(task = {}) {
  return normalizeTaskKind(task) === LONG_RUNNING_TASK_KIND;
}

export function registerLocalAiTask(input = {}) {
  const task = normalizeTask({ ...input, status: input.status || "queued", updatedAt: nowIso() });
  const next = readTasks().filter((item) => item.id !== task.id);
  return writeTasks([task, ...next]).find((item) => item.id === task.id) || task;
}

export function updateLocalAiTask(taskId, updates = {}) {
  const id = String(taskId || "").trim();
  if (!id) return null;
  let updated = null;
  const next = readTasks().map((task) => {
    if (task.id !== id) return task;
    updated = normalizeTask({
      ...task,
      ...updates,
      id,
      updatedAt: nowIso(),
      completedAt: ["done", "failed", "cancelled"].includes(normalizeStatus(updates.status))
        ? nowIso()
        : task.completedAt,
    });
    return updated;
  });
  if (updated) writeTasks(next);
  return updated;
}

export function deleteLocalAiTask(taskId) {
  const id = String(taskId || "").trim();
  if (!id) return false;
  const tasks = readTasks();
  if (!tasks.some((task) => task.id === id)) return false;
  writeTasks(tasks.filter((task) => task.id !== id));
  return true;
}
