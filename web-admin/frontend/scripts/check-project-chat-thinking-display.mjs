import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import {
  chatToolStateLabel,
  classifyChatTool,
  normalizeChatToolState,
} from "../src/modules/project-chat/components/messages/chatToolPresentation.js";

const [projectChatSource, stylesSource, reasoningRowSource, toolRowSource, resultSummarySource] =
  await Promise.all([
    readFile(
      new URL("../src/views/projects/ProjectChat.vue", import.meta.url),
      "utf8",
    ),
    readFile(
      new URL(
        "../src/modules/project-chat/styles/project-chat-style-05.css",
        import.meta.url,
      ),
      "utf8",
    ),
    readFile(
      new URL(
        "../src/modules/project-chat/components/messages/ChatReasoningRow.vue",
        import.meta.url,
      ),
      "utf8",
    ),
    readFile(
      new URL(
        "../src/modules/project-chat/components/messages/ChatToolCallRow.vue",
        import.meta.url,
      ),
      "utf8",
    ),
    readFile(
      new URL(
        "../src/modules/project-chat/components/messages/LocalTaskResultSummary.vue",
        import.meta.url,
      ),
      "utf8",
    ),
  ]);

assert.match(
  projectChatSource,
  /<ChatReasoningRow[\s\S]*v-if="messageReasoningBlocks\(item\)\.length"/s,
  "真实 reasoning block 必须投影为独立思考行组件",
);
assert.match(
  resultSummarySource,
  /本次需求[\s\S]*本地改动[\s\S]*修改文件[\s\S]*下一步计划/s,
  "任务结果卡必须展示需求、改动、文件和下一步计划",
);
assert.match(
  resultSummarySource,
  /is-added[\s\S]*is-modified[\s\S]*is-deleted/s,
  "新增、编辑、删除文件必须使用不同语义颜色",
);
assert.match(
  projectChatSource,
  /isMessageThinkingPlaceholder[\s\S]*<ChatReasoningRow[\s\S]*running/s,
  "首个模型增量到达前必须显示运行中的思考行",
);
assert.match(
  projectChatSource,
  /<ChatToolCallRow[\s\S]*messageTrajectoryToolCalls\(item\)[\s\S]*@action="handleOperationAction/s,
  "工具调用必须投影为独立工具行并保留业务动作",
);
assert.equal(
  projectChatSource.includes("expandedMessageTrajectoryId"),
  false,
  "思考详情不能继续依赖页面级展开状态",
);
assert.equal(
  projectChatSource.includes("expandedMessageTrajectoryToolId"),
  false,
  "工具详情不能继续依赖页面级展开状态",
);
assert.equal(
  projectChatSource.includes("shouldShowInlineThinkingState"),
  false,
  "不能额外生成思考中的伪过程状态",
);
assert.match(
  projectChatSource,
  /function upsertMessageTrajectoryBlock[\s\S]*reasoning_delta[\s\S]*text_delta/s,
  "Runtime 流式增量必须折叠为按索引管理的轨迹 block",
);
assert.match(
  projectChatSource,
  /function messageThinkingDurationLabel[\s\S]*reasoningDurationMs/s,
  "已思考用时必须来自 reasoning 事件而不是整轮 Runtime 时长",
);
assert.match(
  projectChatSource,
  /function pauseLocalLiuAgentReasoningTiming[\s\S]*reasoningCompletedDurationMs[\s\S]*reasoningActiveStartedAtEpochMs = 0/s,
  "等待用户补充时必须暂停思考计时",
);
assert.match(
  projectChatSource,
  /if \(localUserQuestionRequest\) \{[\s\S]*pauseLocalLiuAgentReasoningTiming\(assistantMessage\);/s,
  "出现补充问题时必须结束当前思考计时段",
);
assert.match(
  projectChatSource,
  /function isMessageExecutionActive[\s\S]*function syncMessageExecutionTimer/s,
  "未结束的助手消息必须有独立的响应式耗时刷新机制",
);
assert.match(
  projectChatSource,
  /<details[\s\S]*message-trajectory__inspect[\s\S]*执行详情/s,
  "底层过程日志必须收纳在高级执行详情中",
);
assert.match(
  projectChatSource,
  /v-if="messageTrajectoryAdvancedEntries\(item\)\.length"[\s\S]*v-for="entry in messageTrajectoryAdvancedEntries/s,
  "已投影为独立工具行的事件不能继续重复出现在执行详情中",
);
assert.match(
  projectChatSource,
  /function shouldUpsertLocalLiuAgentRuntimeOperation[\s\S]*"tool_call_started"[\s\S]*"tool_result"[\s\S]*"command_started"[\s\S]*"command_output_chunk"[\s\S]*"command_finished"/s,
  "本地 Runtime 的普通工具与命令事件必须进入 operation 投影",
);
assert.match(
  projectChatSource,
  /toolCallId[\s\S]*`local-tool:\$\{toolCallId\}`/s,
  "工具开始与结果事件必须按 tool_call_id 合并为同一行",
);
assert.match(
  projectChatSource,
  /output_preview:\s*outputPreview/s,
  "工具结果必须向专用详情卡传递完整输出预览",
);
assert.match(
  projectChatSource,
  /function shouldHideGenericRequestLifecycleOperation[\s\S]*hasProjectedOperation[\s\S]*messageProcessLogEntries\(row\)\.length > 0/s,
  "已有实际执行轨迹时必须隐藏重复的根 Runtime 状态卡",
);
assert.equal(
  projectChatSource.includes("message-process-shell--trajectory-detail"),
  false,
  "轨迹中不能恢复旧的过程卡片 DOM",
);

assert.match(
  reasoningRowSource,
  /props\.running \? lines\[lines\.length - 1\][\s\S]*lines\[0\]/s,
  "运行中的思考行显示最新行，完成后显示首行",
);
assert.match(
  reasoningRowSource,
  /split\(\/\\r\?\\n\|\\\*\{4,\}\//s,
  "连续 Markdown 思考片段必须拆分为可读摘要",
);
assert.match(
  reasoningRowSource,
  /\.chat-reasoning-row__summary[\s\S]*overflow: hidden;[\s\S]*text-overflow: ellipsis;[\s\S]*white-space: nowrap;/s,
  "思考摘要必须保持单行并隐藏溢出内容",
);
assert.equal(
  reasoningRowSource.includes("scrollLeft"),
  false,
  "思考摘要不能横向滚动到中间导致句首消失",
);
assert.match(
  reasoningRowSource,
  /chat-reasoning-sweep 2\.6s ease-out infinite/s,
  "思考行必须使用 DeepSeek 风格整行扫光",
);
assert.match(
  reasoningRowSource,
  /prefers-reduced-motion: reduce/s,
  "思考动画必须尊重系统减少动态效果设置",
);

assert.match(
  toolRowSource,
  /const expanded = ref\(false\)/s,
  "工具详情必须默认折叠",
);
assert.match(
  toolRowSource,
  /variant === 'terminal'[\s\S]*variant === 'edit'[\s\S]*variant === 'read'[\s\S]*variant === 'search' \|\| variant === 'web'/s,
  "终端、Diff、读取、搜索和 Web 必须使用专用详情卡",
);
assert.match(
  toolRowSource,
  /nextState === "waiting"[\s\S]*expanded\.value = true/s,
  "等待用户操作的工具必须自动展开",
);
assert.match(
  toolRowSource,
  /chat-tool-row-sweep 2\.6s ease-out infinite/s,
  "运行中的工具行必须使用整行扫光",
);
assert.match(
  stylesSource,
  /\.message-trajectory__tool-calls[\s\S]*display: grid/s,
  "工具组件列表必须保持紧凑的逐行布局",
);

assert.equal(normalizeChatToolState("running"), "running");
assert.equal(normalizeChatToolState("completed"), "ok");
assert.equal(normalizeChatToolState("waiting_user"), "waiting");
assert.equal(normalizeChatToolState("blocked"), "error");
assert.equal(chatToolStateLabel("stopped"), "已停止");
assert.equal(
  classifyChatTool({ kind: "tool", meta: { tool_name: "apply_patch" } }),
  "edit",
);
assert.equal(
  classifyChatTool({ kind: "terminal", meta: { command: "pnpm test" } }),
  "terminal",
);
assert.equal(
  classifyChatTool({ kind: "tool", meta: { tool_name: "read_file" } }),
  "read",
);

console.log("project chat thinking display checks passed.");
