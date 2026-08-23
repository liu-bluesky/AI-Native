<template>
  <div class="voice-library">
    <section class="voice-library__hero">
      <div class="voice-library__copy">
        <div class="voice-library__eyebrow">Voice Studio</div>
        <h1 class="voice-library__title">项目音色模块</h1>
        <p class="voice-library__text">
          把角色声音沉淀成项目资产，旁白和角色配音都能直接复用。
        </p>
      </div>
      <div class="voice-library__actions">
        <el-button
          type="primary"
          :disabled="!audioProviderOptions.length"
          @click="openCreateDialog"
        >
          登记项目音色
        </el-button>
      </div>
    </section>

    <section class="voice-library__panel">
      <div class="voice-library__panel-head">
        <div>
          <div class="voice-library__panel-title">可用音色</div>
          <div class="voice-library__panel-desc">
            已沉淀 {{ voices.length }} 个项目音色
          </div>
        </div>
        <div class="voice-library__panel-meta">
          <span>{{ audioProviderOptions.length }} 个音频模型源</span>
          <span>{{ projectId || "未绑定项目" }}</span>
        </div>
      </div>

      <el-alert
        v-if="!audioProviderOptions.length"
        class="voice-library__notice"
        type="warning"
        :closable="false"
        title="还没有可用的音频模型源"
        description="先到系统设置里接入一个支持音频生成的模型源。"
      />

      <div v-if="voices.length" class="voice-library__grid">
        <article v-for="item in voices" :key="item.id" class="voice-card">
          <div class="voice-card__head">
            <div>
              <div class="voice-card__eyebrow">
                {{ sourceTypeLabel(item.source_type) }}
              </div>
              <div class="voice-card__title">{{ item.name }}</div>
              <div class="voice-card__meta">
                {{ providerLabel(item.provider_id) }} · {{ item.model_name }}
              </div>
            </div>
            <span class="voice-card__status">{{
              statusLabel(item.status)
            }}</span>
          </div>
          <p v-if="item.description" class="voice-card__desc">
            {{ item.description }}
          </p>
          <dl class="voice-card__details">
            <div>
              <dt>音色 ID</dt>
              <dd>{{ item.voice_id }}</dd>
            </div>
            <div>
              <dt>试听文本</dt>
              <dd>{{ item.preview_text || "未填写" }}</dd>
            </div>
            <div>
              <dt>本地音频</dt>
              <dd>{{ localAudioFileName(item) || "未保存" }}</dd>
            </div>
          </dl>
          <div
            class="voice-card__preview"
            :class="{ 'is-empty': !resolveVoiceAudioUrl(item) }"
          >
            <div class="voice-card__preview-head">
              <div class="voice-card__preview-title">
                本地音频
              </div>
              <div class="voice-card__preview-text">
                {{
                  resolveVoiceAudioUrl(item)
                    ? "保留的本地音频文件"
                    : "未保存可播放的本地音频"
                }}
              </div>
            </div>
            <audio
              v-if="resolveVoiceAudioUrl(item)"
              class="voice-card__audio"
              :src="resolveVoiceAudioUrl(item)"
              controls
              preload="none"
            />
            <div v-else class="voice-card__preview-empty">
              暂无可播放音频
            </div>
          </div>
          <div class="voice-card__actions">
            <div class="voice-card__actions-main">
              <el-button
                size="small"
                plain
                @click="openEditDialog(item)"
              >
                编辑
              </el-button>
            </div>
            <el-button
              text
              type="danger"
              :loading="deletingId === item.id"
              @click="removeVoice(item)"
            >
              删除
            </el-button>
          </div>
        </article>
      </div>
      <el-empty v-else description="还没有创建项目音色" :image-size="72" />
    </section>

    <el-dialog
      v-model="dialogVisible"
      width="min(640px, calc(100vw - 32px))"
      class="voice-library-dialog"
      destroy-on-close
    >
      <template #header>
        <div class="voice-library-dialog__header">
          <div class="voice-library__eyebrow">
            {{ dialogMode === "edit" ? "Edit Voice" : "Create Voice" }}
          </div>
          <div class="voice-library-dialog__title">
            {{ dialogMode === "edit" ? "编辑项目音色" : "创建自定义音色" }}
          </div>
          <div class="voice-library-dialog__desc">
            {{
              dialogMode === "edit"
                ? "更新名称、供应商音色 ID、试听文案和备注。"
                : "登记供应商已有的音色 ID，信息仅保存到当前桌面项目。"
            }}
          </div>
        </div>
      </template>

      <div class="voice-library-dialog__body">
        <div class="voice-library-form-grid">
          <label class="voice-library-field">
            <span>模型源</span>
            <el-select
              v-model="form.providerId"
              placeholder="选择模型源"
              :disabled="dialogMode === 'edit'"
            >
              <el-option
                v-for="option in audioProviderOptions"
                :key="option.id"
                :label="option.name"
                :value="option.id"
              />
            </el-select>
          </label>
          <label class="voice-library-field">
            <span>模型</span>
            <el-select
              v-model="form.modelName"
              placeholder="选择模型"
              :disabled="dialogMode === 'edit'"
            >
              <el-option
                v-for="option in audioModelOptions"
                :key="`${form.providerId}-${option}`"
                :label="option"
                :value="option"
              />
            </el-select>
          </label>
        </div>

        <div class="voice-library-form-grid voice-library-form-grid--single">
          <label class="voice-library-field">
            <span>音色名称</span>
            <el-input
              v-model="form.name"
              placeholder="例如：女主旁白 · 冷静版"
            />
          </label>
          <label class="voice-library-field">
            <span>音色 ID</span>
            <el-input
              v-model="form.voiceId"
              placeholder="填写供应商侧的 voice_id"
            />
          </label>
          <label class="voice-library-field">
            <span>试听文本</span>
            <el-input
              v-model="form.previewText"
              type="textarea"
              :rows="3"
              placeholder="用于标记该音色的推荐试听文案。"
            />
          </label>
          <label class="voice-library-field">
            <span>备注</span>
            <el-input
              v-model="form.description"
              type="textarea"
              :rows="3"
              placeholder="一句话备注适合的角色场景。"
            />
          </label>
        </div>

      </div>

      <template #footer>
        <div class="voice-library-dialog__footer">
          <div class="voice-library-dialog__hint">
            {{
              dialogMode === "edit"
                ? "修改仅写入当前桌面项目的音色元数据。"
                : "登记后会立即加入当前项目的本地音色列表。"
            }}
          </div>
          <el-button @click="dialogVisible = false">取消</el-button>
          <el-button type="primary" :loading="submitting" @click="submitForm">
            {{ dialogMode === "edit" ? "保存修改" : "创建音色" }}
          </el-button>
        </div>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { computed, onBeforeUnmount, onMounted, reactive, ref, watch } from "vue";
