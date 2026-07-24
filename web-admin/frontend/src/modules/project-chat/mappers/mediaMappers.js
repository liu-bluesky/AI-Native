const IMAGE_EXTENSIONS = new Set([
  "png",
  "jpg",
  "jpeg",
  "gif",
  "bmp",
  "webp",
  "svg",
  "heic",
  "heif",
]);

export function extractImages(message) {
  if (!message || !Array.isArray(message.images)) return [];
  return message.images
    .map((item) => String(item || "").trim())
    .filter(Boolean);
}

export function extractVideos(message) {
  if (!message || !Array.isArray(message.videos)) return [];
  return message.videos
    .map((item) => String(item || "").trim())
    .filter(Boolean);
}

export function extractAudios(message) {
  if (!message || !Array.isArray(message.audios)) return [];
  return message.audios
    .map((item) => String(item || "").trim())
    .filter(Boolean);
}

function normalizeComparableMediaUrl(value) {
  return String(value || "")
    .trim()
    .replace(/&amp;/gi, "&");
}

function comparableMediaUrlSet(values) {
  return new Set(
    (Array.isArray(values) ? values : [])
      .map(normalizeComparableMediaUrl)
      .filter(Boolean),
  );
}

function htmlTagContainsStructuredUrl(tag, attribute, structuredUrls) {
  if (!structuredUrls.size) return false;
  const attributePattern = new RegExp(
    `\\b${attribute}\\s*=\\s*(?:(["'])(.*?)\\1|([^\\s>]+))`,
    "gi",
  );
  let match = attributePattern.exec(tag);
  while (match) {
    if (structuredUrls.has(normalizeComparableMediaUrl(match[2] || match[3]))) {
      return true;
    }
    match = attributePattern.exec(tag);
  }
  return false;
}

function stripStructuredHtmlMediaBlocks(text, tagName, structuredUrls) {
  if (!structuredUrls.size) return text;
  const tagPattern = new RegExp(
    `<${tagName}\\b[^>]*>[\\s\\S]*?<\\/${tagName}\\s*>|<${tagName}\\b[^>]*\\/?>`,
    "gi",
  );
  return text.replace(tagPattern, (match) =>
    htmlTagContainsStructuredUrl(match, "src", structuredUrls) ? "" : match,
  );
}

