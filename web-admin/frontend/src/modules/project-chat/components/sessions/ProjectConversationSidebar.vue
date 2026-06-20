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

    <div class="chat-sidebar-project-card">
      <div class="chat-sidebar-card__label">项目</div>
      <el-select
        ref="projectSwitcherRef"
        v-model="selectedProjectIdModel"
        class="chat-project-select"
        popper-class="chat-project-select-dropdown"
        filterable
        fit-input-width
        placeholder="搜索或选择项目"
        :disabled="!projects.length"
        @change="emit('project-change', $event)"
      >
        <el-option
          v-for="item in projects"
          :key="item.id"
          :label="item.name || item.id"
          :value="item.id"
        >
          <div class="chat-project-option">
            <span class="chat-project-option__name">{{
              item.name || item.id
            }}</span>
          </div>
        </el-option>
      </el-select>
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
        <div class="chat-session-panel__title">最近对话</div>
      </div>

      <ChatSessionList
        :loading="sessionsLoading"
        :groups="sessionGroups"
        :current-session-id="currentSessionId"
        :deleting-session-id="deletingSessionId"
        @select="emit('select-session', $event)"
        @delete="emit('delete-session', $event)"
      />
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
import { computed, ref } from "vue";
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
  "select-session",
  "delete-session",
  "logout",
]);

const settingsButtonRef = ref(null);
const projectSwitcherRef = ref(null);

const selectedProjectIdModel = computed({
  get: () => props.selectedProjectId,
  set: (value) => emit("update:selectedProjectId", value),
});

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

.chat-sidebar-project-card {
  margin-top: 2px;
  padding: 14px;
  border: 1px solid rgba(191, 219, 254, 0.72);
  border-radius: 22px;
  background:
    radial-gradient(
      circle at top right,
      rgba(59, 130, 246, 0.14),
      transparent 36%
    ),
    linear-gradient(
      180deg,
      rgba(248, 250, 252, 0.98),
      rgba(255, 255, 255, 0.94)
    );
  box-shadow: none;
}

.chat-sidebar-project-card :deep(.chat-project-select) {
  display: block;
  width: 100%;
}

.chat-project-select :deep(.el-select__wrapper) {
  min-height: 42px;
  border: 1px solid rgba(226, 232, 240, 0.92);
  border-radius: 16px;
  background: rgba(255, 255, 255, 0.92);
  box-shadow: none;
}

.chat-project-select :deep(.el-select__wrapper.is-focused),
.chat-project-select :deep(.el-select__wrapper:hover) {
  border-color: rgba(59, 130, 246, 0.3);
  background: rgba(255, 255, 255, 0.98);
  box-shadow: 0 0 0 3px rgba(59, 130, 246, 0.08);
}

.chat-project-select :deep(.el-select__placeholder),
.chat-project-select :deep(.el-select__selected-item) {
  min-width: 0;
  color: #0f172a;
  font-size: 14px;
  font-weight: 600;
}

.chat-sidebar-card__label {
  margin: 0 0 10px;
  color: var(--page-text-soft, #7c8aa0);
  font-size: 11px;
  font-weight: 700;
  letter-spacing: 0.08em;
  text-transform: uppercase;
}

:global(.chat-project-select-dropdown) {
  max-width: calc(100vw - 24px);
  border-radius: 16px;
}

:global(.chat-project-select-dropdown .el-select-dropdown__wrap) {
  max-height: 280px;
}

:global(.chat-project-select-dropdown .el-select-dropdown__item) {
  height: auto;
  min-height: 42px;
  line-height: 1.4;
  padding: 0 12px;
}

.chat-project-option {
  display: flex;
  align-items: center;
  width: 100%;
  min-width: 0;
  padding: 11px 14px;
  box-sizing: border-box;
}

.chat-project-option__name {
  min-width: 0;
  width: 100%;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
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
