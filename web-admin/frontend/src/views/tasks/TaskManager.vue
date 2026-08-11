<template>
  <section class="task-manager">
    <div class="task-manager__ambient" aria-hidden="true" />
    <header class="task-manager__hero">
      <div>
        <span class="task-manager__eyebrow">LOCAL AI RUNTIME</span>
        <h1>长任务</h1>
        <p>跨项目查看本机 AI Runtime 的执行状态。切换项目或会话不会中断任务。</p>
      </div>
      <div class="task-manager__stats" aria-label="长任务统计">
        <span><strong>{{ activeTasks.length }}</strong>执行中</span>
        <span><strong>{{ waitingTasks.length }}</strong>等待处理</span>
        <span><strong>{{ recoverableTasks.length }}</strong>可恢复</span>
        <span><strong>{{ completedTasks.length }}</strong>已完成</span>
      </div>
    </header>

    <section class="local-task-panel">
      <div class="local-task-panel__head">
        <div>
          <span class="task-manager__eyebrow">ON THIS DEVICE</span>
          <h2>AI 长任务</h2>
        </div>
        <span class="local-task-panel__count">仅保存在本机</span>
      </div>

      <div v-if="!localAiTasks.length" class="task-manager__empty">
        <strong>还没有本地 AI 长任务</strong>
        <span>在项目聊天中发送需要持续执行的需求后，任务会自动出现在这里。</span>
      </div>

      <div v-else class="local-task-panel__list">
        <article v-for="task in localAiTasks" :key="task.id" class="local-task-card">
          <div class="local-task-card__head">
            <span class="local-task-card__status" :class="`is-${task.status}`">
              {{ localAiTaskStatusLabel(task.status) }}
            </span>
            <span class="local-task-card__project">{{ task.projectName || task.projectId || "未命名项目" }}</span>
            <time>{{ formatTaskTime(task.updatedAt) }}</time>
          </div>

          <h3>{{ task.title }}</h3>
          <div class="local-task-card__step">
            <span>当前步骤</span>
            <strong>{{ task.currentStep || "本地 Runtime 正在执行" }}</strong>
          </div>
          <p v-if="task.lastOutput" class="local-task-card__output">{{ task.lastOutput }}</p>
          <div class="local-task-card__meta">
            <span>开始 {{ formatTaskTime(task.createdAt) }}</span>
            <span v-if="task.completedAt">结束 {{ formatTaskTime(task.completedAt) }}</span>
            <span v-else>更新 {{ formatTaskTime(task.updatedAt) }}</span>
          </div>
          <div class="local-task-card__actions">
            <button type="button" class="is-primary" @click="openTaskChat(task)">跳转原会话</button>
            <button
              v-if="task.recoverable && isRecoverableStatus(task.status)"
              type="button"
              @click="openTaskChat(task, 'resume')"
            >
              继续执行
            </button>
            <button
              v-if="isTaskActive(task)"
              type="button"
              class="is-danger"
              :disabled="cancellingTaskIds.has(task.id)"
              @click="cancelTask(task)"
            >
              {{ cancellingTaskIds.has(task.id) ? "正在取消…" : "取消任务" }}
            </button>
            <button
              v-if="isTaskRemovable(task)"
              type="button"
              class="is-danger"
              @click="deleteTask(task)"
            >
              删除记录
            </button>
          </div>
        </article>
      </div>
    </section>
  </section>
</template>

<script setup>
import { computed, onBeforeUnmount, onMounted, ref } from "vue";
import { useRouter } from "vue-router";
import { ElMessage } from "element-plus";
import {
  deleteLocalAiTask,
  isLocalAiTaskActive,
  listLocalAiTasks,
  LOCAL_AI_TASKS_UPDATED_EVENT,
  updateLocalAiTask,
} from "@/utils/local-ai-task-store.js";
import {
  hasNativeDesktopBridge,
  pauseNativeLiuAgentLocalChat,
  recoverNativeLiuAgentRuntimeState,
} from "@/utils/native-desktop-bridge.js";
import { openRouteInDesktop } from "@/utils/desktop-app-bridge.js";

const router = useRouter();
const localAiTasks = ref([]);
const cancellingTaskIds = ref(new Set());
let localAiTaskRefreshTimer = null;

