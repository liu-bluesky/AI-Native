<template>
  <el-dialog
    :model-value="modelValue"
    :title="title"
    width="min(520px, calc(100vw - 32px))"
    destroy-on-close
    class="group-chat-dialog"
    @update:model-value="emit('update:modelValue', $event)"
    @closed="emit('closed')"
  >
    <el-form label-position="top" class="group-chat-dialog__form">
      <el-alert
        v-if="status.text"
        class="group-chat-dialog__status"
        :title="status.title"
        :description="status.text"
        :type="status.type"
        show-icon
        :closable="false"
      />
      <el-form-item label="平台">
        <el-select v-model="draftPlatform" class="full-width">
          <el-option
            v-for="item in platformOptions"
            :key="item.value"
            :label="item.label"
            :value="item.value"
          />
        </el-select>
      </el-form-item>
      <el-form-item label="对话别名">
        <el-input
          v-model="draftTitle"
          placeholder="例如：售前机器人 / 设计助手 / 客服机器人"
          maxlength="80"
          show-word-limit
          @keyup.enter="emit('submit')"
        />
        <div class="group-chat-dialog__hint">
          留空时使用“平台机器人对话”，设置后会显示为最近对话标题。
        </div>
      </el-form-item>
      <el-form-item label="绑定机器人">
        <el-select
          v-model="draftConnectorId"
          class="full-width"
          filterable
          placeholder="选择当前群对话使用的机器人"
          :disabled="!connectorOptions.length"
        >
          <el-option
            v-for="item in connectorOptions"
            :key="item.value"
            :label="item.label"
            :value="item.value"
          >
            <div class="group-chat-dialog__connector-option">
              <strong>{{ item.name }}</strong>
              <span>{{ item.description }}</span>
            </div>
          </el-option>
        </el-select>
        <div class="group-chat-dialog__hint">
          {{ connectorHint }}
        </div>
      </el-form-item>
      <el-form-item label="群名称（可选）">
        <el-input
          v-model="draftExternalChatName"
          placeholder="仅在你后续需要关联真实群消息时填写，例如：产品研发群 / 客户项目群"
          maxlength="80"
          show-word-limit
          @keyup.enter="emit('submit')"
        />
        <div class="group-chat-dialog__hint">
          不填写也能直接创建机器人对话。只有需要同步群消息时，才需要后续解析稳定群
          ID；当前状态：{{ editingResolved ? "已解析" : "未绑定群" }}。
        </div>
      </el-form-item>
      <el-form-item label="解析身份" v-if="draftExternalChatName">
        <el-select
          v-model="draftResolveIdentity"
          class="full-width"
          placeholder="选择解析群 ID 时使用的身份"
        >
          <el-option
            v-for="item in resolveIdentityOptions"
            :key="item.value"
            :label="item.label"
            :value="item.value"
          >
            <div class="group-chat-dialog__connector-option">
              <strong>{{ item.label }}</strong>
              <span>{{ item.description }}</span>
            </div>
          </el-option>
        </el-select>
        <div class="group-chat-dialog__hint">
          机器人身份搜索应用可见群；用户身份搜索当前登录用户可见群。解析失败时先切换身份再重试。
        </div>
      </el-form-item>
    </el-form>
    <template #footer>
      <div class="group-chat-dialog__footer">
        <el-button @click="emit('update:modelValue', false)">取消</el-button>
        <el-button
          v-if="editingSessionId"
          :loading="resolving"
          :disabled="!canResolveSource"
          @click="emit('resolve')"
        >
          {{ editingResolved ? "已解析 ID" : "绑定群 ID" }}
        </el-button>
        <el-button
          type="primary"
          :loading="creating"
          :disabled="!canSubmit"
          @click="emit('submit')"
        >
          {{ editingSessionId ? "保存修改" : "创建机器人对话" }}
        </el-button>
      </div>
    </template>
  </el-dialog>
</template>

<script setup>
import { computed } from "vue";

const props = defineProps({
  modelValue: { type: Boolean, default: false },
  title: { type: String, default: "" },
  status: { type: Object, default: () => ({}) },
  draft: { type: Object, default: () => ({}) },
  platformOptions: { type: Array, default: () => [] },
  connectorOptions: { type: Array, default: () => [] },
  connectorHint: { type: String, default: "" },
  resolveIdentityOptions: { type: Array, default: () => [] },
  editingSessionId: { type: String, default: "" },
  creating: { type: Boolean, default: false },
  resolving: { type: Boolean, default: false },
  editingResolved: { type: Boolean, default: false },
  canSubmit: { type: Boolean, default: false },
});

const emit = defineEmits([
  "update:modelValue",
  "update:draft",
  "closed",
  "resolve",
  "submit",
]);

// 通过浅拷贝回传草稿，避免子组件直接修改父级 ref 对象。
function draftField(key) {
  return computed({
    get: () => props.draft?.[key] ?? "",
    set: (value) => {
      emit("update:draft", {
        ...(props.draft || {}),
        [key]: value,
      });
    },
  });
}

const draftTitle = draftField("title");
const draftPlatform = draftField("platform");
const draftConnectorId = draftField("connector_id");
const draftExternalChatName = draftField("external_chat_name");
const draftResolveIdentity = draftField("resolve_identity");

const canResolveSource = computed(
  () =>
    !props.creating &&
    !props.editingResolved &&
    Boolean(String(props.draft?.external_chat_name || "").trim()),
);
</script>

<style scoped>
.group-chat-dialog__hint {
  margin-top: 6px;
  font-size: 12px;
  line-height: 1.5;
  color: #64748b;
}

.group-chat-dialog__status {
  margin-bottom: 14px;
}

.group-chat-dialog__connector-option {
  display: grid;
  gap: 2px;
  line-height: 1.35;
}

.group-chat-dialog__connector-option strong {
  color: #0f172a;
  font-size: 13px;
}

.group-chat-dialog__connector-option span {
  color: #64748b;
  font-size: 12px;
}

.group-chat-dialog__footer {
  display: flex;
  justify-content: flex-end;
  gap: 8px;
}
</style>
