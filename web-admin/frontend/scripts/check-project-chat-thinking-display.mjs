import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";

const [projectChatSource, stylesSource] = await Promise.all([
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
]);

assert.match(
  projectChatSource,
  /v-if="messageReasoningBlocks\(item\)\.length"[\s\S]*message-thinking-quote/s,
  "Thinking 入口只能由真实 reasoning block 驱动",
);
assert.match(
  projectChatSource,
  /message-trajectory__tool-calls[\s\S]*messageTrajectoryToolCalls\(item\)/s,
  "工具调用必须以同一条消息轨迹中的轻量工具行显示",
);
assert.match(
  projectChatSource,
  /const expandedMessageTrajectoryId = ref\(""\)[\s\S]*function toggleMessageTrajectoryExpanded/s,
  "消息详情必须使用当前视图级别的单一展开状态",
);
assert.equal(
  projectChatSource.includes("thinkingExpanded"),
  false,
  "思考详情不能在每条消息上维护独立展开状态",
);
assert.equal(
  projectChatSource.includes("shouldShowInlineThinkingState"),
  false,
  "不能额外生成思考中的伪过程状态",
);
assert.match(
  projectChatSource,
  /isMessageThinkingPlaceholder[\s\S]*message-thinking-live__dots/s,
  "首个模型增量到达前必须显示轻量 Thinking 反馈",
);
assert.match(
  projectChatSource,
  /function upsertMessageTrajectoryBlock[\s\S]*reasoning_delta[\s\S]*text_delta/s,
  "Runtime 流式增量必须折叠为按索引管理的轨迹 block",
);
assert.match(
  projectChatSource,
  /function messageThinkingDurationLabel[\s\S]*reasoningDurationMs[\s\S]*messageTrajectorySummary/s,
  "已思考用时必须来自 reasoning 事件而不是整轮 Runtime 时长",
);
assert.match(
  projectChatSource,
  /v-for="block in messageReasoningBlocks\(item\)"/,
  "Thinking 详情必须按 reasoning block 渲染",
);
assert.match(
  projectChatSource,
  /function messageTrajectoryToolCalls[\s\S]*isMessageTrajectoryToolCall/s,
  "工具行必须只投影真实工具调用，而不是旧过程卡片",
);
assert.equal(
  projectChatSource.includes("message-process-shell--trajectory-detail"),
  false,
  "Thinking 轨迹中不能保留旧的过程卡片 DOM",
);
assert.match(
  stylesSource,
  /\.message-thinking-quote[\s\S]*border-left:[\s\S]*transition: transform 120ms ease-in-out/s,
  "思考区必须使用轻量引用样式和 120ms 箭头旋转",
);
assert.equal(
  stylesSource.includes("message-thinking-pulse"),
  false,
  "思考区不能使用参考实现中不存在的脉冲动画",
);
assert.match(
  stylesSource,
  /message-thinking-live__dots[\s\S]*message-thinking-live-dot/s,
  "进行中的 Thinking 必须有可见的轻量点动画",
);
assert.match(
  stylesSource,
  /\.message-trajectory__tool-calls[\s\S]*\.message-trajectory__tool-call/s,
  "工具调用必须采用参考实现同类的紧凑行样式",
);

console.log("project chat thinking display checks passed.");
