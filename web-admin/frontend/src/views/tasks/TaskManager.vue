<template>
  <section class="task-manager">
    <div class="task-manager__ambient" aria-hidden="true" />
    <header class="task-manager__hero">
      <div>
        <span class="task-manager__eyebrow">Task Center</span>
        <h1>任务</h1>
        <p>从系统状态助手输入“创建任务 + 描述”，也可以在这里手动添加、推进和完成任务。</p>
      </div>
      <div class="task-manager__stats">
        <span><strong>{{ taskStats.todo }}</strong>待处理</span>
        <span><strong>{{ taskStats.doing }}</strong>进行中</span>
        <span><strong>{{ taskStats.done }}</strong>已完成</span>
      </div>
    </header>

    <form class="task-manager__composer" @submit.prevent="submitTask">
      <textarea
        v-model="draftText"
        rows="3"
        placeholder="描述一个任务，例如：明天上午整理飞书群消息发送流程"
      />
      <div class="task-manager__composer-grid">
        <label>
          <span>任务类型</span>
          <select v-model="draftTaskType">
            <option v-for="item in taskTypeOptions" :key="item.value" :value="item.value">
              {{ item.label }}
            </option>
          </select>
        </label>
        <label>
          <span>触发关键词</span>
          <input v-model="draftTriggerText" placeholder="多个关键词用逗号分隔" />
        </label>
        <label>
          <span>执行动作</span>
          <select v-model="draftActionType">
            <option v-for="item in actionTypeOptions" :key="item.value" :value="item.value">
              {{ item.label }}
            </option>
          </select>
        </label>
        <label>
          <span>计划时间</span>
          <input v-model="draftRunAt" type="datetime-local" />
        </label>
      </div>
      <div class="task-manager__composer-footer">
        <span>任务会同步到后端；有关键词会监听事件，有计划时间会进入后台调度。</span>
        <button type="submit" :disabled="!canSubmitTask">创建任务</button>
      </div>
    </form>

    <div class="task-manager__toolbar">
      <button
        v-for="item in statusFilters"
        :key="item.value"
        type="button"
        :class="{ 'is-active': activeFilter === item.value }"
        @click="activeFilter = item.value"
      >
        {{ item.label }}
      </button>
    </div>

    <div v-if="!filteredTasks.length" class="task-manager__empty">
      <strong>暂无任务</strong>
      <span>试试在系统状态助手里输入：创建任务 跟进今天的客户反馈。</span>
    </div>

    <div v-else class="task-manager__list">
      <article
        v-for="task in filteredTasks"
        :key="task.id"
        class="task-card"
        :class="[`is-${task.status}`, { 'is-disabled': !isTaskEnabled(task) }]"
      >
        <div class="task-card__main">
          <div class="task-card__head">
            <span class="task-card__status">{{ statusLabel(task.status) }}</span>
            <span class="task-card__source">{{ sourceLabel(task.source) }}</span>
            <span
              class="task-card__enabled"
              :class="{ 'is-disabled': !isTaskEnabled(task) }"
            >
              {{ isTaskEnabled(task) ? "已启用" : "已停用" }}
            </span>
          </div>
          <h2>{{ task.title }}</h2>
          <p>{{ task.description }}</p>
          <div class="task-card__meta">
            <span>{{ taskTypeLabel(task.task_type) }}</span>
            <span>{{ actionLabel(task.actions?.[0]?.type) }}</span>
            <span>执行 {{ task.executionCount || 0 }} 次</span>
            <span v-if="task.nextRunAt">下次 {{ formatTaskTime(task.nextRunAt) }}</span>
          </div>
          <div v-if="task.triggerPhrases?.length" class="task-card__phrases">
            <span v-for="phrase in task.triggerPhrases" :key="phrase">{{ phrase }}</span>
          </div>
          <time>{{ formatTaskTime(task.createdAt) }}</time>
        </div>
        <div class="task-card__actions">
          <button
            type="button"
            :class="isTaskEnabled(task) ? 'is-muted' : 'is-enable'"
            :disabled="!canEditTask(task)"
            :title="canEditTask(task) ? '' : '进行中的任务不允许修改启停状态'"
            @click="toggleTaskEnabled(task)"
          >
            {{ isTaskEnabled(task) ? "停用" : "启用" }}
          </button>
          <button
            type="button"
            :disabled="!canEditTask(task)"
            :title="canEditTask(task) ? '编辑任务' : '进行中的任务不允许编辑'"
            @click="startEditTask(task)"
          >
            编辑
          </button>
          <button type="button" @click="setTaskStatus(task, 'todo')">待处理</button>
          <button type="button" @click="setTaskStatus(task, 'doing')">进行中</button>
          <button type="button" @click="setTaskStatus(task, 'done')">完成</button>
          <button type="button" class="is-danger" @click="removeTask(task)">删除</button>
        </div>
      </article>
    </div>

    <div v-if="editingTaskId" class="task-manager__modal">
      <div class="task-manager__modal-backdrop" aria-hidden="true" @click="cancelEditTask" />
      <form
        class="task-manager__editor"
        role="dialog"
        aria-modal="true"
        aria-labelledby="task-edit-title"
        @submit.prevent="saveEditedTask"
      >
        <div class="task-manager__editor-head">
          <div>
            <span class="task-manager__eyebrow">Edit Task</span>
            <h2 id="task-edit-title">编辑任务</h2>
          </div>
          <button type="button" class="is-icon" aria-label="关闭编辑弹框" @click="cancelEditTask">
            <span aria-hidden="true">×</span>
          </button>
        </div>
        <textarea
          v-model="editText"
          rows="3"
          placeholder="更新任务描述"
        />
        <div class="task-manager__composer-grid">
          <label>
            <span>任务类型</span>
            <select v-model="editTaskType">
              <option v-for="item in taskTypeOptions" :key="item.value" :value="item.value">
                {{ item.label }}
              </option>
            </select>
          </label>
          <label>
            <span>触发关键词</span>
            <input v-model="editTriggerText" placeholder="多个关键词用逗号分隔" />
          </label>
          <label>
            <span>执行动作</span>
            <select v-model="editActionType">
              <option v-for="item in actionTypeOptions" :key="item.value" :value="item.value">
                {{ item.label }}
              </option>
            </select>
          </label>
          <label>
            <span>计划时间</span>
            <input v-model="editRunAt" type="datetime-local" />
          </label>
        </div>
        <div class="task-manager__modal-actions">
          <span>进行中的任务不允许编辑；可先将任务退回待处理或完成后再调整。</span>
          <div>
            <button type="button" class="is-muted" @click="cancelEditTask">取消</button>
            <button type="submit" :disabled="!canSaveEditedTask">保存修改</button>
          </div>
        </div>
      </form>
    </div>
  </section>
