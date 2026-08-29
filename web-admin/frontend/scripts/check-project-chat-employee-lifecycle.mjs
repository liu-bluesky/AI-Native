import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";

const source = await readFile(
  new URL("../src/views/projects/ProjectChat.vue", import.meta.url),
  "utf8",
);
const dialogSource = await readFile(
  new URL("../src/components/ProjectEmployeeUpdateDialog.vue", import.meta.url),
  "utf8",
);
const directoryServiceSource = await readFile(
  new URL("../src/services/local-agent-directory-service.js", import.meta.url),
  "utf8",
);

assert.doesNotMatch(source, /id:\s*["']employee_create["']/);
assert.doesNotMatch(source, /id:\s*["']employee_delete["']/);
assert.doesNotMatch(source, /assist_employee_create/);
assert.doesNotMatch(source, /case ["']create["']|case ["']draft["']/);
assert.doesNotMatch(source.slice(0, 17000), /创建智能体|确认创建|仅创建智能体/);
assert.match(source, /case ["']update["'][\s\S]*autoUpdateEmployeeFromDraftMessage/s);
assert.match(source, /case ["']delete["'][\s\S]*handleEmployeeDeleteIntent/s);
assert.match(source, /async function handleQuickUpdateEmployee[\s\S]*saveLocalAgentDirectoryResources/s);
assert.match(source, /async function handleEmployeeDeleteIntent[\s\S]*deleteLocalProjectAgent/s);
assert.match(dialogSource, /title="确认更新智能体"[\s\S]*确认更新/s);
assert.doesNotMatch(dialogSource, /确认创建|仅创建智能体|ProjectEmployeeDraftCreateDialog/);
assert.match(directoryServiceSource, /function resolveDirectories[\s\S]*\.ai-employee[\s\S]*agents[\s\S]*skills[\s\S]*rules/s);

console.log("project chat employee lifecycle checks passed.");
