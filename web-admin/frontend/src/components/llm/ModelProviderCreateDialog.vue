<template>
  <el-dialog
    :model-value="modelValue"
    title="新增模型供应商"
    width="min(860px, calc(100vw - 24px))"
    append-to-body
    @update:model-value="$emit('update:modelValue', $event)"
  >
    <el-form :model="form" label-width="120px">
      <el-form-item label="主流模板">
        <div class="provider-preset-panel">
          <div class="provider-preset-row">
            <el-tag v-for="preset in presets" :key="preset.key" class="provider-preset-tag" effect="plain" @click="applyPreset(preset)">{{ preset.label }}</el-tag>
          </div>
          <div class="provider-preset-note">点击模板自动填充接口规范、Base URL 和示例模型；模型名称可按账号权限调整。</div>
        </div>
      </el-form-item>
      <el-form-item label="供应商名称" required><el-input v-model="form.name" placeholder="例如：OpenAI 主账号" /></el-form-item>
      <el-form-item label="接口规范">
        <el-radio-group v-model="form.provider_type">
          <el-radio-button label="openai-compatible">OpenAI-compatible</el-radio-button>
          <el-radio-button label="responses">OpenAI Responses</el-radio-button>
          <el-radio-button label="custom">Custom</el-radio-button>
        </el-radio-group>
      </el-form-item>
      <el-form-item label="Base URL" required><el-input v-model="form.base_url" placeholder="例如：https://api.openai.com/v1" /></el-form-item>
      <el-form-item label="API Key"><el-input v-model="form.api_key" type="password" show-password placeholder="例如：sk-..." /></el-form-item>
      <el-form-item label="模型配置">
        <div class="model-config-editor">
          <div v-for="(model, index) in form.model_configs" :key="model.key" class="model-config-row">
            <el-input v-model="model.name" placeholder="模型名，例如：gpt-5.5" />
            <el-select v-model="model.model_type" placeholder="能力类型"><el-option v-for="option in modelTypeOptions" :key="option.id" :label="option.label" :value="option.id" /></el-select>
            <el-button :type="form.default_model === model.name ? 'primary' : ''" plain @click="form.default_model = model.name">{{ form.default_model === model.name ? '默认模型' : '设为默认' }}</el-button>
            <el-button text type="danger" :disabled="form.model_configs.length <= 1" @click="removeModel(index)">删除</el-button>
          </div>
          <div class="model-config-editor__actions">
            <el-button @click="addModel">添加模型</el-button>
            <el-button :loading="discoveringModels" :disabled="!form.base_url.trim()" @click="discoverModels">获取模型</el-button>
          </div>
        </div>
      </el-form-item>
      <el-form-item label="默认模型">
        <el-select v-model="form.default_model" style="width:100%"><el-option v-for="model in normalizedModels" :key="model.name" :label="model.name" :value="model.name" /></el-select>
      </el-form-item>
      <el-form-item label="额外请求头(JSON)"><el-input v-model="form.extra_headers_text" type="textarea" :rows="3" placeholder='例如：{"X-Provider":"demo"}' /></el-form-item>
      <el-form-item label="启用"><el-switch v-model="form.enabled" /></el-form-item>
    </el-form>
    <template #footer><el-button @click="close">取消</el-button><el-button type="primary" :loading="saving" @click="save">保存</el-button></template>
  </el-dialog>
</template>

<script setup>
import { computed, reactive, ref, watch } from "vue";
import { ElMessage } from "element-plus";
import { FALLBACK_MODEL_TYPE_OPTIONS, normalizeProviderModelConfigs } from "@/utils/llm-models.js";
import { readLocalEntities, writeLocalEntities } from "@/services/local-project-repository.js";
import { discoverNativeProviderModels, hasNativeDesktopBridge } from "@/utils/native-desktop-bridge.js";
import { getStoredAuthProfile } from "@/utils/auth-storage.js";

