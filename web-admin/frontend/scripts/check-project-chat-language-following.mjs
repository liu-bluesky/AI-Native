import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import {
  appendChatResponseLanguageInstruction,
  buildChatResponseLanguageInstruction,
  detectChatResponseLanguage,
} from "../src/modules/project-chat/services/chatResponseLanguage.js";

const projectChatSource = await readFile(
  new URL("../src/views/projects/ProjectChat.vue", import.meta.url),
  "utf8",
);

assert.equal(detectChatResponseLanguage("帮我检查这个 React component").code, "zh-CN");
assert.equal(detectChatResponseLanguage("Please inspect this Vue component").code, "en");
assert.equal(detectChatResponseLanguage("このコードを確認してください").code, "ja");
assert.equal(detectChatResponseLanguage("이 코드를 확인해 주세요").code, "ko");
assert.equal(detectChatResponseLanguage("请用英文回答这个问题").code, "en");
assert.equal(detectChatResponseLanguage("Answer in Chinese, please").code, "zh-CN");
assert.equal(detectChatResponseLanguage("不要用中文，请用英文回答").code, "en");
assert.equal(detectChatResponseLanguage("请用繁体中文回答").code, "zh-TW");
assert.equal(detectChatResponseLanguage("你好 hello /Volumes/work/app").code, "zh-CN");
assert.equal(detectChatResponseLanguage("hello /Volumes/work/app").code, "en");

const chineseInstruction = buildChatResponseLanguageInstruction("帮我分析错误");
assert.match(chineseInstruction, /reasoning\/thinking.*简体中文/s);
assert.match(chineseInstruction, /代码、命令、文件路径、日志原文/);

const englishPrompt = appendChatResponseLanguageInstruction(
  "Review the implementation",
  "Please respond in English",
);
assert.match(englishPrompt, /reasoning\/thinking.*English/s);

assert.match(
  projectChatSource,
  /function appendModelGenerationInstruction[\s\S]*appendChatResponseLanguageInstruction/s,
  "所有项目聊天请求必须经过统一语言约束入口",
);
assert.match(
  projectChatSource,
  /function latestUserMessageLanguageSource[\s\S]*role[\s\S]*user/s,
  "任务恢复必须沿用最近一条用户消息的语言",
);
assert.match(
  projectChatSource,
  /followupLanguageSource[\s\S]*appendModelGenerationInstruction/s,
  "补充需求必须按最新补充内容重新判断语言",
);
assert.match(
  projectChatSource,
  /desktop_local_agent:response_language[\s\S]*priority:\s*180[\s\S]*buildChatResponseLanguageInstruction/s,
  "本地 Runtime 必须使用高优先级语言约束控制思考与回答",
);
assert.match(
  projectChatSource,
  /systemPromptParts:\s*buildLocalLiuAgentSystemPromptParts\([\s\S]*displayUserMessageContent \|\| finalUserPrompt/s,
  "本地 Runtime 主请求必须按本轮用户原文判断语言",
);
assert.match(
  projectChatSource,
  /system_prompt:\s*\[[\s\S]*buildChatResponseLanguageInstruction\([\s\S]*latestUserMessageLanguageSource\((?:payloadText|languageSource)\)/s,
  "服务端主请求必须在 system_prompt 中携带本轮语言规则",
);
assert.match(
  projectChatSource,
  /const localResult = await sendLocalLiuAgentChatRequest\([\s\S]*languageSource,[\s\S]*displayUserMessageContent:/s,
  "本地 Runtime 不得用拼接后的最终提示词猜测本轮语言",
);
assert.match(
  projectChatSource,
  /const finalUserPrompt = appendModelGenerationInstruction\([\s\S]*currentModelParameterMode\.value,[\s\S]*text/s,
  "主聊天请求必须把原始用户消息作为语言来源",
);
assert.match(
  projectChatSource,
  /latestUserMessageLanguageSource\(payloadText\)/s,
  "结构化交互的后续请求必须按用户提交内容重新判断语言",
);

console.log("project chat language following checks passed.");