import { useRoute } from "vue-router";
import { ElMessage, ElMessageBox } from "element-plus";

import { normalizeProviderModelConfigs } from "@/utils/llm-models.js";
import { readLocalModelProviders } from "@/services/local-model-runtime.js";
import {
  getLocalProjectRelations,
  updateLocalProjectRelations,
} from "@/services/local-project-repository.js";
import {
  getStoredProjectContextId,
  setStoredProjectContextId,
} from "@/utils/desktop-shell.js";

const route = useRoute();

const projectId = computed(() =>
  String(route.query.project_id || "").trim() || getStoredProjectContextId(),
);
const dialogVisible = ref(false);
const dialogMode = ref("create");
const editingVoiceId = ref("");
const submitting = ref(false);
const deletingId = ref("");
const providers = ref([]);
const voices = ref([]);

watch(projectId, (value) => {
  const normalizedProjectId = String(value || "").trim();
  if (!normalizedProjectId) return;
  setStoredProjectContextId(normalizedProjectId);
});

const form = reactive({
  providerId: "",
  modelName: "",
  name: "",
  voiceId: "",
  previewText: "你好，这是一段用于标记音色的试听文本。",
  description: "",
});

function normalizeAudioProviders(items) {
  return (Array.isArray(items) ? items : [])
    .map((item) => {
      const audioModelConfigs = normalizeProviderModelConfigs(item)
        .map((model) => ({
          name: String(model?.name || "").trim(),
          modelType: String(model?.model_type || "").trim(),
        }))
        .filter(
          (model) => model.name && model.modelType === "audio_generation",
        );
      if (!audioModelConfigs.length) return null;
      const models = audioModelConfigs.map((item) => item.name);
      const defaultModel =
        audioModelConfigs.find(
          (model) => model.name === String(item?.default_model || "").trim(),
        )?.name ||
        audioModelConfigs[0]?.name ||
        "";
      return {
        id: String(item?.id || "").trim(),
        name: String(item?.name || item?.id || "未命名模型源").trim(),
        models,
        defaultModel,
      };
    })
    .filter(Boolean);
}

