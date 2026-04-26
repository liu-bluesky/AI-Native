import api from "@/utils/api.js";

const TASK_STORAGE_KEY = "desktop_tasks";
export const TASKS_UPDATED_EVENT = "desktop-tasks-updated";

function canUseWindow() {
  return typeof window !== "undefined";
}

function createTaskId() {
  const timestamp = Date.now().toString(36);
  const random = Math.random().toString(36).slice(2, 8);
  return `task-${timestamp}-${random}`;
}

function normalizeTrigger(rawTrigger = {}, fallbackType = "manual") {
  const type = String(rawTrigger.type || rawTrigger.trigger_type || fallbackType || "manual").trim();
  const schedule = rawTrigger.schedule && typeof rawTrigger.schedule === "object" ? rawTrigger.schedule : {};
  return {
    id: String(rawTrigger.id || `trigger-${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 6)}`),
    type: ["manual", "event", "schedule"].includes(type) ? type : "manual",
    enabled: rawTrigger.enabled !== false,
    source: String(rawTrigger.source || "").trim(),
    phrases: Array.isArray(rawTrigger.phrases || rawTrigger.trigger_phrases || rawTrigger.triggerPhrases)
      ? (rawTrigger.phrases || rawTrigger.trigger_phrases || rawTrigger.triggerPhrases).map((item) => String(item || "").trim()).filter(Boolean)
      : [],
    schedule: {
      run_at: String(rawTrigger.run_at || rawTrigger.runAt || schedule.run_at || schedule.runAt || "").trim(),
      next_run_at: String(rawTrigger.next_run_at || rawTrigger.nextRunAt || schedule.next_run_at || schedule.nextRunAt || "").trim(),
      interval_seconds: Number(rawTrigger.interval_seconds || rawTrigger.intervalSeconds || schedule.interval_seconds || schedule.intervalSeconds || 0) || 0,
    },
  };
}

function normalizeAction(rawAction = {}) {
  const type = String(rawAction.type || rawAction.action_type || "record").trim();
  return {
    id: String(rawAction.id || `action-${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 6)}`),
    type: ["record", "notify", "system_speech", "project_chat", "file_processing", "webhook"].includes(type) ? type : "record",
    enabled: rawAction.enabled !== false,
    label: String(rawAction.label || rawAction.name || "").trim(),
    params: rawAction.params && typeof rawAction.params === "object" ? rawAction.params : {},
  };
}

function normalizeTask(rawTask = {}) {
  const description = String(rawTask.description || rawTask.title || "").trim();
  const title = String(rawTask.title || description.split(/\n/)[0] || "未命名任务")
    .trim()
    .slice(0, 60) || "未命名任务";
  const status = String(rawTask.status || "todo").trim();
  const createdAt = String(rawTask.createdAt || rawTask.created_at || "").trim() || new Date().toISOString();
  const updatedAt = String(rawTask.updatedAt || rawTask.updated_at || "").trim() || createdAt;
  const triggers = Array.isArray(rawTask.triggers)
    ? rawTask.triggers.map((item) => normalizeTrigger(item)).filter(Boolean)
    : [];
  const legacyTriggerPhrases = Array.isArray(rawTask.trigger_phrases || rawTask.triggerPhrases)
    ? (rawTask.trigger_phrases || rawTask.triggerPhrases).map((item) => String(item || "").trim()).filter(Boolean)
    : [];
  const normalizedTriggers = triggers.length
    ? triggers
    : [
        normalizeTrigger({
          type: "event",
          enabled: rawTask.listen_enabled !== false && rawTask.listenEnabled !== false,
          source: "feishu",
          phrases: legacyTriggerPhrases,
        }, "event"),
      ];
  const actions = Array.isArray(rawTask.actions)
    ? rawTask.actions.map((item) => normalizeAction(item)).filter(Boolean)
    : [normalizeAction({ type: "record", label: "记录任务执行" })];
  const eventTrigger = normalizedTriggers.find((item) => item.type === "event");
  return {
    id: String(rawTask.id || "").trim() || createTaskId(),
    title,
    description,
    status: ["todo", "doing", "done"].includes(status) ? status : "todo",
    source: String(rawTask.source || "manual").trim() || "manual",
    task_type: String(rawTask.task_type || rawTask.taskType || "generic").trim() || "generic",
    listen_enabled: eventTrigger ? eventTrigger.enabled !== false : rawTask.listen_enabled !== false && rawTask.listenEnabled !== false,
    triggerPhrases: eventTrigger ? eventTrigger.phrases : legacyTriggerPhrases,
    triggers: normalizedTriggers,
    actions,
    nextRunAt: String(rawTask.nextRunAt || rawTask.next_run_at || "").trim(),
    lastRunAt: String(rawTask.lastRunAt || rawTask.last_run_at || "").trim(),
    executionCount: Number(rawTask.executionCount || rawTask.execution_count || 0) || 0,
    executionHistory: Array.isArray(rawTask.executionHistory || rawTask.execution_history)
      ? rawTask.executionHistory || rawTask.execution_history
      : [],
    createdAt,
    updatedAt,
  };
}

