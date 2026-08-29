import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const scriptDir = dirname(fileURLToPath(import.meta.url));
const projectChatPath = resolve(
  scriptDir,
  "../src/views/projects/ProjectChat.vue",
);
const summaryPath = resolve(
  scriptDir,
  "../src/modules/project-chat/components/messages/LocalTaskResultSummary.vue",
);
const projectChatSource = readFileSync(projectChatPath, "utf8");
const summarySource = readFileSync(summaryPath, "utf8");

assert.match(summarySource, /本次任务结果/);
assert.match(summarySource, /statusTitle/);
assert.match(summarySource, /waiting_user/);
assert.match(summarySource, /waiting_approval/);
assert.match(summarySource, /任务已暂停/);
assert.match(summarySource, /本次需求/);
assert.match(summarySource, /本地改动/);
assert.match(summarySource, /修改文件/);
assert.match(summarySource, /下一步计划/);
assert.match(summarySource, /新增/);
assert.match(summarySource, /编辑/);
assert.match(summarySource, /删除/);
assert.match(summarySource, /is-added/);
assert.match(summarySource, /is-modified/);
assert.match(summarySource, /is-deleted/);
assert.match(projectChatSource, /LocalTaskResultSummary/);
assert.match(projectChatSource, /localTaskSummary:/);
assert.match(projectChatSource, /local_task_summary:/);
assert.match(projectChatSource, /localTaskBaseline/);
assert.match(projectChatSource, /baselineItems: assistantMessage\.localTaskBaseline/);
assert.match(projectChatSource, /currentHash/);
assert.match(projectChatSource, /:open="item\.processExpanded === true"/);
assert.match(projectChatSource, /handleMessageProcessDetailsToggle/);
assert.match(projectChatSource, /payload\?\.chat_session_id/);
assert.match(projectChatSource, /buildLocalTaskResultSummary\(/);
assert.match(projectChatSource, /status: "paused"/);
assert.match(projectChatSource, /status: "waiting_user"/);
assert.match(projectChatSource, /status: "waiting_approval"/);
assert.doesNotMatch(
  projectChatSource,
  /employeeCreationProtocolRecovery|employee_creation_protocol_recovery/,
  "本地任务结果不得依赖已删除的智能体创建恢复流程",
);

const summaryBuildCount = (projectChatSource.match(
  /assistantMessage\.localTaskSummary = buildLocalTaskResultSummary\(/g,
) || []).length;
assert.ok(
  summaryBuildCount >= 5,
  "local task result summary must cover pause, wait, approval, success, and failure paths",
);

console.log("project chat local task result checks passed");
