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
          创建自定义音色
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
              <dt>样本音频</dt>
              <dd>{{ item.sample_audio?.original_filename || "未保存" }}</dd>
            </div>
          </dl>
          <div
            class="voice-card__preview"
            :class="{ 'is-empty': !resolveVoiceAudioUrl(item) }"
          >
            <div class="voice-card__preview-head">
              <div class="voice-card__preview-title">
                {{ hasGeneratedPreview(item) ? "生成试听" : "试听区" }}
              </div>
              <div class="voice-card__preview-text">
                {{
                  hasGeneratedPreview(item)
                    ? "当前为最新试听音频"
                    : item.sample_audio?.content_url
                      ? "未生成试听时，可先听上传样本"
                      : "点击试听后会在这里出现音频"
                }}
              </div>
            </div>
            <audio
              v-if="resolveVoiceAudioUrl(item)"
              :ref="(el) => setPreviewAudioRef(item.id, el)"
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
                type="primary"
                :loading="previewingId === String(item.id || '').trim()"
                @click="previewVoice(item)"
              >
                {{ hasGeneratedPreview(item) ? "刷新试听" : "试听" }}
              </el-button>
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
                ? "更新名称、试听文案和备注，让项目里的配音资产更稳定。"
                : "支持参考音频复刻，或登记供应商已有的音色 ID。"
            }}
          </div>
        </div>
      </template>

      <div class="voice-library-dialog__body">
        <div class="voice-library-form-grid">
          <label class="voice-library-field">
            <span>创建方式</span>
            <el-segmented
              v-model="createMode"
              :options="createModeOptions"
              :disabled="dialogMode === 'edit'"
            />
          </label>
        </div>
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
          <label v-if="createMode === 'manual'" class="voice-library-field">
            <span>音色 ID</span>
            <el-input
              v-model="form.voiceId"
              placeholder="填写供应商侧的 voice_id"
            />
          </label>
          <label v-if="createMode === 'clone'" class="voice-library-field">
            <span>样本转写</span>
            <el-input
              v-model="form.transcriptText"
              type="textarea"
              :rows="4"
              placeholder="填写样本音频里的原文，复刻时会用来做对齐。"
            />
          </label>
          <label class="voice-library-field">
            <span>试听文本</span>
            <el-input
              v-model="form.previewText"
              type="textarea"
              :rows="3"
              placeholder="用于生成试听。"
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

        <section v-if="createMode === 'clone'" class="voice-library-upload">
          <div>
            <div class="voice-library__panel-title">参考音频</div>
            <div class="voice-library__panel-desc">
              建议上传 10 到 30 秒的清晰单人语音，噪声越少越稳。
            </div>
          </div>
          <div class="voice-library-upload__actions">
            <el-button :disabled="dialogMode === 'edit'" @click="openFilePicker">
              选择音频
            </el-button>
            <span>{{
              selectedFileName || (dialogMode === "edit" ? "当前保留原始样本" : "尚未选择文件")
            }}</span>
          </div>
          <input
            ref="fileInputRef"
            class="voice-library__hidden-input"
            type="file"
            accept="audio/*"
            @change="handleFileChange"
          />
        </section>
      </div>

      <template #footer>
        <div class="voice-library-dialog__footer">
          <div class="voice-library-dialog__hint">
            {{
              dialogMode === "edit"
                ? "编辑不会重建音色本体，只会更新项目内的展示和试听信息。"
                : createMode === "clone"
                  ? "复刻完成后，会自动加入当前项目音色列表。"
                  : "登记后会立即作为项目音色加入，可直接在短片制作里使用。"
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
import { computed, nextTick, onMounted, reactive, ref, watch } from "vue";
import { useRoute } from "vue-router";
import { ElMessage, ElMessageBox } from "element-plus";

import api from "@/utils/api.js";
import { normalizeProviderModelConfigs } from "@/utils/llm-models.js";
import { resolveMaterialResourceUrl } from "@/utils/project-materials.js";
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
const loading = ref(false);
const deletingId = ref("");
const previewingId = ref("");
const createMode = ref("clone");
const fileInputRef = ref(null);
const selectedFile = ref(null);
const selectedFileName = ref("");
const providers = ref([]);
const voices = ref([]);
const previewAudioMap = reactive({});
const previewAudioRefs = new Map();

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
  transcriptText: "",
  previewText: "你好，这是一段用于校准音色的试听文本。",
  description: "",
});