const activeTasks = computed(() => localAiTasks.value.filter((task) => isLocalAiTaskActive(task)));
const waitingTasks = computed(() =>
  localAiTasks.value.filter((task) => ["waiting_approval", "waiting_user", "reconnecting"].includes(task.status)),
);
const recoverableTasks = computed(() =>
  localAiTasks.value.filter((task) => task.recoverable && isRecoverableStatus(task.status)),
);
const completedTasks = computed(() =>
  localAiTasks.value.filter((task) => ["done", "failed", "cancelled"].includes(task.status)),
);

function refreshLocalAiTasks() {
  localAiTasks.value = listLocalAiTasks();
}

function isTaskActive(task) {
  return isLocalAiTaskActive(task);
}

function isRecoverableStatus(status) {
  return ["interrupted", "failed", "reconnecting"].includes(String(status || "").trim());
}

function isTaskRemovable(task) {
  return ["done", "failed", "cancelled"].includes(String(task?.status || "").trim());
}

async function refreshLocalAiTaskRuntimeStates() {
  refreshLocalAiTasks();
  if (!hasNativeDesktopBridge()) return;
  const activeTasksSnapshot = listLocalAiTasks({ activeOnly: true });
  await Promise.all(
    activeTasksSnapshot.map(async (task) => {
      if (!task.projectId || !task.chatSessionId || !task.workspacePath) return;
      const result = await recoverNativeLiuAgentRuntimeState({
        projectId: task.projectId,
        chatSessionId: task.chatSessionId,
        workspacePath: task.workspacePath,
      }).catch(() => null);
      if (!result?.ok) return;
      const state = result.state && typeof result.state === "object" ? result.state : {};
      const runState = state.run_state && typeof state.run_state === "object" ? state.run_state : {};
      const runtimeStatus = String(runState.status || state.current_state?.status || "").trim().toLowerCase();
      const status = {
        running: "running",
        waiting_approval: "waiting_approval",
        waiting_user: "waiting_user",
        paused: "interrupted",
        interrupted: "interrupted",
        done: "done",
        completed: "done",
        failed: "failed",
        cancelled: "cancelled",
      }[runtimeStatus];
      if (!status) return;
      if (task.status === "cancelling") return;
      if (task.status === "cancelled" && ["paused", "interrupted"].includes(runtimeStatus)) {
        return;
      }
      updateLocalAiTask(task.id, {
        status,
        recoverable: ["interrupted", "failed"].includes(status),
        currentStep: status === "running" ? "本地 Runtime 正在执行" : task.currentStep,
        statePath: state.state_path || runState.state_path || task.statePath,
      });
    }),
  );
  refreshLocalAiTasks();
}

function openTaskChat(task, action = "") {
  if (!task.projectId || !task.chatSessionId) return;
  void openRouteInDesktop(router, {
    path: "/ai/chat",
    query: {
      project_id: task.projectId,
      chat_session_id: task.chatSessionId,
      local_runtime_task: "1",
      local_runtime_task_action: action,
      local_ai_task_id: task.id,
    },
  }, {
    mode: "focus-or-open",
    appId: "chat",
    title: "项目 AI 对话",
    eyebrow: "Project Chat",
    targetWindowId: task.originWindowId,
  });
}

function deleteTask(task) {
  if (!isTaskRemovable(task)) {
    ElMessage.warning("仅已完成、失败或已取消的任务可以删除记录");
    return;
  }
  if (!deleteLocalAiTask(task.id)) {
    ElMessage.warning("任务记录不存在或已被删除");
    return;
  }
  refreshLocalAiTasks();
  ElMessage.success("任务记录已删除");
}

