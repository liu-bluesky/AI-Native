<template>
  <el-dialog
    :model-value="modelValue"
    :title="title"
    width="680px"
    @close="$emit('update:modelValue', false)"
  >
    <div class="picker-shell">
      <div class="picker-copy">
        {{ description }}
      </div>

      <el-form label-width="88px">
        <el-form-item label="模型类型">
          <el-radio-group v-model="draftSourceType" @change="handleSourceTypeChange">
            <el-radio-button
              v-for="item in sourceTypeOptions"
              :key="item.value"
              :label="item.value"
              :disabled="item.disabled"
            >
              {{ item.label }}
            </el-radio-button>
          </el-radio-group>
        </el-form-item>

        <el-form-item v-if="draftSourceType === 'internal'" label="模型源">
          <el-select
            v-model="draftProviderId"
            filterable
            :disabled="!internalProviderOptions.length"
            :placeholder="internalProviderOptions.length ? '请选择模型源' : '当前没有可用内部模型'"
            style="width: 100%"
            :loading="loading"
            @change="handleProviderChange"
          >
            <el-option
              v-for="item in internalProviderOptions"
              :key="item.id"
              :label="item.name"
              :value="item.id"
            />
          </el-select>
        </el-form-item>

        <el-form-item v-if="draftSourceType === 'internal'" label="模型">
          <el-select
            v-model="draftModelName"
            :disabled="!currentInternalModelOptions.length"
            :placeholder="currentInternalModelOptions.length ? '请选择模型' : '当前模型源暂无模型'"
            style="width: 100%"
            :loading="loading"
          >
            <el-option
              v-for="item in currentInternalModelOptions"
              :key="`${item.providerId}-${item.modelName}`"
              :label="item.modelName"
              :value="item.modelName"
            >
              <div class="picker-model-option">
                <span class="picker-model-option__name">{{ item.modelName }}</span>
                <span class="picker-model-option__provider">{{ item.providerName }}</span>
              </div>
            </el-option>
          </el-select>
        </el-form-item>

        <el-form-item v-if="draftSourceType === 'external'" label="连接器">
          <el-select
            v-model="draftLocalConnectorId"
            filterable
            :disabled="!externalConnectorOptions.length"
            :placeholder="externalConnectorOptions.length ? '请选择外部连接器' : '当前没有可用外部连接器'"
            style="width: 100%"
            :loading="loading"
            @change="handleExternalConnectorChange"
          >
            <el-option
              v-for="item in externalConnectorOptions"
              :key="item.id"
              :label="item.name"
              :value="item.id"
            >
              <div class="picker-model-option">
                <span class="picker-model-option__name">{{ item.name }}</span>
                <span class="picker-model-option__provider">
                  {{ item.ownerUsername || "-" }} · {{ item.online ? "在线" : "离线" }}
                </span>
              </div>
            </el-option>
          </el-select>
        </el-form-item>

        <el-form-item v-if="draftSourceType === 'external'" label="外部智能体">
          <el-select
            v-model="draftExternalAgentType"
            :disabled="!currentExternalAgentOptions.length"
            :placeholder="currentExternalAgentOptions.length ? '请选择外部智能体' : '当前连接器没有可用外部智能体'"
            style="width: 100%"
            :loading="loading"
          >
            <el-option
              v-for="item in currentExternalAgentOptions"
              :key="`${draftLocalConnectorId}-${item.agentType}`"
              :label="item.label"
              :value="item.agentType"
              :disabled="!item.available"
            >
              <div class="picker-model-option picker-model-option--stacked">
                <span class="picker-model-option__name">{{ item.label }}</span>
                <span class="picker-model-option__provider">
                  {{ item.available ? "可用" : item.reason || "当前不可用" }}
                </span>
              </div>
            </el-option>
          </el-select>
        </el-form-item>
      </el-form>

      <div v-if="currentSelectionText" class="picker-current">
        当前选择：{{ currentSelectionText }}
      </div>
    </div>

    <template #footer>
      <el-button @click="$emit('update:modelValue', false)">取消</el-button>
      <el-button type="primary" :disabled="confirmDisabled" @click="confirmSelection">
        {{ confirmText }}
      </el-button>
    </template>
  </el-dialog>
