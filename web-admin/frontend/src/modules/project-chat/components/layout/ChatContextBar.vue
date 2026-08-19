<template>
  <div class="chat-context-bar">
    <div ref="contextBarRef" class="chat-context-bar__surface">
      <div class="chat-context-bar__copy">
        <div class="chat-context-bar__eyebrow">AI Operating System</div>
        <el-select
          class="chat-context-bar__project-select"
          :model-value="selectedProjectId"
          filterable
          placeholder="选择项目后开始对话"
          @update:model-value="handleProjectChange"
        >
          <el-option
            v-for="project in projects"
            :key="project.id"
            :label="project.name || project.id"
            :value="project.id"
          />
        </el-select>
        <div class="chat-context-bar__meta">
          <span v-if="sessionSourceLabel">{{ sessionSourceLabel }}</span>
          <span>{{ modelSummary }}</span>
          <span>{{ statusText }}</span>
          <span v-if="offlineStatusText">{{ offlineStatusText }}</span>
        </div>
      </div>
      <div class="chat-context-bar__actions">
        <el-button
          ref="guideButtonRef"
          size="small"
          class="chat-context-bar__action-button chat-context-bar__action-button--guide"
          @click="emit('start-guide', true)"
        >
          使用引导
        </el-button>
        <el-button
          v-if="hasSelectedProject"
          size="small"
          plain
          class="chat-context-bar__action-button"
          @click="emit('open-project-detail')"
        >
          项目详情
        </el-button>
        <el-button
          v-if="canTrustWorkspace"
          size="small"
          plain
          class="chat-context-bar__action-button"
          :loading="workspaceTrustSaving"
          @click="emit('trust-workspace')"
        >
          信任工作区
        </el-button>
        <el-button
          size="small"
          plain
          class="chat-context-bar__action-button"
          @click="emit('open-mcp')"
        >
          MCP 接入
        </el-button>
        <el-button
          size="small"
          plain
          class="chat-context-bar__action-button"
          @click="emit('open-skill-resource')"
        >
          技能资源
        </el-button>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref } from "vue";

defineProps({
  hasSelectedProject: { type: Boolean, default: false },
  projects: { type: Array, default: () => [] },
  selectedProjectId: { type: String, default: "" },
  sessionSourceLabel: { type: String, default: "" },
  modelSummary: { type: String, default: "" },
  statusText: { type: String, default: "" },
  offlineStatusText: { type: String, default: "" },
  canTrustWorkspace: { type: Boolean, default: false },
  workspaceTrustSaving: { type: Boolean, default: false },
});

const emit = defineEmits([
  "start-guide",
  "open-project-detail",
  "trust-workspace",
  "open-mcp",
  "open-skill-resource",
  "project-change",
]);

const guideButtonRef = ref(null);
const contextBarRef = ref(null);

function handleProjectChange(projectId) {
  const normalizedProjectId = String(projectId || "").trim();
  if (!normalizedProjectId) return;
  emit("project-change", normalizedProjectId);
}

// 保留父页引导定位能力，只暴露 DOM 锚点，不把上下文栏内部结构上提。
defineExpose({
  guideButtonRef,
  contextBarRef,
});
</script>

<style scoped>
/* 上下文栏抽离后独立维护面板样式，避免依赖父页 scoped 选择器穿透。 */
.chat-context-bar {
  padding: 0 0 8px;
}

.chat-context-bar__surface {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 14px;
  padding: 14px 18px;
  border: 1px solid rgba(255, 255, 255, 0.78);
  border-radius: 26px;
  background:
    radial-gradient(
      circle at top right,
      rgba(103, 232, 249, 0.12),
      transparent 34%
    ),
    radial-gradient(
      circle at top left,
      rgba(125, 211, 252, 0.12),
      transparent 26%
    ),
    rgba(255, 255, 255, 0.54);
  box-shadow: inset 0 1px 0 rgba(255, 255, 255, 0.86);
}

.chat-context-bar__copy {
  min-width: 0;
  flex: 1;
}

.chat-context-bar__eyebrow {
  color: var(--page-text-soft, #7c8aa0);
  font-size: 11px;
  line-height: 1;
  font-weight: 700;
  letter-spacing: 0.12em;
  text-transform: uppercase;
}

.chat-context-bar__project-select {
  display: block;
  width: min(100%, 360px);
  margin-top: 7px;
}

.chat-context-bar__project-select :deep(.el-select__wrapper) {
  min-height: 40px;
  padding: 4px 12px;
  border: 1px solid rgba(15, 23, 42, 0.1);
  border-radius: 12px;
  background: rgba(255, 255, 255, 0.88);
  box-shadow: none;
}

.chat-context-bar__project-select :deep(.el-select__placeholder),
.chat-context-bar__project-select :deep(.el-select__selected-item) {
  color: #0f172a;
  font-size: 15px;
  font-weight: 600;
}

.chat-context-bar__meta {
  display: inline-flex;
  align-items: center;
  flex-wrap: wrap;
  justify-content: flex-start;
  gap: 4px 8px;
  margin-top: 8px;
  color: var(--page-text-soft, #7c8aa0);
  font-size: 12px;
  line-height: 1.4;
}

.chat-context-bar__meta span:not(:last-child)::after {
  content: "·";
  margin-left: 10px;
  color: #c0c4cc;
}

.chat-context-bar__actions {
  display: flex;
  align-items: center;
  justify-content: flex-end;
  gap: 8px;
  flex-shrink: 0;
  flex-wrap: wrap;
  width: auto;
  align-self: flex-end;
}

.chat-context-bar__action-button {
  border-color: rgba(15, 23, 42, 0.08) !important;
  border-radius: 999px !important;
  background: rgba(255, 255, 255, 0.86) !important;
  color: #334155 !important;
  font-weight: 600;
  box-shadow: 0 8px 18px rgba(15, 23, 42, 0.05);
}

.chat-context-bar__action-button:hover {
  border-color: rgba(56, 189, 248, 0.24) !important;
  background: #ffffff !important;
  color: #0f172a !important;
}

@media (max-width: 1120px) {
  .chat-context-bar__surface {
    flex-direction: column;
    align-items: flex-start;
    padding: 16px;
  }

  .chat-context-bar__actions {
    width: 100%;
    justify-content: flex-start;
  }
}

@media (max-width: 640px) {
  .chat-context-bar__meta {
    display: flex;
    flex-direction: column;
    gap: 4px;
  }

  .chat-context-bar__meta span:not(:last-child)::after {
    display: none;
  }

  .chat-context-bar__surface {
    padding: 14px;
    border-radius: 22px;
  }

  .chat-context-bar__title {
    font-size: 30px;
  }
}
</style>
