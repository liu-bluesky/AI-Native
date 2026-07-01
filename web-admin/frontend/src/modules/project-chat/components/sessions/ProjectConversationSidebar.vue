<template>
  <aside class="chat-conversation-sidebar">
    <div class="chat-sidebar-brand-panel">
      <div class="chat-sidebar-brand">
        <div class="chat-sidebar-brand__mark">{{ surfaceMark }}</div>
        <div>
          <div class="chat-sidebar-brand__name">
            {{ surfaceName }}
          </div>
          <div class="chat-sidebar-brand__meta">
            {{ surfaceMeta }}
          </div>
        </div>
      </div>
      <el-button
        ref="settingsButtonRef"
        class="chat-page-settings-button"
        :icon="Setting"
        circle
        @click="emit('open-settings', 'chat')"
      />
    </div>

    <div class="chat-conversation-sidebar__actions">
      <el-button
        class="chat-new-conversation-button"
        :loading="creatingSession"
        :icon="DocumentCopy"
        @click="emit('create-conversation')"
      >
        新对话
      </el-button>
      <el-button
        text
        class="chat-clear-current-button"
        :disabled="chatLoading || !currentSessionId"
        @click="emit('clear-current')"
      >
        清空对话
      </el-button>
    </div>

    <div class="chat-session-panel">
      <div class="chat-session-panel__head">
        <div class="chat-session-panel__title">项目对话</div>
      </div>

      <div
        ref="projectSwitcherRef"
        class="chat-project-tree"
        :loading="sessionsLoading"
      >
        <div v-if="projects.length" class="chat-project-tree__list">
          <section
            v-for="project in projects"
            :key="project.id"
            class="chat-project-node"
            :class="{
              'is-active': selectedProjectId === project.id,
              'is-expanded': isProjectExpanded(project.id),
            }"
          >
            <button
              type="button"
              class="chat-project-node__button"
              @click="toggleProject(project.id)"
            >
              <span class="chat-project-node__chevron">
                {{ isProjectExpanded(project.id) ? "⌄" : "›" }}
              </span>
              <span class="chat-project-node__name">
                {{ project.name || project.id }}
              </span>
              <span class="chat-project-node__count">
                {{ projectSessionTotalLabel(project.id) }}
              </span>
            </button>

            <ChatSessionList
              v-if="isProjectExpanded(project.id)"
              :loading="isProjectSessionsLoading(project.id)"
              :groups="projectSessionGroups(project.id)"
              :current-session-id="
                selectedProjectId === project.id ? currentSessionId : ''
              "
              :deleting-session-id="deletingSessionId"
              @select="emit('select-session', { projectId: project.id, sessionId: $event })"
              @delete="emit('delete-session', { projectId: project.id, session: $event })"
            />
          </section>
        </div>
        <div v-else class="chat-project-tree__empty">暂无可访问项目</div>
      </div>
    </div>

    <div class="chat-sidebar-footer">
      <div class="chat-sidebar-user">
        <div class="chat-sidebar-user__avatar">
          {{ usernameInitial }}
        </div>
        <div class="chat-sidebar-user__meta">
          <div class="chat-sidebar-user__name">{{ username }}</div>
          <div class="chat-sidebar-user__role">当前账号</div>
        </div>
        <el-button text class="chat-sidebar-user__logout" @click="emit('logout')">
          退出
        </el-button>
      </div>
    </div>
  </aside>
</template>

<script setup>
import { computed, ref, watch } from "vue";
import { DocumentCopy, Setting } from "@element-plus/icons-vue";
import ChatSessionList from "@/modules/project-chat/components/sessions/ChatSessionList.vue";

const props = defineProps({
  selectedProjectId: { type: String, default: "" },
  projects: { type: Array, default: () => [] },
  surfaceMark: { type: String, default: "" },
  surfaceName: { type: String, default: "" },
  surfaceMeta: { type: String, default: "" },
  creatingSession: { type: Boolean, default: false },
  chatLoading: { type: Boolean, default: false },
  hasSelectedProject: { type: Boolean, default: false },
  currentSessionId: { type: String, default: "" },
  sessionsLoading: { type: Boolean, default: false },
  sessionGroups: { type: Array, default: () => [] },
  projectSessionGroupsMap: { type: Object, default: () => ({}) },
  projectSessionLoadingMap: { type: Object, default: () => ({}) },
  projectSessionCounts: { type: Object, default: () => ({}) },
  deletingSessionId: { type: String, default: "" },
  usernameInitial: { type: String, default: "" },
  username: { type: String, default: "" },
});

const emit = defineEmits([
  "update:selectedProjectId",
  "open-settings",
  "project-change",
  "create-conversation",
  "clear-current",
  "toggle-project",
  "select-session",
  "delete-session",
  "logout",
]);

const settingsButtonRef = ref(null);
const projectSwitcherRef = ref(null);
const expandedProjectIds = ref(new Set());

const selectedProjectIdModel = computed({
  get: () => props.selectedProjectId,
  set: (value) => emit("update:selectedProjectId", value),
});

