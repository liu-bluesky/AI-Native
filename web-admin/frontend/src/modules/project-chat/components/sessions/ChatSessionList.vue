<template>
  <div
    class="chat-session-strip"
    v-loading="loading"
    element-loading-text="正在加载历史会话..."
  >
    <div v-if="!loading && groups.length" class="chat-session-groups">
      <div
        v-for="group in groups"
        :key="group.label"
        class="chat-session-group"
      >
        <div class="chat-session-group__title">{{ group.label }}</div>
        <div class="chat-session-list">
          <button
            v-for="session in group.items"
            :key="session.id"
            type="button"
            class="chat-session-chip"
            :class="{ 'is-active': currentSessionId === session.id }"
            @click="$emit('select', session.id)"
          >
            <div class="chat-session-chip__row">
              <span class="chat-session-chip__title">
                {{ sessionDisplayTitle(session) }}
              </span>
              <el-button
                text
                size="small"
                class="chat-session-chip__delete"
                :icon="Delete"
                :loading="deletingSessionId === session.id"
                @click.stop="$emit('delete', session)"
              />
            </div>
            <span
              v-if="formatChatSessionSourceLabel(session)"
              class="chat-session-chip__source"
            >
              {{ formatChatSessionSourceLabel(session) }}
            </span>
            <span class="chat-session-chip__meta">
              {{ formatChatSessionMeta(session) }}
            </span>
          </button>
        </div>
      </div>
    </div>
    <div v-else-if="!loading" class="chat-session-empty">
      暂无历史会话
    </div>
  </div>
</template>

<script setup>
import { Delete } from "@element-plus/icons-vue";
import { formatRelativeDateTime } from "@/utils/date.js";
import {
  formatChatSessionSourceLabel,
} from "@/modules/project-chat/mappers/messageMappers.js";

defineProps({
  loading: {
    type: Boolean,
    default: false,
  },
  groups: {
    type: Array,
    default: () => [],
  },
  currentSessionId: {
    type: String,
    default: "",
  },
  deletingSessionId: {
    type: String,
    default: "",
  },
});

defineEmits(["select", "delete"]);

function formatChatSessionMeta(session) {
  const count = Number(session?.message_count || 0);
  const time = formatRelativeDateTime(
    session?.last_message_at ||
      session?.updated_at ||
      session?.created_at ||
      "",
    { fallback: "刚刚" },
  );
  return `${count} 条 · ${time}`;
}

function sessionDisplayTitle(session) {
  return (
    String(
      session?.latest_requirement ||
        session?.root_goal ||
        session?.rootGoal ||
        session?.preview ||
        session?.last_message ||
        session?.title ||
        "",
    ).trim() || "新对话"
  );
}
</script>

<style scoped>
.chat-session-strip {
  flex: 1;
  min-height: 0;
  position: relative;
}

.chat-session-strip :deep(.el-loading-mask) {
  border-radius: 18px;
  background: rgba(255, 255, 255, 0.72);
}

.chat-session-groups {
  display: flex;
  flex-direction: column;
  gap: 10px;
  height: 100%;
  overflow: auto;
  padding-right: 4px;
}

.chat-session-group__title {
  padding: 0 6px 4px;
  color: var(--page-text-soft, #7c8aa0);
  font-size: 11px;
  font-weight: 600;
  letter-spacing: 0.04em;
}

.chat-session-list {
  display: flex;
  flex-direction: column;
  gap: 2px;
}

.chat-session-chip {
  padding: 8px 10px;
  border: 0;
  border-radius: 10px;
  background: transparent;
  text-align: left;
  cursor: pointer;
  transition:
    background-color 0.16s ease,
    color 0.16s ease;
}

.chat-session-chip:hover {
  background: rgba(15, 23, 42, 0.05);
}

.chat-session-chip.is-active {
  background: rgba(15, 23, 42, 0.08);
}

.chat-session-chip__row {
  display: flex;
  align-items: center;
  gap: 8px;
  width: 100%;
}

.chat-session-chip__title {
  display: block;
  flex: 1;
  min-width: 0;
  width: auto;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  color: #111827;
  font-size: 12px;
  font-weight: 500;
}

.chat-session-chip__source {
  display: block;
  margin-top: 4px;
  overflow: hidden;
  color: #2563eb;
  font-size: 12px;
  font-weight: 600;
  line-height: 1.4;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.chat-session-chip__delete {
  opacity: 0;
}

.chat-session-chip__delete {
  color: #98a2b3;
}

.chat-session-chip:hover .chat-session-chip__delete,
.chat-session-chip.is-active .chat-session-chip__delete {
  opacity: 1;
}

.chat-session-chip__delete:hover {
  color: #ef4444;
}

.chat-session-chip__meta {
  display: block;
  margin-top: 4px;
  color: #64748b;
  font-size: 11px;
  line-height: 1.4;
}

.chat-session-empty {
  display: flex;
  align-items: center;
  justify-content: center;
  min-height: 160px;
  color: var(--page-text-soft, #7c8aa0);
  font-size: 12px;
}
</style>
