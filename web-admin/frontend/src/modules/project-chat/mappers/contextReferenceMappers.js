import { extractAudios, extractImages, extractVideos } from "./mediaMappers.js";

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

function isInlineMediaUrl(value) {
  return /^(?:data:|blob:)/i.test(String(value || "").trim());
}

function isLocalAssetUrl(value) {
  return /^(?:asset:|file:|https?:\/\/asset\.localhost(?:[:/?#]|$))/i.test(
    String(value || "").trim(),
  );
}

export function stripInlineMediaDataUrls(value) {
  return String(value || "").replace(
    /data:(?:image|video|audio|application)\/[^\s"'<>)]+/gi,
    "[local-asset]",
  );
}

export function compactContextReferenceMediaUrl(value) {
  const url = String(value || "").trim();
  if (!url || isInlineMediaUrl(url)) return "";
  return url;
}

export function compactContextReferenceDataUrl(value, type = "") {
  const url = String(value || "").trim();
  if (!url) return "";
  if (isLocalAssetUrl(url) || /^blob:/i.test(url)) return "";
  if (/^https?:\/\//i.test(url)) return url;
  if (String(type || "").toLowerCase() === "audio" && /^data:audio\//i.test(url)) {
    return url;
  }
  return "";
}

function compactContextReferenceId(value) {
  const id = String(value || "").trim();
  if (!id) return "";
  if (isInlineMediaUrl(id) || /data:(?:image|video|audio|application)\//i.test(id)) {
    return "";
  }
  return id;
}

function isGeneratedContextReferenceId(value) {
  return /^context-ref-\d+-/.test(String(value || "").trim());
}

function compactPersistentAssetId(...values) {
  for (const value of values) {
    const id = compactContextReferenceId(value);
    if (id && !isGeneratedContextReferenceId(id)) {
      return id;
    }
  }
  return "";
}

function contextReferencePersistentId(item = {}) {
  return compactPersistentAssetId(
    item.id,
    item.assetId,
    item.asset_id,
    item.localPath,
    item.local_path,
    item.assetUri,
    item.asset_uri,
    item.url,
  );
}

function messageMediaAssetsByKind(message, kind) {
  return (
    Array.isArray(message?.mediaAssets)
      ? message.mediaAssets
      : Array.isArray(message?.media_assets)
        ? message.media_assets
        : []
  ).filter((asset) => String(asset?.kind || "").trim() === kind);
}

function mediaAssetLocatorCandidates(asset = {}) {
  return [
    asset.assetId,
    asset.asset_id,
    asset.assetUri,
    asset.asset_uri,
    asset.displayUrl,
    asset.display_url,
    asset.localPath,
    asset.local_path,
    asset.sourceUrl,
    asset.source_url,
  ]
    .map((value) => String(value || "").trim())
    .filter(Boolean);
}

export function matchMessageMediaAsset(message, reference = {}, index = 0) {
  const kind = String(reference?.type || reference?.kind || "").trim();
  const assets = messageMediaAssetsByKind(message, kind);
  if (!assets.length) return null;
  const needles = [
    reference?.id,
    reference?.assetId,
    reference?.asset_id,
    reference?.assetUri,
    reference?.asset_uri,
    reference?.url,
    reference?.localPath,
    reference?.local_path,
    reference?.displayUrl,
    reference?.display_url,
    reference?.sourceUrl,
    reference?.source_url,
  ]
    .map((value) => String(value || "").trim())
    .filter((value) => value && !isInlineMediaUrl(value));
  const matched = assets.find((asset) => {
    const candidates = mediaAssetLocatorCandidates(asset);
    return needles.some((needle) => candidates.includes(needle));
  });
  if (matched) return matched;
  if (assets.length === 1) return assets[0];
  return index >= 0 ? assets[index] || null : null;
}

export function enrichContextReferenceWithMediaAsset(
  reference = {},
  message = null,
  index = 0,
) {
  const item = normalizeContextReference(reference, index);
  if (!item) return null;
  if (!["image", "video", "audio", "file"].includes(item.type)) {
    return item;
  }
  const asset = matchMessageMediaAsset(
    message,
    { ...item, ...reference, type: item.type },
    index,
  );
  const localPath = compactContextReferenceMediaUrl(
    asset?.localPath || asset?.local_path || item.localPath,
  );
  const assetUri = compactContextReferenceMediaUrl(
    asset?.assetUri ||
      asset?.asset_uri ||
      asset?.displayUrl ||
      asset?.display_url ||
      item.assetUri,
  );
  const url = compactContextReferenceMediaUrl(
    assetUri ||
      localPath ||
      item.url ||
      asset?.sourceUrl ||
      asset?.source_url,
  );
  const persistentId = compactPersistentAssetId(
    asset?.assetId,
    asset?.asset_id,
    reference?.assetId,
    reference?.asset_id,
    reference?.id,
    localPath,
    assetUri,
    url,
  );
  if (!persistentId) return null;
  return {
    ...item,
    id: persistentId,
    url,
    assetUri: assetUri || url,
    localPath,
    mimeType: String(
      item.mimeType || asset?.mimeType || asset?.mime_type || "",
    ).trim(),
  };
}

function compactHistoryFallbackMediaUrl(value) {
  const url = compactContextReferenceMediaUrl(value);
  if (!url || isLocalAssetUrl(url)) return "";
  return url;
}

export function compactHistoryMediaReferences(message, kind = "image") {
  const assets = messageMediaAssetsByKind(message, kind);
  if (assets.length) {
    return assets
      .map((asset) =>
        compactContextReferenceMediaUrl(
          asset.assetId ||
            asset.asset_id ||
            asset.localPath ||
            asset.local_path ||
            "",
        ),
      )
      .filter(Boolean);
  }
  const values =
    kind === "video"
      ? extractVideos(message)
      : kind === "audio"
        ? extractAudios(message)
        : extractImages(message);
  return values.map(compactHistoryFallbackMediaUrl).filter(Boolean);
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
  const url = compactContextReferenceMediaUrl(input?.url);
  const assetUri = compactContextReferenceMediaUrl(
    input?.assetUri || input?.asset_uri,
  );
  const localPath = compactContextReferenceMediaUrl(
    input?.localPath || input?.local_path,
  );
  const dataUrl = compactContextReferenceDataUrl(
    input?.dataUrl || input?.data_url || input?.url,
    type,
  );
  const content = compactText(stripInlineMediaDataUrls(input?.content));
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
  const identity = [type, messageId, url || localPath || assetUri, content].join("|");
  if (!url && !localPath && !assetUri && !dataUrl && !content && !label) return null;
  return {
    id:
      compactContextReferenceId(input?.id) ||
      `context-ref-${index}-${identity}`,
    type,
    messageId,
    url,
    assetUri,
    localPath,
    dataUrl,
    label,
    content,
    mimeType: String(input?.mimeType || input?.mime_type || "").trim(),
    implicit: input?.implicit === true,
    visibility: String(input?.visibility || "").trim() || "user_visible",
    source:
      String(input?.source || input?.sourceType || "").trim() ||
      "conversation_reference",
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
    const key = [
      item.type,
      item.messageId,
      item.url,
      item.localPath,
      item.assetUri,
      item.content,
    ].join("|");
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
    const imageAssets = messageMediaAssetsByKind(message, "image");
    const lastAsset = imageAssets[imageAssets.length - 1];
    const lastUrl = imageUrls[imageUrls.length - 1];
    if (!lastUrl && !lastAsset) continue;
    const enriched = enrichContextReferenceWithMediaAsset(
      {
        type: "image",
        messageId: String(message?.id || "").trim(),
        id: lastAsset?.assetId || lastAsset?.asset_id,
        url:
          lastAsset?.assetUri ||
          lastAsset?.displayUrl ||
          lastAsset?.localPath ||
          lastUrl,
        assetUri: lastAsset?.assetUri || lastAsset?.displayUrl,
        localPath: lastAsset?.localPath,
        label: "最近一张图片",
        mimeType: String(lastAsset?.mimeType || lastAsset?.mime_type || "image/*").trim() || "image/*",
        implicit: true,
        visibility: "model_context",
      },
      message,
      imageAssets.length ? imageAssets.length - 1 : imageUrls.length - 1,
    );
    return enriched ? [enriched] : [];
  }
  return [];
}

export function buildContextReferencesPrompt(references = []) {
  const items = mergeContextReferences([], references);
  if (!items.length) return "";
  const blocks = items.map((item, index) => {
    const lines = [
      `${index + 1}. ${contextReferenceTypeLabel(item.type)}：${item.label}`,
    ];
    const assetId = contextReferencePersistentId(item);
    if (assetId) {
      lines.push(`   资产 ID：${assetId}`);
    }
    if (item.content) lines.push(`   内容：${item.content}`);
    if (item.url && !isInlineMediaUrl(item.url)) {
      lines.push(`   资源地址：${item.url}`);
    }
    return lines.join("\n");
  });
  return [
    "本轮引用了当前会话中的历史内容。请把这些内容视为用户已明确提供的上下文，不要再次要求上传：",
    ...blocks,
    "若用户要求基于上述图片继续生成、重绘或修改，请调用 edit_image，并通过 input_asset_ids 选择一张图片资产；generate_image 仅用于没有参考图的纯文生图。不要声称看不到引用内容，也不要改用本地脚本处理图片。",
  ].join("\n");
}

export function buildContextReferenceAttachments(references = []) {
  return mergeContextReferences([], references)
    .filter((item) => ["image", "video", "audio", "file"].includes(item.type))
    .map((item, index) => {
      const localPath = compactContextReferenceMediaUrl(item.localPath);
      return {
        attachmentId:
          contextReferencePersistentId(item) ||
          `context-ref-attachment-${index}`,
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
        source: item.source || "conversation_reference",
        inputIntent: item.inputIntent || "context",
        remoteUrl: compactContextReferenceMediaUrl(item.remoteUrl || item.url),
        assetUri: compactContextReferenceMediaUrl(item.assetUri || item.url),
        localPath,
        providerFileId: "",
        routingMode: "inline_content",
        extractionStatus:
          item.url || localPath || item.assetUri
            ? "conversation_reference"
            : "metadata_only",
        dataUrl: localPath
          ? ""
          : compactContextReferenceDataUrl(
              item.dataUrl || item.url,
              item.type,
            ),
        extractedText: item.content,
        error: "",
      };
    });
}
