import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const scriptDir = dirname(fileURLToPath(import.meta.url));
const transportPath = resolve(
  scriptDir,
  "../src/modules/project-chat/composables/useProjectChatTransport.js",
);
const source = readFileSync(transportPath, "utf8");

assert.match(
  source,
  /let connectionGeneration = 0;/,
  "project chat transport must track websocket generations",
);

assert.match(
  source,
  /if \(!shouldForceReconnect && connectingPromise && wsProjectId\.value === normalizedProjectId\) \{\s*return connectingPromise;\s*\}/,
  "same-project websocket connection attempts must reuse the in-flight ready promise",
);

assert.match(
  source,
  /const generation = connectionGeneration \+ 1;\s*connectionGeneration = generation;/,
  "new websocket clients must capture a generation before event handlers are registered",
);

assert.match(
  source,
  /onOpen: \(\) => \{\s*if \(connectionGeneration !== generation\) return;\s*wsConnected\.value = true;/,
  "stale websocket open events must not mark the current transport connected",
);

assert.match(
  source,
  /onError: \(\) => \{\s*if \(connectionGeneration !== generation\) return;\s*wsConnected\.value = false;/,
  "stale websocket error events must not mutate current transport state",
);

assert.match(
  source,
  /onStale: \(reason\) => \{\s*if \(connectionGeneration !== generation\) return;\s*wsConnected\.value = false;/,
  "stale websocket heartbeat failures must not mutate current transport state",
);

assert.match(
  source,
  /onClose: \(event\) => \{\s*if \(connectionGeneration !== generation\) return;\s*wsConnected\.value = false;/,
  "stale websocket close events must not clear a replacement websocket",
);

assert.match(
  source,
  /if \(connectionGeneration !== generation \|\| wsClient\.value !== client\) \{\s*throw new Error\("WebSocket 连接已被替换"\);/,
  "ready resolution must only reject as replaced when the generation or active client changed",
);

console.log("project chat websocket transport checks passed");
