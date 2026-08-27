import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";

const source = await readFile(
  new URL("../src/views/projects/ProjectChat.vue", import.meta.url),
  "utf8",
);

const requestEnd = source.indexOf(
  "    if (effectiveAssistAction?.id === \"employee_create\") {",
);
assert.notEqual(
  requestEnd,
  -1,
  "创建智能体模式必须在模型回复完成后处理草稿",
);

const createCall = source.indexOf(
  "await autoCreateEmployeeFromDraftMessage(assistantMessage, {",
  requestEnd,
);
assert.ok(
  createCall > requestEnd,
  "创建智能体模式必须调用草稿创建流程",
);

assert.ok(
  source.includes("resetAssist: true"),
  "草稿创建完成后必须清理创建智能体辅助状态",
);

console.log("project chat employee creation trigger check passed.");
