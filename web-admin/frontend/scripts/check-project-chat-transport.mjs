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
  /const connections = new Map\(\);/,
  "project chat transport must retain websocket connections by project",
);

assert.match(
  transportSource,
  /function getWsClient\(projectId = wsProjectId\.value\)[\s\S]*?connections\.get\(normalizedProjectId\)/,
  "callers must route replies to the websocket that owns the request project",
);

assert.match(
  transportSource,
  /if \(entry\?\.client\?\.isOpen\?\.\(\)\) \{[\s\S]*?return entry\.client;/,
  "returning to a project must reuse its live websocket",
);

assert.doesNotMatch(
  transportSource,
  /wsProjectId\.value !== normalizedProjectId\)[\s\S]{0,160}disconnectWs\("switch project"\)/,
  "opening a project websocket must not close another project's background connection",
);

assert.match(
  transportSource,
  /onMessage: \(eventData\) => onMessage\?\.\(eventData, normalizedProjectId\)/,
  "background websocket events must carry their owning project id",
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
  "project switching must only select the foreground websocket state",
);

assert.doesNotMatch(
  projectWatcher,
  /rejectPendingRequests\(|disconnectWs\(/,
  "project switching must not cancel background requests or disconnect their websocket",
);

assert.match(
  projectChatSource,
  /onUnexpectedClose: \(reason, projectId\) => \{\s*rejectPendingRequests\(reason, \{ projectId \}\);/,
  "a broken project connection must reject only requests owned by that project",
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
