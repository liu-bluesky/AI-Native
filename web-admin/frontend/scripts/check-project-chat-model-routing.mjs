import assert from "node:assert/strict";
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const scriptDirectory = path.dirname(fileURLToPath(import.meta.url));
const modelRoutingSource = fs.readFileSync(
  path.resolve(scriptDirectory, "../src/modules/project-chat/services/modelRouting.js"),
  "utf8",
);
const projectChatSource = fs.readFileSync(
  path.resolve(scriptDirectory, "../src/views/projects/ProjectChat.vue"),
  "utf8",
);

assert.match(
  modelRoutingSource,
  /export function parseModelOptionValue[\s\S]*normalized\.indexOf\("::"\)[\s\S]*providerId[\s\S]*modelName/s,
  "model option parser must split provider/model values by ::",
);
assert.match(
  modelRoutingSource,
  /export function buildModelOptionValue[\s\S]*`\$\{provider\}::\$\{model\}`/s,
  "model option builder must serialize provider/model values with ::",
);
assert.match(
  modelRoutingSource,
  /id: "main"[\s\S]*modelTypes: \["text_generation", "multimodal_chat"\]/,
  "main model routing role must support multimodal chat models",
);
assert.match(
  modelRoutingSource,
  /export function readModelRoleTarget[\s\S]*export function writeModelRoleTarget/s,
  "model routing service must expose read/write helpers for role targets",
);
assert.equal(modelRoutingSource.includes("inferProjectChatModelRole"), false);

const composerTargetDeclarationIndex = projectChatSource.indexOf(
  "const composerSelectedModelTarget = computed",
);
const composerTargetFirstConsumerIndex = projectChatSource.indexOf(
  "const currentSelectedProvider = computed",
);
assert.notEqual(composerTargetDeclarationIndex, -1);
assert.notEqual(composerTargetFirstConsumerIndex, -1);
assert.ok(
  composerTargetDeclarationIndex < composerTargetFirstConsumerIndex,
  "composerSelectedModelTarget must be initialized before its computed consumers",
);
assert.equal(projectChatSource.includes("resolveRequestModelTarget"), false);
assert.equal(projectChatSource.includes("isProviderCapabilityRequest"), false);
assert.equal(projectChatSource.includes("providerCapabilityMode"), false);
assert.ok(projectChatSource.includes("mediaTools: localLiuAgentMediaTools.value"));
assert.ok(projectChatSource.includes("backendContext,"));
assert.ok(projectChatSource.includes("buildNativeBackendApiBaseUrl()"));
assert.ok(projectChatSource.includes("mediaImageToolConfigured"));
assert.ok(projectChatSource.includes("applyLocalLiuAgentMediaToolResults"));
assert.ok(projectChatSource.includes('["image", "edit_image"]'));
assert.match(
  projectChatSource,
  /const mediaToolNames = new Set\(\[[\s\S]*?"edit_image"/,
);

console.log("project chat model routing checks passed");
