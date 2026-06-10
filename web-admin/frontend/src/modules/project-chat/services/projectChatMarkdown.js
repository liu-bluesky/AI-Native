import { marked } from "marked";
import {
  CODE_COPIED_ICON_HTML,
  CODE_COPY_ICON_HTML,
  CODE_PREVIEW_ICON_HTML,
  PREVIEWABLE_CODE_LANGUAGES,
} from "@/modules/project-chat/constants/projectChatConstants.js";

marked.setOptions({
  breaks: true,
  gfm: true,
});

export function escapeHtml(value) {
  return String(value || "")
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#39;");
}

export function normalizeCodeLanguage(value) {
  return String(value || "")
    .trim()
    .split(/\s+/)[0]
    .toLowerCase();
}

export function isPreviewableCodeBlock(content, language) {
  const normalizedLanguage = normalizeCodeLanguage(language);
  const text = String(content || "").trim();
  if (!text) return false;
  if (PREVIEWABLE_CODE_LANGUAGES.has(normalizedLanguage)) return true;
  if (/<template[\s>]/i.test(text) || /<script[\s>]/i.test(text)) return true;
  if (/<!doctype html/i.test(text) || /<html[\s>]/i.test(text)) return true;
  return false;
}

const markdownRenderer = new marked.Renderer();

markdownRenderer.code = ({ text, lang, escaped }) => {
  const language = normalizeCodeLanguage(lang);
  const languageLabel = escapeHtml(language || "code");
  const codeHtml = escaped ? text : escapeHtml(text);
  const actions = [];
  if (isPreviewableCodeBlock(text, language)) {
    actions.push(
      `<button type="button" class="chat-code-block__preview" aria-label="预览代码" title="预览代码" data-code-lang="${escapeHtml(language || "")}">${CODE_PREVIEW_ICON_HTML}</button>`,
    );
  }
  actions.push(
    `<button type="button" class="chat-code-block__copy" aria-label="复制代码" title="复制代码" data-copy-label="复制代码" data-copied-label="已复制" data-copy-icon="${escapeHtml(CODE_COPY_ICON_HTML)}" data-copied-icon="${escapeHtml(CODE_COPIED_ICON_HTML)}">${CODE_COPY_ICON_HTML}</button>`,
  );
  return [
    '<div class="chat-code-block">',
    '<div class="chat-code-block__toolbar">',
    `<span class="chat-code-block__lang">${languageLabel}</span>`,
    `<div class="chat-code-block__actions">${actions.join("")}</div>`,
    "</div>",
    `<pre><code${language ? ` class="language-${escapeHtml(language)}"` : ""}>${codeHtml}</code></pre>`,
    "</div>",
  ].join("");
};

export function renderProjectChatMarkdown(text) {
  return marked.parse(String(text || ""), { renderer: markdownRenderer });
}
