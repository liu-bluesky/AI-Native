import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const scriptDir = dirname(fileURLToPath(import.meta.url));
const rootDir = resolve(scriptDir, "..");

function read(relativePath) {
  return readFileSync(resolve(rootDir, relativePath), "utf8");
}

const tauriMain = read("src-tauri/src/main.rs");
const appVue = read("src/App.vue");
const botRuntime = read("src-tauri/src/bot/runtime.rs");
const botMod = read("src-tauri/src/bot/mod.rs");
const botFeishu = read("src-tauri/src/bot/feishu.rs");
const liuagentDefinitions = read("src-tauri/src/liuagent_core/definitions.rs");
const liuagentRuntime = read("src-tauri/src/liuagent_core/runtime.rs");
const liuagentMod = read("src-tauri/src/liuagent_core/mod.rs");
const liuagentProjectTools = read("src-tauri/src/liuagent_core/tools/projects.rs");
const botFeishuSdkWorker = read("src-tauri/bot_workers/feishu_sdk_listener.py");
const tauriConfig = read("src-tauri/tauri.conf.json");
const bridge = read("src/utils/native-desktop-bridge.js");
const projectChat = read("src/views/projects/ProjectChat.vue");
const botConnectorPage = read("src/views/system/SystemBotConnectors.vue");
const botConnectorModule = read("src/components/system/BotPlatformConnectorModule.vue");
const chatStorage = read("src/modules/project-chat/services/projectChatStorage.js");
const shouldHandleEventMatch = botFeishu.match(
  /fn should_handle_event\([^)]*\) -> bool \{[\s\S]*?\n\}/,
);
assert.ok(
  shouldHandleEventMatch,
  "Feishu listener must keep an explicit should_handle_event gate",
);
const shouldHandleEventSource = shouldHandleEventMatch[0];

assert.match(
  tauriMain,
  /\.join\("agent-runtime-v2"\)[\s\S]*?\.join\("bots"\)[\s\S]*?\.join\("connectors\.json"\)/,
  "global bot connector config must live in ~/.ai-employee/agent-runtime-v2/bots/connectors.json",
);

assert.match(
  tauriMain,
  /start_persisted_local_listeners\(app\.handle\(\)\.clone\(\)\)/,
  "Tauri startup must restore persisted local bot listeners with the desktop app",
);

assert.match(
  appVue,
  /\/llm\/providers\/\$\{encodeURIComponent\(normalizedProviderId\)\}\/desktop-runtime[\s\S]*syncLocalBotListeners[\s\S]*readGlobalBotConnectorConfigFile[\s\S]*startNativeFeishuLocalBotListener/s,
  "desktop app shell must refresh local Feishu listeners with provider-derived model runtime without requiring ProjectChat to mount",
);

