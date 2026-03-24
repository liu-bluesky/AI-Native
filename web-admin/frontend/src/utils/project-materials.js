export const MATERIAL_ASSET_TYPE_OPTIONS = [
  { value: "image", label: "图片" },
  { value: "storyboard", label: "分镜" },
  { value: "video", label: "视频" },
  { value: "audio", label: "音频" },
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
  { value: "audio/mpeg", label: "MP3 音频" },
  { value: "audio/wav", label: "WAV 音频" },
  { value: "audio/mp4", label: "M4A / MP4 音频" },
  { value: "audio/aac", label: "AAC 音频" },
  { value: "audio/ogg", label: "OGG 音频" },
  { value: "audio/flac", label: "FLAC 音频" },
  { value: "application/pdf", label: "PDF 文档" },
  { value: "application/msword", label: "Word 文档" },
  {
    value:
      "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    label: "DOCX 文档",
  },
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

function extractVideoUrls(message) {
  const directVideos = Array.isArray(message?.videos)
    ? message.videos
        .map((item) => String(item || "").trim())
        .filter(Boolean)
    : [];
  const content = String(message?.content || "");
  const matchedUrls = Array.from(
    content.matchAll(/https?:\/\/[^\s)"'<>\]]+/gi),
    (match) => String(match?.[0] || "").trim(),
  ).filter(Boolean);
  const candidates = [...directVideos, ...matchedUrls];
  const seen = new Set();
  return candidates.filter((item) => {
    if (!item || seen.has(item)) return false;
    seen.add(item);
    const mimeType = inferMaterialMimeTypeFromUrl(item);
    return mimeType.startsWith("video/");
  });
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
  if (ext === "mp3") return "audio/mpeg";
  if (ext === "wav") return "audio/wav";
  if (ext === "m4a") return "audio/mp4";
  if (ext === "aac") return "audio/aac";
  if (ext === "ogg") return "audio/ogg";
  if (ext === "flac") return "audio/flac";
  if (ext === "pdf") return "application/pdf";
  if (ext === "doc") return "application/msword";
  if (ext === "docx") {
    return "application/vnd.openxmlformats-officedocument.wordprocessingml.document";
  }
  if (ext === "txt") return "text/plain";
  if (ext === "json") return "application/json";
  return "";
}

export function inferMaterialAssetTypeFromFile(file) {
  const mimeType = String(file?.type || "").trim().toLowerCase();
  const name = String(file?.name || "").trim().toLowerCase();
  const ext = fileExtension(name);
  if (mimeType.startsWith("image/")) return "image";
  if (mimeType.startsWith("video/")) return "video";
  if (mimeType.startsWith("audio/")) return "audio";
  if (["jpg", "jpeg", "png", "gif", "webp", "svg", "bmp"].includes(ext)) {
    return "image";
  }
  if (["mp4", "mov", "m4v", "webm", "avi", "mkv"].includes(ext)) {
    return "video";
  }
  if (["mp3", "wav", "m4a", "aac", "ogg", "flac"].includes(ext)) {
    return "audio";
  }
  if (
    [
      ".json",
      ".txt",
      ".pdf",
      ".doc",
      ".docx",
      ".md",
    ].some((suffix) => name.endsWith(suffix))
  ) {
    return "storyboard";
  }
  return "storyboard";
}

export function resolveMaterialResourceUrl(url) {
  const normalized = String(url || "").trim();
  if (!normalized) return "";
  if (
    normalized.startsWith("data:") ||
    normalized.startsWith("blob:") ||
    normalized.startsWith("file://")
  ) {
    return normalized;
  }
  const token =
    typeof window !== "undefined" ? String(localStorage.getItem("token") || "").trim() : "";
  try {
    const base =
      typeof window !== "undefined" && window.location?.origin
        ? window.location.origin
        : "http://localhost";
    const resolved = new URL(normalized, base);
    const isSameOrigin =
      typeof window === "undefined" || !window.location?.origin
        ? normalized.startsWith("/")
        : resolved.origin === window.location.origin;
    if (isSameOrigin && resolved.pathname.startsWith("/api/") && token) {
      resolved.searchParams.set("token", token);
    }
    return resolved.toString();
  } catch {
    return normalized;
  }
}

function readVideoMetadata(source) {
  return new Promise((resolve, reject) => {
    if (typeof document === "undefined") {
      reject(new Error("当前环境不支持读取视频元数据"));
      return;
    }
    const video = document.createElement("video");
    video.preload = "metadata";
    video.muted = true;
    video.playsInline = true;

    let objectUrl = "";
    if (source instanceof File) {
      objectUrl = URL.createObjectURL(source);
      video.src = objectUrl;
    } else {
      video.src = String(source || "").trim();
    }

    let settled = false;
    const finalize = (callback) => {
      if (settled) return;
      settled = true;
      video.pause?.();
      video.removeAttribute("src");
      video.load?.();
      if (objectUrl) {
        URL.revokeObjectURL(objectUrl);
      }
      callback();
    };

    video.addEventListener(
      "loadedmetadata",
      () => {
        const duration = Number(video.duration || 0);
        if (!Number.isFinite(duration) || duration <= 0) {
          finalize(() => reject(new Error("无法读取视频时长")));
          return;
        }
        finalize(() => resolve(duration));
      },
      { once: true },
    );
    video.addEventListener(
      "error",
      () => finalize(() => reject(new Error("视频元数据加载失败"))),
      { once: true },
    );
  });
}

export async function readVideoDurationFromFile(file) {
  return readVideoMetadata(file);
}

export async function readVideoDurationFromUrl(url) {
  const normalized = resolveMaterialResourceUrl(url);
  if (!normalized) {
    throw new Error("缺少视频地址");
  }
  return readVideoMetadata(normalized);
}

function defaultMaterialTypeForMessage(message) {
  if (extractImages(message).length) {
    return "image";
  }
  if (extractVideoUrls(message).length) {
    return "video";
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
        : assetType === "audio"
          ? "聊天音频素材"
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
  const videos = extractVideoUrls(message);
  const attachments = extractAttachmentNames(message);
  if (assetType === "image") {
    return {
      text: content,
      images,
      attachments,
    };
  }
  if (assetType === "video") {
    return {
      text: content,
      videos,
      attachments,
    };
  }
  if (assetType === "audio") {
    return {
      text: content,
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
    video_count: extractVideoUrls(message).length,
    attachment_names: extractAttachmentNames(message),
  };
}

export function canSaveMessageAsMaterial(message, projectId = "") {
  if (!String(projectId || "").trim()) return false;
  const role = String(message?.role || "").trim();
  if (!["user", "assistant"].includes(role)) return false;
  if (extractImages(message).length) return true;
  if (extractVideoUrls(message).length) return true;
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
  const videos = extractVideoUrls(message);
  const firstImageUrl = images[0] || "";
  const firstVideoUrl = videos[0] || "";
  const primaryResourceUrl = firstImageUrl || firstVideoUrl;
  return {
    message,
    form: {
      asset_type: assetType,
      title: buildMaterialTitle(message, assetType),
      summary: buildMaterialSummary(message, assetType),
      preview_url: assetType === "image" ? firstImageUrl : "",
      content_url: primaryResourceUrl,
      mime_type: inferMaterialMimeTypeFromUrl(primaryResourceUrl),
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
