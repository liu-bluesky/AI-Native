import { extractImages } from "./mediaMappers.js";

const CONTEXT_REFERENCE_TYPES = new Set([
  "image",
  "video",
  "audio",
  "file",
  "text",
  "message",
]);

const IMPLICIT_RECENT_IMAGE_REFERENCE_PATTERN =
  /(?:这个|那个|这张|那张|该|上述|上面(?:的)?|前面(?:的)?|刚才(?:的)?|刚刚(?:的)?|刚生成(?:的)?)(?:照片|图片|图像|图)|(?:上一张|最近(?:的)?(?:一张)?)(?:照片|图片|图像|图)?/;

function compactText(value, maxLength = 4000) {
  const text = String(value || "").trim();
  if (!text || text.length <= maxLength) return text;
  return `${text.slice(0, maxLength)}…`;
}

function normalizeContextReferenceLabel(value, type, index) {
  const label = compactText(value, 160);
  if (!label) return label;
  if (label === "选中的历史文字") return "选中文字";
  if (/^(?:机器人|登录用户|AI 助手|用户)的历史消息$/.test(label)) {
    return "消息内容";
  }
  const legacyMediaLabel = label.match(
    /^(?:机器人(?:\s*·\s*.+)?|登录用户|AI 助手|用户)的(图片|视频|音频|附件)\s*(\d+)?$/,
  );
  if (!legacyMediaLabel) return label;
  return `${legacyMediaLabel[1]} ${legacyMediaLabel[2] || index + 1}`;
}

export function normalizeContextReference(input = {}, index = 0) {
  const type = CONTEXT_REFERENCE_TYPES.has(
    String(input?.type || "").trim().toLowerCase(),
  )
    ? String(input.type).trim().toLowerCase()
    : "message";
  const messageId = String(input?.messageId || input?.message_id || "").trim();
  const url = String(input?.url || "").trim();
  const content = compactText(input?.content);
  const label = normalizeContextReferenceLabel(
    input?.label ||
      (type === "text"
        ? "选中文字"
        : type === "message"
          ? "历史消息"
          : `历史${contextReferenceTypeLabel(type)}`),
    type,
    index,
  );
  const identity = [type, messageId, url, content].join("|");
  if (!url && !content && !label) return null;
  return {
    id: String(input?.id || "").trim() || `context-ref-${index}-${identity}`,
    type,
    messageId,
    url,
    label,
    content,
    mimeType: String(input?.mimeType || input?.mime_type || "").trim(),
    implicit: input?.implicit === true,
    visibility: String(input?.visibility || "").trim() || "user_visible",
    source: "conversation_history",
    usage: type === "image" ? "reference_image" : "context",
  };
}

export function contextReferenceTypeLabel(type) {
  return (
    {
      image: "图片",
      video: "视频",
      audio: "音频",
      file: "附件",
      text: "文字",
      message: "消息",
    }[String(type || "").trim()] || "内容"
  );
}

export function mergeContextReferences(current = [], additions = []) {
  const result = [];
  const seen = new Set();
  for (const [index, raw] of [...current, ...additions].entries()) {
    const item = normalizeContextReference(raw, index);
    if (!item) continue;
    const key = [item.type, item.messageId, item.url, item.content].join("|");
    if (seen.has(key)) continue;
    seen.add(key);
    result.push(item);
  }
  return result;
}

export function requestsImplicitRecentImageReference(value) {
  const text = String(value || "").trim();
  if (!text) return false;
  return IMPLICIT_RECENT_IMAGE_REFERENCE_PATTERN.test(text);
}

export function buildImplicitRecentImageReferences(messages = [], userText = "") {
  if (!requestsImplicitRecentImageReference(userText)) return [];
  const rows = Array.isArray(messages) ? messages : [];
  for (let messageIndex = rows.length - 1; messageIndex >= 0; messageIndex -= 1) {
    const message = rows[messageIndex];
    const imageUrls = extractImages(message);
    if (!imageUrls.length) continue;
    const imageIndex = imageUrls.length - 1;
    return [
      normalizeContextReference({
        type: "image",
        messageId: String(message?.id || "").trim(),
        url: imageUrls[imageIndex],
        label: "最近一张图片",
        mimeType: "image/*",
        implicit: true,
        visibility: "model_context",
      }),
    ].filter(Boolean);
  }
  return [];
}

export function buildContextReferencesPrompt(references = []) {
  const items = mergeContextReferences([], references);
  if (!items.length) return "";
  const blocks = items.map((item, index) => {
    const lines = [
      `${index + 1}. ${contextReferenceTypeLabel(item.type)}：${item.label}`,
      `   资产 ID：${item.id}`,
    ];
    if (item.content) lines.push(`   内容：${item.content}`);
    if (item.url) lines.push(`   资源地址：${item.url}`);
    return lines.join("\n");
  });
  return [
    "本轮引用了当前会话中的历史内容。请把这些内容视为用户已明确提供的上下文，不要再次要求上传：",
    ...blocks,
    "若用户要求基于上述图片继续生成，请调用 generate_image 并通过 reference_asset_ids 选择资产；若要求修改现有图片，请调用 edit_image 并通过 input_asset_ids 选择资产。不要声称看不到引用内容，也不要改用本地脚本处理图片。",
  ].join("\n");
}

export function buildContextReferenceAttachments(references = []) {
  return mergeContextReferences([], references)
    .filter((item) => ["image", "video", "audio", "file"].includes(item.type))
    .map((item, index) => ({
      attachmentId: item.id || `context-ref-attachment-${index}`,
      name: item.label || `${contextReferenceTypeLabel(item.type)} ${index + 1}`,
      mimeType:
        item.mimeType ||
        (item.type === "image"
          ? "image/*"
          : item.type === "video"
            ? "video/*"
            : item.type === "audio"
              ? "audio/*"
              : "application/octet-stream"),
      size: 0,
      kind: item.type,
      routingMode: item.type === "image" ? "inline_image" : "local_extract",
      extractionStatus: item.url ? "conversation_reference" : "metadata_only",
      dataUrl: item.url,
      extractedText: item.content,
      providerFileId: "",
      error: "",
    }));
}