function readStoredTasks() {
  if (!canUseWindow()) return [];
  try {
    const parsed = JSON.parse(String(window.localStorage.getItem(TASK_STORAGE_KEY) || "[]"));
    if (!Array.isArray(parsed)) return [];
    return parsed.map((item) => normalizeTask(item));
  } catch {
    return [];
  }
}

function sortTasks(tasks = []) {
  return [...tasks].sort((left, right) => {
    const leftTime = new Date(left.createdAt).getTime() || 0;
    const rightTime = new Date(right.createdAt).getTime() || 0;
    return rightTime - leftTime;
  });
}

function writeStoredTasks(tasks = []) {
  if (!canUseWindow()) return [];
  const normalized = sortTasks((Array.isArray(tasks) ? tasks : []).map((item) => normalizeTask(item)));
  window.localStorage.setItem(TASK_STORAGE_KEY, JSON.stringify(normalized));
  window.dispatchEvent(new CustomEvent(TASKS_UPDATED_EVENT, { detail: { tasks: normalized } }));
  return normalized;
}

function mergeTasks(localTasks = [], serverTasks = []) {
  const mergedById = new Map();
  for (const task of Array.isArray(localTasks) ? localTasks : []) {
    const normalized = normalizeTask(task);
    mergedById.set(normalized.id, normalized);
  }
  for (const task of Array.isArray(serverTasks) ? serverTasks : []) {
    const serverTask = normalizeTask(task);
    const localTask = mergedById.get(serverTask.id);
    mergedById.set(
      serverTask.id,
      normalizeTask({
        ...(localTask || {}),
        ...serverTask,
        executionCount: Math.max(Number(localTask?.executionCount || 0), Number(serverTask.executionCount || 0)),
        executionHistory: serverTask.executionHistory?.length ? serverTask.executionHistory : localTask?.executionHistory || [],
        lastRunAt: serverTask.lastRunAt || localTask?.lastRunAt || "",
      }),
    );
  }
  return sortTasks([...mergedById.values()]);
}

function mergeServerTasksIntoStorage(serverTasks = []) {
  if (!canUseWindow()) return [];
  return writeStoredTasks(mergeTasks(readStoredTasks(), serverTasks));
}

function toServerPayload(task = {}) {
  const normalized = normalizeTask(task);
  return {
    id: normalized.id,
    title: normalized.title,
    description: normalized.description,
    status: normalized.status,
    source: normalized.source,
    task_type: normalized.task_type,
    listen_enabled: normalized.listen_enabled !== false,
    trigger_phrases: Array.isArray(normalized.triggerPhrases) ? normalized.triggerPhrases : [],
    triggers: normalized.triggers,
    actions: normalized.actions,
    next_run_at: normalized.nextRunAt,
  };
}

function isTaskConfigurationUpdate(updates = {}) {
  const configurationKeys = new Set([
    "title",
    "description",
    "source",
    "task_type",
    "taskType",
    "listen_enabled",
    "listenEnabled",
    "triggerPhrases",
    "trigger_phrases",
    "triggers",
    "actions",
    "nextRunAt",
    "next_run_at",
  ]);
  return Object.keys(updates || {}).some((key) => configurationKeys.has(key));
}

