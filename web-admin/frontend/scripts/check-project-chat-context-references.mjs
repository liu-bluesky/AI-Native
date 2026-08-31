import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";

import {
  buildImplicitRecentImageReferences,
  buildContextReferenceAttachments,
  buildContextReferencesPrompt,
  mergeContextReferences,
  requestsImplicitRecentImageReference,
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
assert.match(prompt, /edit_image/);
assert.match(prompt, /input_asset_ids/);
assert.match(prompt, /纯文生图/);
assert.doesNotMatch(prompt, /reference_asset_ids/);
assert.match(prompt, /资产 ID/);
assert.match(prompt, /不要声称看不到引用内容/);
assert.match(prompt, /https:\/\/example\.test\/gourd\.png/);

const attachments = buildContextReferenceAttachments(references);
assert.equal(attachments.length, 4);
assert.equal(attachments[0].kind, "image");
assert.equal(attachments[0].attachmentId, references[0].id);
assert.equal(attachments[0].routingMode, "inline_content");
assert.equal(attachments[0].dataUrl, "https://example.test/gourd.png");
assert.equal(attachments[1].kind, "video");
assert.equal(attachments[2].kind, "audio");
assert.equal(attachments[2].dataUrl, "data:audio/wav;base64,AAAA");
assert.equal(attachments[3].kind, "file");
assert.equal(attachments[3].extractedText, "历史附件摘要");

assert.equal(requestsImplicitRecentImageReference("这个照片保存本地"), true);
assert.equal(requestsImplicitRecentImageReference("把上一张保存到 images"), true);
assert.equal(requestsImplicitRecentImageReference("把上面的内容记录一下"), false);

const implicitReferences = buildImplicitRecentImageReferences(
  [
    {
      id: "assistant-old",
      role: "assistant",
      images: ["https://example.test/old.png"],
    },
    {
      id: "assistant-latest",
      role: "assistant",
      images: [
        "https://example.test/latest-1.png",
        "https://example.test/latest-2.png",
      ],
    },
  ],
  "这个照片保存本地",
);
assert.equal(implicitReferences.length, 1);
assert.equal(implicitReferences[0].messageId, "assistant-latest");
assert.equal(implicitReferences[0].url, "https://example.test/latest-2.png");
assert.equal(implicitReferences[0].label, "最近一张图片");
assert.equal(implicitReferences[0].implicit, true);
assert.equal(implicitReferences[0].visibility, "model_context");

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
const resourceContextMenuSource = readFileSync(
  resolve(
    scriptDir,
    "../src/modules/project-chat/components/resource-context-menu/ResourceContextMenu.vue",
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
assert.doesNotMatch(projectChatSource, /追加到当前会话/);
assert.match(projectChatSource, /<ResourceContextMenu/);
assert.match(projectChatSource, /handleTeleportedResourceContextMenu/);
assert.match(projectChatSource, /\.el-image-viewer__canvas img/);
assert.match(resourceContextMenuSource, /添加到 liuAgent 对话/);
assert.match(resourceContextMenuSource, /在新窗口打开/);
assert.match(resourceContextMenuSource, /下载 \/ 另存为/);
assert.match(resourceContextMenuSource, /复制地址/);
assert.match(resourceContextMenuSource, /复制文件本身/);
assert.match(resourceContextMenuSource, /复制内容/);
assert.doesNotMatch(
  projectChatSource,
  /<small>\{\{ messageContextMenu\.label \}\}<\/small>/,
);
assert.match(projectChatSource, /buildContextReferenceAttachments\(activeContextRefs\)/);
assert.match(projectChatSource, /buildImplicitRecentImageReferences\(messages\.value, text\)/);
assert.match(projectChatSource, /images:\s*extractImages\(item\)/);
assert.match(projectChatSource, /videos:\s*extractVideos\(item\)/);
assert.match(projectChatSource, /audios:\s*extractAudios\(item\)/);
assert.match(
  projectChatSource,
  /visibleContextRefs = activeContextRefs\.filter\([\s\S]*?contextRefs:\s*visibleContextRefs/,
  "implicit historical image references must stay out of the visible user message",
);
assert.match(
  projectChatSource,
  /context_references:\s*activeContextRefs/,
  "implicit historical image references must remain available to the model",
);
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
assert.match(nativeBridgeSource, /saveResourceFile/);
assert.match(nativeBridgeSource, /save_resource_file/);
assert.match(nativeBridgeSource, /persistProjectChatAsset/);
assert.match(nativeBridgeSource, /persist_project_chat_asset/);
assert.match(tauriMainSource, /fn copy_resource_file_to_clipboard/);
assert.match(tauriMainSource, /fn save_resource_file/);
assert.match(tauriMainSource, /fn persist_project_chat_asset/);
assert.match(tauriMainSource, /copy_local_file_to_system_clipboard/);

console.log("project chat context reference checks passed");