</template>

<script setup>
import { computed, onBeforeUnmount, onMounted, ref } from "vue";
import {
  TASKS_UPDATED_EVENT,
  buildTaskTitle,
  createTask,
  deleteTask,
  listTasks,
  syncTasksToServer,
  updateTask,
} from "@/utils/task-store.js";

const tasks = ref([]);
const draftText = ref("");
const draftTaskType = ref("generic");
const draftTriggerText = ref("");
const draftActionType = ref("record");
const draftRunAt = ref("");
const editingTaskId = ref("");
const editText = ref("");
const editTaskType = ref("generic");
const editTriggerText = ref("");
const editActionType = ref("record");
const editRunAt = ref("");
const activeFilter = ref("all");
const statusFilters = [
  { label: "全部", value: "all" },
  { label: "待处理", value: "todo" },
  { label: "进行中", value: "doing" },
  { label: "已完成", value: "done" },
];
const taskTypeOptions = [
  { label: "通用任务", value: "generic" },
  { label: "消息监听", value: "message_listener" },
  { label: "文件处理", value: "file_processing" },
  { label: "工作流", value: "workflow" },
  { label: "提醒", value: "reminder" },
];
const actionTypeOptions = [
  { label: "记录执行", value: "record" },
  { label: "通知", value: "notify" },
  { label: "系统播报", value: "system_speech" },
  { label: "项目对话", value: "project_chat" },
  { label: "文件处理", value: "file_processing" },
];

