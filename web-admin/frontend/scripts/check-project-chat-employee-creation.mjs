import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";

const source = await readFile(
  new URL("../src/views/projects/ProjectChat.vue", import.meta.url),
  "utf8",
);

const requestEnd = source.indexOf(
  'extractEmployeeIntentPayload(assistantMessage.content)?.intent ===\n      "create"',
);
assert.notEqual(
  requestEnd,
  -1,
  "创建智能体必须在模型回复并明确返回 create 意图后处理草稿",
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
  source.includes('resetAssist: effectiveAssistAction?.id === "employee_create"'),
  "手动创建智能体辅助状态必须在草稿确认流程后清理",
);

console.log("project chat employee creation trigger check passed.");