const createModeOptions = [
  { label: "参考音频复刻", value: "clone" },
  { label: "手动登记音色ID", value: "manual" },
];

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
      const cloneModelConfigs = audioModelConfigs.filter((model) =>
        /clone/i.test(model.name),
      );
      const modelConfigs = cloneModelConfigs.length
        ? cloneModelConfigs
        : audioModelConfigs;
      const models = modelConfigs.map((item) => item.name);
      const defaultModel =
        modelConfigs.find(
          (model) => model.name === String(item?.default_model || "").trim(),
        )?.name ||
        modelConfigs[0]?.name ||
        "";
      return {
        id: String(item?.id || "").trim(),
        name: String(item?.name || item?.id || "未命名模型源").trim(),
        cloneModels: cloneModelConfigs.map((entry) => entry.name),
        speechModels: audioModelConfigs
          .filter((entry) => !/clone/i.test(entry.name))
          .map((entry) => entry.name),
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
  if (!target) return [];
  if (createMode.value === "clone") {
    return target.cloneModels?.length ? target.cloneModels : [];
  }
  return target.speechModels?.length ? target.speechModels : target.models || [];
});

function syncModelSelection() {
  const provider =
    audioProviderOptions.value.find((item) => item.id === form.providerId) ||
    audioProviderOptions.value[0] ||
    null;
  if (!provider) {
    form.providerId = "";
    form.modelName = "";
    createMode.value = "clone";
    return;
  }
  form.providerId = provider.id;
  if (dialogMode.value === "edit") {
    form.modelName =
      form.modelName || provider.defaultModel || provider.models[0] || "";
    return;
  }
  if (createMode.value === "clone" && !(provider.cloneModels || []).length) {
    createMode.value = "manual";
  }
  if (createMode.value === "manual" && !(provider.speechModels || []).length) {
    createMode.value = "clone";
  }
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
  if (normalized === "manual_binding") return "手动接入";
  if (normalized === "custom_clone") return "参考音频复刻";
  return "项目音色";
}

function statusLabel(status) {
  const normalized = String(status || "")
    .trim()
    .toLowerCase();
  if (normalized === "ready") return "可用";
  if (normalized === "failed") return "失败";
  return "处理中";
}

function resolveUrl(url) {
  return resolveMaterialResourceUrl(String(url || "").trim());
}

function resolveVoiceAudioUrl(item) {
  const normalizedId = String(item?.id || "").trim();
  return resolveUrl(
    previewAudioMap[normalizedId]?.url ||
      item?.preview_audio?.content_url ||
      item?.sample_audio?.content_url,
  );
}

function hasGeneratedPreview(item) {
  const normalizedId = String(item?.id || "").trim();
  return Boolean(
    previewAudioMap[normalizedId]?.url ||
      String(item?.preview_audio?.content_url || "").trim(),
  );
}

function setPreviewAudioRef(id, element) {
  const normalizedId = String(id || "").trim();
  if (!normalizedId) return;
  if (element) {
    previewAudioRefs.set(normalizedId, element);
    return;
  }
  previewAudioRefs.delete(normalizedId);
}

function playPreviewAudio(id) {
  const player = previewAudioRefs.get(String(id || "").trim());
  if (!player?.play) return;
  player.currentTime = 0;
  const playback = player.play();
  if (playback?.catch) {
    playback.catch(() => {});
  }
}

async function fetchProviders() {
  const currentProjectId = projectId.value;
  if (!currentProjectId) {
    providers.value = [];
    return;
  }
  try {
    const data = await api.get(
      `/projects/${currentProjectId}/studio/model-sources`,
    );
    providers.value = Array.isArray(data?.providers) ? data.providers : [];
    syncModelSelection();
  } catch (err) {
    providers.value = [];
    ElMessage.error(err?.detail || err?.message || "加载音频模型源失败");
  }
}

