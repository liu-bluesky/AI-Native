import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const scriptDir = dirname(fileURLToPath(import.meta.url));
const projectChatPath = resolve(
  scriptDir,
  "../src/views/projects/ProjectChat.vue",
);
const storagePath = resolve(
  scriptDir,
  "../src/modules/project-chat/services/projectChatStorage.js",
);
const projectChatSource = readFileSync(projectChatPath, "utf8");
const storageSource = readFileSync(storagePath, "utf8");

for (const [label, endpointPattern] of [
  ["/chat/sessions", /\/chat\/sessions/],
  ["/chat/runtime", /\/chat\/runtime/],
  ["/chat/history", /\/chat\/history`/],
]) {
  assert.doesNotMatch(
    projectChatSource,
    endpointPattern,
    `project chat must not use remote conversation endpoint ${label}`,
  );
}

assert.ok(
  (projectChatSource.match(/persist_history:\s*false/g) || []).length >= 2,
  "normal and interaction chat requests must disable server history persistence",
);
assert.match(
  storageSource,
  /LOCAL_CHAT_SESSIONS_STORAGE_PREFIX/,
  "local session metadata storage must be defined",
);
assert.match(
  storageSource,
  /export function readLocalChatSessions/,
  "local session metadata must be readable",
);
assert.match(
  storageSource,
  /export function writeLocalChatSessions/,
  "local session metadata must be writable",
);

console.log("project chat local history checks passed");
