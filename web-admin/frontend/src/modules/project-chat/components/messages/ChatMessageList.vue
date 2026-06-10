<template>
  <div class="message-list-inner">
    <div v-if="historyLoading" class="chat-history-loading-state">
      <div class="chat-history-loading-state__title">
        正在加载对话记录
      </div>
      <div class="chat-history-loading-state__text">
        历史消息同步中，请稍候。
      </div>
    </div>
    <div v-else-if="!messages.length" class="chat-empty-state">
      <div class="chat-empty-state__hero">
        <div class="chat-empty-badge">
          {{
            hasSelectedProject
              ? "Project Context Ready"
              : hasAccessibleProjects
                ? "General Chat"
                : "Access Pending"
          }}
        </div>
        <div class="chat-empty-title">{{ emptyStateTitle }}</div>
        <div class="chat-empty-text">{{ emptyStateText }}</div>
      </div>
      <div v-if="starterPrompts.length" class="chat-empty-actions">
        <button
          v-for="prompt in starterPrompts"
          :key="prompt"
          type="button"
          class="chat-empty-action"
          @click="$emit('apply-starter-prompt', prompt)"
        >
          {{ prompt }}
        </button>
      </div>
    </div>
    <template v-else>
      <div
        v-if="historyHasMore || historyLoadingMore"
        class="chat-history-loader"
      >
        <el-button
          text
          class="chat-history-loader__button"
          :loading="historyLoadingMore"
          @click="$emit('load-older')"
        >
          {{
            historyLoadingMore
              ? "正在加载更早消息..."
              : "加载更早消息"
          }}
        </el-button>
      </div>
      <slot />
    </template>
  </div>
</template>

<script setup>
defineProps({
  historyLoading: {
    type: Boolean,
    default: false,
  },
  messages: {
    type: Array,
    default: () => [],
  },
  hasSelectedProject: {
    type: Boolean,
    default: false,
  },
  hasAccessibleProjects: {
    type: Boolean,
    default: false,
  },
  emptyStateTitle: {
    type: String,
    default: "",
  },
  emptyStateText: {
    type: String,
    default: "",
  },
  starterPrompts: {
    type: Array,
    default: () => [],
  },
  historyHasMore: {
    type: Boolean,
    default: false,
  },
  historyLoadingMore: {
    type: Boolean,
    default: false,
  },
});

defineEmits(["apply-starter-prompt", "load-older"]);
</script>

<style src="./ChatMessageList.css"></style>
