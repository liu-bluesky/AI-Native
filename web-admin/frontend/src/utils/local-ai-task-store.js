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

function readTasks() {
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

function writeTasks(tasks) {
  if (!canUseWindow()) return [];
  const normalized = sortTasks((Array.isArray(tasks) ? tasks : []).map((item) => normalizeTask(item)));
  window.localStorage.setItem(LOCAL_AI_TASKS_STORAGE_KEY, JSON.stringify(normalized));
  window.dispatchEvent(new CustomEvent(LOCAL_AI_TASKS_UPDATED_EVENT, { detail: { tasks: normalized } }));
  return normalized;
}

export function listLocalAiTasks(options = {}) {
  const tasks = readTasks();
  return options.activeOnly ? tasks.filter((task) => isLocalAiTaskActive(task)) : tasks;
}

export function getLocalAiTask(taskId) {
  const id = String(taskId || "").trim();
  if (!id) return null;
  return readTasks().find((task) => task.id === id) || null;
}

export function isLocalAiTaskActive(task = {}) {
  return ACTIVE_STATUSES.has(normalizeStatus(task.status));
}

export function registerLocalAiTask(input = {}) {
  const task = normalizeTask({ ...input, status: input.status || "queued", updatedAt: nowIso() });
  const tasks = readTasks();
  const next = tasks.filter((item) => item.id !== task.id);
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
