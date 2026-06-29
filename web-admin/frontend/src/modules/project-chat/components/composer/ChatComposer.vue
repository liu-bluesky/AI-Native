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
            <div class="preview-item__icon">
              <img v-if="file.url" :src="file.url" class="preview-img" />
              <el-icon v-else :size="28"><Document /></el-icon>
            </div>
            <div class="preview-item__body">
              <span class="preview-item__name">{{ file.name }}</span>
              <div class="preview-item__meta">
                <span
                  v-if="file.uploadStatus === 'uploading'"
                  class="preview-item__status preview-item__status--uploading"
                  >上传中...</span
                >
                <span
                  v-else-if="
                    file.uploadStatus === 'ready' && file.providerFileId
                  "
                  class="preview-item__id"
                  >{{ file.providerFileId }}</span
                >
                <span
                  v-else-if="file.uploadStatus === 'fallback'"
                  class="preview-item__status preview-item__status--fallback"
                  >本地解析</span
                >
                <span
                  v-else-if="file.uploadStatus === 'error'"
                  class="preview-item__status preview-item__status--error"
                  >上传失败</span
                >
                <span v-if="file.sizeLabel" class="preview-item__size">
                  {{ file.sizeLabel }}
                </span>
                <span
                  v-if="attachmentSupported && file.processingLabel"
                  class="preview-item__mode"
                  >{{ file.processingLabel }}</span
                >
              </div>
              <span
                v-if="file.uploadStatus === 'error' && file.uploadError"
                class="preview-item__error"
                >{{ file.uploadError }}</span
              >
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
              v-if="isChatSettingsDisplayReady"
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
                        <!-- {{ option.providerLabel }} -->
                      </span>
                    </div>
                    <span class="chat-model-option__type">
                      {{ option.modelTypeLabel }}
                    </span>
                  </div>
                </el-option>
              </el-option-group>
            </el-select>
            <span v-if="modelProviderOffline" class="chat-model-offline-badge">
              离线
            </span>
            <el-tooltip :content="modelProviderSyncTooltip" placement="top">
              <el-button
                class="chat-model-sync-button"
                text
                circle
                :loading="modelProviderSyncing"
                :disabled="chatLoading"
                @click="$emit('sync-model-providers')"
              >
                <el-icon><Refresh /></el-icon>
              </el-button>
            </el-tooltip>
            <div
              v-if="!isChatSettingsDisplayReady"
              class="chat-model-pill is-loading"
            >
              项目配置加载中
            </div>
            <el-upload
              v-if="attachmentSupported"
              action="#"
              :auto-upload="false"
              :show-file-list="false"
              :accept="uploadAccept"
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
              v-if="attachmentSupported"
              action="#"
              :auto-upload="false"
              :show-file-list="false"
              :accept="uploadAccept"
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
            <el-tooltip
              v-else
              :content="`当前模型不支持附件输入${attachmentModeLabel ? '（' + attachmentModeLabel + '）' : ''}`"
              placement="top"
            >
              <el-button text circle disabled>
                <el-icon><Document /></el-icon>
              </el-button>
            </el-tooltip>
            <slot name="media-parameters" />
            <div
              v-if="showLocalAgentAuthLevel"
              class="local-agent-auth-level"
            >
              <span class="local-agent-auth-level__label">授权级别</span>
              <el-select
                v-model="localAgentAuthLevelModel"
                class="local-agent-auth-level__control"
                size="small"
                :disabled="chatLoading"
                :teleported="true"
              >
                <el-option
                  v-for="option in localAgentAuthLevelOptions"
                  :key="option.value"
                  :label="option.label"
                  :value="option.value"
                />
              </el-select>
            </div>
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
              :class="{ 'is-blocked': !canSend }"
              type="primary"
              :aria-disabled="!canSend"
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
  Refresh,
  VideoPause,
} from "@element-plus/icons-vue";

const props = defineProps([
  "agentWorkflowMetaItems",
  "agentWorkflowState",
  "canSend",
  "chatLoading",
  "composerHintText",
  "composerPlaceholder",
  "draftText",
  "externalAgentDisplayLabel",
  "filteredSlashCommands",
  "formatFileType",
  "hasSelectedProject",
  "inputFocused",
  "isChatSettingsDisplayReady",
  "isComposerDisabled",
  "isDragging",
  "isExternalAgentMode",
  "isSlashCommandMenuVisible",
  "localAgentAuthLevel",
  "modelProviderOffline",
  "modelProviderSyncing",
  "modelProviderSyncTooltip",
  "providerModelGroups",
  "selectedModelOptionValue",
  "selectedProjectId",
  "showAgentWorkflowStatusStrip",
  "showLocalAgentAuthLevel",
  "showPauseGenerationButton",
  "showWorkingStatusBar",
  "slashCommandHighlightIndex",
  "attachmentSupported",
  "attachmentMode",
  "attachmentModeLabel",
  "uploadAccept",
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
  "file-change",
  "remove-file",
  "send",
  "sync-model-providers",
  "stop-generation",
  "update:draftText",
  "update:inputFocused",
  "update:localAgentAuthLevel",
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

const localAgentAuthLevelOptions = [
  { label: "询问", value: "ask" },
  { label: "完全访问", value: "full_access" },
];

const localAgentAuthLevelModel = computed({
  get: () => props.localAgentAuthLevel || "ask",
  set: (value) => emit("update:localAgentAuthLevel", value),
});

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
