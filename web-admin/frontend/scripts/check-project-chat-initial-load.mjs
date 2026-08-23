import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const scriptDir = dirname(fileURLToPath(import.meta.url));
const projectChatPath = resolve(
  scriptDir,
  "../src/views/projects/ProjectChat.vue",
);
const source = readFileSync(projectChatPath, "utf8");

assert.match(
  source,
  /const runtimeExternalTools = ref\(\[\]\);/,
  "project chat must keep runtime external tools in local reactive state",
);
assert.doesNotMatch(
  source,
  /runtimeExternalToolsRefreshingProjectIds/,
  "project chat must not retain the removed remote runtime tool refresh queue",
);
assert.match(
  source,
  /watch\(selectedProjectId, async \(value\) => \{[\s\S]*await loadSelectedProjectConversation\(projectId\);/,
  "selectedProjectId watcher must remain the conversation loading entry",
);

const mountedBlock = source.match(/onMounted\(async \(\) => \{[\s\S]*?\n\}\);/)?.[0] || "";
assert.ok(mountedBlock, "ProjectChat must define its mounted initialization block");
assert.doesNotMatch(
  mountedBlock,
  /await fetchChatSessions\(/,
  "mounted initialization must not load chat sessions outside the project watcher",
);
assert.doesNotMatch(
  mountedBlock,
  /loadSelectedProjectConversation\(/,
  "mounted initialization must not duplicate the project watcher conversation load",
);

console.log("project chat initial load checks passed");
