import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";

const source = await readFile(
  new URL("../src/views/projects/ProjectChat.vue", import.meta.url),
  "utf8",
);
const dialogSource = await readFile(
  new URL("../src/components/ProjectEmployeeDraftCreateDialog.vue", import.meta.url),
  "utf8",
);

assert.match(
  source,
  /async function handleEmployeeIntentAfterAssistantResponse\([\s\S]*case "create":[\s\S]*autoCreateEmployeeFromDraftMessage/s,
  "create 意图必须进入草稿确认流程",
);

assert.match(
  source,
  /case "draft":[\s\S]*autoCreateEmployeeFromDraftMessage/s,
  "可确认 draft 必须进入本地草稿确认流程",
);

assert.match(
  source,
  /case "question":\s*return;/s,
  "question 必须保持等待用户补充状态",
);

assert.doesNotMatch(
  source,
  /未识别到模型创建意图，请重新生成后再试/,
  "内部意图协议解析失败不得作为用户错误展示",
);

assert.doesNotMatch(
  source,
  /function employeeIntentFallbackDisplayText\(/,
  "不得用通用文案伪造模型追问或草稿状态",
);

assert.match(
  source,
  /当信息不足、存在多个合理方向或缺少用户才能决定的内容时，必须选择 question，并在可见正文中提出最多 3 个具体问题/,
  "创建智能体提示必须要求模型在信息不足时可见追问",
);

assert.match(
  source,
  /当运行时提供 ask_user_question 工具且缺少只能由用户决定的信息时，必须优先调用 ask_user_question/,
  "创建智能体缺少用户决策信息时必须优先使用可恢复提问工具",
);

assert.match(
  source,
  /function localLiuAgentUserQuestionRequestFromChatResult\(/,
  "桌面 Runtime 必须识别结构化用户问题请求",
);

assert.match(
  source,
  /async function submitCurrentLocalLiuAgentUserQuestion\([\s\S]*userQuestionAnswer:[\s\S]*resumeFromCheckpoint: true/s,
  "用户回答必须通过 checkpoint 恢复到同一个 Agent Loop",
);

assert.doesNotMatch(
  source,
  /LOCAL_LIU_AGENT_CUSTOM_ANSWER_VALUE|其他 \/ 手动填写/,
  "补充信息输入框不应依赖额外的手动填写选项",
);

assert.match(
  source,
  /const selected = custom \? \[\] : optionSelected;/,
  "手动输入内容必须覆盖单选或多选结果",
);

assert.match(
  source,
  /async function submitCurrentLocalLiuAgentUserQuestion\([\s\S]*messages\.value\.push\(userMessage, row\)[\s\S]*persistUserMessage: true/s,
  "每次补充信息必须作为新的用户消息写入会话记录",
);

assert.match(
  source,
  /用户刚刚提交了以下最终补充信息[\s\S]*不得再次询问相同问题/,
  "恢复提示必须明确禁止重复询问已经回答的问题",
);

assert.ok(
  source.includes("function formatLocalLiuAgentUserQuestionAnswerMessage(") &&
    source.includes('return ["补充上方问题：", details]') &&
    source.includes('`问题：${question}\\n回答：${String('),
  "补充信息消息必须同时保留原问题与用户回答",
);

assert.match(
  source,
  /async function doSend\([\s\S]*submitPendingEmployeeDraftConfirmationIfNeeded/s,
  "发送确认文本时必须优先消费待确认智能体草稿",
);

assert.match(
  source,
  /async function submitPendingEmployeeDraftConfirmationIfNeeded\([\s\S]*await confirmEmployeeDraftCreation\(\)/s,
  "确定、好的创建、没问题等确认文本必须直接执行草稿创建",
);

assert.match(
  source,
  /\["draft", "create", "update"\]\.includes\(intent\)/,
  "文字确认必须能够恢复 draft、create 和 update 三种待确认草稿",
);

assert.ok(
  dialogSource.includes("'待确认的 AI 智能体'") &&
    dialogSource.includes('"确认创建"'),
  "新建草稿必须通过待确认弹框中的确认创建按钮完成",
);

assert.match(
  source,
  /function supersedeOtherPendingEmployeeDrafts\([\s\S]*employeeDraftSuperseded = true/s,
  "同一会话只能保留一个待确认智能体草稿",
);

assert.match(
  source,
  /function buildEmployeeUpdateDraftPayload\([\s\S]*resolveEmployeeUpdateTarget[\s\S]*employee_id:/s,
  "关闭更新弹框后恢复确认时必须重新解析目标智能体",
);

assert.match(
  source,
  /每个问题必须显式设置 multi_select[\s\S]*可以组合选择的内容设为 true/s,
  "提问提示必须明确区分单选和多选语义",
);

assert.ok(
  source.includes('resetAssist: assistActionId === "employee_create"'),
  "手动创建智能体辅助状态必须在草稿确认流程后清理",
);

assert.doesNotMatch(
  source,
  /function buildFallbackEmployeeDraftForCreation\(/,
  "不得根据聊天关键词本地猜测并伪造智能体草稿",
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
  /case "update":[\s\S]*autoUpdateEmployeeFromDraftMessage/s,
  "模型 update 意图必须触发智能体更新草稿",
);

console.log("project chat employee creation trigger check passed.");
