import { formatDateGroupLabel } from "@/utils/date.js";

// 会话来源映射保持纯函数，messageMappers.js 继续作为兼容出口供页面统一导入。
export function cloneInteractionValue(value) {
  if (Array.isArray(value)) {
    return value.map((item) => cloneInteractionValue(item));
  }
  if (value && typeof value === "object") {
    return Object.fromEntries(
      Object.entries(value).map(([key, item]) => [
        key,
        cloneInteractionValue(item),
      ]),
    );
  }
  return value;
}

export function normalizeStringList(values, max = 200) {
  if (!Array.isArray(values)) return [];
  const set = new Set();
  const items = [];
  for (const item of values) {
    const text = String(item || "").trim();
    if (!text) continue;
    const key = text.toLowerCase();
    if (set.has(key)) continue;
    set.add(key);
    items.push(text);
    if (items.length >= max) break;
  }
  return items;
}

export function normalizeChatSourceContext(item) {
  const source =
    item?.source_context && typeof item.source_context === "object"
      ? item.source_context
      : item || {};
  const normalized = {
    source_type: String(source.source_type || "").trim(),
    platform: String(source.platform || "").trim(),
    connector_id: String(source.connector_id || "").trim(),
    resolve_identity: String(source.resolve_identity || "").trim(),
    external_chat_id: String(source.external_chat_id || "").trim(),
    external_chat_name: String(source.external_chat_name || "").trim(),
    external_message_id: String(source.external_message_id || "").trim(),
    sender_id: String(source.sender_id || "").trim(),
    sender_name: String(source.sender_name || "").trim(),
    thread_key: String(source.thread_key || "").trim(),
    chat_mode: String(source.chat_mode || "").trim(),
    external_agent_type: String(source.external_agent_type || "").trim(),
    agent_session_id: String(source.agent_session_id || "").trim(),
    session_id: String(source.session_id || "").trim(),
    thread_id: String(source.thread_id || "").trim(),
  };
  [
    "assistant_workflow",
    "archive_workflow",
    "pending_interaction",
    "interaction_submission",
    "agent_runtime_v2",
    "agent_runtime_trace",
  ].forEach((key) => {
    if (source[key] && typeof source[key] === "object") {
      normalized[key] = cloneInteractionValue(source[key]);
    }
  });
  return normalized;
}

export function normalizeChatSession(item) {
  const sourceContext = normalizeChatSourceContext(item || {});
  return {
    id: String(item?.id || "").trim(),
    title: String(item?.title || "新对话").trim() || "新对话",
    preview: String(item?.preview || "").trim(),
    message_count: Number(item?.message_count || 0),
    source_type: sourceContext.source_type,
    platform: sourceContext.platform,
    connector_id: sourceContext.connector_id,
    external_chat_id: sourceContext.external_chat_id,
    external_chat_name: sourceContext.external_chat_name,
    thread_key: sourceContext.thread_key,
    source_context: sourceContext,
    created_at: String(item?.created_at || "").trim(),
    updated_at: String(item?.updated_at || "").trim(),
    last_message_at: String(item?.last_message_at || "").trim(),
  };
}

export function isGroupChatSession(session) {
  const source = normalizeChatSourceContext(session || {});
  return Boolean(source.external_chat_name || source.external_chat_id);
}

export function isBotConversationSession(session) {
  const source = normalizeChatSourceContext(session || {});
  return Boolean(
    source.platform ||
      source.connector_id ||
      source.external_chat_name ||
      source.external_chat_id,
  );
}

export function formatChatPlatformLabel(platform) {
  const normalized = String(platform || "")
    .trim()
    .toLowerCase();
  if (normalized === "feishu") return "飞书";
  if (normalized === "wechat") return "微信/企微";
  if (normalized === "qq") return "QQ";
  return normalized;
}

export function formatChatSessionSourceLabel(session) {
  const source = normalizeChatSourceContext(session || {});
  const sourceType = String(source.source_type || "").trim().toLowerCase();
  const groupName = source.external_chat_name;
  const platformLabel = formatChatPlatformLabel(source.platform);
  if (!groupName && !platformLabel) return "";
  if (sourceType === "manual_ai_chat" && platformLabel && !groupName) {
    return `${platformLabel}机器人对话`;
  }
  const suffix = source.external_chat_id ? "已解析" : "待解析 ID";
  if (groupName && platformLabel)
    return `${platformLabel}群 · ${groupName} · ${suffix}`;
  if (groupName) return `群 · ${groupName} · ${suffix}`;
  return `${platformLabel}群 · ${suffix}`;
}

export function resolveChatSessionGroupLabel(session) {
  const source = String(
    session?.last_message_at ||
      session?.updated_at ||
      session?.created_at ||
      "",
  ).trim();
  return formatDateGroupLabel(source, { fallback: "更早" });
}
