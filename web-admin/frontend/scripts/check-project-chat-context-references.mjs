import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";

import {
  buildContextReferenceAttachments,
  buildContextReferencesPrompt,
  mergeContextReferences,
} from "../src/modules/project-chat/mappers/contextReferenceMappers.js";

const references = mergeContextReferences(
  [],
  [
    {
      type: "image",
      messageId: "message-1",
      url: "https://example.test/gourd.png",
      label: "图片 1",
    },
    {
      type: "image",
      messageId: "message-1",
      url: "https://example.test/gourd.png",
      label: "重复图片",
    },
    {
      type: "text",
      messageId: "message-1",
      label: "选中文字",
      content: "把葫芦身体改成绿色",
    },
    {
      type: "video",
      messageId: "message-2",
      url: "https://example.test/demo.mp4",
      label: "视频 1",
    },
    {
      type: "audio",
      messageId: "message-3",
      url: "data:audio/wav;base64,AAAA",
      label: "音频 1",
    },
    {
      type: "file",
      messageId: "message-4",
      label: "需求文档.pdf",
      content: "历史附件摘要",
    },
  ],
);

assert.equal(references.length, 5, "identical context references must be deduplicated");

const legacyReferences = mergeContextReferences([], [
  {
    type: "image",
    messageId: "legacy-image",
    url: "https://example.test/legacy.png",
    label: "机器人的图片 1",
  },
  {
    type: "message",
    messageId: "legacy-message",
    label: "登录用户的历史消息",
    content: "历史消息内容",
  },
]);
assert.equal(legacyReferences[0].label, "图片 1");
assert.equal(legacyReferences[1].label, "消息内容");

const prompt = buildContextReferencesPrompt(references);
assert.match(prompt, /视为用户已明确提供的上下文/);
assert.match(prompt, /不要再次要求上传/);
assert.match(prompt, /generate_image/);
assert.match(prompt, /reference_asset_ids/);
assert.match(prompt, /edit_image/);
assert.match(prompt, /input_asset_ids/);
assert.match(prompt, /资产 ID/);
assert.match(prompt, /不要声称看不到引用内容/);
assert.match(prompt, /https:\/\/example\.test\/gourd\.png/);

const attachments = buildContextReferenceAttachments(references);
assert.equal(attachments.length, 4);
assert.equal(attachments[0].kind, "image");
assert.equal(attachments[0].attachmentId, references[0].id);
assert.equal(attachments[0].routingMode, "inline_image");
assert.equal(attachments[0].dataUrl, "https://example.test/gourd.png");
assert.equal(attachments[1].kind, "video");
assert.equal(attachments[2].kind, "audio");
assert.equal(attachments[2].dataUrl, "data:audio/wav;base64,AAAA");
assert.equal(attachments[3].kind, "file");
assert.equal(attachments[3].extractedText, "历史附件摘要");

const scriptDir = dirname(fileURLToPath(import.meta.url));
const projectChatSource = readFileSync(
  resolve(scriptDir, "../src/views/projects/ProjectChat.vue"),
  "utf8",
);
const composerSource = readFileSync(
  resolve(
    scriptDir,
    "../src/modules/project-chat/components/composer/ChatComposer.vue",
  ),
  "utf8",
);
const nativeBridgeSource = readFileSync(
  resolve(scriptDir, "../src/utils/native-desktop-bridge.js"),
  "utf8",
);
const tauriMainSource = readFileSync(
  resolve(scriptDir, "../src-tauri/src/main.rs"),
  "utf8",
);

assert.match(projectChatSource, /@contextmenu\.prevent="openMessageContextMenu/);
assert.match(projectChatSource, /添加到 liuAgent 对话/);
assert.doesNotMatch(projectChatSource, /追加到当前会话/);
assert.match(projectChatSource, /复制地址/);
assert.match(projectChatSource, /复制文件本身/);
assert.match(projectChatSource, /复制内容/);
assert.doesNotMatch(
  projectChatSource,
  /<small>\{\{ messageContextMenu\.label \}\}<\/small>/,
);
assert.match(projectChatSource, /buildContextReferenceAttachments\(activeContextRefs\)/);
assert.match(projectChatSource, /contextRefs:\s*activeContextRefs/);
assert.match(projectChatSource, /context_references:\s*activeContextRefs/);
assert.match(projectChatSource, /source: "desktop_local_agent\.media_tool_orchestration"/);
assert.match(
  projectChatSource,
  /用户要求修改现有图片时必须调用 edit_image/,
);
assert.match(projectChatSource, /不得改用 run_command、Python、Pillow、OpenCV/);
assert.match(projectChatSource, /主模型对话已完成（桌面端编排）/);
assert.doesNotMatch(
  projectChatSource,
  /messageRoleName\(message\)\}的\$\{contextReferenceTypeLabel/,
);
assert.match(composerSource, /composer-context-card/);
assert.match(composerSource, /clear-context-refs/);
assert.match(composerSource, /remove-context-ref/);
assert.match(nativeBridgeSource, /copyResourceFileToClipboard/);
assert.match(nativeBridgeSource, /copy_resource_file_to_clipboard/);
assert.match(tauriMainSource, /fn copy_resource_file_to_clipboard/);
assert.match(tauriMainSource, /copy_local_file_to_system_clipboard/);

console.log("project chat context reference checks passed");