const audioProviderOptions = computed(() =>
  normalizeAudioProviders(providers.value),
);

const audioModelOptions = computed(() => {
  const target = audioProviderOptions.value.find(
    (item) => item.id === String(form.providerId || "").trim(),
  );
  return target?.models || [];
});

function syncModelSelection() {
  const provider =
    audioProviderOptions.value.find((item) => item.id === form.providerId) ||
    audioProviderOptions.value[0] ||
    null;
  if (!provider) {
    form.providerId = "";
    form.modelName = "";
    return;
  }
  form.providerId = provider.id;
  const allowedModels = audioModelOptions.value;
  form.modelName = allowedModels.includes(form.modelName)
    ? form.modelName
    : allowedModels[0] || provider.defaultModel || provider.models[0] || "";
}

function providerLabel(providerId) {
  return (
    audioProviderOptions.value.find((item) => item.id === providerId)?.name ||
    providerId ||
    "模型源"
  );
}

function sourceTypeLabel(sourceType) {
  const normalized = String(sourceType || "").trim().toLowerCase();
  if (normalized === "manual_binding") return "本地登记";
  if (normalized === "custom_clone") return "历史复刻记录";
  return "项目音色";
}

function statusLabel(status) {
  return String(status || "").trim().toLowerCase() === "failed"
    ? "不可用"
    : "可用";
}

function resolveLocalAudioUrl(value) {
  const url = String(value || "").trim();
  return /^(data:audio\/|blob:|file:\/\/)/i.test(url) ? url : "";
}

function resolveVoiceAudioUrl(item) {
  return [
    item?.local_audio?.content_url,
    item?.preview_audio?.content_url,
    item?.sample_audio?.content_url,
    item?.local_audio_url,
  ]
    .map(resolveLocalAudioUrl)
    .find(Boolean) || "";
}

function localAudioFileName(item) {
  const localAudio = item?.local_audio || {};
  const previewAudio = item?.preview_audio || {};
  const sampleAudio = item?.sample_audio || {};
  return String(
    localAudio.original_filename ||
      previewAudio.original_filename ||
      sampleAudio.original_filename ||
      "",
  ).trim();
}

function normalizeVoice(item) {
  const id = String(item?.id || "").trim();
  if (!id) return null;
  return {
    ...item,
    id,
    provider_id: String(item?.provider_id || "").trim(),
    model_name: String(item?.model_name || "").trim(),
    name: String(item?.name || id).trim() || id,
    voice_id: String(item?.voice_id || "").trim(),
    preview_text: String(item?.preview_text || "").trim(),
    description: String(item?.description || "").trim(),
    source_type: String(item?.source_type || "manual_binding").trim(),
    status: String(item?.status || "ready").trim(),
  };
}

function fetchProviders() {
  providers.value = readLocalModelProviders();
  syncModelSelection();
}

function fetchVoices() {
  const currentProjectId = String(projectId.value || "").trim();
  if (!currentProjectId) {
    voices.value = [];
    return;
  }
  const relations = getLocalProjectRelations(currentProjectId);
  voices.value = (Array.isArray(relations.voices) ? relations.voices : [])
    .map(normalizeVoice)
    .filter(Boolean);
}

function resetForm() {
  dialogMode.value = "create";
  editingVoiceId.value = "";
  form.name = "";
  form.voiceId = "";
  form.previewText = "你好，这是一段用于标记音色的试听文本。";
  form.description = "";
  syncModelSelection();
}

function openCreateDialog() {
  resetForm();
  dialogVisible.value = true;
}

function openEditDialog(item) {
  resetForm();
  dialogMode.value = "edit";
  editingVoiceId.value = String(item?.id || "").trim();
  form.providerId = String(item?.provider_id || "").trim();
  form.modelName = String(item?.model_name || "").trim();
  form.name = String(item?.name || "").trim();
  form.voiceId = String(item?.voice_id || "").trim();
  form.previewText =
    String(item?.preview_text || "").trim() ||
    "你好，这是一段用于标记音色的试听文本。";
  form.description = String(item?.description || "").trim();
  syncModelSelection();
  dialogVisible.value = true;
}

