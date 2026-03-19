export const MATERIAL_ASSET_TYPE_OPTIONS = [
  { value: "image", label: "图片" },
  { value: "storyboard", label: "分镜" },
  { value: "video", label: "视频" },
];

export const MATERIAL_MIME_TYPE_OPTIONS = [
  { value: "image/png", label: "PNG 图片" },
  { value: "image/jpeg", label: "JPEG 图片" },
  { value: "image/webp", label: "WebP 图片" },
  { value: "image/gif", label: "GIF 图片" },
  { value: "image/svg+xml", label: "SVG 图片" },
  { value: "image/bmp", label: "BMP 图片" },
  { value: "video/mp4", label: "MP4 视频" },
  { value: "video/quicktime", label: "MOV / QuickTime 视频" },
  { value: "application/json", label: "JSON 结构化结果" },
  { value: "text/plain", label: "纯文本" },
];

function clipText(text, maxChars) {
  const value = String(text || "").trim();
  if (!value) return "";
  if (value.length <= maxChars) return value;
  return `${value.slice(0, maxChars)}\n（内容已截断）`;
}

function fileExtension(name) {
  const text = String(name || "").trim();
  const idx = text.lastIndexOf(".");
  if (idx < 0 || idx === text.length - 1) return "";
  return text.slice(idx + 1).toLowerCase();
}

function stripMarkdownForMaterial(text) {
  return String(text || "")
    .replace(/```[\s\S]*?```/g, " ")
    .replace(/!\[[^\]]*]\([^)]+\)/g, " ")
    .replace(/\[([^\]]+)\]\([^)]+\)/g, "$1")
    .replace(/[#>*`_-]+/g, " ")
    .replace(/\s+/g, " ")
    .trim();
}

function extractImages(message) {
  if (!message || !Array.isArray(message.images)) return [];
  return message.images
    .map((item) => String(item || "").trim())
    .filter(Boolean);
}

function extractAttachmentNames(message) {
  if (!message || !Array.isArray(message.attachments)) return [];
  return message.attachments
    .map((item) => String(item || "").trim())
    .filter(Boolean);
}

function inferMaterialMimeTypeFromUrl(url) {
  const normalized = String(url || "").trim();
  if (!normalized) return "";
  const ext = fileExtension(normalized.split("?")[0].split("#")[0]);
  if (!ext) return "";
  if (["jpg", "jpeg"].includes(ext)) return "image/jpeg";
  if (ext === "png") return "image/png";
  if (ext === "gif") return "image/gif";
  if (ext === "webp") return "image/webp";
  if (ext === "svg") return "image/svg+xml";
  if (ext === "bmp") return "image/bmp";
  if (ext === "mp4") return "video/mp4";
  if (ext === "mov") return "video/quicktime";
  return "";
}

function defaultMaterialTypeForMessage(message) {
  if (extractImages(message).length) {
    return "image";
  }
  return "storyboard";
}

function resolveMaterialSourceUsername(message, currentUsername) {
  const role = String(message?.role || "").trim();
  if (role === "user") {
    return String(currentUsername || "").trim() || "anonymous";
  }
  const username = String(message?.username || "").trim();
  return username || "assistant";
}

function buildMaterialTitle(message, assetType) {
  const content = stripMarkdownForMaterial(message?.content || "");
  const firstLine = content
    .split(/\n+/)
    .find((line) => String(line || "").trim());
  const prefix =
    assetType === "image"
      ? "聊天图片素材"
      : assetType === "video"
        ? "聊天视频素材"
        : "聊天分镜素材";
  return clipText(firstLine || prefix, 120).replace(/\n/g, " ");
}

function buildMaterialSummary(message, assetType) {
  const content = stripMarkdownForMaterial(message?.content || "");
  if (content) {
    return clipText(content, 180).replace(/\n/g, " ");
  }
  if (assetType === "image") {
    return "来自项目聊天消息的图片结果";
  }
  if (assetType === "video") {
    return "来自项目聊天消息的视频结果";
  }
  return "来自项目聊天消息的分镜内容";
}

function buildMaterialStructuredContent(message, assetType) {
  const content = String(message?.content || "").trim();
  const images = extractImages(message);
  const attachments = extractAttachmentNames(message);
  if (assetType === "image") {
    return {
      text: content,
      images,
      attachments,
    };
  }
  return {
    text: content,
    attachments,
  };
}

function buildMaterialMetadata(message, messageIndex, assetType) {
  return {
    source: "project-chat",
    asset_type_suggestion: assetType,
    message_index: Number(messageIndex),
    message_role: String(message?.role || "").trim() || "assistant",
    message_time: String(message?.time || message?.created_at || "").trim(),
    display_mode: String(message?.displayMode || "").trim(),
    image_count: extractImages(message).length,
    attachment_names: extractAttachmentNames(message),
  };
}

export function canSaveMessageAsMaterial(message, projectId = "") {
  if (!String(projectId || "").trim()) return false;
  const role = String(message?.role || "").trim();
  if (!["user", "assistant"].includes(role)) return false;
  if (extractImages(message).length) return true;
  return Boolean(String(message?.content || "").trim());
}

export function buildMaterialDialogPayload({
  message,
  messageIndex,
  currentChatSessionId = "",
  currentUsername = "",
}) {
  const assetType = defaultMaterialTypeForMessage(message);
  const images = extractImages(message);
  const firstImageUrl = images[0] || "";
  return {
    message,
    form: {
      asset_type: assetType,
      title: buildMaterialTitle(message, assetType),
      summary: buildMaterialSummary(message, assetType),
      preview_url: firstImageUrl,
      content_url: firstImageUrl,
      mime_type: inferMaterialMimeTypeFromUrl(firstImageUrl),
      structured_content_text: JSON.stringify(
        buildMaterialStructuredContent(message, assetType),
        null,
        2,
      ),
      metadata_text: JSON.stringify(
        buildMaterialMetadata(message, messageIndex, assetType),
        null,
        2,
      ),
    },
    source_message_id: String(message?.id || "").trim(),
    source_chat_session_id: String(currentChatSessionId || "").trim(),
    source_username: resolveMaterialSourceUsername(message, currentUsername),
  };
}
