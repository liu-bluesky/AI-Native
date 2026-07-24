export const MODEL_ROUTING_MODE_AUTO = "auto";
export const MODEL_ROUTING_MODE_MANUAL = "manual";

export const MODEL_ROLE_CONFIGS = [
  {
    id: "main",
    label: "主对话模型",
    description: "用于普通对话、意图识别和工具编排。",
    providerKey: "provider_id",
    modelKey: "model_name",
    modelTypes: ["text_generation", "multimodal_chat"],
  },
  {
    id: "image",
    label: "Images / 图片生成",
    description: "由主模型通过 generate_image 工具调用。",
    providerKey: "image_provider_id",
    modelKey: "image_model_name",
    modelTypes: ["image_generation"],
  },
  {
    id: "video",
    label: "Videos / 视频生成",
    description: "由主模型通过 generate_video 工具调用。",
    providerKey: "video_provider_id",
    modelKey: "video_model_name",
    modelTypes: ["video_generation"],
  },
  {
    id: "audio_generation",
    label: "Speech / 音频生成",
    description: "由主模型通过 generate_audio 工具调用。",
    providerKey: "audio_generation_provider_id",
    modelKey: "audio_generation_model_name",
    modelTypes: ["audio_generation"],
  },
  {
    id: "audio_transcription",
    label: "Transcriptions / 音频转写",
    description: "由主模型通过 transcribe_audio 工具调用。",
    providerKey: "audio_transcription_provider_id",
    modelKey: "audio_transcription_model_name",
    modelTypes: ["audio_transcription"],
  },
];

const ROLE_BY_ID = new Map(MODEL_ROLE_CONFIGS.map((item) => [item.id, item]));

export function parseModelOptionValue(value) {
  const normalized = String(value || "").trim();
  const separatorIndex = normalized.indexOf("::");
  if (separatorIndex <= 0) return { providerId: "", modelName: "" };
  return {
    providerId: normalized.slice(0, separatorIndex).trim(),
    modelName: normalized.slice(separatorIndex + 2).trim(),
  };
}

export function buildModelOptionValue(providerId, modelName) {
  const provider = String(providerId || "").trim();
  const model = String(modelName || "").trim();
  return provider && model ? `${provider}::${model}` : "";
}

export function readModelRoleTarget(settings, roleId) {
  const role = ROLE_BY_ID.get(String(roleId || "").trim());
  if (!role) return { roleId: "", providerId: "", modelName: "" };
  return {
    roleId: role.id,
    providerId: String(settings?.[role.providerKey] || "").trim(),
    modelName: String(settings?.[role.modelKey] || "").trim(),
  };
}

export function writeModelRoleTarget(settings, roleId, value) {
  const role = ROLE_BY_ID.get(String(roleId || "").trim());
  if (!role) return { ...(settings || {}) };
  const target = parseModelOptionValue(value);
  return {
    ...(settings || {}),
    [role.providerKey]: target.providerId,
    [role.modelKey]: target.modelName,
  };
}