async function submitForm() {
  const currentProjectId = String(projectId.value || "").trim();
  if (!currentProjectId) {
    ElMessage.warning("缺少项目 ID");
    return;
  }
  if (!form.providerId || !form.modelName) {
    ElMessage.warning("请先选择模型源和模型");
    return;
  }
  if (!form.name.trim()) {
    ElMessage.warning("请填写音色名称");
    return;
  }
  if (!form.voiceId.trim()) {
    ElMessage.warning("请填写供应商音色 ID");
    return;
  }

  const isEditing = dialogMode.value === "edit" && editingVoiceId.value;
  submitting.value = true;
  try {
    const now = new Date().toISOString();
    const relations = getLocalProjectRelations(currentProjectId);
    const existingVoices = Array.isArray(relations.voices) ? relations.voices : [];
    const existingVoice = existingVoices.find(
      (item) => String(item?.id || "").trim() === editingVoiceId.value,
    );
    const voice = normalizeVoice({
      ...existingVoice,
      id:
        editingVoiceId.value ||
        `local-voice-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`,
      project_id: currentProjectId,
      source_type: "manual_binding",
      provider_id: form.providerId,
      model_name: form.modelName,
      name: form.name.trim(),
      voice_id: form.voiceId.trim(),
      preview_text: form.previewText.trim(),
      description: form.description.trim(),
      status: "ready",
      created_at: existingVoice?.created_at || now,
      updated_at: now,
    });
    const nextVoices = isEditing
      ? existingVoices.map((item) =>
          String(item?.id || "").trim() === voice.id ? voice : item,
        )
      : [...existingVoices, voice];
    updateLocalProjectRelations(currentProjectId, { voices: nextVoices });
    dialogVisible.value = false;
    fetchVoices();
    ElMessage.success(isEditing ? "项目音色已更新" : "项目音色已登记");
  } catch (err) {
    ElMessage.error(
      err?.detail ||
        err?.message ||
        (isEditing ? "更新项目音色失败" : "登记项目音色失败"),
    );
  } finally {
    submitting.value = false;
  }
}

async function removeVoice(item) {
  const currentProjectId = String(projectId.value || "").trim();
  const id = String(item?.id || "").trim();
  if (!currentProjectId || !id) return;
  try {
    await ElMessageBox.confirm(
      `确定删除项目音色「${item.name || "未命名音色"}」吗？这只会删除本地登记信息。`,
      "删除项目音色",
      { type: "warning" },
    );
  } catch {
    return;
  }
  deletingId.value = id;
  try {
    const relations = getLocalProjectRelations(currentProjectId);
    updateLocalProjectRelations(currentProjectId, {
      voices: (relations.voices || []).filter(
        (entry) => String(entry?.id || "").trim() !== id,
      ),
    });
    fetchVoices();
    ElMessage.success("项目音色已删除");
  } catch (err) {
    ElMessage.error(err?.detail || err?.message || "删除项目音色失败");
  } finally {
    deletingId.value = "";
  }
}

function handleLocalEntityUpdate(event) {
  if (String(event?.detail?.entityName || "").trim() === "llm_providers") {
    fetchProviders();
  }
}

function handleLocalRelationsUpdate() {
  fetchVoices();
}

watch(
  () => form.providerId,
  () => {
    syncModelSelection();
  },
);

watch(projectId, () => {
  fetchProviders();
  fetchVoices();
});

onMounted(() => {
  fetchProviders();
  fetchVoices();
  window.addEventListener("local-entities-updated", handleLocalEntityUpdate);
  window.addEventListener(
    "local-project-relations-updated",
    handleLocalRelationsUpdate,
  );
});

onBeforeUnmount(() => {
  window.removeEventListener("local-entities-updated", handleLocalEntityUpdate);
  window.removeEventListener(
    "local-project-relations-updated",
    handleLocalRelationsUpdate,
  );
});
</script>

<style scoped>
.voice-library {
  display: grid;
  gap: 24px;
}

.voice-library__hero,
.voice-library__panel,
.voice-library-upload {
  border: 1px solid rgba(255, 255, 255, 0.84);
  border-radius: 30px;
  background: rgba(255, 255, 255, 0.72);
  box-shadow: 0 14px 34px rgba(15, 23, 42, 0.06);
  backdrop-filter: blur(20px);
}

.voice-library__hero {
  display: flex;
  align-items: flex-end;
  justify-content: space-between;
  gap: 20px;
  padding: 30px 32px;
}

.voice-library__copy {
  max-width: 680px;
}

.voice-library__eyebrow {
  font-size: 12px;
  letter-spacing: 0.18em;
  text-transform: uppercase;
  color: rgba(15, 23, 42, 0.48);
}

.voice-library__title,
.voice-library-dialog__title {
  margin: 8px 0 0;
  font-size: clamp(28px, 4vw, 40px);
  line-height: 1.05;
  color: #0f172a;
}

