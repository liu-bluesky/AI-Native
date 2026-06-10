<template>
  <div class="chat-composer">
    <div class="chat-composer-panel">
      <div
        v-if="showAgentWorkflowStatusStrip"
        class="agent-workflow-status"
        :class="`is-${agentWorkflowState.phase}`"
        role="status"
        aria-live="polite"
      >
        <div class="agent-workflow-status__main">
          <span class="agent-workflow-status__dot"></span>
          <div class="agent-workflow-status__copy">
            <strong>{{ agentWorkflowState.title }}</strong>
            <span v-if="agentWorkflowState.detail">
              {{ agentWorkflowState.detail }}
            </span>
          </div>
        </div>
        <div class="agent-workflow-status__side">
          <span
            v-for="item in agentWorkflowMetaItems"
            :key="item"
            class="agent-workflow-status__item"
          >
            {{ item }}
          </span>
          <el-button
            v-if="agentWorkflowState.actionLabel"
            size="small"
            text
            @click="$emit('focus-agent-workflow-operation')"
          >
            {{ agentWorkflowState.actionLabel }}
          </el-button>
        </div>
      </div>
      <div
        v-else-if="showWorkingStatusBar"
        class="chat-working-status"
        role="status"
        aria-live="polite"
      >
        <div class="chat-working-status__main">
          <span class="chat-working-status__dot"></span>
          <strong>{{ workingStatusTitle }}</strong>
          <span>{{ workingStatusElapsedLabel }}</span>
        </div>
        <div class="chat-working-status__meta">
          <span
            v-for="item in workingStatusMetaItems"
            :key="item"
            class="chat-working-status__item"
          >
            {{ item }}
          </span>
        </div>
      </div>
      <div
        ref="inputWrapperRef"
        class="chat-input-wrapper"
        :class="{
          'is-focused': inputFocusedModel,
          'is-dragover': isDragging,
        }"
        @dragover.prevent="$emit('drag-over', $event)"
        @dragleave.prevent="$emit('drag-leave', $event)"
        @drop.prevent="$emit('drop-files', $event)"
      >
        <div v-if="uploadFiles.length > 0" class="upload-preview-area">
          <div
            v-for="(file, idx) in uploadFiles"
            :key="idx"
            class="preview-item"
          >
            <img v-if="file.url" :src="file.url" class="preview-img" />
            <div v-else class="preview-doc">
              <el-icon :size="24"><Document /></el-icon>
              <span class="doc-name">{{ file.name }}</span>
              <span class="doc-type">
                {{ formatUploadFileType(file.name) }}
              </span>
            </div>
            <div class="remove-mask" @click="$emit('remove-file', idx)">
              <el-icon><Delete /></el-icon>
            </div>
          </div>
        </div>

        <el-input
          v-model="draftTextModel"
          type="textarea"
          :autosize="{ minRows: 2, maxRows: 8 }"
          :placeholder="composerPlaceholder"
          resize="none"
          :disabled="isComposerDisabled"
          class="chat-textarea"
          @focus="inputFocusedModel = true"
          @blur="$emit('editor-blur', $event)"
          @keydown="$emit('editor-keydown', $event)"
          @paste="$emit('editor-paste', $event)"
          @compositionstart="$emit('editor-composition-start', $event)"
          @compositionend="$emit('editor-composition-end', $event)"
        />

        <div v-if="isSlashCommandMenuVisible" class="chat-slash-menu">
          <div class="chat-slash-menu__head">
            <span class="chat-slash-menu__title">可用命令</span>
            <span class="chat-slash-menu__summary">
              输入命令后回车发送，或先点选再补充内容
            </span>
          </div>
          <button
            v-for="(item, index) in filteredSlashCommands"
            :key="item.id"
            type="button"
            class="chat-slash-menu__item"
            :class="{ 'is-active': index === slashCommandHighlightIndex }"
            @mousedown.prevent="$emit('apply-slash-command-selection', item)"
          >
            <div class="chat-slash-menu__item-main">
              <span class="chat-slash-menu__command">
                {{ item.command }}
              </span>
              <span class="chat-slash-menu__label">
                {{ item.label }}
              </span>
            </div>
            <div class="chat-slash-menu__description">
              {{ item.description }}
            </div>
          </button>
        </div>

        <div class="input-footer">
          <div class="footer-left">
            <el-select
              v-if="!isExternalAgentMode"
              v-model="selectedModelOptionValueModel"
              class="chat-model-select"
              popper-class="chat-model-select-dropdown"
              size="small"
              filterable
              placeholder="选择模型"
              :disabled="chatLoading || !providerModelGroups.length"
            >
              <el-option-group
                v-for="group in providerModelGroups"
                :key="group.providerId"
                :label="group.label"
              >
                <el-option
                  v-for="option in group.options"
                  :key="option.value"
                  :label="option.label"
                  :value="option.value"
                >
                  <div class="chat-model-option">
                    <div class="chat-model-option__main">
                      <span class="chat-model-option__name">
                        {{ option.modelName }}
                      </span>
                      <span class="chat-model-option__provider">
                        {{ option.providerLabel }}
                      </span>
                    </div>
                    <span class="chat-model-option__type">
                      {{ option.modelTypeLabel }}
                    </span>
                  </div>
                </el-option>
              </el-option-group>
            </el-select>
            <div v-else class="chat-model-pill">
              {{ externalAgentDisplayLabel }}
            </div>
            <ChatExecutionStatusPopover
              :visible="hasSelectedProject"
              :tone-class="executionRuntimeToneClass"
              :chip-label="composerExecutionChipLabel"
              :title="executionRuntimeTitle"
              :description="executionRuntimeDescription"
              :status-tag-type="composerExecutionStatusTagType"
              :status-label="composerExecutionStatusLabel"
              :summary-items="composerExecutionSummaryItems"
              :detail-available="composerExecutionDetailAvailable"
              :native-executor-detecting="nativeExecutorDetecting"
              :native-runner-self-checking="nativeRunnerSelfChecking"
              :external-agent-warmup-loading="externalAgentWarmupLoading"
              :action-label="executionRuntimeActionLabel"
              @open-settings="$emit('open-settings', 'chat')"
              @open-execution-detail="$emit('open-execution-detail')"
              @execute-primary="$emit('execute-primary')"
            />
            <el-upload
              action="#"
              :auto-upload="false"
              :show-file-list="false"
              accept="image/*"
              :multiple="true"
              :on-change="emitFileChange"
              :disabled="isExternalAgentMode || !selectedProjectId"
            >
              <el-tooltip content="添加图片" placement="top">
                <el-button text circle>
                  <el-icon><Picture /></el-icon>
                </el-button>
              </el-tooltip>
            </el-upload>
            <el-upload
              action="#"
              :auto-upload="false"
              :show-file-list="false"
              accept=".wps,.doc,.docx,.pdf,.txt,.csv,.xlsx,.xls"
              :multiple="true"
              :on-change="emitFileChange"
              :disabled="isExternalAgentMode || !selectedProjectId"
            >
              <el-tooltip content="添加文档" placement="top">
                <el-button text circle>
                  <el-icon><Document /></el-icon>
                </el-button>
              </el-tooltip>
            </el-upload>
            <slot name="media-parameters" />
          </div>
          <div class="footer-right">
            <span class="hint-text">{{ composerHintText }}</span>
            <el-tooltip
              v-if="showPauseGenerationButton"
              content="暂停当前回答"
              placement="top"
            >
              <el-button
                class="pause-generation-button"
                type="danger"
                plain
                @click="$emit('stop-generation')"
              >
                <el-icon><VideoPause /></el-icon>
                <span>暂停</span>
              </el-button>
            </el-tooltip>
            <el-button
              class="send-message-button"
              type="primary"
              :disabled="!canSend"
              circle
              @click="$emit('send')"
            >
              <el-icon><Promotion /></el-icon>
            </el-button>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { computed, ref } from "vue";