const canSubmitTask = computed(() => Boolean(String(draftText.value || "").trim()));
const editingTask = computed(() => tasks.value.find((task) => task.id === editingTaskId.value) || null);
const canSaveEditedTask = computed(() => {
  const task = editingTask.value;
  return Boolean(task && canEditTask(task) && String(editText.value || "").trim());
});
const filteredTasks = computed(() => {
  if (activeFilter.value === "all") return tasks.value;
  return tasks.value.filter((task) => task.status === activeFilter.value);
});
const taskStats = computed(() =>
  tasks.value.reduce(
    (result, task) => ({
      ...result,
      [task.status]: Number(result[task.status] || 0) + 1,
    }),
    { todo: 0, doing: 0, done: 0 },
  ),
);

function refreshTasks() {
  tasks.value = listTasks();
}

function submitTask() {
  const description = String(draftText.value || "").trim();
  if (!description) return;
  const payload = buildTaskPayloadFromForm({
    description,
    taskType: draftTaskType.value,
    triggerText: draftTriggerText.value,
    actionType: draftActionType.value,
    runAtValue: draftRunAt.value,
  });
  createTask({
    ...payload,
    source: "tasks-module",
  });
  draftText.value = "";
  draftTaskType.value = "generic";
  draftTriggerText.value = "";
  draftActionType.value = "record";
  draftRunAt.value = "";
  refreshTasks();
}

function buildTaskPayloadFromForm({ description, taskType, triggerText, actionType, runAtValue }) {
  const triggerPhrases = String(triggerText || "")
    .split(/[,，\n]/)
    .map((item) => item.trim())
    .filter(Boolean);
  const runAt = runAtValue ? new Date(runAtValue).toISOString() : "";
  const triggers = [
    {
      type: "event",
      enabled: triggerPhrases.length > 0,
      source: "feishu",
      phrases: triggerPhrases,
    },
  ];
  if (runAt) {
    triggers.push({
      type: "schedule",
      enabled: true,
      schedule: {
        run_at: runAt,
        next_run_at: runAt,
        interval_seconds: 0,
      },
    });
  }
  return {
    title: buildTaskTitle(description),
    description,
    task_type: taskType,
    listen_enabled: triggerPhrases.length > 0 || Boolean(runAt),
    triggerPhrases,
    triggers,
    actions: [{ type: actionType, enabled: true }],
    nextRunAt: runAt,
  };
}

function setTaskStatus(task, status) {
  updateTask(task.id, { status });
  refreshTasks();
}

function canEditTask(task) {
  return String(task?.status || "todo") !== "doing";
}

function toDatetimeLocalValue(value) {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "";
  const localDate = new Date(date.getTime() - date.getTimezoneOffset() * 60_000);
  return localDate.toISOString().slice(0, 16);
}

function taskRunAtValue(task) {
  if (task?.nextRunAt) return toDatetimeLocalValue(task.nextRunAt);
  const scheduleTrigger = Array.isArray(task?.triggers)
    ? task.triggers.find((trigger) => trigger?.type === "schedule")
    : null;
  return toDatetimeLocalValue(scheduleTrigger?.schedule?.next_run_at || scheduleTrigger?.schedule?.run_at || "");
}

function startEditTask(task) {
  if (!canEditTask(task)) {
    window.alert("进行中的任务不允许编辑");
    return;
  }
  editingTaskId.value = task.id;
  editText.value = String(task.description || task.title || "").trim();
  editTaskType.value = String(task.task_type || "generic");
  editTriggerText.value = Array.isArray(task.triggerPhrases) ? task.triggerPhrases.join("，") : "";
  editActionType.value = String(task.actions?.[0]?.type || "record");
  editRunAt.value = taskRunAtValue(task);
}

function cancelEditTask() {
  editingTaskId.value = "";
  editText.value = "";
  editTaskType.value = "generic";
  editTriggerText.value = "";
  editActionType.value = "record";
  editRunAt.value = "";
}