.voice-library__text,
.voice-library-dialog__desc,
.voice-library__panel-desc {
  margin: 10px 0 0;
  max-width: 620px;
  font-size: 14px;
  line-height: 1.75;
  color: rgba(15, 23, 42, 0.64);
}

.voice-library__panel {
  padding: 24px;
}

.voice-library__panel-head {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 16px;
}

.voice-library__panel-title {
  font-size: 18px;
  font-weight: 600;
  color: #0f172a;
}

.voice-library__panel-meta {
  display: flex;
  flex-wrap: wrap;
  gap: 10px;
}

.voice-library__panel-meta span,
.voice-card__status {
  padding: 7px 12px;
  border-radius: 999px;
  background: rgba(241, 245, 249, 0.82);
  font-size: 12px;
  color: rgba(15, 23, 42, 0.64);
}

.voice-library__notice {
  margin-top: 18px;
}

.voice-library__grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 18px;
  margin-top: 20px;
}

.voice-card {
  display: grid;
  gap: 16px;
  padding: 20px;
  border-radius: 26px;
  background:
    linear-gradient(180deg, rgba(255, 255, 255, 0.92), rgba(248, 250, 252, 0.84)),
    rgba(248, 250, 252, 0.8);
  border: 1px solid rgba(226, 232, 240, 0.96);
  box-shadow: 0 18px 42px rgba(15, 23, 42, 0.06);
}

.voice-card__head,
.voice-library-upload__actions,
.voice-library-dialog__footer {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
}

.voice-card__eyebrow {
  margin-bottom: 6px;
  font-size: 11px;
  font-weight: 600;
  letter-spacing: 0.16em;
  text-transform: uppercase;
  color: rgba(14, 116, 144, 0.72);
}

.voice-card__title {
  font-size: 18px;
  font-weight: 600;
  color: #0f172a;
}

.voice-card__meta,
.voice-card__desc,
.voice-library-dialog__hint {
  font-size: 13px;
  line-height: 1.7;
  color: rgba(15, 23, 42, 0.62);
}

.voice-card__desc {
  margin: 0;
}

.voice-card__details {
  display: grid;
  gap: 10px;
  margin: 0;
}

.voice-card__details div {
  display: grid;
  gap: 4px;
}

.voice-card__details dt {
  font-size: 12px;
  color: rgba(15, 23, 42, 0.46);
}

.voice-card__details dd {
  margin: 0;
  font-size: 13px;
  color: #0f172a;
  word-break: break-all;
}

.voice-card__preview {
  display: grid;
  gap: 12px;
  padding: 14px;
  border-radius: 18px;
  background: rgba(255, 255, 255, 0.7);
  border: 1px solid rgba(226, 232, 240, 0.9);
}

.voice-card__preview.is-empty {
  background: rgba(248, 250, 252, 0.7);
  border-style: dashed;
}

.voice-card__preview-head {
  display: flex;
  align-items: baseline;
  justify-content: space-between;
  gap: 12px;
}

.voice-card__preview-title {
  font-size: 13px;
  font-weight: 600;
  color: #0f172a;
}

.voice-card__preview-text,
.voice-card__preview-empty {
  font-size: 12px;
  line-height: 1.6;
  color: rgba(15, 23, 42, 0.56);
}

.voice-card__actions {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
}

.voice-card__actions-main {
  display: flex;
  flex-wrap: wrap;
  gap: 10px;
}

.voice-card__audio {
  width: 100%;
}

.voice-library-dialog__body {
  display: grid;
  gap: 18px;
}

.voice-library-form-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 14px;
}

.voice-library-form-grid--single {
  grid-template-columns: minmax(0, 1fr);
}

.voice-library-field {
  display: grid;
  gap: 8px;
}

.voice-library-field span {
  font-size: 13px;
  color: rgba(15, 23, 42, 0.74);
}

.voice-library-upload {
  display: grid;
  gap: 14px;
  padding: 18px;
}

.voice-library__hidden-input {
  display: none;
}

.voice-library-dialog__footer {
  width: 100%;
}

@media (max-width: 960px) {
  .voice-library__hero,
  .voice-library__panel-head,
  .voice-card__actions,
  .voice-card__preview-head,
  .voice-library-upload__actions,
  .voice-library-dialog__footer {
    flex-direction: column;
    align-items: flex-start;
  }

  .voice-library__grid,
  .voice-library-form-grid {
    grid-template-columns: minmax(0, 1fr);
  }
}
</style>
