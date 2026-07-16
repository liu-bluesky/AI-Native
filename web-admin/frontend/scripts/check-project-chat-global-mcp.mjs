import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const scriptDir = dirname(fileURLToPath(import.meta.url));
const projectChatSource = readFileSync(
  resolve(scriptDir, "../src/views/projects/ProjectChat.vue"),
  "utf8",
);

const reloadFunction = projectChatSource.match(
  /async function reloadLocalMcpConfig[\s\S]*?\n}\n\nasync function reloadLocalWebToolsConfig/,
)?.[0];

assert.ok(reloadFunction, "project chat must define reloadLocalMcpConfig");
assert.match(
  reloadFunction,
  /const globalFile = await readGlobalMcpConfigFile\(\)/,
  "project chat must load the global MCP file independently",
);
assert.match(
  reloadFunction,
  /if \(!normalizedProjectId \|\| !workspacePath\)[\s\S]*syncEffectiveMcpConfig\(\)[\s\S]*return/,
  "missing project workspace must keep the loaded global MCP config effective",
);
assert.match(
  reloadFunction,
  /const projectFile = await readProjectMcpConfigFile\(workspacePath\)/,
  "project MCP loading must remain scoped to a resolved workspace",
);
assert.doesNotMatch(
  reloadFunction,
  /if \(!normalizedProjectId \|\| !workspacePath\)[\s\S]{0,300}globalMcpConfig\.value = \{ mcpServers: \{\} \}/,
  "missing project workspace must not clear the global MCP config",
);

console.log("project chat global MCP checks passed");
