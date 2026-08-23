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
const liuagentPaths = read("src-tauri/src/liuagent_core/paths.rs");
const liuagentProjectCatalog = read(
  "src-tauri/src/liuagent_core/project_catalog.rs",
);
const liuagentProjectTools = read("src-tauri/src/liuagent_core/tools/projects.rs");
const botFeishuSdkWorker = read("src-tauri/bot_workers/feishu_sdk_listener.py");
const botFeishuSdkRequirements = read("src-tauri/bot_workers/requirements.txt");
const tauriConfig = read("src-tauri/tauri.conf.json");
const bridge = read("src/utils/native-desktop-bridge.js");
const projectChat = read("src/views/projects/ProjectChat.vue");
const botConnectorPage = read("src/views/system/SystemBotConnectors.vue");
const botConnectorModule = read("src/components/system/BotPlatformConnectorModule.vue");
const localModelRuntime = read("src/services/local-model-runtime.js");
const localMainModelRuntime = read("src/services/local-main-model-runtime.js");
const localProjectRepository = read("src/services/local-project-repository.js");
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
  liuagentPaths,
  /pub const DESKTOP_RUNTIME_DIR_NAME: &str = "desktop-agent-runtime";[\s\S]*?pub fn desktop_runtime_root[\s\S]*?\.join\("\.ai-employee"\)[\s\S]*?\.join\(DESKTOP_RUNTIME_DIR_NAME\)/,
  "desktop runtime root must be ~/.ai-employee/desktop-agent-runtime",
);