function saveEditedTask() {
  const task = editingTask.value;
  if (!task) return;
  if (!canEditTask(task)) {
    window.alert("进行中的任务不允许编辑");
    cancelEditTask();
    return;
  }
  const description = String(editText.value || "").trim();
  if (!description) return;
  updateTask(
    task.id,
    buildTaskPayloadFromForm({
      description,
      taskType: editTaskType.value,
      triggerText: editTriggerText.value,
      actionType: editActionType.value,
      runAtValue: editRunAt.value,
    }),
  );
  cancelEditTask();
  refreshTasks();
}

function isTaskEnabled(task) {
  if (Array.isArray(task.triggers) && task.triggers.length) {
    return task.triggers.some((trigger) => trigger?.enabled !== false);
  }
  return task.listen_enabled !== false;
}

function toggleTaskEnabled(task) {
  if (!canEditTask(task)) {
    window.alert("进行中的任务不允许编辑");
    return;
  }
  const nextEnabled = !isTaskEnabled(task);
  const triggers = Array.isArray(task.triggers)
    ? task.triggers.map((trigger) => ({ ...trigger, enabled: nextEnabled }))
    : [];
  updateTask(task.id, {
    listen_enabled: nextEnabled,
    triggers,
  });
  refreshTasks();
}

function removeTask(task) {
  if (!window.confirm(`确定删除任务“${task.title}”？`)) return;
  deleteTask(task.id);
  refreshTasks();
}

function statusLabel(status) {
  if (status === "doing") return "进行中";
  if (status === "done") return "已完成";
  return "待处理";
}

function sourceLabel(source) {
  if (source === "global-assistant") return "系统状态助手";
  return "任务模块";
}

function taskTypeLabel(type) {
  return taskTypeOptions.find((item) => item.value === type)?.label || "通用任务";
}

function actionLabel(type) {
  return actionTypeOptions.find((item) => item.value === type)?.label || "记录执行";
}

function formatTaskTime(value) {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "刚刚";
  return new Intl.DateTimeFormat("zh-CN", {
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
  }).format(date);
}

function handleTasksUpdated() {
  refreshTasks();
}

function handleEditorKeydown(event) {
  if (event.key === "Escape" && editingTaskId.value) {
    cancelEditTask();
  }
}

onMounted(() => {
  refreshTasks();
  void syncTasksToServer(tasks.value);
  window.addEventListener(TASKS_UPDATED_EVENT, handleTasksUpdated);
  window.addEventListener("keydown", handleEditorKeydown);
});

onBeforeUnmount(() => {
  window.removeEventListener(TASKS_UPDATED_EVENT, handleTasksUpdated);
  window.removeEventListener("keydown", handleEditorKeydown);
});
</script>

<style scoped>
.task-manager {
  position: relative;
  min-height: 100%;
  padding: 30px;
  overflow: hidden;
  color: #0f172a;
  background:
    radial-gradient(circle at 14% 4%, rgba(56, 189, 248, 0.18), transparent 30%),
    linear-gradient(180deg, rgba(248, 250, 252, 0.96), rgba(241, 245, 249, 0.92));
}

.task-manager__ambient {
  position: absolute;
  inset: auto -120px -180px auto;
  width: 360px;
  height: 360px;
  border-radius: 999px;
  background: rgba(37, 99, 235, 0.14);
  filter: blur(12px);
  pointer-events: none;
}

.task-manager__hero,
.task-manager__composer,
.task-manager__toolbar,
.task-card,
.task-manager__empty {
  position: relative;
  z-index: 1;
}

.task-manager__hero {
  display: flex;
  justify-content: space-between;
  gap: 20px;
  align-items: flex-start;
  margin-bottom: 22px;
}

.task-manager__eyebrow {
  display: inline-flex;
  margin-bottom: 8px;
  color: #2563eb;
  font-size: 12px;
  font-weight: 800;
  letter-spacing: 0.16em;
  text-transform: uppercase;
}

.task-manager h1 {
  margin: 0;
  font-size: 34px;
  letter-spacing: -0.04em;
}

.task-manager p {
  margin: 8px 0 0;
  color: #64748b;
  line-height: 1.7;
}

.task-manager__stats {
  display: grid;
  grid-template-columns: repeat(3, minmax(86px, 1fr));
  gap: 10px;
}

