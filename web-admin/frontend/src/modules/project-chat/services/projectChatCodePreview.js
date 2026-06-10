import {
  escapeHtml,
  normalizeCodeLanguage,
} from "@/modules/project-chat/services/projectChatMarkdown.js";

export function buildCodePreviewTitle(language, content) {
  const normalizedLanguage = normalizeCodeLanguage(language);
  if (normalizedLanguage === "vue" || /<template[\s>]/i.test(content)) {
    return "Vue 组件预览";
  }
  if (normalizedLanguage === "html" || normalizedLanguage === "htm") {
    return "HTML 预览";
  }
  return "代码预览";
}

function extractSfcTemplate(content) {
  const match = String(content || "").match(
    /<template[^>]*>([\s\S]*?)<\/template>/i,
  );
  return String(match?.[1] || "").trim();
}

function extractSfcStyles(content) {
  const styles = [];
  const regex = /<style[^>]*>([\s\S]*?)<\/style>/gi;
  for (const match of String(content || "").matchAll(regex)) {
    const text = String(match?.[1] || "").trim();
    if (text) styles.push(text);
  }
  return styles;
}

function extractSfcScript(content) {
  const setupMatch = String(content || "").match(
    /<script\b[^>]*setup[^>]*>([\s\S]*?)<\/script>/i,
  );
  if (setupMatch) return String(setupMatch[1] || "");
  const normalMatch = String(content || "").match(
    /<script\b[^>]*>([\s\S]*?)<\/script>/i,
  );
  return String(normalMatch?.[1] || "");
}

function collectScriptRefInitializers(scriptContent) {
  const refs = [];
  const regex =
    /const\s+([A-Za-z_$][\w$]*)\s*=\s*ref(?:<[^>]+>)?\s*\(([\s\S]*?)\)\s*(?:;|\n)/g;
  for (const match of String(scriptContent || "").matchAll(regex)) {
    const name = String(match?.[1] || "").trim();
    const expression = String(match?.[2] || "").trim();
    if (!name) continue;
    refs.push({ name, expression });
  }
  return refs;
}

function collectScriptReactiveInitializers(scriptContent) {
  const reactives = [];
  const regex =
    /const\s+([A-Za-z_$][\w$]*)\s*=\s*reactive\s*\((\{[\s\S]*?\})\s*\)\s*(?:;|\n)/g;
  for (const match of String(scriptContent || "").matchAll(regex)) {
    const name = String(match?.[1] || "").trim();
    const expression = String(match?.[2] || "").trim();
    if (!name) continue;
    reactives.push({ name, expression });
  }
  return reactives;
}

function collectScriptFunctionNames(scriptContent) {
  const names = new Set();
  const regex = /(?:async\s+)?function\s+([A-Za-z_$][\w$]*)\s*\(/g;
  for (const match of String(scriptContent || "").matchAll(regex)) {
    const name = String(match?.[1] || "").trim();
    if (!name) continue;
    names.add(name);
  }
  return Array.from(names);
}

function collectTemplateModelPaths(template) {
  const paths = new Set();
  const regex = /v-model(?:\.[^=]+)?="([^"]+)"/g;
  for (const match of String(template || "").matchAll(regex)) {
    const path = String(match?.[1] || "").trim();
    if (!path) continue;
    paths.add(path);
  }
  return Array.from(paths);
}