assert.match(
  liuagentProjectCatalog,
  /pub fn global_project_catalog_path\(\) -> Result<PathBuf, String> \{[\s\S]*?desktop_runtime_root\(&home\)[\s\S]*?\.join\("projects"\)[\s\S]*?\.join\("catalog\.json"\)/,
  "desktop-global project catalog must live under ~/.ai-employee/desktop-agent-runtime/projects/catalog.json",
);

assert.match(
  tauriMain,
  /fn global_bot_connector_config_path\(\) -> Result<PathBuf, String> \{[\s\S]*?desktop_runtime_root\(&home\)[\s\S]*?\.join\("bots"\)[\s\S]*?\.join\("connectors\.json"\)/,
  "global bot connector config must live under the desktop runtime bots directory",
);

assert.match(
  tauriMain,
  /fn read_global_project_catalog_file[\s\S]*?read_global_project_catalog[\s\S]*?fn write_global_project_catalog_file[\s\S]*?write_global_project_catalog/s,
  "Tauri must expose the desktop-global project catalog independently of bot connector config",
);

assert.match(
  tauriMain,
  /start_persisted_local_listeners\(app\.handle\(\)\.clone\(\)\)/,
  "Tauri startup must restore persisted local bot listeners with the desktop app",
);

assert.match(
  appVue,
  /resolveLocalMainModelRuntime[\s\S]*syncLocalBotListeners[\s\S]*readGlobalBotConnectorConfigFile[\s\S]*startNativeFeishuLocalBotListener/s,
  "desktop app shell must refresh local Feishu listeners from the shared system main model without requiring ProjectChat to mount",
);

assert.match(
  appVue,
  /function buildConnectorModelRuntime[\s\S]*return resolveLocalMainModelRuntime\(\)/s,
  "desktop bot listener sync must rebuild runtime from the shared system main model",
);

assert.doesNotMatch(
  appVue,
  /function buildConnectorModelRuntime[\s\S]*(?:connector\.provider_id|connector\.model_name|connector\.model_runtime)/s,
  "desktop bot listener sync must not use connector-specific model fields",
);

assert.match(
  appVue,
  /local-bot-runtime-diagnostic/,
  "desktop app shell must emit a local diagnostic when a bot has no usable model runtime",
);

assert.doesNotMatch(
  appVue,
  /\/llm\/providers\/\$\{encodeURIComponent\(normalizedProviderId\)\}\/desktop-runtime/,
  "desktop bot listener sync must not call the backend desktop-runtime endpoint",
);

assert.doesNotMatch(
  appVue,
  /syncLocalProjectsToNativeCatalog/,
  "bot listener and login lifecycle must not overwrite the desktop-global project catalog",
);

assert.match(
  chatStorage,
  /export function globalBotConnectorConfigPathLabel\(\) \{[\s\S]*?~\/\.ai-employee\/desktop-agent-runtime\/bots\/connectors\.json/,
  "frontend storage label must point to the local global bot connector config file",
);

assert.doesNotMatch(
  chatStorage,
  /project_workspaces|projectWorkspaces/,
  "bot connector config storage must not persist project workspace choices",
);

assert.match(
  botConnectorPage,
  /readGlobalBotConnectorConfigFile[\s\S]*writeGlobalBotConnectorConfigFile/,
  "bot connector page must read and write local global connector config through Tauri",
);

assert.doesNotMatch(
  botConnectorPage,
  /buildLocalModelRuntime|normalizeLocalModelRuntime|model_runtime/s,
  "bot connector page must not derive or persist a connector-specific model runtime",
);

assert.doesNotMatch(
  botConnectorPage,
  /\/llm\/providers\/\$\{encodeURIComponent\(normalizedProviderId\)\}\/desktop-runtime|import api from/,
  "bot connector page save and scan flow must not call backend model runtime APIs",
);

assert.doesNotMatch(
  botConnectorPage,
  /\/api\/bot-connectors|api\.(?:get|post|patch|delete)\([^)]*bot-connectors/,
  "bot connector page must not use backend bot connector APIs as the config source",
);

assert.match(
  botConnectorModule,
  /跟随系统主对话模型[\s\S]*机器人与系统主对话使用同一个模型渠道和模型选择/,
  "bot connector module must show that bots follow the system main chat model",
);

assert.doesNotMatch(
  botConnectorModule,
  /readLocalModelProviders|fetchBotChatModelOptions|mergeBotChatProviders|api\.get\(["']\/llm\/providers|import api from/,
  "bot connector module must not load or show a separate model provider selector",
);

assert.doesNotMatch(
  botConnectorModule,
  /机器人提示词|system_prompt|prompt_policy|provider_id|model_name|model_runtime/,
  "bot connector configuration must not expose a second agent prompt or model runtime",
);

assert.match(
  botConnectorModule,
  /项目来源[\s\S]*桌面项目目录/,
  "bot connector configuration must identify the desktop project catalog as the project source",
);

assert.doesNotMatch(
  botConnectorModule,
  /机器人项目工作区|project_workspaces|projectWorkspaces|pickProjectWorkspace/,
  "bot connector configuration must not expose project or workspace selection",
);

assert.match(
  localProjectRepository,
  /function mergeNativeProjectCatalogEntries[\s\S]*project\.workspace_path \|\| previous\.workspace_path[\s\S]*return \[\.\.\.merged\.values\(\)\]/s,
  "desktop-global project catalog sync must preserve entries absent from the current browser cache",
);

assert.match(
  localProjectRepository,
  /function writeNativeProjectCatalog[\s\S]*readNativeGlobalProjectCatalogFile[\s\S]*mergeNativeProjectCatalogEntries\([\s\S]*parseNativeProjectCatalogEntries[\s\S]*writeNativeGlobalProjectCatalogFile[\s\S]*projects: mergedProjects/s,
  "actual local project updates must merge entries into the desktop-global project catalog",
);

assert.match(
  localProjectRepository,
  /export function writeLocalProjects\(projects\) \{[\s\S]*scheduleNativeProjectCatalogSync\(normalized\)/,
  "project changes must refresh the desktop-global project catalog",
);

assert.match(
  localModelRuntime,
  /export function normalizeLocalModelRuntime[\s\S]*export function buildLocalModelRuntime/,
  "local model runtime service must normalize persisted runtime snapshots",
);

assert.match(
  localMainModelRuntime,
  /MAIN_PROVIDER_KEY = "default_ai_provider_id"[\s\S]*MAIN_MODEL_KEY = "default_ai_model_name"/s,
  "shared local main model runtime must define canonical system main model keys",
);

assert.match(
  localMainModelRuntime,
  /main_chat_provider_id[\s\S]*mainChatProviderId[\s\S]*main_chat_model_name[\s\S]*mainChatModelName/s,
  "shared local main model runtime must accept legacy system main model aliases",
);

assert.match(
  localMainModelRuntime,
  /export function resolveLocalMainModelRuntime[\s\S]*readLocalMainModelSelection[\s\S]*buildLocalModelRuntime[\s\S]*normalizeLocalModelRuntime/s,
  "shared local main model runtime must build the desktop runtime from the system main model selection",
);

assert.match(
  botRuntime,
  /pub fn build_local_chat_request\(request: BotChatRequest\) -> LocalChatRequest \{[\s\S]*?system_prompt_parts: Vec::new\(\),/,
  "bot runtime must pass through without injecting a connector-specific prompt",
);

assert.doesNotMatch(
  botRuntime,
  /connector_prompt|BOT_PROJECT_CONTEXT_PROMPT_SOURCE|bot_project_context\.policy/,
  "bot runtime must not inject connector or project-routing prompt text",
);

assert.doesNotMatch(
  botRuntime,
  /(?:^|\n)\s*system_prompt:\s*(?:Some\(|None|")/m,
  "bot runtime must not set a built-in system_prompt field",
);

assert.match(
  botRuntime,
  /fn validate_bot_model_runtime[\s\S]*bot\.model_runtime_unconfigured[\s\S]*机器人未配置可用的桌面模型运行时，已跳过回复/,
  "bot runtime must fail before liuAgent mock mode when no real desktop model runtime is configured",
);

assert.match(
  botRuntime,
  /"role": "connector_controller"/,
  "bot runtime metadata must identify the bot as the connector controller",
);

assert.match(
  botMod,
  /connector_metadata_does_not_become_a_model_prompt[\s\S]*system_prompt_parts\.is_empty\(\)/,
  "bot unit tests must lock connector metadata out of model prompts",
);

assert.match(
  botMod,
  /local_request\.mcp_config\["botContext"\][\s\S]*runtime[\s\S]*connector_controller/,
  "bot unit tests must lock connector-controller runtime metadata",
);

assert.match(
  botRuntime,
  /project_access: "desktop_global_project_catalog_only"[\s\S]*tool_access: "connector_authorized_desktop_tools"/,
  "bot permission contract must scope project access to the desktop-global catalog",
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
  tauriConfig,
  /"bot_workers\/requirements\.txt"/,
  "Tauri bundle resources must include the Feishu Python SDK requirements",
);

assert.match(
  botFeishuSdkRequirements,
  /^lark-oapi>=1\.4\.0,<2\s*$/m,
  "Feishu Python SDK requirements must declare a compatible lark-oapi package",
);

assert.match(
  botFeishuSdkWorker,
  /def normalize_message_event/,
  "Feishu Python SDK worker must normalize received message events",
);

assert.match(
  botFeishuSdkWorker,
  /"message_id", "messageId"/,
  "Feishu Python SDK worker must normalize snake_case and camelCase message IDs",
);

assert.match(
  botFeishuSdkWorker,
  /"chat_id", "chatId"/,
  "Feishu Python SDK worker must normalize snake_case and camelCase chat IDs",
);

assert.match(
  botFeishuSdkWorker,
  /"chat_type", "chatType"/,
  "Feishu Python SDK worker must normalize snake_case and camelCase chat types",
);

assert.match(
  botFeishuSdkWorker,
  /"sender_id", "senderId"/,
  "Feishu Python SDK worker must normalize snake_case and camelCase sender IDs",
);

assert.match(
  botFeishuSdkWorker,
  /def event_shape_diagnostic/,
  "Feishu Python SDK worker must diagnose empty event shapes",
);

assert.match(
  botFeishuSdkWorker,
  /"root_keys"[\s\S]*"event_keys"[\s\S]*"message_keys"/s,
  "Feishu event-shape diagnostics must identify only field names",
);

assert.match(
  botFeishuSdkWorker,
  /\[feishu-sdk\] event-shape \{diagnostic\}/,
  "Feishu Python SDK worker must emit shape diagnostics for empty events",
);

assert.match(
  botFeishuSdkWorker,
  /"mentions": plain\([\s\S]*"mentions"[\s\S]*"message_mentions"/s,
  "Feishu Python SDK worker must preserve message mentions for ignored-message diagnostics",
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
  /struct StoredBotConversation/,
  "Feishu bot must persist structured conversation history",
);

assert.match(
  botFeishu,
  /fn global_bot_runtime_dir\(\) -> Result<PathBuf, String> \{[\s\S]*?desktop_runtime_root\(&home\)\.join\("bots"\)/s,
  "Feishu bot runtime files must use the desktop runtime bots directory",
);

assert.match(
  botFeishu,
  /fn global_bot_conversation_dir\(\) -> Result<PathBuf, String> \{[\s\S]*?global_bot_runtime_dir\(\)\?\.join\("conversations"\)/s,
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
  "Feishu listener must always handle p2p/private messages",
);

assert.match(
  shouldHandleEventSource,
  /event_mentions_bot[\s\S]*event_text_matches_connector/,
  "Feishu listener must allow group messages when mentioned or name-matched",
);

assert.match(
  botFeishu,
  /飞书消息未命中机器人触发条件：chatType=\{\} mentions=\{\} nameMatched=\{\}/,
  "Feishu ignored messages must log non-sensitive trigger diagnostics",
);

assert.match(
  botFeishu,
  /listener-contexts\.json[\s\S]*persist_listener_context[\s\S]*start_persisted_local_listeners/s,
  "Feishu listener context must be persisted locally so enabled bots can restart with the desktop app",
);

assert.match(
  botFeishu,
  /model_runtime: context\.model_runtime/,
  "Feishu persisted listener startup must use the shared main-model runtime snapshot",
);

assert.match(
  botFeishu,
  /unwrap_or_else\(\|\| StoredFeishuListenerContext \{[\s\S]*connector_id: connector_id\.clone\(\),[\s\S]*model_runtime: None,[\s\S]*mcp_config: load_global_mcp_config\(\),/s,
  "Feishu auto-start must not require a pre-existing listener context or connector-owned workspace",
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
  /const DESKTOP_BOT_GLOBAL_PROJECT_ID: &str = "desktop-bot-global";/,
  "Feishu connector must use a neutral desktop-global runtime scope",
);

assert.match(
  botFeishu,
  /fn catalog_bot_workspace_selection[\s\S]*find_global_project_catalog_entry[\s\S]*valid_bot_workspace_selection\(BotWorkspaceSelection \{[\s\S]*workspace_path: project\.workspace_path/s,
  "Feishu connector must validate persisted chat selections against the desktop-global project catalog",
);

assert.doesNotMatch(
  botFeishu,
  /connector_project_workspaces|project_workspaces|projectWorkspaces/,
  "Feishu connector must not load a connector-owned project workspace catalog",
);

assert.doesNotMatch(
  botFeishu,
  /StoredBotProjectBinding|load_bot_project_binding|persist_bot_project_binding|prefetch_bot_project_binding|project_ids_from_text|is_global_project_query/,
  "Feishu connector must not bind, infer, or route projects before the main agent decides",
);

assert.match(
  liuagentRuntime,
  /fn is_tauri_bot_local_chat_config[\s\S]*botContext[\s\S]*tauri_bot_local_chat/,
  "shared runtime must recognize connector requests without changing the model agent",
);

assert.match(
  liuagentRuntime,
  /当前飞书会话尚未选择项目；收到项目查询或切换请求时，先调用 list_bot_projects，再按 project_id 调用 switch_project_workspace/,
  "shared runtime must let the main agent choose from the desktop-global project catalog",
);

assert.match(
  botFeishu,
  /let chat_session_id = bot_chat_session_id[\s\S]*?load_bot_workspace_selection\(&context\.connector, &chat_session_id\)[\s\S]*?unwrap_or_else\(\|\| DESKTOP_BOT_GLOBAL_PROJECT_ID\.to_string\(\)\)[\s\S]*?project_id: project_id\.clone\(\)/s,
  "Feishu connector must persist selections per chat while falling back to a neutral runtime scope",
);

assert.match(
  liuagentDefinitions,
  /name: "list_bot_projects"[\s\S]*不读取桌面当前登录用户[\s\S]*机器人连接器配置/s,
  "bot project list definition must be independent of the desktop login user and connector config",
);

assert.match(
  liuagentDefinitions,
  /name: "switch_project_workspace"[\s\S]*桌面本机全局项目目录/s,
  "bot workspace switch definition must use the desktop-global project catalog",
);

assert.match(
  liuagentDefinitions,
  /name: "list_projects"[\s\S]*本机全局项目目录[\s\S]*desktop-bot-global/,
  "desktop project list must read the local global catalog and must not treat desktop-bot-global as a real project",
);

assert.match(
  liuagentDefinitions,
  /name: "get_project"[\s\S]*本机全局项目目录/,
  "desktop project detail must read the local global catalog",
);

assert.doesNotMatch(
  liuagentRuntime,
  /Project tools are disabled because no backend login context is available/,
  "desktop project tools must remain available without backend login context",
);

assert.match(
  liuagentRuntime,
  /"list_projects" \| "get_project" => \{[\s\S]*Feishu bot sessions must use list_bot_projects and switch_project_workspace for project selection[\s\S]*None/,
  "Feishu bot sessions must keep using bot project tools instead of desktop list_projects",
);

assert.doesNotMatch(
  liuagentRuntime,
  /if !matches!\(\s*tool_name,\s*"list_projects"[\s\S]*"get_project"[\s\S]*"get_project_deploy_options"/s,
  "list_projects/get_project must not receive backend auth at execution time",
);

assert.match(
  liuagentMod,
  /use tools::projects::\{get_project, list_bot_projects, list_projects, switch_project_workspace\};[\s\S]*"list_bot_projects" => list_bot_projects[\s\S]*"switch_project_workspace" => switch_project_workspace/s,
  "desktop liuagent runtime must execute the bot project and workspace tools",
);

assert.match(
  liuagentProjectTools,
  /pub fn list_projects[\s\S]*list_catalog_projects[\s\S]*project_catalog\(\)\?/s,
  "list_projects must read the desktop-global project catalog",
);

assert.match(
  liuagentProjectTools,
  /fn project_catalog\(\) -> Result<Vec<DesktopProjectCatalogEntry>, ToolError> \{[\s\S]*read_global_project_catalog/s,
  "project tools must read the desktop-global project catalog at execution time",
);

assert.doesNotMatch(
  liuagentProjectTools,
  /backend_get_json|_backend_token|_backend_api_base_url/,
  "desktop project tools must not query the backend or require a desktop login token",
);

assert.match(
  liuagentRuntime,
  /if matches!\(tool_name, "list_bot_projects" \| "switch_project_workspace"\) \{[\s\S]*if is_bot_request \{[\s\S]*"_bot_request"[\s\S]*return arguments/s,
  "bot project tools must receive only the bot-session marker at execution time",
);

assert.doesNotMatch(
  liuagentRuntime,
  /_bot_project_workspaces|projectWorkspaces/,
  "shared runtime must not pass connector-owned project workspace configuration to bot tools",
);

const switchBotProjectToolMatch = liuagentProjectTools.match(
  /pub fn switch_project_workspace\(arguments: &Value\) -> Result<\(Value, String\), ToolError> \{[\s\S]*?\n\}\n\npub fn get_project/,
);
assert.ok(
  switchBotProjectToolMatch,
  "bot workspace switch implementation must be present",
);
assert.doesNotMatch(
  switchBotProjectToolMatch[0],
  /backend_get_json|_backend_token|_backend_api_base_url/,
  "bot workspace switching must not query the backend or require a desktop login token",
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
  /"mentions": plain\(\s*first_field\(\(message, event, raw\), "mentions", "message_mentions"\) or \[\]\s*\)/s,
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
  /readGlobalProjectCatalogFile: "read_global_project_catalog_file"[\s\S]*writeGlobalProjectCatalogFile: "write_global_project_catalog_file"[\s\S]*botStartFeishuLocalListener: "bot_start_feishu_local_listener"[\s\S]*botScanFeishuChats: "bot_scan_feishu_chats"/,
  "native bridge must expose the desktop project catalog and desktop-owned Feishu listener commands",
);

assert.doesNotMatch(
  bridge,
  /bot_start_local_chat|bot_reply_feishu_message|bot_download_feishu_message_resource|bot_get_feishu_message|startNativeBotLocalChat|replyNativeFeishuBotMessage|downloadNativeFeishuMessageResource|getNativeFeishuMessage/,
  "browser pages must not expose direct Feishu bot execution or message-control commands",
);

assert.match(
  appVue,
  /startNativeFeishuLocalBotListener\(\{[\s\S]*modelRuntime[\s\S]*mcpConfig[\s\S]*permissionDecision: null/s,
  "App shell must pass refreshed model runtime and global MCP config into the persistent Tauri Feishu listener",
);

assert.doesNotMatch(
  `${appVue}\n${projectChat}`,
  /startNativeFeishuLocalBotListener\(\{[^}]*projectId|startNativeFeishuLocalBotListener\(\{[^}]*chatSessionId/s,
  "Feishu bot listener startup must not bind to the current project or current ProjectChat session",
);

assert.doesNotMatch(
  projectChat,
  /readGlobalBotConnectorConfigFile|startNativeBotLocalChat|syncLocalFeishuBotListeners|handleNativeFeishuLocalBotEvent|replyNativeFeishuBotMessage|downloadNativeFeishuMessageResource|getNativeFeishuMessage/,
  "ProjectChat must not own Feishu bot listener, project selection, or message-control work",
);

assert.doesNotMatch(
  projectChat,
  /\/api\/bot-connectors|bot_local_chat|run_project_chat_once|external-agent\/tasks\/claim|completeDesktopBotRunnerTask|claimDesktopBotRunnerTaskOnce|desktopBotRunner/,
  "ProjectChat bot path must not call backend bot connector APIs, backend bot_local_chat, or the old backend desktop bot task queue",
);

console.log("local bot runtime checks passed");