function syncTaskToServer(task) {
  if (!canUseWindow()) return;
  void api
    .post("/projects/chat/global/tasks", toServerPayload(task))
    .then((response) => {
      if (response?.task) mergeServerTasksIntoStorage([response.task]);
    })
    .catch(() => {});
}

function deleteTaskFromServer(taskId) {
  const targetId = String(taskId || "").trim();
  if (!canUseWindow() || !targetId) return;
  void api.delete(`/projects/chat/global/tasks/${encodeURIComponent(targetId)}`).catch(() => {});
}

export async function syncTasksToServer(tasks = readStoredTasks()) {
  if (!canUseWindow()) return [];
  const normalized = (Array.isArray(tasks) ? tasks : []).map((item) => normalizeTask(item));
  try {
    const response = await api.get("/projects/chat/global/tasks");
    const serverTasks = Array.isArray(response?.tasks) ? response.tasks.map((item) => normalizeTask(item)) : [];
    const serverIds = new Set(serverTasks.map((task) => task.id));
    const localOnlyTasks = normalized.filter((task) => !serverIds.has(task.id));
    const createdResults = await Promise.allSettled(
      localOnlyTasks.map((task) => api.post("/projects/chat/global/tasks", toServerPayload(task))),
    );
    const createdTasks = createdResults
      .map((result) => (result.status === "fulfilled" ? result.value?.task : null))
      .filter(Boolean);
    return writeStoredTasks(mergeTasks(normalized, [...serverTasks, ...createdTasks]));
  } catch {
    return normalized;
  }
}

export function listTasks() {
  return sortTasks(readStoredTasks());
}

export function createTask(input = {}) {
  const task = normalizeTask({
    ...input,
    id: createTaskId(),
    status: input.status || "todo",
    createdAt: new Date().toISOString(),
    updatedAt: new Date().toISOString(),
  });
  writeStoredTasks([task, ...readStoredTasks()]);
  syncTaskToServer(task);
  return task;
}

export function updateTask(taskId, updates = {}) {
  const targetId = String(taskId || "").trim();
  if (!targetId) return null;
  let updatedTask = null;
  const nextTasks = readStoredTasks().map((task) => {
    if (task.id !== targetId) return task;
    if (task.status === "doing" && isTaskConfigurationUpdate(updates)) {
      return task;
    }
    updatedTask = normalizeTask({
      ...task,
      ...updates,
      id: task.id,
      updatedAt: new Date().toISOString(),
    });
    return updatedTask;
  });
  writeStoredTasks(nextTasks);
  if (updatedTask) syncTaskToServer(updatedTask);
  return updatedTask;
}

export function deleteTask(taskId) {
  const targetId = String(taskId || "").trim();
  if (!targetId) return false;
  const tasks = readStoredTasks();
  const nextTasks = tasks.filter((task) => task.id !== targetId);
  if (nextTasks.length === tasks.length) return false;
  writeStoredTasks(nextTasks);
  deleteTaskFromServer(targetId);
  return true;
}

export function parseTaskCreationCommand(text) {
  const rawText = String(text || "").trim();
  if (!rawText) return null;
  const patterns = [
    /^(?:请|请你|帮我|麻烦|你帮我|给我)?(?:创建|新建|添加|新增|记录)(?:一个|一条)?任务[：:\s]+(.+)$/i,
    /^(?:任务)[：:\s]+(.+)$/i,
  ];
  for (const pattern of patterns) {
    const match = rawText.match(pattern);
    const description = String(match?.[1] || "").trim();
    if (description) return { description };
  }
  return null;
}

export function buildTaskTitle(description) {
  const normalized = String(description || "")
    .replace(/\s+/g, " ")
    .trim();
  if (!normalized) return "未命名任务";
  return normalized.length > 32 ? `${normalized.slice(0, 32)}…` : normalized;
}