</template>

<script setup>
import { computed, ref, watch } from "vue";

const props = defineProps({
  modelValue: {
    type: Boolean,
    default: false,
  },
  title: {
    type: String,
    default: "选择 AI 来源",
  },
  description: {
    type: String,
    default: "先选择本次操作要使用的内部模型或外部智能体 CLI，再继续执行。",
  },
  confirmText: {
    type: String,
    default: "确认",
  },
  internalProviders: {
    type: Array,
    default: () => [],
  },
  externalConnectors: {
    type: Array,
    default: () => [],
  },
  loading: {
    type: Boolean,
    default: false,
  },
  sourceType: {
    type: String,
    default: "internal",
  },
  providerId: {
    type: String,
    default: "",
  },
  modelName: {
    type: String,
    default: "",
  },
  localConnectorId: {
    type: String,
    default: "",
  },
  externalAgentType: {
    type: String,
    default: "codex_cli",
  },
});

const emit = defineEmits([
  "update:modelValue",
  "update:sourceType",
  "update:providerId",
  "update:modelName",
  "update:localConnectorId",
  "update:externalAgentType",
  "confirm",
]);

const draftProviderId = ref("");
const draftModelName = ref("");
const draftSourceType = ref("internal");
const draftLocalConnectorId = ref("");
const draftExternalAgentType = ref("codex_cli");

const internalProviderOptions = computed(() =>
  (Array.isArray(props.internalProviders) ? props.internalProviders : [])
    .map((item) => ({
      id: String(item?.id || "").trim(),
      name: String(item?.name || item?.id || "未命名模型源").trim(),
      models: Array.isArray(item?.models)
        ? item.models.map((model) => String(model || "").trim()).filter(Boolean)
        : [],
      defaultModel: String(item?.default_model || "").trim(),
    }))
    .filter((item) => item.id && item.models.length),
);
const externalConnectorOptions = computed(() =>
  (Array.isArray(props.externalConnectors) ? props.externalConnectors : [])
    .map((item) => ({
      id: String(item?.id || "").trim(),
      name: String(item?.name || item?.connector_name || item?.id || "未命名连接器").trim(),
      ownerUsername: String(item?.owner_username || "").trim(),
      online: Boolean(item?.online),
      agentTypes: Array.isArray(item?.agent_types)
        ? item.agent_types
            .map((agent) => ({
              agentType: String(agent?.agent_type || "").trim(),
              label: String(agent?.label || agent?.agent_type || "外部智能体").trim(),
              available: Boolean(agent?.available),
              reason: String(agent?.reason || "").trim(),
            }))
            .filter((agent) => agent.agentType)
        : [],
    }))
    .filter((item) => item.id),
);
const availableSourceTypeValues = computed(() => {
  const values = new Set();
  if (internalProviderOptions.value.length) {
    values.add("internal");
  }
  if (externalConnectorOptions.value.length) {
    values.add("external");
  }
  return values;
});
const sourceTypeOptions = computed(() => {
  return [
    {
      value: "internal",
      label: "内部",
      disabled: !availableSourceTypeValues.value.has("internal"),
    },
    {
      value: "external",
      label: "外部",
      disabled: !availableSourceTypeValues.value.has("external"),
    },
  ];
});
const currentInternalProvider = computed(
  () =>
    internalProviderOptions.value.find(
      (item) => item.id === String(draftProviderId.value || "").trim(),
    ) || null,
);
const currentExternalConnector = computed(
  () =>
    externalConnectorOptions.value.find(
      (item) => item.id === String(draftLocalConnectorId.value || "").trim(),
    ) || null,
);

