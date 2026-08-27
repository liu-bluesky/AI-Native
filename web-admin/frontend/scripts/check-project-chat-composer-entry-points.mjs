import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";

const [projectChatSource, composerSource] = await Promise.all([
  readFile(
    new URL("../src/views/projects/ProjectChat.vue", import.meta.url),
    "utf8",
  ),
  readFile(
    new URL(
      "../src/modules/project-chat/components/composer/ChatComposer.vue",
      import.meta.url,
    ),
    "utf8",
  ),
]);

assert.match(
  projectChatSource,
  /const composerVisibleToolCommands = computed\([\s\S]*assist_employee_create[\s\S]*package_deploy[\s\S]*image/s,
  "创建智能体、打包部署和图片快捷入口必须从工具栏隐藏",
);
assert.match(
  projectChatSource,
  /:tool-command-items="composerVisibleToolCommands"/,
  "对话框必须使用过滤后的工具入口列表",
);
assert.match(
  projectChatSource,
  /智能体意图协议（必须遵守）[\s\S]*employee-intent[\s\S]*question、draft 或 create/s,
  "智能体创建意图必须由模型结构化输出",
);
assert.equal(
  projectChatSource.includes("isExplicitEmployeeCreateRequest"),
  false,
  "前端不能用正则猜测用户是否要创建智能体",
);
assert.match(
  composerSource,
  /class="chat-model-routing-trigger"[\s\S]*:disabled="chatLoading"/,
  "未配置模型时设置入口只能因生成中而禁用",
);
assert.equal(
  composerSource.includes(":disabled=\"chatLoading || !providerModelGroups.length\""),
  false,
  "未配置模型不能禁用模型设置入口",
);

console.log("project chat composer entry point checks passed.");