.task-manager__stats span {
  padding: 12px 14px;
  border: 1px solid rgba(148, 163, 184, 0.2);
  border-radius: 18px;
  background: rgba(255, 255, 255, 0.76);
  color: #64748b;
  box-shadow: 0 18px 44px rgba(15, 23, 42, 0.08);
}

.task-manager__stats strong {
  display: block;
  color: #0f172a;
  font-size: 22px;
}

.task-manager__composer {
  padding: 16px;
  border: 1px solid rgba(148, 163, 184, 0.22);
  border-radius: 24px;
  background: rgba(255, 255, 255, 0.86);
  box-shadow: 0 22px 60px rgba(15, 23, 42, 0.1);
}

.task-manager__editor {
  position: relative;
  z-index: 21;
  box-sizing: border-box;
  width: min(760px, 100%);
  max-height: calc(100vh - 48px);
  overflow: auto;
  padding: 16px;
  border: 1px solid rgba(37, 99, 235, 0.18);
  border-radius: 24px;
  background: #f8fbff;
  box-shadow: 0 28px 80px rgba(15, 23, 42, 0.24);
}

.task-manager__modal {
  position: fixed;
  inset: 0;
  z-index: 20;
  display: grid;
  place-items: center;
  padding: 24px;
}

.task-manager__modal-backdrop {
  position: absolute;
  inset: 0;
  background: rgba(15, 23, 42, 0.46);
  backdrop-filter: blur(4px);
}

.task-manager__editor-head {
  display: flex;
  justify-content: space-between;
  gap: 14px;
  align-items: flex-start;
  margin-bottom: 12px;
}

.task-manager__editor h2 {
  margin: 0;
  font-size: 20px;
}

.task-manager__composer textarea,
.task-manager__editor textarea {
  box-sizing: border-box;
  width: 100%;
  border: none;
  outline: none;
  resize: vertical;
  min-height: 82px;
  border-radius: 16px;
  padding: 14px 16px;
  color: #0f172a;
  background: rgba(241, 245, 249, 0.86);
  font: inherit;
  line-height: 1.6;
}

.task-manager__composer-grid {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 10px;
  margin-top: 12px;
}

.task-manager__composer-grid label {
  display: grid;
  gap: 6px;
  min-width: 0;
  color: #475569;
  font-size: 12px;
  font-weight: 800;
}

.task-manager__composer-grid input,
.task-manager__composer-grid select {
  box-sizing: border-box;
  width: 100%;
  min-width: 0;
  border: 1px solid rgba(148, 163, 184, 0.24);
  border-radius: 12px;
  outline: none;
  padding: 9px 10px;
  color: #0f172a;
  background: #ffffff;
  font: inherit;
}

.task-manager__composer-footer {
  display: flex;
  justify-content: space-between;
  gap: 14px;
  align-items: center;
  margin-top: 12px;
  color: #64748b;
  font-size: 13px;
}

.task-manager__modal-actions {
  display: flex;
  justify-content: space-between;
  gap: 14px;
  align-items: center;
  margin-top: 12px;
  color: #64748b;
  font-size: 13px;
}

.task-manager__modal-actions div {
  display: flex;
  gap: 10px;
  align-items: center;
}

.task-manager button {
  border: none;
  cursor: pointer;
  font: inherit;
}

.task-manager button:disabled {
  cursor: not-allowed;
  opacity: 0.5;
}

.task-manager__composer button,
.task-manager__editor button,
.task-card__actions button,
.task-manager__toolbar button {
  border-radius: 999px;
  padding: 9px 14px;
  color: #1d4ed8;
  background: rgba(219, 234, 254, 0.9);
  font-weight: 700;
}