const currentInternalModelOptions = computed(() => {
  const provider = currentInternalProvider.value;
  if (!provider) return [];
  return provider.models.map((modelName) => ({
    providerId: provider.id,
    providerName: provider.name,
    modelName,
  }));
});
const currentExternalAgentOptions = computed(() => {
  const connector = currentExternalConnector.value;
  if (!connector) return [];
  return connector.agentTypes;
});

const currentSelectionText = computed(() => {
  if (draftSourceType.value === "external") {
    const connector = currentExternalConnector.value;
    const agentType = String(draftExternalAgentType.value || "").trim();
    const agent = currentExternalAgentOptions.value.find((item) => item.agentType === agentType);
    if (!connector || !agentType || !agent) return "";
    return `${agent.label} · ${connector.name}`;
  }
  const provider = currentInternalProvider.value;
  const modelName = String(draftModelName.value || "").trim();
  if (!provider || !modelName) return "";
  return `${modelName} · ${provider.name}`;
});
const confirmDisabled = computed(() => {
  if (draftSourceType.value === "external") {
    const connector = currentExternalConnector.value;
    const agentType = String(draftExternalAgentType.value || "").trim();
    const agent = currentExternalAgentOptions.value.find((item) => item.agentType === agentType);
    return !connector || !agent || !agent.available;
  }
  return !draftProviderId.value || !draftModelName.value;
});

function firstAvailableSourceType() {
  if (availableSourceTypeValues.value.has("internal")) return "internal";
  if (availableSourceTypeValues.value.has("external")) return "external";
  return "internal";
}

function syncDraftFromProps() {
  const normalizedSourceType = String(props.sourceType || "").trim();
  const normalizedProviderId = String(props.providerId || "").trim();
  const normalizedModelName = String(props.modelName || "").trim();
  const normalizedLocalConnectorId = String(props.localConnectorId || "").trim();
  const normalizedExternalAgentType = String(props.externalAgentType || "").trim();
  const preferredProvider =
    internalProviderOptions.value.find((item) => item.id === normalizedProviderId) || null;
  const preferredConnector =
    externalConnectorOptions.value.find((item) => item.id === normalizedLocalConnectorId) || null;
  draftSourceType.value =
    availableSourceTypeValues.value.has(normalizedSourceType)
      ? normalizedSourceType
      : preferredConnector
        ? "external"
        : preferredProvider
          ? "internal"
          : firstAvailableSourceType();
  const matchedProvider =
    internalProviderOptions.value.find((item) => item.id === normalizedProviderId) ||
    internalProviderOptions.value[0] ||
    null;
  draftProviderId.value = matchedProvider?.id || "";
  const availableModels = matchedProvider?.models || [];
  if (matchedProvider && availableModels.includes(normalizedModelName)) {
    draftModelName.value = normalizedModelName;
  } else {
    draftModelName.value =
      matchedProvider?.defaultModel || availableModels[0] || "";
  }
  const matchedConnector =
    externalConnectorOptions.value.find((item) => item.id === normalizedLocalConnectorId) ||
    externalConnectorOptions.value[0] ||
    null;
  draftLocalConnectorId.value = matchedConnector?.id || "";
  const availableAgents = matchedConnector?.agentTypes || [];
  const preferredAgent = availableAgents.find(
    (item) => item.agentType === normalizedExternalAgentType,
  );
  draftExternalAgentType.value =
    preferredAgent?.agentType ||
    availableAgents.find((item) => item.available)?.agentType ||
    availableAgents[0]?.agentType ||
    "codex_cli";
}

