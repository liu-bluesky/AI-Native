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

assert.match(
  source,
  /function buildFallbackEmployeeDraftForCreation\(/,
  "创建意图缺少完整草稿时必须有本地可确认兜底",
);
assert.match(
  source,
  /function buildEmployeeAutoCreatePayload\([\s\S]*if \(!draft\.name\) return null/s,
  "名称缺失时不得创建未命名智能体",
);
assert.match(
  source,
  /智能体草稿缺少名称，尚未创建/s,
  "名称缺失时必须停在草稿阶段",
);
assert.match(
  source,
  /function isInternalProtocolProcessLog\(/,
  "执行记录不得展示内部协议内容",
);
assert.match(
  source,
  /function extractJsonObjectsFromText\(/,
  "必须兼容模型返回的裸 JSON 创建意图和草稿",
);
assert.match(
  source,
  /frontend_enginer:\s*"frontend_engineer"/,
  "常见前端角色拼写错误必须被归一化",
);
assert.match(
  source,
  /async function autoUpdateEmployeeFromDraftMessage\(/,
  "当前会话智能体的技能和规则更新必须进入确认流程",
);
assert.match(
  source,
  /async function handleQuickUpdateEmployee\([\s\S]*saveLocalAgentDirectoryResources/s,
  "确认更新后必须真实写入智能体目录",
);
assert.match(
  source,
  /intent ===\s*"update"[\s\S]*autoUpdateEmployeeFromDraftMessage/s,
  "模型 update 意图必须触发智能体更新草稿",
);

console.log("project chat employee creation trigger check passed.");
