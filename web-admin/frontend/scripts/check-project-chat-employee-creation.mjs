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
const directoryServiceSource = await readFile(
  new URL("../src/services/local-agent-directory-service.js", import.meta.url),
  "utf8",
);
const runtimeSource = await readFile(
  new URL("../src-tauri/src/liuagent_core/runtime.rs", import.meta.url),
  "utf8",
);
const nativeBridgeSource = await readFile(
  new URL("../src/utils/native-desktop-bridge.js", import.meta.url),
  "utf8",
);
const composerStateSource = await readFile(
  new URL(
    "../src/modules/project-chat/composables/useProjectChatComposer.js",
    import.meta.url,
  ),
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
  /用户已给出名称，且至少给出一项技术\/能力和一项预期交付物时，信息已足够：直接生成完整草稿，不得再次补充提问/,
  "创建智能体已有名称、能力和交付物时必须直接生成草稿",
);

assert.match(
  source,
  /仅当名称、能力方向、预期交付物这三类信息全部缺失，或缺少会导致草稿无法成立的唯一关键决策时，才可调用 ask_user_question/,
  "创建智能体只能为唯一关键决策请求补充信息",
);
assert.match(
  source,
  /function ensureLocalLiuAgentUserQuestionAnswer\([\s\S]*answers\[normalizedQuestionId\] = \{ choice: "", selected: \[\], custom: "" \}/s,
  "补充问题答案必须在绑定前安全初始化",
);
assert.match(
  source,
  /v-model="ensureLocalLiuAgentUserQuestionAnswer\(question\.id\)\.selected"[\s\S]*v-model="ensureLocalLiuAgentUserQuestionAnswer\(question\.id\)\.choice"[\s\S]*v-model="ensureLocalLiuAgentUserQuestionAnswer\(question\.id\)\.custom"/s,
  "补充问题的单选、多选和自定义输入必须使用安全答案绑定",
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
assert.match(
  source,
  /收到 ask_user_question 的工具结果后，selected 和 custom 都是最终答案：不得再次调用 ask_user_question，也不得以自然语言要求继续补充，必须直接生成草稿/,
  "创建流程收到补充答案后必须直接生成草稿",
);
assert.match(
  runtimeSource,
  /answered_user_question\.is_some\(\)[\s\S]*_answered_user_question[\s\S]*request_has_answered_user_question\(request\)/s,
  "补充答案续跑时 Runtime 不得再次暴露 ask_user_question 工具",
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
  /只有缺少会导致草稿无法成立的唯一关键决策时才调用 ask_user_question[\s\S]*不得再次调用 ask_user_question/s,
  "创建流程必须限制追问到唯一关键决策，并在回答后禁止再次提问",
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

assert.match(
  source,
  /创建草稿至少提供 1 个技能候选和 1 个规则候选/s,
  "创建草稿必须产出可选择的技能和规则候选",
);
assert.match(
  source,
  /读取到 0 个本地技能或规则是正常结果[\s\S]*生成新的技能与规则候选及完整草稿/s,
  "空资源目录不能阻止创建模式直接生成技能、规则和草稿",
);
assert.match(
  source,
  /创建模式还必须追加一个 ```employee-intent``` 代码块/s,
  "创建草稿必须明确返回可被宿主消费的 create intent",
);
assert.match(
  source,
  /function createEmployeeCreationProtocolRecoveryQuestion[\s\S]*employee_creation_protocol_recovery[\s\S]*智能体主要职责/s,
  "创建模式普通文本补充信息必须转为可提交的问题卡片",
);
assert.match(
  source,
  /restartAfterProtocolRecovery[\s\S]*resumeFromCheckpoint: !restartAfterProtocolRecovery/s,
  "协议恢复问题提交后必须启动新创建回合而非恢复不存在的工具 checkpoint",
);
assert.match(
  source,
  /parsedIntent \|\|[\s\S]*assistActionId === "employee_create"[\s\S]*\? "create"/s,
  "创建模式只有草稿时也必须自动进入确认流程",
);
assert.match(
  source,
  /每个新技能必须同时出现在 skills 和 skill_drafts 中/s,
  "新技能必须包含可写入的独立定义",
);
assert.match(
  source,
  /每个新规则必须写入 rule_drafts/s,
  "新规则必须包含可写入的独立定义",
);
assert.match(
  source,
  /function normalizeEmployeeDraftPayload\([\s\S]*skill_drafts: skillDrafts/s,
  "草稿解析必须保留技能 Markdown 定义",
);
assert.match(
  source,
  /const selectedSkills = employee\.skills\.map[\s\S]*selectedSkills\.length !== employee\.skills\.length/s,
  "勾选的技能必须全部解析为可写入定义",
);
assert.match(
  source,
  /handleQuickCreateEmployee\([\s\S]*mergeEmployeeSkillDefinitions\([\s\S]*employee\.skill_drafts/s,
  "创建智能体时必须把每项技能的独立内容传入目录写入层",
);
assert.match(
  source,
  /handleQuickUpdateEmployee\([\s\S]*mergeEmployeeSkillDefinitions\([\s\S]*employee\.skill_drafts/s,
  "更新智能体时必须保留并使用每项技能的独立内容",
);
assert.match(
  directoryServiceSource,
  /const definedSkills = preserveExistingResources[\s\S]*skills\.filter\(hasSkillDefinition\);/s,
  "目录写入层必须校验新建技能具有独立定义",
);
assert.doesNotMatch(
  directoryServiceSource,
  /此技能由 AI Employee 本地智能体配置引用。/,
  "目录写入层不得保留技能通用占位正文",
);
assert.match(
  directoryServiceSource,
  /async function removeAgentDefinitionDirectory\([\s\S]*deleteNativeWorkspaceDirectory[\s\S]*export async function deleteLocalProjectAgent[\s\S]*await removeAgentDefinitionDirectory/s,
  "删除智能体必须递归清理其目录后再刷新本地索引",
);
assert.match(
  nativeBridgeSource,
  /deleteWorkspaceDirectory: "delete_workspace_directory"[\s\S]*export async function deleteNativeWorkspaceDirectory/s,
  "前端原生桥必须暴露工作区目录删除命令",
);
assert.match(
  directoryServiceSource,
  /const AGENT_METADATA_FILE = "\.ai-employee\.json";/,
  "完整智能体配置必须写入独立 sidecar 文件",
);
assert.match(
  directoryServiceSource,
  /function agentDirectoryName\([\s\S]*function skillDirectoryName\([\s\S]*function ruleDirectoryName\(/s,
  "智能体、技能和规则必须使用可读名称加稳定短 ID 的目录名",
);
assert.match(
  directoryServiceSource,
  /path: `\$\{directoryName\}\/AGENT\.md`,[\s\S]*path: `\$\{directoryName\}\/\$\{AGENT_METADATA_FILE\}`/s,
  "智能体正文与机器配置必须分别写入 Markdown 和 sidecar 文件",
);
assert.doesNotMatch(
  directoryServiceSource,
  /function mergeManagedBlock\(/,
  "新建定义文件不得再写入受管区块注释",
);

console.log("project chat employee creation trigger check passed.");

assert.match(
  source,
  /if \(localUserQuestionRequest\) \{[\s\S]*assistantMessage\.employeeDraftAwaitingInput = true/s,
  "等待补充信息时必须标记中间智能体草稿，禁止进入确认阶段",
);
assert.doesNotMatch(
  source,
  /employee\.skill_markdown_missing[\s\S]*await doSend\(\)/s,
  "缺失技能不得触发自动补全重试",
);
assert.match(
  dialogSource,
  /<el-checkbox-group[\s\S]*selectedSkillIds[\s\S]*<el-checkbox-group[\s\S]*selectedRuleKeys/s,
  "确认弹窗必须提供技能和规则多选",
);
assert.match(
  dialogSource,
  /selected_skill_ids:[\s\S]*selected_rule_keys:/s,
  "确认弹窗必须回传勾选的技能和规则",
);
assert.match(
  source,
  /const selectedSkillIds = normalizeStringList[\s\S]*const selectedRuleKeys = normalizeStringList[\s\S]*rule_drafts: ruleDrafts/s,
  "创建处理必须只接收勾选的技能和规则",
);
assert.match(
  source,
  /writtenSkills\.length !== selectedSkills\.length[\s\S]*writtenRules\.length !== selectedRules\.length/s,
  "创建后必须校验技能和规则完整写入",
);
assert.match(
  source,
  /mediaTools: localLiuAgentMediaTools\.value,[\s\S]*interactionMode:[\s\S]*employee_create/s,
  "主聊天创建请求必须传入 employee_create 模式",
);
assert.match(
  source,
  /const isEmployeeCreationMode = normalizedInteractionMode === "employee_create";[\s\S]*const employeeOrchestrationPart = isEmployeeCreationMode[\s\S]*employeeOrchestrationPart/s,
  "智能体创建编排提示只能在 employee_create 模式下注入",
);
assert.doesNotMatch(
  source,
  /id: "desktop_local_agent:employee_natural_language_orchestration",\s*source: "desktop_local_agent\.employee_natural_language_orchestration",\s*scope: "global"/s,
  "普通聊天不得全局注入智能体创建编排提示",
);
assert.match(
  runtimeSource,
  /fn hydrate_mcp_tool_snapshot\([\s\S]*request\.selected_mcp_tools = discovered;/s,
  "MCP 工具发现必须完整注入当前模型请求",
);
assert.doesNotMatch(
  runtimeSource,
  /fn select_mcp_catalog_tools\(/,
  "MCP 工具查询不得依赖服务自身提供目录工具",
);
assert.match(
  source,
  /function clearEmployeeCreationComposerAssist\(\) \{[\s\S]*activeComposerAssist\.value = ""[\s\S]*activeComposerToolCommandId\.value = ""[\s\S]*rememberCurrentChatSessionComposerState\(\);/s,
  "创建智能体辅助状态只能在创建成功后显式清理并同步会话缓存",
);
assert.match(
  source,
  /if \(!updated\) \{[\s\S]*clearLocalLiuAgentUserQuestionsForChatSession\(currentChatSessionId\.value\);[\s\S]*clearEmployeeCreationComposerAssist\(\);/s,
  "创建成功后必须清理创建智能体辅助状态",
);
assert.doesNotMatch(
  source,
  /const assistAction = effectiveAssistAction;[\s\S]*if \(assistAction\?\.id === "employee_create"\)[\s\S]*activeComposerAssist\.value = ""/s,
  "普通发送不得提前清理创建智能体辅助状态",
);
assert.doesNotMatch(
  composerStateSource,
  /activeAssist === "employee_create" \? "" : activeAssist|activeToolCommandId === "assist_employee_create"/s,
  "会话缓存不得在普通发送后丢弃创建智能体辅助状态",
);
assert.match(
  source,
  /async function handleCreateNewConversation\(\) \{[\s\S]*activeComposerAssist\.value = "";[\s\S]*activeComposerToolCommandId\.value = "";/s,
  "新建会话必须清理工具栏的创建智能体辅助状态",
);
assert.match(
  source,
  /function getEmployeeDraftCard\(item\) \{[\s\S]*employeeDraftAwaitingInput/s,
  "等待补充信息的中间草稿不得渲染为待确认卡片",
);
assert.match(
  source,
  /const waitingForUserInput = localLiuAgentPendingUserQuestionsForChatSession\([\s\S]*if \(!waitingForUserInput\) \{[\s\S]*handleEmployeeIntentAfterAssistantResponse/s,
  "有未回答问题时不得打开智能体草稿确认流程",
);
assert.match(
  source,
  /继续完善[\s\S]*确认\{\{[\s\S]*取消/s,
  "待确认智能体草稿必须提供继续完善、确认和取消操作",
);