const selectedSessionTotalLabel = computed(() => {
  const total = props.sessionGroups.reduce(
    (sum, group) => sum + (Array.isArray(group?.items) ? group.items.length : 0),
    0,
  );
  return total ? `${total}` : "0";
});

watch(
  () => props.selectedProjectId,
  (projectId) => {
    const normalizedProjectId = String(projectId || "").trim();
    if (!normalizedProjectId) return;
    const next = new Set(expandedProjectIds.value);
    next.add(normalizedProjectId);
    expandedProjectIds.value = next;
  },
  { immediate: true },
);

watch(
  () => props.projects,
  (projects) => {
    const validIds = new Set(
      (Array.isArray(projects) ? projects : [])
        .map((item) => String(item?.id || "").trim())
        .filter(Boolean),
    );
    const next = new Set(
      [...expandedProjectIds.value].filter((projectId) => validIds.has(projectId)),
    );
    const selected = String(props.selectedProjectId || "").trim();
    if (selected && validIds.has(selected)) {
      next.add(selected);
    }
    expandedProjectIds.value = next;
  },
  { immediate: true },
);

function selectProject(projectId) {
  const normalizedProjectId = String(projectId || "").trim();
  if (!normalizedProjectId) return;
  selectedProjectIdModel.value = normalizedProjectId;
  emit("project-change", normalizedProjectId);
}

function toggleProject(projectId) {
  const normalizedProjectId = String(projectId || "").trim();
  if (!normalizedProjectId) return;
  const next = new Set(expandedProjectIds.value);
  if (next.has(normalizedProjectId)) {
    next.delete(normalizedProjectId);
  } else {
    next.add(normalizedProjectId);
    emit("toggle-project", normalizedProjectId);
  }
  expandedProjectIds.value = next;
  selectProject(normalizedProjectId);
}

function isProjectExpanded(projectId) {
  return expandedProjectIds.value.has(String(projectId || "").trim());
}

function projectSessionGroups(projectId) {
  const normalizedProjectId = String(projectId || "").trim();
  if (normalizedProjectId === String(props.selectedProjectId || "").trim()) {
    return props.sessionGroups;
  }
  const groups = props.projectSessionGroupsMap?.[normalizedProjectId];
  return Array.isArray(groups) ? groups : [];
}

function isProjectSessionsLoading(projectId) {
  const normalizedProjectId = String(projectId || "").trim();
  if (normalizedProjectId === String(props.selectedProjectId || "").trim()) {
    return props.sessionsLoading;
  }
  return Boolean(props.projectSessionLoadingMap?.[normalizedProjectId]);
}

function projectSessionTotalLabel(projectId) {
  const normalizedProjectId = String(projectId || "").trim();
  if (normalizedProjectId === String(props.selectedProjectId || "").trim()) {
    return selectedSessionTotalLabel.value;
  }
  const count = Number(props.projectSessionCounts?.[normalizedProjectId] || 0);
  return count ? `${count}` : "0";
}

// 父页的新手引导仍需要定位内部控件，组件只暴露定位锚点，不暴露业务状态。
defineExpose({
  settingsButtonRef,
  projectSwitcherRef,
});
</script>

<style scoped>
/* 抽成子组件后，父页 scoped CSS 不再命中内部结构；左侧栏样式由组件自己维护。 */
.chat-conversation-sidebar {
  display: flex;
  flex-direction: column;
  width: 100%;
  height: 100%;
  max-height: 100%;
  min-height: 0;
  padding: 14px;
  border: 1px solid rgba(226, 232, 240, 0.92);
  border-radius: 28px;
  background: linear-gradient(
    180deg,
    rgba(255, 255, 255, 0.96),
    rgba(245, 247, 250, 0.92)
  );
  box-shadow:
    0 20px 40px rgba(15, 23, 42, 0.06),
    0 2px 10px rgba(15, 23, 42, 0.03);
}

.chat-sidebar-brand-panel {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  padding: 4px 2px 16px;
}

.chat-sidebar-brand {
  display: flex;
  align-items: center;
  gap: 8px;
  min-width: 0;
}

.chat-sidebar-brand__mark {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 34px;
  height: 34px;
  border-radius: 11px;
  background: #0f172a;
  color: #fff;
  font-size: 11px;
  font-weight: 700;
  letter-spacing: 0.08em;
}

.chat-sidebar-brand__name {
  color: #0f172a;
  font-size: 16px;
  line-height: 1.2;
  font-weight: 600;
  font-family:
    "Avenir Next", "IBM Plex Sans", "PingFang SC", "Microsoft YaHei", sans-serif;
}