async function fetchVoices() {
  const currentProjectId = projectId.value;
  if (!currentProjectId) {
    voices.value = [];
    return;
  }
  loading.value = true;
  try {
    const data = await api.get(`/projects/${currentProjectId}/studio/voices`);
    voices.value = Array.isArray(data?.items) ? data.items : [];
  } catch (err) {
    voices.value = [];
    ElMessage.error(err?.detail || err?.message || "加载项目音色失败");
  } finally {
    loading.value = false;
  }
}

function resetForm() {
  dialogMode.value = "create";
  editingVoiceId.value = "";
  form.name = "";
  form.voiceId = "";
  form.transcriptText = "";
  form.previewText = "你好，这是一段用于校准音色的试听文本。";
  form.description = "";
  selectedFile.value = null;
  selectedFileName.value = "";
  syncModelSelection();
  if (fileInputRef.value) {
    fileInputRef.value.value = "";
  }
}

function openCreateDialog() {
  resetForm();
  dialogVisible.value = true;
}

function openEditDialog(item) {
  resetForm();
  dialogMode.value = "edit";
  editingVoiceId.value = String(item?.id || "").trim();
  createMode.value =
    String(item?.source_type || "").trim().toLowerCase() === "manual_binding"
      ? "manual"
      : "clone";
  form.providerId = String(item?.provider_id || "").trim();
  form.modelName = String(item?.model_name || "").trim();
  form.name = String(item?.name || "").trim();
  form.voiceId = String(item?.voice_id || "").trim();
  form.transcriptText = String(item?.transcript_text || "").trim();
  form.previewText =
    String(item?.preview_text || "").trim() ||
    "你好，这是一段用于校准音色的试听文本。";
  form.description = String(item?.description || "").trim();
  selectedFileName.value = String(item?.sample_audio?.original_filename || "").trim();
  syncModelSelection();
  dialogVisible.value = true;
}

function openFilePicker() {
  fileInputRef.value?.click?.();
}

function handleFileChange(event) {
  const file = event?.target?.files?.[0];
  selectedFile.value = file || null;
  selectedFileName.value = file ? String(file.name || "").trim() : "";
}

async function submitForm() {
  const currentProjectId = projectId.value;
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
  const isEditing = dialogMode.value === "edit" && editingVoiceId.value;
  if (createMode.value === "clone") {
    if (!form.transcriptText.trim()) {
      ElMessage.warning("请填写样本转写");
      return;
    }
    if (!isEditing && !selectedFile.value) {
      ElMessage.warning("请上传参考音频");
      return;
    }
  } else if (!form.voiceId.trim()) {
    ElMessage.warning("请填写音色 ID");
    return;
  }
  submitting.value = true;
  try {
    if (dialogMode.value === "edit" && editingVoiceId.value) {
      await api.patch(
        `/projects/${currentProjectId}/studio/voices/${encodeURIComponent(editingVoiceId.value)}`,
        {
          name: form.name.trim(),
          voice_id: createMode.value === "manual" ? form.voiceId.trim() : undefined,
          transcript_text: createMode.value === "clone" ? form.transcriptText.trim() : undefined,
          preview_text: form.previewText.trim(),
          description: form.description.trim(),
        },
      );
    } else {
      const formData = new FormData();
      formData.append("mode", createMode.value);
      formData.append("provider_id", form.providerId);
      formData.append("model_name", form.modelName);
      formData.append("name", form.name.trim());
      formData.append("voice_id", form.voiceId.trim());
      formData.append("transcript_text", form.transcriptText.trim());
      formData.append("preview_text", form.previewText.trim());
      formData.append("description", form.description.trim());
      if (createMode.value === "clone" && selectedFile.value) {
        formData.append("sample_file", selectedFile.value);
      }
      await api.post(`/projects/${currentProjectId}/studio/voices`, formData, {
        headers: { "Content-Type": "multipart/form-data" },
      });
    }
    dialogVisible.value = false;
    await fetchVoices();
    ElMessage.success(dialogMode.value === "edit" ? "项目音色已更新" : "项目音色已创建");
  } catch (err) {
    ElMessage.error(
      err?.detail ||
        err?.message ||
        (dialogMode.value === "edit" ? "更新项目音色失败" : "创建项目音色失败"),
    );
  } finally {
    submitting.value = false;
  }
}

