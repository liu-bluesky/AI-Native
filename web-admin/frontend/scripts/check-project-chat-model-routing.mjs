import assert from "node:assert/strict";
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";
import {
  buildModelOptionValue,
  MODEL_ROLE_CONFIGS,
  parseModelOptionValue,
  readModelRoleTarget,
  writeModelRoleTarget,
} from "../src/modules/project-chat/services/modelRouting.js";

assert.deepEqual(parseModelOptionValue("provider-a::image-model"), {
  providerId: "provider-a",
  modelName: "image-model",
});
assert.equal(buildModelOptionValue("provider-a", "image-model"), "provider-a::image-model");

const settings = writeModelRoleTarget({}, "image", "provider-a::image-model");
assert.deepEqual(readModelRoleTarget(settings, "image"), {
  roleId: "image",
  providerId: "provider-a",
  modelName: "image-model",
});

const mainRole = MODEL_ROLE_CONFIGS.find((item) => item.id === "main");
assert.ok(mainRole.modelTypes.includes("multimodal_chat"));
const routingModule = await import(
  "../src/modules/project-chat/services/modelRouting.js"
);
assert.equal(
  Object.prototype.hasOwnProperty.call(routingModule, "inferProjectChatModelRole"),
  false,
);

const scriptDirectory = path.dirname(fileURLToPath(import.meta.url));
const projectChatSource = fs.readFileSync(
  path.resolve(scriptDirectory, "../src/views/projects/ProjectChat.vue"),
  "utf8",
);
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
assert.ok(projectChatSource.includes("applyLocalLiuAgentMediaToolResults"));
assert.ok(projectChatSource.includes('["image", "edit_image"]'));
assert.match(
  projectChatSource,
  /const mediaToolNames = new Set\(\[[\s\S]*?"edit_image"/,
);

console.log("project chat model routing checks passed");
