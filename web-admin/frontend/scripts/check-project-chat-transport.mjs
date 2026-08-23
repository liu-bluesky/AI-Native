import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath, pathToFileURL } from "node:url";

const scriptDir = dirname(fileURLToPath(import.meta.url));
const transportPath = resolve(
  scriptDir,
  "../src/modules/project-chat/composables/useProjectChatTransport.js",
);
const pendingRequestsPath = resolve(
  scriptDir,
  "../src/modules/project-chat/composables/useProjectChatPendingRequests.js",
);
const projectChatPath = resolve(
  scriptDir,
  "../src/views/projects/ProjectChat.vue",
);
const transportSource = readFileSync(transportPath, "utf8");
const pendingRequestsSource = readFileSync(pendingRequestsPath, "utf8");
const projectChatSource = readFileSync(projectChatPath, "utf8");

assert.match(
  transportSource,
  /本地项目聊天不使用远程实时接口/,
  "project chat transport must explicitly reject the removed remote websocket path",
);

assert.match(
  transportSource,
  /wsStatusText = computed\(\(\) => "本地 Runtime"\)/,
  "project chat transport must report the local runtime as its transport",
);

assert.doesNotMatch(
  `${transportSource}\n${projectChatSource}`,
  /new WebSocket|buildWsBaseUrl/,
  "local project chat must not construct a remote websocket",
);

assert.match(
  pendingRequestsSource,
  /function rejectAndCleanupRequests\(reason, options = \{\}\)[\s\S]*?pendingMatchesScope\(pending, options\)/,
  "pending request cleanup must support project-scoped rejection",
);

const projectWatcher =
  projectChatSource.match(
    /watch\(selectedProjectId, async \(value\) => \{[\s\S]*?\n\}\);/,
  )?.[0] || "";

assert.match(
  projectWatcher,
  /selectWsProject\(projectId\);/,
  "project switching must keep the local transport project context in sync",
);

globalThis.window = { setTimeout, clearTimeout };
const { useProjectChatPendingRequests } = await import(
  pathToFileURL(pendingRequestsPath).href
);
const pendingHarness = useProjectChatPendingRequests({
  currentChatSessionId: { value: "chat-a" },
});
const settled = [];
pendingHarness.createPendingRequest(
  "request-a",
  {
    projectId: "project-a",
    chatSessionId: "chat-a",
    resolve: () => settled.push("a:resolved"),
    reject: () => settled.push("a:rejected"),
  },
  { timeoutMs: 0 },
);
pendingHarness.createPendingRequest(
  "request-b",
  {
    projectId: "project-b",
    chatSessionId: "chat-b",
    resolve: () => settled.push("b:resolved"),
    reject: () => settled.push("b:rejected"),
  },
  { timeoutMs: 0 },
);
pendingHarness.rejectAndCleanupRequests("project b disconnected", {
  projectId: "project-b",
});
assert.equal(
  pendingHarness.pendingRequests.has("request-a"),
  true,
  "disconnecting project B must preserve project A's pending request",
);
assert.equal(
  pendingHarness.pendingRequests.has("request-b"),
  false,
  "disconnecting project B must clean up project B's pending request",
);
assert.deepEqual(
  settled,
  ["b:rejected"],
  "project-scoped cleanup must reject only the matching request",
);

console.log("project chat websocket transport checks passed");
