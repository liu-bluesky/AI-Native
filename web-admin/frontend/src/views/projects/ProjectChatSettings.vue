<template>
  <main class="project-chat-settings-page">
    <ProjectChatSettingsContent
      v-if="settingsContext"
      :context="settingsContext"
    />
    <el-empty
      v-else
      description="请先从会话页面打开对话设置"
    />
  </main>
</template>

<script setup>
import ProjectChatSettingsContent from "@/modules/project-chat/components/settings/ProjectChatSettingsContent.vue";
import { getProjectChatSettingsContext } from "@/modules/project-chat/services/project-chat-settings-context.js";

const settingsContext = getProjectChatSettingsContext();
</script>

<style scoped>
.project-chat-settings-page {
  width: 100%;
  min-width: 0;
  height: 100%;
  min-height: 0;
  max-height: 100%;
  overflow: hidden;
}

.project-chat-settings-page :deep(.settings-center-page) {
  height: 100%;
  min-height: 0;
  overflow: hidden;
}

.project-chat-settings-page :deep(.settings-center-shell),
.project-chat-settings-page :deep(.settings-center-stage) {
  height: 100%;
  min-height: 0;
}

.project-chat-settings-page :deep(.settings-center-stage__body--chat) {
  overflow-x: hidden;
  overflow-y: auto !important;
}
</style>
