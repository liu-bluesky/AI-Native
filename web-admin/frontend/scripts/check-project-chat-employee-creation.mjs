import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";

const source = await readFile(
  new URL("../src/views/projects/ProjectChat.vue", import.meta.url),
  "utf8",
);
const dialogSource = await readFile(
  new URL("../src/components/ProjectEmployeeDraftCreateDialog.vue", import.meta.url),
  "utf8",
);
const directoryServiceSource = await readFile(
  new URL("../src/services/local-agent-directory-service.js", import.meta.url),
  "utf8",
);

assert.doesNotMatch(source, /id:\s*["']employee_create["']/, "创建智能体不得再注册为对话辅助入口");
assert.doesNotMatch(source, /assist_employee_create/, "创建智能体不得再注册为快捷命令");
assert.doesNotMatch(source, /case ["']create["']|case ["']draft["']/, "智能体创建和草稿分支必须移除");
assert.doesNotMatch(source.slice(0, 17000), /创建智能体|确认创建|仅创建智能体/, "业务界面不得再展示创建智能体入口");
assert.match(source, /case ["']update["'][\s\S]*autoUpdateEmployeeFromDraftMessage/s, "已有智能体更新能力必须保留");
assert.match(source, /case ["']delete["'][\s\S]*handleEmployeeDeleteIntent/s, "已有智能体删除能力必须保留");
assert.match(source, /async function handleQuickUpdateEmployee[\s\S]*saveLocalAgentDirectoryResources/s, "更新必须写回智能体目录");
assert.match(source, /async function handleEmployeeDeleteIntent[\s\S]*deleteLocalProjectAgent/s, "删除必须操作智能体自身目录");
assert.match(dialogSource, /title="确认更新 AI 智能体"[\s\S]*确认更新/s, "确认弹窗只能用于更新已有智能体");
assert.doesNotMatch(dialogSource, /确认创建|仅创建智能体/, "更新弹窗不得保留创建文案");
assert.match(directoryServiceSource, /function resolveDirectories[\s\S]*\.ai-employee[\s\S]*agents[\s\S]*skills[\s\S]*rules/s, "已有智能体资源目录解析必须保留");

console.log("project chat employee creation removal check passed.");
