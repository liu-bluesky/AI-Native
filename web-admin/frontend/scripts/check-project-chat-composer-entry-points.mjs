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
  /function isEmployeeCreateRequest[\s\S]*inferredEmployeeCreateAction[\s\S]*employee_create/s,
  "自然语言创建智能体请求必须自动进入创建流程",
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
