import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";

import {
  stripStructuredImageDuplicatesFromMarkdown,
  stripStructuredMediaDuplicatesFromMarkdown,
} from "../src/modules/project-chat/mappers/mediaMappers.js";

const duplicateUrl =
  "https://img.pinest.xyz/amg/images/2026/07/23/generated.png";
const inlineUrl = "https://example.test/inline.png";
const markdown = [
  "图片已经生成。",
  "",
  `![生成结果](${duplicateUrl})`,
  "",
  `![正文参考图](${inlineUrl})`,
  "",
  `<img src="${duplicateUrl}" alt="重复结果">`,
  "",
  "后续说明。",
].join("\n");

const deduplicated = stripStructuredImageDuplicatesFromMarkdown(markdown, [
  duplicateUrl,
]);

assert.doesNotMatch(
  deduplicated,
  new RegExp(duplicateUrl.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")),
  "structured image URLs must not render again inside the markdown body",
);
assert.match(
  deduplicated,
  new RegExp(inlineUrl.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")),
  "unrelated inline markdown images must remain visible",
);
assert.match(deduplicated, /图片已经生成。/);
assert.match(deduplicated, /后续说明。/);

const duplicateVideoUrl = "https://example.test/generated.mp4?token=a&amp;b";
const duplicateAudioUrl = "https://example.test/generated.mp3";
const inlineVideoUrl = "https://example.test/reference.mp4";
const mediaMarkdown = [
  "视频和音频已经生成。",
  "",
  `[查看视频](${duplicateVideoUrl})`,
  "",
  `<video controls><source src="${duplicateVideoUrl}"></video>`,
  "",
  duplicateAudioUrl,
  "",
  `<audio controls src="${duplicateAudioUrl}"></audio>`,
  "",
  `[保留参考视频](${inlineVideoUrl})`,
  "",
  "后续媒体说明。",
].join("\n");

const deduplicatedMedia = stripStructuredMediaDuplicatesFromMarkdown(
  mediaMarkdown,
  {
    videos: [duplicateVideoUrl.replace("&amp;", "&")],
    audios: [duplicateAudioUrl],
  },
);

assert.doesNotMatch(deduplicatedMedia, /generated\.mp4/);
assert.doesNotMatch(deduplicatedMedia, /generated\.mp3/);
assert.match(deduplicatedMedia, /reference\.mp4/);
assert.match(deduplicatedMedia, /视频和音频已经生成。/);
assert.match(deduplicatedMedia, /后续媒体说明。/);

const scriptDir = dirname(fileURLToPath(import.meta.url));
const projectChatSource = readFileSync(
  resolve(scriptDir, "../src/views/projects/ProjectChat.vue"),
  "utf8",
);
const messageCssSource = readFileSync(
  resolve(
    scriptDir,
    "../src/modules/project-chat/components/messages/ChatMessageList.css",
  ),
  "utf8",
);

assert.match(
  projectChatSource,
  /formatContent\([\s\S]*?images: extractImages\(row\),[\s\S]*?videos: extractVideos\(row\),[\s\S]*?audios: extractAudios\(row\),/,
  "assistant message rendering must suppress media already shown by the structured media area",
);
assert.match(
  projectChatSource,
  /const mediaToolNames = new Set\(\[[\s\S]*?"generate_image",[\s\S]*?"edit_image"/,
  "edit_image artifacts must be collected by the structured media renderer",
);
assert.match(
  messageCssSource,
  /\.chat-layout \.message-text img\s*\{[\s\S]*?max-width:\s*100%;[\s\S]*?height:\s*auto;/,
  "inline markdown images must stay within the message bubble",
);
assert.match(
  messageCssSource,
  /\.chat-layout \.preview-video\s*\{[\s\S]*?max-width:\s*100%;[\s\S]*?max-height:/,
  "structured videos must stay within the message bubble",
);
assert.match(
  messageCssSource,
  /\.chat-layout \.preview-audio\s*\{[\s\S]*?max-width:\s*100%;/,
  "structured audio controls must stay within the message bubble",
);

console.log("project chat media rendering checks passed");