export function stripStructuredMediaDuplicatesFromMarkdown(
  content,
  { images = [], videos = [], audios = [] } = {},
) {
  const text = String(content || "");
  const imageUrls = comparableMediaUrlSet(images);
  const videoUrls = comparableMediaUrlSet(videos);
  const audioUrls = comparableMediaUrlSet(audios);
  const linkedMediaUrls = new Set([...videoUrls, ...audioUrls]);
  if (!text || (!imageUrls.size && !linkedMediaUrls.size)) return text;

  const withoutMarkdownDuplicates = text.replace(
    /!\[[^\]]*\]\(\s*(?:<([^>]+)>|([^\s)]+))(?:\s+(?:"[^"]*"|'[^']*'|\([^)]*\)))?\s*\)/g,
    (match, angleUrl, plainUrl) =>
      imageUrls.has(normalizeComparableMediaUrl(angleUrl || plainUrl))
        ? ""
        : match,
  );

  const withoutImageDuplicates = withoutMarkdownDuplicates.replace(
    /<img\b[^>]*\bsrc\s*=\s*(["'])(.*?)\1[^>]*>/gi,
    (match, _quote, imageUrl) =>
      imageUrls.has(normalizeComparableMediaUrl(imageUrl)) ? "" : match,
  );

  const withoutLinkedMediaDuplicates = withoutImageDuplicates
    .replace(
      /(^|[^!])\[[^\]]*\]\(\s*(?:<([^>]+)>|([^\s)]+))(?:\s+(?:"[^"]*"|'[^']*'|\([^)]*\)))?\s*\)/gm,
      (match, prefix, angleUrl, plainUrl) =>
        linkedMediaUrls.has(
          normalizeComparableMediaUrl(angleUrl || plainUrl),
        )
          ? prefix
          : match,
    )
    .replace(/<a\b[^>]*>[\s\S]*?<\/a\s*>/gi, (match) =>
      htmlTagContainsStructuredUrl(match, "href", linkedMediaUrls) ? "" : match,
    )
    .replace(/<((?:https?:\/\/)[^>\s]+)>/gi, (match, mediaUrl) =>
      linkedMediaUrls.has(normalizeComparableMediaUrl(mediaUrl)) ? "" : match,
    );

  const withoutVideoDuplicates = stripStructuredHtmlMediaBlocks(
    withoutLinkedMediaDuplicates,
    "video",
    videoUrls,
  );
  const withoutAudioDuplicates = stripStructuredHtmlMediaBlocks(
    withoutVideoDuplicates,
    "audio",
    audioUrls,
  );

  return withoutAudioDuplicates
    .split("\n")
    .map((line) =>
      linkedMediaUrls.has(normalizeComparableMediaUrl(line)) ? "" : line,
    )
    .join("\n")
    .replace(/\n{3,}/g, "\n\n")
    .trim();
}

export function stripStructuredImageDuplicatesFromMarkdown(
  content,
  structuredImages = [],
) {
  return stripStructuredMediaDuplicatesFromMarkdown(content, {
    images: structuredImages,
  });
}

export function mergeMediaUrls(...groups) {
  const urls = [];
  const seen = new Set();
  for (const group of groups) {
    for (const item of Array.isArray(group) ? group : []) {
      const url = String(item || "").trim();
      if (!url || seen.has(url)) continue;
      seen.add(url);
      urls.push(url);
    }
  }
  return urls;
}

export function mergeImageUrls(...groups) {
  return mergeMediaUrls(...groups);
}

export function mergeVideoUrls(...groups) {
  return mergeMediaUrls(...groups);
}

export function mergeAudioUrls(...groups) {
  return mergeMediaUrls(...groups);
}

export function inferArtifactAssetType(item) {
  const explicit = String(item?.asset_type || item?.assetType || "")
    .trim()
    .toLowerCase();
  if (["image", "video", "audio"].includes(explicit)) return explicit;
  const mimeType = String(
    item?.mime_type || item?.mimeType || item?.content_type || "",
  )
    .trim()
    .toLowerCase();
  if (mimeType.startsWith("video/")) return "video";
  if (mimeType.startsWith("audio/")) return "audio";
  const contentUrl = String(
    item?.content_url ||
      item?.contentUrl ||
      item?.video_url ||
      item?.videoUrl ||
      item?.url ||
      "",
  ).trim();
  if (/\.(mp4|mov|m4v|webm|avi|mkv)(?:[?#].*)?$/i.test(contentUrl)) {
    return "video";
  }
  if (/\.(mp3|wav|m4a|aac|ogg|flac)(?:[?#].*)?$/i.test(contentUrl)) {
    return "audio";
  }
  return "image";
}

export function collectArtifactImageUrls(payload) {
  const directImages = Array.isArray(payload?.images) ? payload.images : [];
  const artifacts = Array.isArray(payload?.artifacts) ? payload.artifacts : [];
  // 统一素材消息里的直传图片和 artifact 预览地址，保持去重顺序稳定。
  return mergeImageUrls(
    directImages,
    artifacts.flatMap((item) =>
      inferArtifactAssetType(item) === "image"
        ? [
            item?.preview_url,
            item?.content_url,
            item?.previewUrl,
            item?.contentUrl,
            item?.url,
          ]
        : [],
    ),
  );
}

export function collectArtifactVideoUrls(payload) {
  const directVideos = Array.isArray(payload?.videos) ? payload.videos : [];
  const artifacts = Array.isArray(payload?.artifacts) ? payload.artifacts : [];
  // 视频 artifact 可能只有通用 url 字段，需要和显式 video 字段一起归并。
  return mergeVideoUrls(
    directVideos,
    artifacts.flatMap((item) =>
      inferArtifactAssetType(item) === "video"
        ? [
            item?.content_url,
            item?.contentUrl,
            item?.video_url,
            item?.videoUrl,
            item?.url,
          ]
        : [],
    ),
  );
}

export function collectArtifactAudioUrls(payload) {
  const directAudios = Array.isArray(payload?.audios) ? payload.audios : [];
  const artifacts = Array.isArray(payload?.artifacts) ? payload.artifacts : [];
  return mergeAudioUrls(
    directAudios,
    artifacts.flatMap((item) =>
      inferArtifactAssetType(item) === "audio"
        ? [
            item?.content_url,
            item?.contentUrl,
            item?.preview_url,
            item?.previewUrl,
            item?.url,
          ]
        : [],
    ),
  );
}

export function isAudioFile(file) {
  const mime = String(file?.type || "").toLowerCase();
  if (mime.startsWith("audio/")) return true;
  return ["mp3", "wav", "m4a", "aac", "ogg", "flac"].includes(
    fileExtension(file?.name || ""),
  );
}

export function fileExtension(name) {
  const text = String(name || "").trim();
  const idx = text.lastIndexOf(".");
  if (idx < 0 || idx === text.length - 1) return "";
  return text.slice(idx + 1).toLowerCase();
}

export function isImageFile(file) {
  const mime = String(file?.type || "").toLowerCase();
  if (mime.startsWith("image/")) return true;
  return IMAGE_EXTENSIONS.has(fileExtension(file?.name || ""));
}

export function isAllowedFileType(file, allowedTypes = []) {
  const rules = Array.isArray(allowedTypes) ? allowedTypes : [];
  if (!rules.length) return true;
  const mime = String(file?.type || "").toLowerCase();
  const ext = `.${fileExtension(file?.name || "")}`;
  for (const rule of rules) {
    if (!rule) continue;
    if (rule === "image/*" && isImageFile(file)) return true;
    if (rule.endsWith("/*") && mime.startsWith(rule.slice(0, -1))) return true;
    if (rule.startsWith(".") && rule === ext) return true;
    if (rule === mime) return true;
  }
  return false;
}

export function formatFileType(name) {
  const ext = fileExtension(name);
  return ext ? ext.toUpperCase() : "FILE";
}

export function clipText(text, maxChars) {
  const value = String(text || "").trim();
  if (!value) return "";
  if (value.length <= maxChars) return value;
  return `${value.slice(0, maxChars)}\n（内容已截断）`;
}

export function normalizeAttachment(name) {
  const normalizedName = String(name || "").trim();
  if (!normalizedName) return null;
  const ext = fileExtension(normalizedName);
  const kind = IMAGE_EXTENSIONS.has(ext) ? "image" : "document";
  return {
    name: normalizedName,
    kind,
    ext,
  };
}

export function extractAttachments(message) {
  const values = Array.isArray(message?.attachments) ? message.attachments : [];
  return values.map(normalizeAttachment).filter(Boolean);
}

export function attachmentTagType(kind) {
  return kind === "image" ? "success" : "info";
}

export function attachmentTypeLabel(attachment) {
  const ext = String(attachment?.ext || "")
    .trim()
    .toUpperCase();
  if (ext) return ext;
  return attachment?.kind === "image" ? "图片" : "文档";
}
