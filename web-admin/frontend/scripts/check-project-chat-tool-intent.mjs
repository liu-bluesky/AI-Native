import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";

const source = await readFile(
  new URL("../src/views/projects/ProjectChat.vue", import.meta.url),
  "utf8",
);
const defaultsSource = await readFile(
  new URL(
    "../src/modules/project-chat/constants/chatSettingsDefaults.js",
    import.meta.url,
  ),
  "utf8",
);

for (const identifier of [
  "isActionableOperationPrompt",
  "isLarkOperationPrompt",
  "buildAgenticOperationInstruction",
  "appendAgenticOperationInstruction",
  "ACTIONABLE_OPERATION_HINT_RE",
  "LARK_OPERATION_RE",
]) {
  assert.equal(
    source.includes(identifier),
    false,
    `普通文本不能通过 ${identifier} 决定工具调用策略`,
  );
}

assert.match(
  source,
  /const effectiveAutoUseTools =[\s\S]*?projectChatToolsEnabled\(\)/,
  "普通对话的工具可用性必须由项目设置提供给模型决定",
);
assert.match(
  defaultsSource,
  /auto_use_tools:\s*true/,
  "未配置时也要将已启用工具提供给模型按需选择",
);
assert.match(
  source,
  /slashCommandRequiresTools[\s\S]*?activeCommandToolNames\.length > 0[\s\S]*?assistAction && assistToolNames\.length/,
  "显式斜杠命令和辅助动作仍可明确请求工具",
);

console.log("project chat model-owned tool intent checks passed.");