async function cancelTask(task) {
  if (cancellingTaskIds.value.has(task.id)) return;
  cancellingTaskIds.value = new Set([...cancellingTaskIds.value, task.id]);
  updateLocalAiTask(task.id, {
    status: "cancelling",
    currentStep: "正在停止本地 Runtime",
    recoverable: false,
  });
  refreshLocalAiTasks();
  const result = await Promise.race([
    pauseNativeLiuAgentLocalChat({
      projectId: task.projectId,
      chatSessionId: task.chatSessionId,
      workspacePath: task.workspacePath,
      reason: "manual_pause",
    })
      .then((paused) => ({ completed: true, paused }))
      .catch(() => ({ completed: true, paused: false })),
    new Promise((resolve) => {
      window.setTimeout(() => resolve({ completed: false, paused: false }), 5000);
    }),
  ]);
  cancellingTaskIds.value = new Set(
    [...cancellingTaskIds.value].filter((taskId) => taskId !== task.id),
  );
  if (result.paused) {
    updateLocalAiTask(task.id, {
      status: "cancelled",
      currentStep: "任务已取消",
      recoverable: false,
    });
    refreshLocalAiTasks();
    openTaskChat(task, "cancelled");
    ElMessage.success("已停止本地 AI Runtime");
    return;
  }
  updateLocalAiTask(task.id, {
    status: "interrupted",
    currentStep: result.completed ? "未能停止本地 Runtime" : "停止请求超时",
    lastOutput: result.completed
      ? "本地 Runtime 未接受取消请求，请打开原会话重试。"
      : "本地 Runtime 暂未响应取消请求，请打开原会话重试。",
    recoverable: true,
  });
  refreshLocalAiTasks();
  ElMessage.error("未能停止本地 Runtime，已标记为可恢复，请在原会话重试");
}