assert.match(
  chatStorage,
  /export function globalBotConnectorConfigPathLabel\(\) \{[\s\S]*?~\/\.ai-employee\/agent-runtime-v2\/bots\/connectors\.json/,
  "frontend storage label must point to the local global bot connector config file",
);

assert.match(
  botConnectorPage,
  /readGlobalBotConnectorConfigFile[\s\S]*writeGlobalBotConnectorConfigFile/,
  "bot connector page must read and write local global connector config through Tauri",
);

assert.match(
  botConnectorPage,
  /fetchDesktopModelRuntime[\s\S]*\/llm\/providers\/\$\{encodeURIComponent\(normalizedProviderId\)\}\/desktop-runtime[\s\S]*model_runtime/s,
  "bot connector page must persist a desktop model runtime snapshot with the local connector config",
);

assert.doesNotMatch(
  botConnectorPage,
  /\/api\/bot-connectors|api\.(?:get|post|patch|delete)\([^)]*bot-connectors/,
  "bot connector page must not use backend bot connector APIs as the config source",
);

assert.match(
  botRuntime,
  /const BOT_CONNECTOR_PROMPT_SOURCE: &str = "bot_connector\.system_prompt";/,
  "bot runtime must identify connector.system_prompt as the only bot prompt source",
);

assert.match(
  botRuntime,
  /let connector_prompt = request\.connector\.system_prompt\.trim\(\)\.to_string\(\);[\s\S]*?if !connector_prompt\.is_empty\(\) \{[\s\S]*?source: BOT_CONNECTOR_PROMPT_SOURCE\.to_string\(\)[\s\S]*?content: connector_prompt/,
  "bot runtime must inject only a nonblank connector prompt",
);

assert.match(
  botRuntime,
  /system_prompt: None,[\s\S]*?system_prompt_parts,/,
  "bot runtime must not set a built-in system_prompt",
);

assert.match(
  botRuntime,
  /fn validate_bot_model_runtime[\s\S]*bot\.model_runtime_unconfigured[\s\S]*机器人未配置可用的桌面模型运行时，已跳过回复/,
  "bot runtime must fail before liuAgent mock mode when no real desktop model runtime is configured",
);

assert.match(
  botRuntime,
  /"promptPolicy": "connector_system_prompt_only"/,
  "bot runtime metadata must expose the connector-only prompt policy",
);

assert.match(
  botMod,
  /blank_connector_prompt_does_not_add_a_bot_prompt[\s\S]*assert!\(local_request\.system_prompt_parts\.is_empty\(\)\)/,
  "bot unit tests must lock blank prompt behavior to no injected bot prompt",
);

assert.match(
  botMod,
  /configured_connector_prompt_is_the_only_bot_prompt[\s\S]*bot_connector\.system_prompt/,
  "bot unit tests must lock configured prompt behavior to connector.system_prompt",
);

assert.match(
  botRuntime,
  /tool_access: "same_as_desktop_project_chat_tools"/,
  "bot permission contract must grant the same tool surface as desktop project chat",
);

assert.match(
  botRuntime,
  /command_execution: "desktop_runner_confirmed"[\s\S]*deployment: "project_deploy_config_and_separate_confirmation"/,
  "bot permission contract must keep local commands and deployments behind desktop confirmations",
);

assert.match(
  tauriConfig,
  /"resources": \[[\s\S]*?"bot_workers\/feishu_sdk_listener\.py"/,
  "Tauri bundle resources must include the Feishu Python SDK listener worker",
);

assert.match(
  botFeishu,
  /const FEISHU_SDK_WORKER_RELATIVE_PATH: &str = "bot_workers\/feishu_sdk_listener\.py";[\s\S]*?Command::new\(python\)[\s\S]*?\.arg\(worker_path\)[\s\S]*?AI_EMPLOYEE_FEISHU_APP_SECRET/,
  "Feishu listener must start the local Python SDK worker with connector credentials from local config",
);

assert.match(
  botFeishu,
  /fn handle_local_feishu_event_inner[\s\S]*start_bot_chat_with_event_sink[\s\S]*reply_message_with_connector/s,
  "Feishu listener must execute bot chat and reply inside the Tauri bot module instead of relying on a mounted ProjectChat page",
);

assert.match(
  botFeishu,
  /load_bot_conversation_history\(&context\.connector\.connector_id, &chat_session_id\)[\s\S]*history,/s,
  "Feishu listener must pass same-chat local conversation history into the desktop bot runtime",
);

assert.match(
  botFeishu,
  /append_bot_conversation_turn\([\s\S]*&message,[\s\S]*&reply_content/s,
  "Feishu listener must persist final user/assistant turns after a successful reply",
);

assert.match(
  botFeishu,
  /agent-runtime-v2[\s\S]*bots[\s\S]*conversations[\s\S]*StoredBotConversation/s,
  "Feishu bot conversation history must live in the local global bot runtime store",
);

assert.match(
  botFeishu,
  /append_bot_conversation_messages[\s\S]*bot_conversation_history_keeps_only_final_user_assistant_turns/s,
  "Feishu bot history tests must ensure progress acknowledgements do not pollute chat context",
);

assert.doesNotMatch(
  botFeishu,
  /history: Vec::new\(\),/,
  "Feishu listener must not discard same-chat bot conversation history",
);

assert.match(
  botFeishu,
  /reply_feishu_status_message[\s\S]*👋 收到，正在处理。[\s\S]*start_bot_chat_with_event_sink/s,
  "Feishu listener must reply immediately to private messages before running the local agent",
);

assert.match(
  botFeishu,
  /bot_progress_reply_for_runtime_event[\s\S]*model_call_started[\s\S]*tool_call_started[\s\S]*approval_required/s,
  "Feishu listener must forward key desktop-agent progress states back to Feishu",
);

assert.match(
  botFeishu,
  /if !result\.ok \{[\s\S]*bot_safe_failure_reply[\s\S]*return Ok\(\(\)\);[\s\S]*fn bot_reply_content\(result: &LocalChatResult\) -> String \{[\s\S]*if !result\.ok \{[\s\S]*return String::new\(\);/s,
  "Feishu listener must send a safe failure notice while still blocking mock diagnostics as normal bot replies",
);

assert.match(
  botFeishu,
  /fn bot_safe_failure_reply[\s\S]*处理未完成[\s\S]*truncate_status_text/s,
  "Feishu failure replies must be short user-safe status messages",
);

assert.match(
  botFeishu,
  /fn event_mention_count[\s\S]*mentions[\s\S]*fn event_text_matches_connector[\s\S]*connector\.name[\s\S]*fn should_handle_event/s,
  "Feishu listener must keep non-sensitive ignored-message diagnostics",
);

assert.match(
  shouldHandleEventSource,
  /chat_type == "p2p"/,
  "Feishu listener must only handle p2p/private messages",
);

assert.doesNotMatch(
  shouldHandleEventSource,
  /event_mentions_bot|event_text_matches_connector/,
  "Feishu listener must not allow group messages through mentions or connector-name matching",
);

assert.match(
  botFeishu,
  /飞书消息未进入机器人：仅处理私聊；chatType=\{\} mentions=\{\} nameMatched=\{\}/,
  "Feishu ignored group messages must log non-sensitive trigger diagnostics",
);

assert.match(
  botFeishu,
  /fn connector_model_runtime[\s\S]*model_runtime[\s\S]*modelRuntime[\s\S]*LocalModelRuntimeConfig/s,
  "Feishu listener must restore a persisted desktop model runtime from the local connector config",
);

assert.match(
  botFeishu,
  /listener-contexts\.json[\s\S]*persist_listener_context[\s\S]*start_persisted_local_listeners/s,
  "Feishu listener context must be persisted locally so enabled bots can restart with the desktop app",
);

assert.match(
  botFeishu,
  /unwrap_or_else\(\|\| StoredFeishuListenerContext[\s\S]*default_bot_workspace_path/s,
  "Feishu auto-start must not require a pre-existing listener-contexts.json file",
);

assert.match(
  botFeishu,
  /fn stop_stale_sdk_listener_processes[\s\S]*FEISHU_SDK_WORKER_RELATIVE_PATH[\s\S]*pkill/s,
  "Feishu auto-start must clean stale SDK listener processes before starting the desktop-owned listener",
);

assert.match(
  botFeishu,
  /pub fn start_local_listener[\s\S]*store\.is_empty\(\)[\s\S]*stop_stale_sdk_listener_processes\(\)/s,
  "Feishu manual listener startup must clean stale SDK listener processes when no desktop-owned listener is tracked",
);

assert.doesNotMatch(
  botFeishu,
  /if let Some\(existing\) = store\.get\(&connector_id\)[\s\S]*return Ok\(existing\.status\.clone\(\)\)/,
  "Feishu listener startup must replace an existing process so refreshed model runtime is not ignored",
);

assert.match(
  botFeishu,
  /const DESKTOP_BOT_GLOBAL_PROJECT_ID: &str = "desktop-bot-global";[\s\S]*bot_chat_session_id[\s\S]*project_id: DESKTOP_BOT_GLOBAL_PROJECT_ID\.to_string\(\)/s,
  "Feishu bot runtime must use a desktop-global virtual project and per-chat bot sessions instead of binding to ProjectChat project state",
);

assert.match(
  liuagentDefinitions,
  /name: "list_projects"[\s\S]*真实项目列表[\s\S]*不要用 desktop-bot-global/,
  "desktop bot tools must expose a backend-backed project list tool instead of treating desktop-bot-global as a real project",
);

assert.match(
  liuagentDefinitions,
  /name: "get_project"[\s\S]*读取当前桌面登录用户有权限访问的真实项目详情/,
  "desktop bot tools must expose a backend-backed project detail tool",
);

assert.match(
  liuagentRuntime,
  /"list_projects" \| "get_project"[\s\S]*backend_context[\s\S]*Project tools are disabled because no backend login context is available/,
  "project tools must be hidden when desktop backend login context is missing",
);

assert.match(
  liuagentRuntime,
  /"list_projects"[\s\S]*"get_project"[\s\S]*"_backend_token"/,
  "project tools must receive backend auth only at execution time",
);

assert.match(
  liuagentMod,
  /use tools::projects::\{get_project, list_projects\};[\s\S]*"list_projects" => list_projects[\s\S]*"get_project" => get_project/s,
  "project tools must be executed by the desktop liuagent runtime",
);

assert.match(
  liuagentProjectTools,
  /pub fn list_projects[\s\S]*backend_get_json[\s\S]*\/projects|fn projects_url[\s\S]*backend_url\(api_base_url, "projects"\)/s,
  "list_projects must call the backend /api/projects endpoint",
);

assert.doesNotMatch(
  botFeishu,
  /struct StoredFeishuListenerContext \{[^}]*project_id|struct StoredFeishuListenerContext \{[^}]*chat_session_id/s,
  "Persisted Feishu listener context must not store project_id/chat_session_id bindings",
);

assert.doesNotMatch(
  botFeishu,
  /FEISHU_MESSAGE_EVENT_KEY|"event",\s*"consume"/,
  "Feishu listener must not use lark-cli event consume for incoming messages",
);

assert.doesNotMatch(
  botFeishu,
  /messages-reply/,
  "Feishu message replies must not depend on lark-cli messages-reply",
);

assert.match(
  botFeishuSdkWorker,
  /from lark_oapi\.ws import Client[\s\S]*register_p2_im_message_receive_v1[\s\S]*Client\(app_id, app_secret, event_handler=handler\)\.start\(\)/,
  "Feishu Python SDK worker must use lark_oapi long connection message events",
);

assert.match(
  botFeishuSdkWorker,
  /"mentions": plain\(message\.get\("mentions"\) or event\.get\("mentions"\) or \[\]\)/,
  "Feishu Python SDK worker must preserve message mentions for ignored-message diagnostics",
);

assert.match(
  botFeishuSdkWorker,
  /AI_EMPLOYEE_FEISHU_COMMAND[\s\S]*ReplyMessageRequest[\s\S]*client\.im\.v1\.message\.reply/,
  "Feishu Python SDK worker must also support SDK-based message replies",
);

assert.match(
  botFeishuSdkWorker,
  /FEISHU_OPEN_API_UUID_MAX_LENGTH = 50[\s\S]*def normalize_feishu_uuid[\s\S]*hashlib\.sha256[\s\S]*\.uuid\(uuid\)/,
  "Feishu Python SDK replies must normalize overlong idempotency keys before calling the reply API",
);

assert.match(
  botFeishuSdkWorker,
  /def sdk_response_error_detail[\s\S]*get_troubleshooter[\s\S]*detail=sdk_response_error_detail\(response\)/,
  "Feishu Python SDK reply failures must expose detailed SDK error metadata",
);

assert.match(
  botFeishuSdkWorker,
  /AI_EMPLOYEE_FEISHU_APP_ID[\s\S]*AI_EMPLOYEE_FEISHU_APP_SECRET[\s\S]*\[feishu-sdk\] ready event_key=im\.message\.receive_v1/,
  "Feishu Python SDK worker must read local connector credentials from env and emit a ready marker",
);

assert.match(
  bridge,
  /botStartLocalChat: "bot_start_local_chat"[\s\S]*botStartFeishuLocalListener: "bot_start_feishu_local_listener"/,
  "native bridge must expose Tauri bot chat and Feishu listener commands",
);

assert.match(
  projectChat,
  /startNativeFeishuLocalBotListener\(\{[\s\S]*modelRuntime[\s\S]*mcpConfig: globalMcpConfig\.value[\s\S]*backendContext/s,
  "ProjectChat must pass model, global MCP, and backend context into the persistent Tauri Feishu listener",
);

assert.doesNotMatch(
  projectChat,
  /startNativeFeishuLocalBotListener\(\{[^}]*projectId|startNativeFeishuLocalBotListener\(\{[^}]*chatSessionId/s,
  "Feishu bot listener startup must not bind to the current project or current ProjectChat session",
);

assert.doesNotMatch(
  projectChat,
  /subscribeNativeFeishuLocalBotEvents\(handleNativeFeishuLocalBotEvent\)/,
  "ProjectChat must not be the required consumer for Feishu bot message events",
);

assert.match(
  projectChat,
  /function normalizeLocalFeishuBotEvent[\s\S]*event\.message[\s\S]*raw_content[\s\S]*mentions/s,
  "ProjectChat must normalize official nested Feishu event.message payloads",
);

assert.match(
  projectChat,
  /function buildLocalFeishuBotAttachments[\s\S]*downloadNativeFeishuMessageResource/s,
  "ProjectChat must pass Feishu resources into local bot chat as attachments",
);

assert.match(
  projectChat,
  /const localFeishuBotStatusText = computed[\s\S]*飞书监听失败[\s\S]*飞书监听已就绪/s,
  "ProjectChat must surface local Feishu listener status instead of failing silently",
);

assert.match(
  projectChat,
  /function normalizeLocalFeishuBotStatusMessage[\s\S]*error\.message[\s\S]*error\.hint/s,
  "ProjectChat must normalize Feishu local listener error envelopes for visible diagnostics",
);

assert.doesNotMatch(
  projectChat,
  /\/api\/bot-connectors|bot_local_chat|run_project_chat_once|external-agent\/tasks\/claim|completeDesktopBotRunnerTask|claimDesktopBotRunnerTaskOnce|desktopBotRunner/,
  "ProjectChat bot path must not call backend bot connector APIs, backend bot_local_chat, or the old backend desktop bot task queue",
);

assert.match(
  botConnectorModule,
  /未填写机器人提示词，运行时不会注入内置机器人提示词/,
  "bot connector diagnostics must explain that blank prompt means no built-in bot prompt",
);

console.log("local bot runtime checks passed");
