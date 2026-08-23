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
    description:
      "由主模型调用统一的图片工具协议；系统通过供应商适配器使用当前选择的图片模型，支持从零生成和现有图片编辑。",
    providerKey: "image_provider_id",
    modelKey: "image_model_name",
    buildFeature: "image",
    modelTypes: ["image_generation"],
  },
  {
    id: "video",
    label: "Videos / 视频生成",
    description:
      "由主模型调用统一的视频工具协议；系统通过供应商适配器使用当前选择的视频模型，实际生成和编辑能力以供应商能力为准。",
    providerKey: "video_provider_id",
    modelKey: "video_model_name",
    buildFeature: "video",
    modelTypes: ["video_generation"],
  },
  {
    id: "audio_generation",
    label: "Speech / 音频生成",
    description:
      "由主模型调用统一的文本转语音工具协议；系统通过供应商适配器使用当前选择的语音模型。",
    providerKey: "audio_generation_provider_id",
    modelKey: "audio_generation_model_name",
    buildFeature: "audioGeneration",
    modelTypes: ["audio_generation"],
  },
  {
    id: "audio_transcription",
    label: "Transcriptions / 音频转写",
    description:
      "由主模型调用统一的音频转写工具协议；系统通过供应商适配器使用当前选择的转写模型。",
    providerKey: "audio_transcription_provider_id",
    modelKey: "audio_transcription_model_name",
    buildFeature: "audioTranscription",
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
