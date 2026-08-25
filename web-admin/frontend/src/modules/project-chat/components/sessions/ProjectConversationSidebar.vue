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
      <div class="chat-conversation-sidebar__primary-actions">
        <el-button
          class="chat-new-conversation-button"
          :loading="creatingSession"
          :disabled="!hasSelectedProject"
          :icon="DocumentCopy"
          @click="emit('create-conversation')"
        >
          新对话
        </el-button>
        <el-button
          class="chat-new-project-button"
          :loading="projectCreating"
          :icon="FolderAdd"
          @click="emit('create-project')"
        >
          新建项目
        </el-button>
      </div>
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
        <div>
          <div class="chat-session-panel__title">会话历史</div>
          <div class="chat-session-panel__subtitle">
            {{ hasSelectedProject ? "当前项目" : "先选择一个项目" }}
          </div>
        </div>
        <span class="chat-session-panel__hint">
          {{ hasSelectedProject ? "按时间排列" : "" }}
        </span>
      </div>

      <div
        ref="projectSwitcherRef"
        class="chat-session-history"
        :loading="sessionsLoading"
      >
        <ChatSessionList
          v-if="hasSelectedProject"
          :loading="sessionsLoading"
          :groups="sessionGroups"
          :current-session-id="currentSessionId"
          :deleting-session-id="deletingSessionId"
          @select="emit('select-session', { sessionId: $event })"
          @delete="emit('delete-session', { session: $event })"
        />
        <div v-else class="chat-session-history__empty">
          请在右上方选择项目后查看会话
        </div>
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
import { ref } from "vue";
import { DocumentCopy, FolderAdd, Setting } from "@element-plus/icons-vue";
import ChatSessionList from "@/modules/project-chat/components/sessions/ChatSessionList.vue";

const props = defineProps({
  surfaceMark: { type: String, default: "" },
  surfaceName: { type: String, default: "" },
  surfaceMeta: { type: String, default: "" },
  creatingSession: { type: Boolean, default: false },
  projectCreating: { type: Boolean, default: false },
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
  "open-settings",
  "create-conversation",
  "create-project",
  "clear-current",
  "select-session",
  "delete-session",
  "logout",
]);

const settingsButtonRef = ref(null);
const projectSwitcherRef = ref(null);

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
  padding: 16px 14px 14px;
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

.chat-conversation-sidebar__primary-actions {
  display: flex;
  gap: 8px;
}

.chat-new-conversation-button {
  flex: 1;
  min-width: 0;
  height: 42px !important;
  border: 1px solid rgba(17, 24, 39, 0.06) !important;
  border-radius: 18px !important;
  background: linear-gradient(180deg, #111827, #1f2937) !important;
  color: #f8fafc !important;
  font-weight: 600;
  box-shadow: 0 12px 28px rgba(15, 23, 42, 0.16) !important;
}

.chat-new-project-button {
  flex: 1;
  min-width: 0;
  height: 42px !important;
  border: 1px solid rgba(15, 23, 42, 0.08) !important;
  border-radius: 18px !important;
  background: rgba(255, 255, 255, 0.78) !important;
  color: #334155 !important;
  font-weight: 600;
  box-shadow: 0 12px 28px rgba(15, 23, 42, 0.07) !important;
}

.chat-new-project-button:hover {
  border-color: rgba(56, 189, 248, 0.28) !important;
  background: #ffffff !important;
  color: #0f172a !important;
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
  justify-content: space-between;
  gap: 10px;
  padding: 0 6px 12px;
}

.chat-session-panel__title {
  color: #475569;
  font-size: 13px;
  font-weight: 700;
  letter-spacing: 0.08em;
  text-transform: uppercase;
}

.chat-session-panel__subtitle {
  margin-top: 3px;
  color: #94a3b8;
  font-size: 11px;
  line-height: 1.3;
}

.chat-session-panel__hint {
  color: #94a3b8;
  font-size: 11px;
  white-space: nowrap;
}

.chat-session-history {
  flex: 1;
  min-height: 0;
  position: relative;
}

.chat-session-history :deep(.el-loading-mask) {
  border-radius: 18px;
  background: rgba(255, 255, 255, 0.72);
}

.chat-session-history :deep(.chat-session-strip),
.chat-session-history :deep(.chat-session-groups) {
  height: 100%;
}

.chat-session-history__empty {
  display: flex;
  align-items: center;
  justify-content: center;
  min-height: 160px;
  padding: 24px;
  border: 1px dashed rgba(148, 163, 184, 0.3);
  border-radius: 16px;
  color: var(--page-text-soft, #7c8aa0);
  font-size: 12px;
  line-height: 1.6;
  text-align: center;
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

@media (max-width: 760px) {
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