.chat-sidebar-brand__meta {
  margin-top: 2px;
  color: var(--page-text-soft, #7c8aa0);
  font-size: 11px;
  line-height: 1.3;
}

.chat-page-settings-button {
  flex-shrink: 0;
  width: 36px;
  height: 36px;
  border: 1px solid rgba(255, 255, 255, 0.72) !important;
  background: rgba(255, 255, 255, 0.66) !important;
  color: #475569 !important;
  box-shadow: 0 12px 24px rgba(15, 23, 42, 0.05) !important;
}

.chat-page-settings-button:hover {
  border-color: rgba(56, 189, 248, 0.28) !important;
  background: rgba(255, 255, 255, 0.86) !important;
  color: #0f172a !important;
}

.chat-conversation-sidebar__actions {
  display: flex;
  flex-direction: column;
  align-items: stretch;
  gap: 8px;
  margin-top: 10px;
  margin-bottom: 10px;
  padding: 0;
}

.chat-new-conversation-button {
  width: 100%;
  height: 42px !important;
  border: 1px solid rgba(17, 24, 39, 0.06) !important;
  border-radius: 18px !important;
  background: linear-gradient(180deg, #111827, #1f2937) !important;
  color: #f8fafc !important;
  font-weight: 600;
  box-shadow: 0 12px 28px rgba(15, 23, 42, 0.16) !important;
}

.chat-clear-current-button {
  justify-content: flex-start;
  min-height: 32px !important;
  padding: 0 6px !important;
  color: var(--page-text-soft, #7c8aa0) !important;
}

.chat-session-panel {
  display: flex;
  flex: 1;
  flex-direction: column;
  min-height: 0;
  margin-top: 0;
  padding: 0 2px 2px;
  border: 0;
  border-radius: 0;
  background: transparent;
  box-shadow: none;
}

.chat-session-panel__head {
  display: flex;
  align-items: center;
  justify-content: flex-start;
  gap: 10px;
  padding: 0 6px 10px;
}

.chat-session-panel__title {
  color: #475569;
  font-size: 12px;
  font-weight: 700;
  letter-spacing: 0.08em;
  text-transform: uppercase;
}

.chat-project-tree {
  flex: 1;
  min-height: 0;
  position: relative;
}

.chat-project-tree :deep(.el-loading-mask) {
  border-radius: 18px;
  background: rgba(255, 255, 255, 0.72);
}

.chat-project-tree__list {
  display: flex;
  flex-direction: column;
  gap: 6px;
  height: 100%;
  overflow: auto;
  padding-right: 4px;
}

.chat-project-node {
  min-width: 0;
}

.chat-project-node__button {
  display: flex;
  align-items: center;
  gap: 8px;
  width: 100%;
  min-height: 38px;
  padding: 8px 10px;
  border: 0;
  border-radius: 10px;
  background: transparent;
  color: #334155;
  text-align: left;
  cursor: pointer;
  transition:
    background-color 0.16s ease,
    color 0.16s ease;
}

.chat-project-node__button:hover {
  background: rgba(15, 23, 42, 0.05);
  color: #0f172a;
}

.chat-project-node.is-active > .chat-project-node__button {
  background: rgba(15, 23, 42, 0.07);
  color: #0f172a;
  font-weight: 600;
}

.chat-project-node__chevron {
  flex: 0 0 14px;
  color: #94a3b8;
  font-size: 16px;
  line-height: 1;
  text-align: center;
}

.chat-project-node__name {
  flex: 1;
  min-width: 0;
  overflow: hidden;
  font-size: 13px;
  line-height: 1.35;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.chat-project-node__count {
  flex-shrink: 0;
  min-width: 20px;
  padding: 2px 6px;
  border-radius: 999px;
  background: rgba(15, 23, 42, 0.08);
  color: #64748b;
  font-size: 11px;
  line-height: 1.3;
  text-align: center;
}

.chat-project-node :deep(.chat-session-strip) {
  margin: 3px 0 8px 22px;
}

.chat-project-node :deep(.chat-session-groups) {
  gap: 8px;
  height: auto;
  overflow: visible;
  padding-right: 0;
}

.chat-project-node :deep(.chat-session-group__title) {
  padding-left: 4px;
}

.chat-project-tree__empty {
  display: flex;
  align-items: center;
  justify-content: center;
  min-height: 160px;
  color: var(--page-text-soft, #7c8aa0);
  font-size: 12px;
}

.chat-sidebar-footer {
  margin-top: 14px;
  padding: 0;
}

.chat-sidebar-user {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 14px;
  border: 1px solid rgba(226, 232, 240, 0.9);
  border-radius: 18px;
  background: rgba(255, 255, 255, 0.72);
  box-shadow: none;
}

.chat-sidebar-user__avatar {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 30px;
  height: 30px;
  border-radius: 999px;
  background: #e4e4e7;
  color: #52525b;
  font-size: 12px;
  font-weight: 700;
}

.chat-sidebar-user__meta {
  min-width: 0;
  flex: 1;
}

.chat-sidebar-user__name {
  color: #27272a;
  font-size: 13px;
  font-weight: 500;
}

.chat-sidebar-user__role {
  margin-top: 2px;
  color: #9ca3af;
  font-size: 11px;
}

.chat-sidebar-user__logout {
  flex-shrink: 0;
  color: #8b8d93 !important;
}

@media (max-width: 1120px) {
  .chat-conversation-sidebar {
    order: 2;
    padding: 0;
    border: 0;
  }
}

@media (max-width: 640px) {
  .chat-conversation-sidebar__actions {
    justify-content: flex-start;
  }
}
</style>