function handleSourceTypeChange(value) {
  const normalizedType = String(value || "internal").trim() || "internal";
  draftSourceType.value = availableSourceTypeValues.value.has(normalizedType)
    ? normalizedType
    : firstAvailableSourceType();
  if (draftSourceType.value === "external") {
    const matchedConnector =
      externalConnectorOptions.value.find(
        (item) => item.id === String(draftLocalConnectorId.value || "").trim(),
      ) || externalConnectorOptions.value[0] || null;
    draftLocalConnectorId.value = matchedConnector?.id || "";
    const availableAgents = matchedConnector?.agentTypes || [];
    draftExternalAgentType.value =
      availableAgents.find((item) => item.available)?.agentType ||
      availableAgents[0]?.agentType ||
      "codex_cli";
    return;
  }
  const matchedProvider =
    internalProviderOptions.value.find(
      (item) => item.id === String(draftProviderId.value || "").trim(),
    ) || internalProviderOptions.value[0] || null;
  draftProviderId.value = matchedProvider?.id || "";
  const availableModels = matchedProvider?.models || [];
  draftModelName.value = matchedProvider?.defaultModel || availableModels[0] || "";
}

function handleProviderChange(value) {
  const normalizedProviderId = String(value || "").trim();
  const matchedProvider =
    internalProviderOptions.value.find((item) => item.id === normalizedProviderId) || null;
  const availableModels = matchedProvider?.models || [];
  if (availableModels.includes(String(draftModelName.value || "").trim())) return;
  draftModelName.value =
    matchedProvider?.defaultModel || availableModels[0] || "";
}

function handleExternalConnectorChange(value) {
  const normalizedConnectorId = String(value || "").trim();
  const matchedConnector =
    externalConnectorOptions.value.find((item) => item.id === normalizedConnectorId) || null;
  const availableAgents = matchedConnector?.agentTypes || [];
  if (
    availableAgents.some(
      (item) =>
        item.agentType === String(draftExternalAgentType.value || "").trim() &&
        item.available,
    )
  ) {
    return;
  }
  draftExternalAgentType.value =
    availableAgents.find((item) => item.available)?.agentType ||
    availableAgents[0]?.agentType ||
    "codex_cli";
}

function confirmSelection() {
  emit("update:sourceType", String(draftSourceType.value || "internal").trim());
  emit("update:providerId", String(draftProviderId.value || "").trim());
  emit("update:modelName", String(draftModelName.value || "").trim());
  emit("update:localConnectorId", String(draftLocalConnectorId.value || "").trim());
  emit("update:externalAgentType", String(draftExternalAgentType.value || "").trim());
  emit("confirm", {
    sourceType: String(draftSourceType.value || "internal").trim(),
    providerId: String(draftProviderId.value || "").trim(),
    modelName: String(draftModelName.value || "").trim(),
    localConnectorId: String(draftLocalConnectorId.value || "").trim(),
    externalAgentType: String(draftExternalAgentType.value || "").trim(),
  });
  emit("update:modelValue", false);
}

watch(
  () => [
    props.modelValue,
    props.sourceType,
    props.providerId,
    props.modelName,
    props.localConnectorId,
    props.externalAgentType,
    internalProviderOptions.value.map((item) => `${item.id}:${item.models.join("|")}`).join("||"),
    externalConnectorOptions.value
      .map((item) => `${item.id}:${item.agentTypes.map((agent) => `${agent.agentType}:${agent.available}`).join("|")}`)
      .join("||"),
  ],
  () => {
    if (!props.modelValue) return;
    syncDraftFromProps();
  },
  { immediate: true },
);
</script>

<style scoped>
.picker-shell {
  display: grid;
  gap: 16px;
}

.picker-copy {
  font-size: 13px;
  line-height: 1.7;
  color: #6b7280;
}

.picker-model-option {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
}

.picker-model-option--stacked {
  align-items: flex-start;
}

.picker-model-option__name {
  color: #161616;
}

.picker-model-option__provider {
  color: #6b7280;
  font-size: 12px;
}

.picker-current {
  padding: 10px 12px;
  border-radius: 14px;
  background: rgba(139, 115, 85, 0.08);
  color: #6c5a44;
  font-size: 13px;
}
</style>
