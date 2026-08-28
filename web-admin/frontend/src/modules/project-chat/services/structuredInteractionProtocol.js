const INTERACTION_KINDS = new Set([
  "clarification",
  "confirmation",
  "data_collection",
  "operation",
]);

const PRESENTATION_TYPES = new Set([
  "natural_language",
  "clarification",
  "summary",
  "form",
  "card",
  "table",
  "list",
  "wizard",
]);

const CHANNEL_PRESENTATIONS = {
  web: new Set(["natural_language", "clarification", "summary", "form", "table", "list", "wizard"]),
  mobile: new Set(["natural_language", "clarification", "summary", "card", "list", "wizard"]),
  bot: new Set(["natural_language", "clarification", "summary", "card", "list"]),
  desktop: new Set(["natural_language", "clarification", "summary", "form", "table", "list", "wizard"]),
};

function text(value) {
  return String(value || "").trim();
}

function clone(value) {
  if (value === undefined) return undefined;
  return JSON.parse(JSON.stringify(value));
}

function normalizePresentationHint(value) {
  const source = value && typeof value === "object" ? value : {};
  const type = text(source.type || source.mode).toLowerCase();
  return {
    type: PRESENTATION_TYPES.has(type) ? type : "",
    reason: text(source.reason),
  };
}

export function normalizeStructuredInteraction(value) {
  if (!value || typeof value !== "object" || Array.isArray(value)) return null;
  const source = value.structured_interaction || value.structuredInteraction || value;
  if (!source || typeof source !== "object" || Array.isArray(source)) return null;

  const kind = text(source.kind || source.type).toLowerCase();
  const fields = Array.isArray(source.fields)
    ? source.fields.filter((field) => field && typeof field === "object").map(clone)
    : [];
  const options = Array.isArray(source.options)
    ? source.options.filter((option) => option && typeof option === "object").map(clone)
    : [];
  const data = source.data && typeof source.data === "object" && !Array.isArray(source.data)
    ? clone(source.data)
    : {};

  if (!INTERACTION_KINDS.has(kind) && !fields.length && !options.length) return null;

  return {
    version: text(source.version) || "1",
    id: text(source.id || source.interaction_id),
    kind: INTERACTION_KINDS.has(kind) ? kind : "data_collection",
    operation: text(source.operation),
    status: text(source.status) || "waiting_user",
    userMessage: text(source.user_message || source.userMessage || source.message),
    summary: text(source.summary),
    data,
    fields,
    options,
    confirmationRequired: source.confirmation_required !== false,
    presentationHint: normalizePresentationHint(
      source.presentation_hint || source.presentationHint || source.presentation,
    ),
    submitLabel: text(source.submit_label || source.submitLabel) || "确认",
    cancelLabel: text(source.cancel_label || source.cancelLabel) || "取消",
    raw: clone(source),
  };
}

export function isStructuredInteraction(value) {
  return Boolean(normalizeStructuredInteraction(value));
}

export function extractStructuredInteractionCodeBlocks(value) {
  const blocks = [];
  const pattern = /```(?:structured-interaction|structured_interaction|interaction-json)\s*\n([\s\S]*?)```/gi;
  for (const match of String(value || "").matchAll(pattern)) {
    try {
      const parsed = JSON.parse(String(match[1] || "").trim());
      const interaction = normalizeStructuredInteraction(parsed);
      if (interaction) blocks.push(interaction);
    } catch {
      continue;
    }
  }
  return blocks;
}

export function chooseInteractionPresentation(value, context = {}) {
  const interaction = normalizeStructuredInteraction(value);
  if (!interaction) return "natural_language";

  const channel = text(context.channel || context.surface).toLowerCase() || "web";
  const supported = CHANNEL_PRESENTATIONS[channel] || CHANNEL_PRESENTATIONS.web;
  const hinted = interaction.presentationHint.type;
  if (hinted && supported.has(hinted)) return hinted;

  if ((interaction.options.length || interaction.fields.length) && channel === "bot") {
    return "card";
  }
  if (interaction.fields.length > 6 && channel !== "bot") return "wizard";
  if (interaction.fields.length && channel !== "bot") return "form";
  if (interaction.options.length) return channel === "web" ? "form" : "card";
  return interaction.confirmationRequired ? "summary" : "natural_language";
}

export function buildInteractionUserSummary(value) {
  const interaction = normalizeStructuredInteraction(value);
  if (!interaction) return "";
  const lines = [];
  if (interaction.userMessage) lines.push(interaction.userMessage);
  if (interaction.summary && interaction.summary !== interaction.userMessage) {
    lines.push(interaction.summary);
  }
  const entries = Object.entries(interaction.data);
  if (entries.length) {
    lines.push(
      entries
        .map(([key, item]) => `${key}：${Array.isArray(item) ? item.join("、") : String(item ?? "未填写")}`)
        .join("\n"),
    );
  }
  return lines.join("\n\n").trim();
}

export function buildStructuredInteractionPrompt() {
  return [
    "结构化交互协议：当需求需要补充信息、用户确认或多条数据编辑时，先输出渠道无关的 structured_interaction 数据。",
    "不要把 element-easy-form、飞书卡片或其他具体 UI 当作必选输出格式；presentation_hint 只能表达推荐方式，最终由宿主根据渠道和能力选择渲染器。",
    "structured_interaction 不能代替面向用户的自然语言说明；必须同时给出 user_message 或 summary，让用户理解准备做什么。",
    "只有用户明确确认后，系统才可以执行保存、创建、修改或删除操作。",
    "推荐字段：version、id、kind、operation、status、user_message、summary、data、fields、options、confirmation_required、presentation_hint、submit_label、cancel_label。",
  ].join("\n");
}