.task-manager__composer button {
  color: #ffffff;
  background: linear-gradient(135deg, #2563eb, #06b6d4);
  box-shadow: 0 12px 24px rgba(37, 99, 235, 0.24);
}

.task-manager__editor button[type="submit"] {
  color: #ffffff;
  background: #2563eb;
  box-shadow: 0 12px 24px rgba(37, 99, 235, 0.18);
}

.task-manager__editor button.is-icon {
  display: inline-grid;
  place-items: center;
  width: 34px;
  height: 34px;
  border-radius: 999px;
  padding: 0;
  color: #475569;
  background: rgba(226, 232, 240, 0.95);
  font-size: 22px;
  line-height: 1;
}

.task-manager__editor button.is-muted {
  color: #475569;
  background: rgba(226, 232, 240, 0.95);
}

.task-manager__toolbar {
  display: flex;
  gap: 10px;
  margin: 18px 0;
}

.task-manager__toolbar button.is-active {
  color: #ffffff;
  background: #0f172a;
}

.task-manager__empty {
  display: grid;
  place-items: center;
  gap: 8px;
  min-height: 220px;
  border: 1px dashed rgba(148, 163, 184, 0.5);
  border-radius: 24px;
  color: #64748b;
  background: rgba(255, 255, 255, 0.58);
}

.task-manager__empty strong {
  color: #0f172a;
  font-size: 20px;
}

.task-manager__list {
  display: grid;
  gap: 14px;
}

.task-card {
  display: flex;
  justify-content: space-between;
  gap: 18px;
  padding: 18px;
  border: 1px solid rgba(148, 163, 184, 0.2);
  border-radius: 24px;
  background: rgba(255, 255, 255, 0.86);
  box-shadow: 0 18px 48px rgba(15, 23, 42, 0.08);
}

.task-card.is-done {
  opacity: 0.72;
}

.task-card.is-disabled {
  border-color: rgba(148, 163, 184, 0.34);
  background: rgba(248, 250, 252, 0.78);
}

.task-card.is-disabled h2,
.task-card.is-disabled p {
  color: #64748b;
}

.task-card__head,
.task-card__actions {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}

.task-card__status,
.task-card__source,
.task-card__enabled {
  display: inline-flex;
  border-radius: 999px;
  padding: 4px 9px;
  color: #2563eb;
  background: rgba(219, 234, 254, 0.9);
  font-size: 12px;
  font-weight: 800;
}

.task-card__source {
  color: #0f766e;
  background: rgba(204, 251, 241, 0.86);
}

.task-card__enabled {
  color: #15803d;
  background: rgba(220, 252, 231, 0.9);
}

.task-card__enabled.is-disabled {
  color: #64748b;
  background: rgba(226, 232, 240, 0.9);
}

.task-card h2 {
  margin: 10px 0 0;
  font-size: 18px;
}

.task-card__meta,
.task-card__phrases {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  margin-top: 10px;
}

.task-card__meta span,
.task-card__phrases span {
  display: inline-flex;
  border: 1px solid rgba(148, 163, 184, 0.18);
  border-radius: 10px;
  padding: 4px 8px;
  color: #475569;
  background: rgba(248, 250, 252, 0.92);
  font-size: 12px;
  font-weight: 700;
}

.task-card__phrases span {
  color: #7c2d12;
  background: rgba(255, 247, 237, 0.96);
}

.task-card time {
  display: inline-flex;
  margin-top: 12px;
  color: #94a3b8;
  font-size: 12px;
}

.task-card__actions {
  align-content: flex-start;
  justify-content: flex-end;
  min-width: 260px;
}

.task-card__actions button.is-enable {
  color: #15803d;
  background: rgba(220, 252, 231, 0.95);
}

.task-card__actions button.is-muted {
  color: #475569;
  background: rgba(226, 232, 240, 0.95);
}

.task-card__actions button.is-danger {
  color: #b91c1c;
  background: rgba(254, 226, 226, 0.9);
}

@media (max-width: 760px) {
  .task-manager {
    padding: 20px;
  }

  .task-manager__hero,
  .task-card,
  .task-manager__composer-footer,
  .task-manager__modal-actions {
    flex-direction: column;
  }

  .task-manager__stats {
    width: 100%;
  }

  .task-manager__composer-grid {
    grid-template-columns: 1fr;
  }

  .task-manager__modal {
    padding: 16px;
  }

  .task-manager__modal-actions {
    align-items: stretch;
  }

  .task-manager__modal-actions div {
    justify-content: flex-end;
  }

  .task-card__actions {
    min-width: 0;
    justify-content: flex-start;
  }
}
</style>
