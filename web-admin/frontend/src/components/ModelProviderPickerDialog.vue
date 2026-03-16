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
        <el-form-item label="模型源">
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

        <el-form-item label="模型">
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
    default: "先选择本次操作要使用的模型，再继续执行。",
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
  providerId: {
    type: String,
    default: "",
  },
  modelName: {
    type: String,
    default: "",
  },
});

const emit = defineEmits([
  "update:modelValue",
  "update:providerId",
  "update:modelName",
  "confirm",
]);

const draftProviderId = ref("");
const draftModelName = ref("");

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
const currentInternalProvider = computed(
  () =>
    internalProviderOptions.value.find(
      (item) => item.id === String(draftProviderId.value || "").trim(),
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
const currentSelectionText = computed(() => {
  const provider = currentInternalProvider.value;
  const modelName = String(draftModelName.value || "").trim();
  if (!provider || !modelName) return "";
  return `${modelName} · ${provider.name}`;
});
const confirmDisabled = computed(() => !draftProviderId.value || !draftModelName.value);

function syncDraftFromProps() {
  const normalizedProviderId = String(props.providerId || "").trim();
  const normalizedModelName = String(props.modelName || "").trim();
  const preferredProvider =
    internalProviderOptions.value.find((item) => item.id === normalizedProviderId) || null;
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

function confirmSelection() {
  emit("update:providerId", String(draftProviderId.value || "").trim());
  emit("update:modelName", String(draftModelName.value || "").trim());
  emit("confirm", {
    sourceType: "internal",
    providerId: String(draftProviderId.value || "").trim(),
    modelName: String(draftModelName.value || "").trim(),
  });
  emit("update:modelValue", false);
}

watch(
  () => [
    props.modelValue,
    props.providerId,
    props.modelName,
    internalProviderOptions.value.map((item) => `${item.id}:${item.models.join("|")}`).join("||"),
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
