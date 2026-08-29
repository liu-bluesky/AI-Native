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
const composerStateSource = await readFile(
  new URL(
    "../src/modules/project-chat/composables/useProjectChatComposer.js",
    import.meta.url,
  ),
  "utf8",
);

assert.match(
  projectChatSource,
  /const composerVisibleToolCommands = computed\([\s\S]*package_deploy/s,
  "打包部署入口保持隐藏",
);
assert.doesNotMatch(
  projectChatSource,
  /const visibleCommandIds = new Set\(\[\s*"package_deploy",\s*"form_json",\s*"image"/s,
  "图片能力不应作为固定输入框快捷入口展示",
);
assert.match(
  composerStateSource,
  /activeComposerToolCommandId[\s\S]*composerCache\.set[\s\S]*activeComposerToolCommandId/s,
  "图片等输入框快捷选择必须按当前会话缓存",
);
assert.match(
  projectChatSource,
  /function handleCreateNewConversation\([\s\S]*activeComposerAssist\.value = ""[\s\S]*activeComposerToolCommandId\.value = ""/s,
  "新建会话必须清空当前会话的工具选择",
);
assert.match(
  projectChatSource,
  /:tool-command-items="composerVisibleToolCommands"/,
  "对话框必须使用过滤后的工具入口列表",
);
assert.doesNotMatch(
  projectChatSource,
  /employee_create|assist_employee_create|创建智能体|确认创建/,
  "对话输入区不得保留创建智能体工具或入口",
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