function transformVueTemplateToStaticHtml(template) {
  let html = String(template || "").trim();
  if (!html) return "";

  html = html.replace(/<template[^>]*>|<\/template>/gi, "");
  html = html.replace(/<script[\s\S]*?<\/script>/gi, "");

  html = html.replace(/{{[\s\S]*?}}/g, "示例内容");
  html = html.replace(/\s(?:v-|:|@)[^=\s>]+(?:=(["'])[\s\S]*?\1)?/g, "");

  html = html.replace(
    /<el-form-item\b([^>]*)>/gi,
    '<div class="preview-form-item"$1>',
  );
  html = html.replace(/<\/el-form-item>/gi, "</div>");
  html = html.replace(/<el-form\b([^>]*)>/gi, '<form class="preview-form"$1>');
  html = html.replace(/<\/el-form>/gi, "</form>");
  html = html.replace(/<el-alert\b([^>]*)>/gi, '<div class="preview-alert"$1>');
  html = html.replace(/<\/el-alert>/gi, "</div>");
  html = html.replace(
    /<el-checkbox\b([^>]*)>/gi,
    '<label class="preview-checkbox"$1><input type="checkbox" />',
  );
  html = html.replace(/<\/el-checkbox>/gi, "</label>");
  html = html.replace(
    /<el-button\b([^>]*)>/gi,
    '<button type="button" class="preview-button"$1>',
  );
  html = html.replace(/<\/el-button>/gi, "</button>");
  html = html.replace(
    /<el-input-number\b([^>]*)\/>/gi,
    '<input type="number" class="preview-input" $1 />',
  );
  html = html.replace(/<el-input\b([^>]*)\/>/gi, (_match, attrs) => {
    const typeMatch = String(attrs || "").match(/\btype=(['"])(.*?)\1/i);
    const type = String(typeMatch?.[2] || "text").trim() || "text";
    return `<input class="preview-input" type="${escapeHtml(type)}" ${attrs || ""} />`;
  });
  html = html.replace(
    /<el-input\b([^>]*)>([\s\S]*?)<\/el-input>/gi,
    (_match, attrs) => {
      const typeMatch = String(attrs || "").match(/\btype=(['"])(.*?)\1/i);
      const type = String(typeMatch?.[2] || "text").trim() || "text";
      if (type === "textarea") {
        return `<textarea class="preview-textarea" ${attrs || ""}></textarea>`;
      }
      return `<input class="preview-input" type="${escapeHtml(type)}" ${attrs || ""} />`;
    },
  );
  html = html.replace(
    /<el-select\b([^>]*)>([\s\S]*?)<\/el-select>/gi,
    '<select class="preview-select"$1>$2</select>',
  );
  html = html.replace(
    /<el-option\b([^>]*)>([\s\S]*?)<\/el-option>/gi,
    (_match, attrs, inner) => {
      const labelMatch = String(attrs || "").match(/\blabel=(['"])(.*?)\1/i);
      const label = String(labelMatch?.[2] || inner || "选项").trim() || "选项";
      return `<option>${escapeHtml(label)}</option>`;
    },
  );
  html = html.replace(
    /<el-radio-group\b([^>]*)>/gi,
    '<div class="preview-radio-group"$1>',
  );
  html = html.replace(/<\/el-radio-group>/gi, "</div>");
  html = html.replace(
    /<el-radio\b([^>]*)>([\s\S]*?)<\/el-radio>/gi,
    '<label class="preview-radio"$1><input type="radio" />$2</label>',
  );
  html = html.replace(
    /<el-switch\b([^>]*)\/?>/gi,
    '<label class="preview-switch"$1><span class="preview-switch__track"></span></label>',
  );
  html = html.replace(/<el-icon\b[^>]*>[\s\S]*?<\/el-icon>/gi, "");

  html = html.replace(
    /<el-[a-z0-9-]+\b([^>]*)>/gi,
    '<div class="preview-block"$1>',
  );
  html = html.replace(/<\/el-[a-z0-9-]+>/gi, "</div>");

  html = html.replace(
    /\s(?:clearable|show-password|filterable|multiple|text|circle|plain|border|show-icon|destroy-on-close|closable)(?=[\s>])/gi,
    "",
  );
  return html;
}

function buildStaticVuePreviewHtml(template) {
  const html = transformVueTemplateToStaticHtml(template);
  if (!html) return "";
  return ['<div class="preview-static-shell">', html, "</div>"].join("");
}

export function buildHtmlPreviewSrcdoc(content) {
  const html = String(content || "").trim();
  if (!html) return "";
  if (/<!doctype html/i.test(html) || /<html[\s>]/i.test(html)) {
    return html;
  }
  return [
    "<!doctype html>",
    '<html lang="zh-CN">',
    "<head>",
    '<meta charset="UTF-8" />',
    '<meta name="viewport" content="width=device-width, initial-scale=1.0" />',
    "<style>html,body{margin:0;padding:0;min-height:100%;background:#f7f7f8;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,'Helvetica Neue',Arial,'Noto Sans','PingFang SC','Microsoft YaHei',sans-serif;}body{padding:24px;}</style>",
    "</head>",
    "<body>",
    html,
    "</body>",
    "</html>",
  ].join("");
}

export function buildVuePreviewSrcdoc(content) {
  const template = extractSfcTemplate(content) || String(content || "").trim();
  if (!template) return "";
  const styles = extractSfcStyles(content).join("\n\n");
  const scriptContent = extractSfcScript(content);
  const refInitializers = collectScriptRefInitializers(scriptContent);
  const reactiveInitializers = collectScriptReactiveInitializers(scriptContent);
  const functionNames = collectScriptFunctionNames(scriptContent);
  const modelPaths = collectTemplateModelPaths(template);
  const staticPreviewHtml = buildStaticVuePreviewHtml(template);

  // 预览页先渲染静态降级 DOM，再尝试加载 Vue/Element Plus，避免外链失败时弹窗空白。
  return [
    "<!doctype html>",
    '<html lang="zh-CN">',
    "<head>",
    '<meta charset="UTF-8" />',
    '<meta name="viewport" content="width=device-width, initial-scale=1.0" />',
    '<link rel="stylesheet" href="https://unpkg.com/element-plus/dist/index.css" />',
    "<style>",
    "html,body{margin:0;padding:0;min-height:100%;background:#f7f7f8;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,'Helvetica Neue',Arial,'Noto Sans','PingFang SC','Microsoft YaHei',sans-serif;}",
    "body{padding:24px;box-sizing:border-box;}",
    "#app{min-height:calc(100vh - 48px);}",
    ".preview-static-shell{min-height:calc(100vh - 48px);}",
    ".preview-form{display:block;}",
    ".preview-form-item{display:flex;flex-direction:column;gap:8px;margin-bottom:18px;}",
    ".preview-input,.preview-textarea,.preview-select{width:100%;box-sizing:border-box;padding:10px 12px;border:1px solid #dcdfe6;border-radius:8px;background:#fff;color:#1f2937;font-size:14px;line-height:1.5;}",
    ".preview-textarea{min-height:96px;resize:vertical;}",
    ".preview-button{display:inline-flex;align-items:center;justify-content:center;min-height:40px;padding:0 18px;border-radius:10px;border:1px solid #0f172a;background:#0f172a;color:#fff;font-size:14px;font-weight:600;cursor:default;}",
    ".preview-checkbox,.preview-radio{display:inline-flex;align-items:center;gap:8px;color:#4b5563;font-size:14px;}",
    ".preview-switch{display:inline-flex;align-items:center;width:42px;height:24px;padding:2px;border-radius:999px;background:rgba(226,232,240,.92);box-sizing:border-box;}",
    ".preview-switch__track{display:block;width:20px;height:20px;border-radius:50%;background:#0f172a;margin-left:auto;}",
    ".preview-alert{margin-bottom:16px;padding:10px 12px;border-radius:10px;border:1px solid rgba(56,189,248,.18);background:rgba(239,249,255,.88);color:#0f172a;font-size:13px;line-height:1.6;}",
    ".preview-block{display:block;}",
    ".preview-error{padding:16px;border-radius:16px;background:#fff1f2;border:1px solid rgba(244,63,94,.18);color:#9f1239;font-size:14px;line-height:1.7;white-space:pre-wrap;}",
    styles,
    "</style>",
    "</head>",
    "<body>",
    `<div id="app">${staticPreviewHtml}</div>`,
    '<script src="https://unpkg.com/vue@3/dist/vue.global.prod.js"><\\/script>',
    '<script src="https://unpkg.com/element-plus/dist/index.full.min.js"><\\/script>',
    "<script>",
    `const previewTemplate = ${JSON.stringify(template)};`,
    `const previewRefs = ${JSON.stringify(refInitializers)};`,
    `const previewReactives = ${JSON.stringify(reactiveInitializers)};`,
    `const previewFunctions = ${JSON.stringify(functionNames)};`,
    `const previewModelPaths = ${JSON.stringify(modelPaths)};`,
    `function evaluateLiteral(source, fallback){ if(!source){ return fallback; } try { return (new Function("return (" + source + ")"))(); } catch { return fallback; } }`,
    `function inferLeafDefault(path){ const leaf = String(path.split('.').pop() || '').toLowerCase(); if(/^(is|has|can|show|enable|loading|locked|disabled|visible|checked|remember|submitting)/.test(leaf)){ return false; } if(/count|size|total|days|length|index|step/.test(leaf)){ return 0; } return ''; }`,
    `function ensurePath(root, path){ const parts = String(path || '').split('.').map((item) => item.trim()).filter(Boolean); if(!parts.length){ return; } let current = root; for(let i = 0; i < parts.length; i += 1){ const key = parts[i]; const isLast = i === parts.length - 1; if(isLast){ if(current[key] === undefined){ current[key] = inferLeafDefault(path); } break; } if(!current[key] || typeof current[key] !== 'object' || Array.isArray(current[key])){ current[key] = {}; } current = current[key]; } }`,
    `function noop(){ return undefined; }`,
    `const component = { setup(){ const ctx = {}; for(const item of previewReactives){ ctx[item.name] = Vue.reactive(evaluateLiteral(item.expression, {})); } for(const item of previewRefs){ ctx[item.name] = Vue.ref(evaluateLiteral(item.expression, inferLeafDefault(item.name))); } if(!ctx.form){ ctx.form = Vue.reactive({}); } if(!ctx.rules){ ctx.rules = Vue.reactive({}); } for(const path of previewModelPaths){ const rootName = String(path.split('.')[0] || '').trim(); if(!rootName){ continue; } const rootValue = ctx[rootName]; if(rootValue && typeof rootValue === 'object' && !('value' in rootValue)){ ensurePath(rootValue, path.split('.').slice(1).join('.')); continue; } if(rootValue && typeof rootValue === 'object' && 'value' in rootValue){ if(rootValue.value === undefined || rootValue.value === null || typeof rootValue.value !== 'object'){ rootValue.value = {}; } ensurePath(rootValue.value, path.split('.').slice(1).join('.')); continue; } if(path.includes('.')){ ctx[rootName] = Vue.reactive({}); ensurePath(ctx[rootName], path.split('.').slice(1).join('.')); } else if(ctx[rootName] === undefined){ ctx[rootName] = Vue.ref(inferLeafDefault(path)); } } for(const name of previewFunctions){ if(!ctx[name]){ ctx[name] = noop; } } return ctx; }, template: previewTemplate };`,
    `function showError(error){ const el = document.getElementById('app'); if(el){ el.innerHTML = '<div class="preview-error">' + String(error && error.message ? error.message : error) + '</div>'; } }`,
    `window.setTimeout(() => { if(!window.Vue || !window.ElementPlus){ return; } try { const app = Vue.createApp(component); app.use(ElementPlus); app.config.errorHandler = (error) => { showError(error); }; app.mount('#app'); } catch (error) { showError(error); } }, 80);`,
    "<\\/script>",
    "</body>",
    "</html>",
  ].join("");
}