function resolvePreviewModelName(item) {
  const provider = audioProviderOptions.value.find(
    (option) => option.id === String(item?.provider_id || "").trim(),
  );
  return (
    provider?.speechModels?.[0] ||
    String(item?.model_name || "").trim() ||
    ""
  );
}

async function previewVoice(item) {
  const currentProjectId = projectId.value;
  const voiceRecordId = String(item?.id || "").trim();
  if (!currentProjectId) {
    ElMessage.warning("缺少项目 ID");
    return;
  }
  if (hasGeneratedPreview(item)) {
    await nextTick();
    playPreviewAudio(voiceRecordId);
    return;
  }
  const text =
    String(item?.preview_text || "").trim() ||
    `你好，我是${String(item?.name || "当前音色").trim()}。`;
  const modelName = resolvePreviewModelName(item);
  if (!String(item?.provider_id || "").trim() || !modelName || !String(item?.voice_id || "").trim()) {
    ElMessage.warning("当前音色缺少试听所需配置");
    return;
  }
  previewingId.value = voiceRecordId;
  try {
    const data = await api.post(`/projects/${currentProjectId}/studio/voiceovers/generate`, {
      provider_id: String(item.provider_id || "").trim(),
      model_name: modelName,
      voice: String(item.voice_id || "").trim(),
      text,
      title: `${String(item.name || "音色").trim()} 试听`,
      voice_record_id: voiceRecordId,
      response_format: "wav",
      speed: 1,
    });
    previewAudioMap[voiceRecordId] = {
      url: String(data?.item?.content_url || "").trim(),
      generatedAt: Date.now(),
    };
    const voiceIndex = voices.value.findIndex(
      (entry) => String(entry?.id || "").trim() === voiceRecordId,
    );
    if (voiceIndex >= 0 && data?.voice_item && typeof data.voice_item === "object") {
      voices.value.splice(voiceIndex, 1, data.voice_item);
    }
    await nextTick();
    playPreviewAudio(voiceRecordId);
    ElMessage.success("试听音频已生成");
  } catch (err) {
    ElMessage.error(err?.detail || err?.message || "生成试听音频失败");
  } finally {
    previewingId.value = "";
  }
}

async function removeVoice(item) {
  const currentProjectId = projectId.value;
  const id = String(item?.id || "").trim();
  if (!currentProjectId || !id) return;
  try {
    await ElMessageBox.confirm(
      `删除后音色「${item.name || "未命名音色"}」将无法继续在短片制作中复用。`,
      "删除项目音色",
      { type: "warning" },
    );
  } catch {
    return;
  }
  deletingId.value = id;
  try {
    const result = await api.delete(
      `/projects/${currentProjectId}/studio/voices/${encodeURIComponent(id)}`,
    );
    delete previewAudioMap[id];
    previewAudioRefs.delete(id);
    await fetchVoices();
    if (result?.provider_delete_error) {
      ElMessage.warning(
        `本地已删除，远端清理失败：${result.provider_delete_error}`,
      );
      return;
    }
    ElMessage.success("项目音色已删除");
  } catch (err) {
    ElMessage.error(err?.detail || err?.message || "删除项目音色失败");
  } finally {
    deletingId.value = "";
  }
}

watch(
  () => form.providerId,
  () => {
    syncModelSelection();
  },
);

watch(createMode, () => {
  syncModelSelection();
});

watch(projectId, async () => {
  await fetchProviders();
  await fetchVoices();
});

onMounted(async () => {
  await fetchProviders();
  await fetchVoices();
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
