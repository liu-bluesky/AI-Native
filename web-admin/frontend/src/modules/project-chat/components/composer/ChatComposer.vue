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
        <div v-if="contextRefs.length" class="composer-context-area">
          <div class="composer-context-area__header">
            <span>已追加 {{ contextRefs.length }} 项会话内容</span>
            <el-button text size="small" @click="$emit('clear-context-refs')">
              清空
            </el-button>
          </div>
          <div class="composer-context-list">
            <div
              v-for="item in contextRefs"
              :key="item.id"
              class="composer-context-card"
            >
              <div class="composer-context-card__preview">
                <img
                  v-if="item.type === 'image' && item.url"
                  :src="item.url"
                  alt=""
                />
                <video
                  v-else-if="item.type === 'video' && item.url"
                  :src="item.url"
                  muted
                  preload="metadata"
                />
                <el-icon v-else-if="item.type === 'image'"><Picture /></el-icon>
                <el-icon v-else-if="item.type === 'video'"><VideoPause /></el-icon>
                <el-icon v-else><Document /></el-icon>
              </div>
              <div class="composer-context-card__body">
                <span class="composer-context-card__type">{{
                  contextRefTypeLabel(item.type)
                }}</span>
                <strong>{{ item.label }}</strong>
                <span v-if="item.content">{{ item.content }}</span>
              </div>
              <button
                type="button"
                class="composer-context-card__remove"
                aria-label="移除引用内容"
                @click="$emit('remove-context-ref', item.id)"
              >
                ×
              </button>
            </div>
          </div>
        </div>
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
            <el-button
              v-if="isChatSettingsDisplayReady"
              class="chat-model-routing-trigger"
              :disabled="chatLoading || !providerModelGroups.length"
              @click="modelRoutingDialogVisible = true"
            >
              <el-icon><Setting /></el-icon>
              <span class="chat-model-routing-trigger__mode">
                主模型编排
              </span>
              <span class="chat-model-routing-trigger__summary">
                {{ activeModelSummary || "选择模型" }}
              </span>
            </el-button>
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

    <el-dialog
      v-model="modelRoutingDialogVisible"
      title="对话模型配置"
      width="min(720px, 92vw)"
      append-to-body
      destroy-on-close
      class="chat-model-routing-dialog"
    >
      <div class="chat-model-routing-dialog__intro">
        主模型是唯一对话入口，负责理解意图并通过结构化工具调用图片、视频和音频模型。
      </div>
      <div class="chat-model-routing-roles">
        <section
          v-for="role in modelRoutingRoles"
          :key="role.id"
          class="chat-model-routing-role"
        >
          <div class="chat-model-routing-role__copy">
            <strong>{{ role.label }}</strong>
            <span>{{ role.description }}</span>
          </div>
          <el-select
            :model-value="role.value"
            filterable
            clearable
            :placeholder="role.id === 'main' ? '请选择主对话模型' : '未配置'"
            @update:model-value="
              $emit('update:modelRoleSelection', {
                roleId: role.id,
                value: $event,
              })
            "
          >
            <el-option-group
              v-for="group in role.groups"
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
                  <span class="chat-model-option__name">{{ option.modelName }}</span>
                  <span class="chat-model-option__type">{{ option.modelTypeLabel }}</span>
                </div>
              </el-option>
            </el-option-group>
          </el-select>
        </section>
      </div>
      <template #footer>
        <el-button type="primary" @click="modelRoutingDialogVisible = false">
          完成
        </el-button>
      </template>
    </el-dialog>
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
  Setting,
  VideoPause,
} from "@element-plus/icons-vue";

const props = defineProps([
  "agentWorkflowMetaItems",
  "agentWorkflowState",
  "canSend",
  "chatLoading",
  "composerHintText",
  "composerPlaceholder",
  "contextRefs",
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
  "modelRoutingMode",
  "modelRoutingRoles",
  "manualModelOptionValue",
  "activeModelSummary",
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
  "clear-context-refs",
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
  "remove-context-ref",
  "send",
  "sync-model-providers",
  "stop-generation",
  "update:draftText",
  "update:inputFocused",
  "update:localAgentAuthLevel",
  "update:manualModelOptionValue",
  "update:modelRoleSelection",
  "update:modelRoutingMode",
  "update:selectedModelOptionValue",
]);

const inputWrapperRef = ref(null);
const modelRoutingDialogVisible = ref(false);

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

function contextRefTypeLabel(type) {
  return (
    {
      image: "图片",
      video: "视频",
      audio: "音频",
      file: "附件",
      text: "选中文字",
      message: "历史消息",
    }[String(type || "").trim()] || "会话内容"
  );
}

defineExpose({
  querySelector(selector) {
    return inputWrapperRef.value?.querySelector?.(selector);
  },
});
</script>

<style scoped src="./ChatComposer.css"></style>