function localAiTaskStatusLabel(status) {
  return {
    queued: "排队中",
    running: "运行中",
    waiting_approval: "等待授权",
    waiting_user: "等待输入",
    reconnecting: "准备续跑",
    cancelling: "正在取消",
    interrupted: "可恢复",
    done: "已完成",
    failed: "执行失败",
    cancelled: "已取消",
  }[String(status || "").trim()] || "本地任务";
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

function handleLocalAiTasksUpdated() {
  refreshLocalAiTasks();
}

onMounted(() => {
  void refreshLocalAiTaskRuntimeStates();
  localAiTaskRefreshTimer = window.setInterval(() => {
    void refreshLocalAiTaskRuntimeStates();
  }, 3000);
  window.addEventListener(LOCAL_AI_TASKS_UPDATED_EVENT, handleLocalAiTasksUpdated);
});

onBeforeUnmount(() => {
  if (localAiTaskRefreshTimer !== null) {
    window.clearInterval(localAiTaskRefreshTimer);
    localAiTaskRefreshTimer = null;
  }
  window.removeEventListener(LOCAL_AI_TASKS_UPDATED_EVENT, handleLocalAiTasksUpdated);
});
</script>

<style scoped>
.task-manager {
  position: relative;
  min-height: 100%;
  padding: 30px;
  overflow: hidden;
  color: #0f172a;
  background: radial-gradient(circle at 14% 4%, rgba(56, 189, 248, 0.18), transparent 30%), linear-gradient(180deg, #f8fafc, #f1f5f9);
}

.task-manager__ambient {
  position: absolute;
  right: -120px;
  bottom: -180px;
  width: 360px;
  height: 360px;
  border-radius: 999px;
  background: rgba(37, 99, 235, 0.14);
  filter: blur(12px);
  pointer-events: none;
}

.task-manager__hero,
.local-task-panel {
  position: relative;
  z-index: 1;
}

.task-manager__hero {
  display: flex;
  justify-content: space-between;
  gap: 24px;
  align-items: flex-start;
  margin-bottom: 24px;
}

.task-manager__eyebrow {
  color: #2563eb;
  font-size: 11px;
  font-weight: 800;
  letter-spacing: 0.12em;
  text-transform: uppercase;
}

.task-manager h1,
.local-task-panel h2,
.local-task-card h3 {
  margin: 0;
}

.task-manager h1 {
  margin-top: 8px;
  font-size: 32px;
}

.task-manager__hero p {
  max-width: 620px;
  margin: 8px 0 0;
  color: #64748b;
  line-height: 1.55;
}

.task-manager__stats {
  display: grid;
  grid-template-columns: repeat(4, minmax(78px, 1fr));
  gap: 8px;
  min-width: 360px;
}

.task-manager__stats span {
  display: grid;
  gap: 3px;
  padding: 12px;
  border: 1px solid rgba(148, 163, 184, 0.2);
  border-radius: 16px;
  color: #64748b;
  background: rgba(255, 255, 255, 0.72);
  font-size: 12px;
  text-align: center;
}

.task-manager__stats strong {
  color: #0f172a;
  font-size: 22px;
}

.local-task-panel {
  padding: 20px;
  border: 1px solid rgba(37, 99, 235, 0.2);
  border-radius: 26px;
  background: linear-gradient(135deg, rgba(239, 246, 255, 0.94), rgba(255, 255, 255, 0.9));
  box-shadow: 0 18px 48px rgba(37, 99, 235, 0.1);
}

.local-task-panel__head,
.local-task-card__head,
.local-task-card__meta,
.local-task-card__actions {
  display: flex;
  align-items: center;
  gap: 10px;
}

.local-task-panel__head,
.local-task-card__head {
  justify-content: space-between;
}

.local-task-panel h2 {
  margin-top: 5px;
  font-size: 21px;
}

.local-task-panel__count {
  color: #2563eb;
  font-size: 13px;
  font-weight: 700;
}

.local-task-panel__list {
  display: grid;
  gap: 12px;
  margin-top: 16px;
}

.local-task-card {
  padding: 17px;
  border: 1px solid rgba(148, 163, 184, 0.22);
  border-radius: 20px;
  background: rgba(255, 255, 255, 0.88);
}

.local-task-card__head {
  color: #64748b;
  font-size: 12px;
}

.local-task-card__status {
  border-radius: 999px;
  padding: 4px 9px;
  color: #2563eb;
  background: #dbeafe;
  font-weight: 800;
}

.local-task-card__status.is-done { color: #15803d; background: #dcfce7; }
.local-task-card__status.is-failed { color: #b91c1c; background: #fee2e2; }
.local-task-card__status.is-cancelled { color: #64748b; background: #e2e8f0; }
.local-task-card__status.is-waiting_approval,
.local-task-card__status.is-waiting_user,
.local-task-card__status.is-reconnecting,
.local-task-card__status.is-interrupted { color: #a16207; background: #fef3c7; }

.local-task-card__project {
  flex: 1;
  color: #475569;
}

.local-task-card h3 {
  margin-top: 13px;
  font-size: 17px;
  line-height: 1.45;
}

.local-task-card__step {
  display: grid;
  gap: 4px;
  margin-top: 12px;
  padding: 11px 12px;
  border-radius: 13px;
  background: #f8fafc;
}

.local-task-card__step span,
.local-task-card__meta {
  color: #64748b;
  font-size: 12px;
}

.local-task-card__step strong {
  color: #334155;
  font-size: 13px;
  font-weight: 700;
}

.local-task-card__output {
  margin: 10px 0 0;
  color: #475569;
  font-size: 13px;
  line-height: 1.55;
  white-space: pre-wrap;
}

.local-task-card__meta {
  margin-top: 12px;
}

.local-task-card__actions {
  justify-content: flex-end;
  margin-top: 14px;
}

.task-manager button {
  border: 0;
  border-radius: 999px;
  padding: 9px 14px;
  color: #1d4ed8;
  background: #dbeafe;
  cursor: pointer;
  font: inherit;
  font-size: 13px;
  font-weight: 700;
}

.task-manager button:hover { filter: brightness(0.97); }
.task-manager button.is-primary { color: #fff; background: linear-gradient(135deg, #2563eb, #06b6d4); }
.task-manager button.is-danger { color: #b91c1c; background: #fee2e2; }

.task-manager__empty {
  display: grid;
  place-items: center;
  gap: 8px;
  min-height: 220px;
  margin-top: 16px;
  border: 1px dashed rgba(148, 163, 184, 0.5);
  border-radius: 20px;
  color: #64748b;
  text-align: center;
}

.task-manager__empty strong { color: #0f172a; font-size: 19px; }

@media (max-width: 760px) {
  .task-manager { padding: 20px; }
  .task-manager__hero { flex-direction: column; }
  .task-manager__stats { width: 100%; min-width: 0; }
  .local-task-card__head { align-items: flex-start; flex-wrap: wrap; }
  .local-task-card__project { flex-basis: 100%; order: 3; }
  .local-task-card__meta,
  .local-task-card__actions { align-items: flex-start; flex-wrap: wrap; }
  .local-task-card__actions { justify-content: flex-start; }
}
</style>