const props = defineProps({ modelValue: Boolean });
const emit = defineEmits(["update:modelValue", "saved"]);
const saving = ref(false);
const discoveringModels = ref(false);
const modelTypeOptions = FALLBACK_MODEL_TYPE_OPTIONS;
const presets = [
  { key: "openai", label: "OpenAI", name: "OpenAI", provider_type: "responses", base_url: "https://api.openai.com/v1", model_configs: [{ name: "gpt-5.5", model_type: "multimodal_chat" }], default_model: "gpt-5.5" },
  { key: "deepseek", label: "DeepSeek", name: "DeepSeek", provider_type: "openai-compatible", base_url: "https://api.deepseek.com/v1", model_configs: [{ name: "deepseek-chat", model_type: "text_generation" }], default_model: "deepseek-chat" },
  { key: "ollama", label: "Ollama", name: "Ollama 本地模型", provider_type: "openai-compatible", base_url: "http://127.0.0.1:11434/v1", model_configs: [{ name: "qwen3", model_type: "text_generation" }], default_model: "qwen3" },
];
function createModel(name = "", modelType = "text_generation") { return { key: `${Date.now()}-${Math.random()}`, name, model_type: modelType }; }
const form = reactive({ name: "", provider_type: "openai-compatible", base_url: "", api_key: "", model_configs: [createModel()], default_model: "", enabled: true, extra_headers_text: "" });
const normalizedModels = computed(() => normalizeProviderModelConfigs({ model_configs: form.model_configs }, modelTypeOptions));
function reset() { form.name = ""; form.provider_type = "openai-compatible"; form.base_url = ""; form.api_key = ""; form.model_configs = [createModel()]; form.default_model = ""; form.enabled = true; form.extra_headers_text = ""; }
function close() { emit("update:modelValue", false); }
function applyPreset(preset) { form.name = preset.name; form.provider_type = preset.provider_type; form.base_url = preset.base_url; form.model_configs = preset.model_configs.map((model) => createModel(model.name, model.model_type)); form.default_model = preset.default_model; }
function addModel() { form.model_configs.push(createModel()); }
function removeModel(index) { form.model_configs.splice(index, 1); if (!form.model_configs.length) form.model_configs.push(createModel()); if (!form.model_configs.some((model) => model.name === form.default_model)) form.default_model = ""; }
function createId() { return typeof crypto !== "undefined" && crypto.randomUUID ? `local-provider-${crypto.randomUUID()}` : `local-provider-${Date.now()}-${Math.random().toString(36).slice(2, 10)}`; }
function parseHeaders() { const raw = String(form.extra_headers_text || "").trim(); if (!raw) return {}; const parsed = JSON.parse(raw); if (!parsed || typeof parsed !== "object" || Array.isArray(parsed)) throw new Error("额外请求头必须是 JSON 对象"); return parsed; }
async function discoverModels() {
  if (!form.base_url.trim()) return ElMessage.warning("请先填写 Base URL");
  let extraHeaders;
  try { extraHeaders = parseHeaders(); } catch (error) { return ElMessage.error(error.message); }
  if (!hasNativeDesktopBridge()) return ElMessage.error("当前环境不支持本地模型获取，请在桌面应用中操作");
  discoveringModels.value = true;
  try {
    const result = await discoverNativeProviderModels({ providerType: form.provider_type, baseUrl: form.base_url.trim(), apiKey: form.api_key.trim(), extraHeaders });
    const values = Array.isArray(result?.models) ? result.models : Array.isArray(result?.data) ? result.data : [];
    const names = [...new Set(values.map((item) => String(typeof item === "object" ? item?.id || item?.name || item?.model : item || "").trim()).filter(Boolean))];
    if (!names.length) throw new Error("供应商没有返回可用模型，请检查 API Key 和接口地址");
    const existing = new Map(form.model_configs.map((item) => [String(item.name || "").trim(), item]));
    form.model_configs = names.map((name) => existing.get(name) || createModel(name));
    if (!form.default_model || !names.includes(form.default_model)) form.default_model = names[0];
    ElMessage.success(`已获取 ${names.length} 个模型，请确认后保存`);
  } catch (error) {
    ElMessage.error(error?.detail || error?.message || "获取模型失败");
  } finally { discoveringModels.value = false; }
}
function save() {
  const name = String(form.name || "").trim(); const baseUrl = String(form.base_url || "").trim(); const models = normalizedModels.value;
  if (!name || !baseUrl) return ElMessage.warning("请填写供应商名称和 Base URL");
  if (!models.length) return ElMessage.warning("请至少添加一个模型");
  let extraHeaders; try { extraHeaders = parseHeaders(); } catch (error) { return ElMessage.error(error.message); }
  saving.value = true;
  try {
    const now = new Date().toISOString(); const defaultModel = models.some((model) => model.name === form.default_model) ? form.default_model : models[0].name;
    const profile = getStoredAuthProfile();
    writeLocalEntities("llm_providers", [...readLocalEntities("llm_providers"), { id: createId(), name, provider_type: form.provider_type, base_url: baseUrl, api_key: String(form.api_key || "").trim(), model_configs: models, default_model: defaultModel, enabled: Boolean(form.enabled), extra_headers: extraHeaders, shared_usernames: [], created_by: String(profile.username || "local-user").trim() || "local-user", owner_username: String(profile.username || "local-user").trim() || "local-user", can_manage: true, created_at: now, updated_at: now }]);
    ElMessage.success("模型供应商已创建"); close(); emit("saved");
  } catch (error) { ElMessage.error(error?.message || "保存失败"); } finally { saving.value = false; }
}
watch(() => props.modelValue, (visible) => { if (visible) reset(); });
</script>

<style scoped>
.provider-preset-panel,.model-config-editor { width:100%; padding:12px; border:1px solid #e2e8f0; border-radius:12px; background:#f8fafc; }.provider-preset-row { display:flex; flex-wrap:wrap; gap:8px; }.provider-preset-tag { cursor:pointer; }.provider-preset-note { margin-top:10px; color:#64748b; font-size:12px; }.model-config-editor { display:grid; gap:10px; }.model-config-row { display:grid; grid-template-columns:minmax(160px,1fr) minmax(130px,.7fr) auto auto; gap:8px; align-items:center; }.model-config-editor__actions { display:flex; gap:8px; } @media (max-width:700px) { .model-config-row { grid-template-columns:1fr; } }
</style>