import {
  Delete,
  Document,
  Picture,
  Promotion,
  VideoPause,
} from "@element-plus/icons-vue";
import ChatExecutionStatusPopover from "../execution-status/ChatExecutionStatusPopover.vue";

const props = defineProps([
  "agentWorkflowMetaItems",
  "agentWorkflowState",
  "canSend",
  "chatLoading",
  "composerExecutionChipLabel",
  "composerExecutionDetailAvailable",
  "composerExecutionStatusLabel",
  "composerExecutionStatusTagType",
  "composerExecutionSummaryItems",
  "composerHintText",
  "composerPlaceholder",
  "draftText",
  "executionRuntimeActionLabel",
  "executionRuntimeDescription",
  "executionRuntimeTitle",
  "executionRuntimeToneClass",
  "externalAgentDisplayLabel",
  "externalAgentWarmupLoading",
  "filteredSlashCommands",
  "formatFileType",
  "hasSelectedProject",
  "inputFocused",
  "isComposerDisabled",
  "isDragging",
  "isExternalAgentMode",
  "isSlashCommandMenuVisible",
  "nativeExecutorDetecting",
  "nativeRunnerSelfChecking",
  "providerModelGroups",
  "selectedModelOptionValue",
  "selectedProjectId",
  "showAgentWorkflowStatusStrip",
  "showPauseGenerationButton",
  "showWorkingStatusBar",
  "slashCommandHighlightIndex",
  "uploadFiles",
  "workingStatusElapsedLabel",
  "workingStatusMetaItems",
  "workingStatusTitle",
]);

const emit = defineEmits([
  "apply-slash-command-selection",
  "drag-leave",
  "drag-over",
  "drop-files",
  "editor-blur",
  "editor-composition-end",
  "editor-composition-start",
  "editor-keydown",
  "editor-paste",
  "execute-primary",
  "file-change",
  "focus-agent-workflow-operation",
  "open-execution-detail",
  "open-settings",
  "remove-file",
  "send",
  "stop-generation",
  "update:draftText",
  "update:inputFocused",
  "update:selectedModelOptionValue",
]);

const inputWrapperRef = ref(null);

const draftTextModel = computed({
  get: () => props.draftText,
  set: (value) => emit("update:draftText", value),
});

const inputFocusedModel = computed({
  get: () => props.inputFocused,
  set: (value) => emit("update:inputFocused", value),
});

const selectedModelOptionValueModel = computed({
  get: () => props.selectedModelOptionValue,
  set: (value) => emit("update:selectedModelOptionValue", value),
});

function formatUploadFileType(name) {
  return typeof props.formatFileType === "function"
    ? props.formatFileType(name)
    : "";
}

function emitFileChange(uploadFile, uploadFiles) {
  emit("file-change", uploadFile, uploadFiles);
}

defineExpose({
  querySelector(selector) {
    return inputWrapperRef.value?.querySelector?.(selector);
  },
});
</script>

<style scoped src="./ChatComposer.css"></style>
