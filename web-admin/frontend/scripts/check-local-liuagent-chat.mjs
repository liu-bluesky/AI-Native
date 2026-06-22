import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const scriptDir = dirname(fileURLToPath(import.meta.url));
const rootDir = resolve(scriptDir, "..");

const tauriMain = readFileSync(resolve(rootDir, "src-tauri/src/main.rs"), "utf8");
const runtime = readFileSync(
  resolve(rootDir, "src-tauri/src/liuagent_core/runtime.rs"),
  "utf8",
);
const fileTools = readFileSync(
  resolve(rootDir, "src-tauri/src/liuagent_core/tools/file.rs"),
  "utf8",
);
const gateway = readFileSync(
  resolve(rootDir, "src-tauri/src/liuagent_core/gateway.rs"),
  "utf8",
);
const bridge = readFileSync(resolve(rootDir, "src/utils/native-desktop-bridge.js"), "utf8");
const projectChat = readFileSync(resolve(rootDir, "src/views/projects/ProjectChat.vue"), "utf8");
const projectChatResponsiveCss = readFileSync(
  resolve(rootDir, "src/modules/project-chat/styles/project-chat-style-15.css"),
  "utf8",
);
const llmProvidersRouter = readFileSync(
  resolve(rootDir, "../api/routers/llm_providers.py"),
  "utf8",
);

assert.match(
  tauriMain,
  /async fn liuagent_start_local_chat\(\s*app: tauri::AppHandle,\s*request: liuagent_core::LocalChatRequest,/,
  "Tauri must expose liuagent_start_local_chat with an AppHandle for runtime event broadcast",
);

assert.match(
  tauriMain,
  /tauri::async_runtime::spawn_blocking\(move \|\| \{[\s\S]*?liuagent_core::start_local_chat_with_event_sink\(request,[\s\S]*?\}\)\s*\.await/,
  "local liuAgent chat must run blocking model/tool work on a background worker while streaming runtime events",
);

assert.match(
  tauriMain,
  /liuagent_start_local_chat/,
  "liuagent_start_local_chat must be registered in the invoke handler",
);

assert.match(
  tauriMain,
  /app\.emit\("liuagent-runtime-event",\s*event\.clone\(\)\)[\s\S]*app\.emit\("liuagent:\/\/runtime-event",\s*event\)/,
  "local liuAgent chat must broadcast live runtime events through stable and legacy Tauri event channels",
);

assert.match(
  tauriMain,
  /fn liuagent_recover_runtime_state\(\s*request: liuagent_core::LocalRuntimeRecoveryRequest,/,
  "Tauri must expose local liuAgent runtime recovery",
);

assert.match(
  bridge,
  /recoverNativeLiuAgentRuntimeState/,
  "native desktop bridge must expose local liuAgent runtime recovery",
);

assert.match(
  tauriMain,
  /fn liuagent_list_runtime_events\(\s*request: liuagent_core::LocalRuntimeEventsRequest,/,
  "Tauri must expose local liuAgent runtime event listing",
);

assert.match(
  tauriMain,
  /fn liuagent_list_runtime_outbox\(\s*request: liuagent_core::LocalRuntimeOutboxRequest,/,
  "Tauri must expose local liuAgent runtime outbox listing",
);

assert.match(
  tauriMain,
  /fn liuagent_ack_runtime_outbox\(\s*request: liuagent_core::LocalRuntimeOutboxAckRequest,/,
  "Tauri must expose local liuAgent runtime outbox ack",
);

assert.match(
  tauriMain,
  /liuagent_list_runtime_events[\s\S]*liuagent_list_runtime_outbox[\s\S]*liuagent_ack_runtime_outbox/,
  "runtime event and outbox Tauri commands must be registered in the invoke handler",
);

assert.match(
  tauriMain,
  /fn liuagent_prepare_agent_invocation\(\s*request: liuagent_core::AgentInvocationRequest,/,
  "Tauri must expose liuagent_prepare_agent_invocation",
);

assert.match(
  tauriMain,
  /liuagent_prepare_agent_invocation/,
  "liuagent_prepare_agent_invocation must be registered in the invoke handler",
);

assert.match(
  gateway,
  /desktop-agent-gateway-requirement/,
  "Agent Gateway must persist a local requirement record",
);

assert.match(
  gateway,
  /"serverCanAccess": false/,
  "Agent Gateway workspace binding must state that the server cannot access local workspace",
);

assert.match(
  gateway,
  /"canonicalEntry": "Unified MCP"/,
  "Agent Gateway must keep Unified MCP as the canonical recording entry",
);

assert.match(
  runtime,
  /desktop-local-agent-requirement/,
  "local chat must persist a desktop-local-agent requirement record",
);

assert.match(
  runtime,
  /\.join\("requirements"\)/,
  "local chat requirement records must live under .ai-employee/requirements",
);

assert.doesNotMatch(
  runtime,
  /infer_(?:delete|write)_file_tool|extract_file_name_after_delete|extract_marked_value/,
  "local chat must not infer file tool calls from user text",
);

assert.doesNotMatch(
  runtime,
  /fn plan_local_tool\(\s*run_key:\s*&str,\s*user_message:/,
  "plan_local_tool must not receive user_message",
);

assert.match(
  runtime,
  /if !model_result\.tool_calls\.is_empty\(\)\s*\{\s*return model_result\.tool_calls\.clone\(\);/s,
  "local chat must prefer standard model tool_calls instead of parsing user text",
);

assert.match(
  fileTools,
  /exists_after/,
  "local delete flow must verify that the file no longer exists",
);

assert.match(
  runtime,
  /local_chat_does_not_delete_from_user_text_without_model_tool_call/,
  "local chat must test that natural-language delete requests do not delete files",
);

assert.match(
  runtime,
  /assert!\(result\.tool_results\.is_empty\(\)\)/,
  "local chat must not execute a default local tool when the model did not request one",
);

assert.match(
  runtime,
  /fn tool_failure_signature\(/,
  "local Agent Loop must generate a failure signature for failed tool attempts",
);

assert.match(
  runtime,
  /\"repeated_failure\"[\s\S]*相同方案和相同失败签名重复出现/,
  "local Agent Loop must pause when the same failed strategy repeats",
);

assert.match(
  runtime,
  /retry_instruction[\s\S]*不同 strategy_signature/,
  "local Agent Loop must tell the model to switch strategy after a failed attempt",
);

assert.match(
  runtime,
  /agent_loop_pauses_when_same_failed_strategy_repeats/,
  "local Agent Loop must test repeated failed strategy pause behavior",
);

assert.match(
  runtime,
  /struct AgentLoopCandidateSolution/,
  "local Agent Loop must model candidate solutions inside the desktop runtime",
);

assert.match(
  runtime,
  /fn rank_local_tool_candidates\(/,
  "local Agent Loop must rank candidate tool strategies before execution",
);

assert.match(
  runtime,
  /verification_failed_replan_required/,
  "local Agent Loop must force replanning when a failed attempt remains unverified",
);

assert.match(
  runtime,
  /agent_loop_reprompts_when_model_tries_to_finish_after_failed_attempt/,
  "local Agent Loop must test that a failed attempt cannot be marked complete without a new verified strategy",
);

assert.match(
  runtime,
  /"task_lifecycle"[\s\S]*"candidate_solutions"[\s\S]*"verification"/,
  "desktop local runtime must keep its own Agent Loop audit with candidate solutions and verification status",
);

assert.match(
  readFileSync(resolve(rootDir, "src-tauri/src/liuagent_core/definitions.rs"), "utf8"),
  /name: "delete_file"/,
  "builtin tool definitions must register delete_file",
);

assert.match(
  runtime,
  /fn run_model_step\(/,
  "local chat must include a desktop-side model step contract",
);

assert.match(
  runtime,
  /prepare_agent_invocation\(AgentInvocationRequest/,
  "local chat must create an AgentInvocation before local execution",
);

assert.match(
  runtime,
  /gateway_result: Some\(gateway_result\)/,
  "local chat result must expose Agent Gateway metadata",
);

assert.match(
  runtime,
  /"direct-openai-compatible"/,
  "desktop model runtime must reserve an OpenAI-compatible local direct mode",
);

assert.match(
  bridge,
  /liuagentStartLocalChat: "liuagent_start_local_chat"/,
  "frontend bridge must map liuagentStartLocalChat to the Tauri command",
);

assert.match(
  bridge,
  /liuagentPrepareAgentInvocation: "liuagent_prepare_agent_invocation"/,
  "frontend bridge must map liuagentPrepareAgentInvocation to the Tauri command",
);

assert.match(
  bridge,
  /export async function startNativeLiuAgentLocalChat/,
  "frontend bridge must export startNativeLiuAgentLocalChat",
);

assert.match(
  bridge,
  /liuagentListRuntimeEvents: "liuagent_list_runtime_events"/,
  "frontend bridge must map liuagentListRuntimeEvents to the Tauri command",
);

assert.match(
  bridge,
  /liuagentListRuntimeOutbox: "liuagent_list_runtime_outbox"/,
  "frontend bridge must map liuagentListRuntimeOutbox to the Tauri command",
);

assert.match(
  bridge,
  /liuagentAckRuntimeOutbox: "liuagent_ack_runtime_outbox"/,
  "frontend bridge must map liuagentAckRuntimeOutbox to the Tauri command",
);

assert.match(
  bridge,
  /export async function listNativeLiuAgentRuntimeEvents/,
  "frontend bridge must export listNativeLiuAgentRuntimeEvents",
);

assert.match(
  bridge,
  /export async function listNativeLiuAgentRuntimeOutbox/,
  "frontend bridge must export listNativeLiuAgentRuntimeOutbox",
);

assert.match(
  bridge,
  /export async function ackNativeLiuAgentRuntimeOutbox/,
  "frontend bridge must export ackNativeLiuAgentRuntimeOutbox",
);

assert.match(
  bridge,
  /export async function subscribeNativeLiuAgentRuntimeEvents[\s\S]*listenTauriEvent\("liuagent-runtime-event"[\s\S]*listenTauriEvent\("liuagent:\/\/runtime-event"/,
  "frontend bridge must subscribe to stable and legacy runtime event channels",
);

assert.match(
  runtime,
  /emit_model_call_started_event\([\s\S]*?let model_result = model_runner\(&request\)/,
  "Agent Loop must emit a model_call_started event before waiting on the model response",
);

assert.match(
  runtime,
  /emit_tool_call_started_event\([\s\S]*?let result = tool_runner\(ToolExecutionRequest/,
  "Agent Loop must emit a tool_call_started event before executing a local tool",
);

assert.match(
  runtime,
  /"tool_index": tool_index,[\s\S]*"tool_count": tool_count,[\s\S]*"arguments_preview": arguments_preview/,
  "tool_call_started events must include index, total count, and argument preview for step-by-step UI",
);

assert.match(
  projectChat,
  /type === "model_call_started"[\s\S]*?请求中/,
  "ProjectChat must render model_call_started as a visible running detail",
);

assert.match(
  projectChat,
  /type === "tool_call_started"[\s\S]*?toolIndex[\s\S]*?toolCount[\s\S]*?argumentsPreview[\s\S]*?准备调用/,
  "ProjectChat must render tool_call_started as a visible running detail with index and argument preview",
);

assert.match(
  bridge,
  /export async function prepareNativeLiuAgentInvocation/,
  "frontend bridge must export prepareNativeLiuAgentInvocation",
);

assert.match(
  projectChat,
  /if \(isLocalRunnerSurface\.value\) \{\s*await sendLocalLiuAgentChatRequest/s,
  "local-runner chat sends must use the local liuAgent runtime path",
);

assert.match(
  projectChat,
  /const shouldPrepareRemoteAttachmentPayload = !isLocalRunnerSurface\.value;/,
  "local-runner sends must skip remote attachment preprocessing before the message enters the chat",
);

assert.match(
  projectChat,
  /const base64Images = shouldPrepareRemoteAttachmentPayload\s*\?\s*await Promise\.all\(imageFiles\.map\(readAsBase64\)\)\s*:\s*\[\];/s,
  "image base64 conversion must be limited to the remote chat path",
);

assert.match(
  projectChat,
  /if \(shouldPrepareRemoteAttachmentPayload && docFiles\.length > 0\)/,
  "document text extraction must be limited to the remote chat path",
);

assert.match(
  projectChat,
  /const chatSurface = computed\(\(\) => \{\s*return "local-runner";\s*\}\);/,
  "project chat must default to the desktop local liuAgent runtime surface",
);

assert.match(
  projectChat,
  /const modelRuntime = await buildLocalLiuAgentModelRuntime\(\)/,
  "local-runner chat must fetch an explicit desktop model runtime contract before invoking Tauri",
);

assert.match(
  projectChat,
  /modelRuntime,/,
  "local-runner chat must pass an explicit desktop model runtime contract",
);

assert.match(
  projectChat,
  /\/llm\/providers\/\$\{encodeURIComponent\(normalizedProviderId\)\}\/desktop-runtime/,
  "desktop model runtime config must be fetched from the backend as config data only",
);

assert.match(
  llmProvidersRouter,
  /provider_type != "openai-compatible"/,
  "desktop runtime config endpoint must only expose provider types implemented by the Tauri direct runtime",
);

assert.doesNotMatch(
  projectChat,
  /if \(isLocalRunnerSurface\.value\) return false;/,
  "local-runner composer must show a working status bar while local execution continues",
);

assert.match(
  projectChat,
  /!isLocalRunnerSurface\.value &&\s*Boolean\(String\(selectedProjectId\.value/,
  "local-runner composer must not show global agent workflow failures above the input",
);

assert.match(
  projectChat,
  /source: "desktop_local_agent"/,
  "local-runner failures must be recorded as desktop local agent events",
);

assert.match(
  projectChat,
  /async function syncLocalLiuAgentRuntimeOutbox\(/,
  "ProjectChat must sync local liuAgent runtime outbox entries",
);

assert.match(
  projectChat,
  /listNativeLiuAgentRuntimeOutbox\([\s\S]*source: "desktop_local_agent_outbox"[\s\S]*ackNativeLiuAgentRuntimeOutbox/s,
  "ProjectChat must upsert local runtime outbox entries and ack synced entries",
);

assert.match(
  projectChat,
  /status: "waiting_approval"[\s\S]*await syncLocalLiuAgentRuntimeOutbox\(/,
  "ProjectChat must sync local runtime outbox when local chat pauses for approval",
);

assert.match(
  projectChat,
  /function removeLocalLiuAgentPermissionOperation\(row, requestId\)[\s\S]*localLiuAgentPermissionOperationId\(normalizedRequestId\)[\s\S]*meta\.local_liuagent_permission/,
  "ProjectChat must remove the local liuAgent permission operation by request id",
);

assert.match(
  projectChat,
  /localLiuAgentPendingPermissions\.delete\(requestId\);\s*removeLocalLiuAgentPermissionOperation\(row, requestId\);/,
  "ProjectChat must hide the local liuAgent permission card immediately after a permission decision",
);

assert.match(
  projectChat,
  /function upsertLocalLiuAgentContinuationOperation\([\s\S]*AI 正在继续执行[\s\S]*phase: "running"/,
  "ProjectChat must show a running local liuAgent operation after a permission decision",
);

assert.match(
  projectChat,
  /upsertLocalLiuAgentContinuationOperation\(row, pending, requestId, allowSession\);\s*chatLoading\.value = true;/,
  "ProjectChat must keep the local runner visibly busy while continuing after permission",
);

assert.match(
  projectChat,
  /const workingStatusActiveKey = ref\(""\);/,
  "working status must track the active requirement/run, not only the chat session",
);

assert.match(
  projectChat,
  /function workingStatusRunKey\([\s\S]*return normalizedRunId \? `\$\{sessionKey\}::\$\{normalizedRunId\}` : sessionKey;/,
  "working status timer keys must include a per-run id when available",
);

assert.match(
  projectChat,
  /async function doSend\(options = \{\}\) \{[\s\S]*startWorkingStatusTimer\(assistantMessage\.id, activeChatSessionId\);/,
  "each newly sent requirement must start a fresh working timer keyed by its assistant message",
);

assert.match(
  projectChat,
  /startWorkingStatusTimer\(\s*row\?\.id \|\| pending\?\.assistantMessageId \|\| `permission:\$\{requestId\}`,\s*pending\?\.activeChatSessionId \|\| currentChatSessionId\.value,\s*\);/,
  "local liuAgent permission continuation must keep the same requirement timer instead of falling back to the chat-session timer",
);

assert.match(
  projectChat,
  /for \(const key of Array\.from\(workingStatusStartedAtBySession\.keys\(\)\)\) \{[\s\S]*key\.startsWith\(`\$\{sessionKey\}::`\)/,
  "clearing a chat session timer must remove all per-run timer keys for that session",
);

assert.doesNotMatch(
  projectChat,
  /const showWorkingStatusBar = computed\(\(\) => \{[\s\S]*if \(isLocalRunnerSurface\.value\) return false;/,
  "local-runner mode must not be excluded from the working status bar",
);

assert.match(
  projectChat,
  /status: ok \? "done" : "blocked"[\s\S]*await syncLocalLiuAgentRuntimeOutbox\(/,
  "ProjectChat must sync local runtime outbox after local chat completes or fails",
);

assert.doesNotMatch(
  projectChat,
  /if \(!ok\) \{\s*throw new Error\(String\(result\?\.error \|\| "桌面端本地对话失败"\)\);\s*\}/,
  "local-runner ok=false results must stay inside the assistant bubble instead of entering the global request failure path",
);

assert.match(
  projectChat,
  /if \(isLocalRunnerSurface\.value\) \{[\s\S]*assistantMessage\.content = `执行失败：\$\{errorMessage\}`;[\s\S]*source: "desktop_local_agent"[\s\S]*\} else \{[\s\S]*ElMessage\.error/,
  "local-runner thrown errors must be rendered in the assistant bubble while non-local chat keeps the global error toast",
);

assert.match(
  projectChat,
  /function scheduleChatSessionListMetadataRefresh\(projectId\)[\s\S]*refreshChatSessionListMetadata\(normalizedProjectId\)/,
  "send completion must refresh chat session metadata without reselecting or clearing the active conversation",
);

assert.match(
  projectChat,
  /rememberCurrentChatSessionMessages\(\);\s*scheduleChatSessionListMetadataRefresh\(selectedProjectId\.value\);/,
  "send completion must keep current messages cached before refreshing session metadata",
);

assert.doesNotMatch(
  projectChat,
  /finally \{[\s\S]*await fetchChatSessions\(selectedProjectId\.value,\s*sessionToKeep,[\s\S]*useRemembered: false,[\s\S]*\);[\s\S]*if \(\s*!requestCancelled/,
  "send completion must not call fetchChatSessions because that can replace the active messages while an answer is visible",
);

assert.match(
  projectChat,
  /function applySavedProjectChatSettings\(settings\)[\s\S]*projectChatSettings\.value = nextSettings;/,
  "model/settings save must merge returned settings locally",
);

assert.doesNotMatch(
  projectChat,
  /async function saveProjectChatSettings\(silent = false\)[\s\S]*await fetchProvidersByProject\(projectId\);[\s\S]*if \(!silent\)/,
  "model/settings auto-save must not fully reload project providers after every model switch",
);

assert.doesNotMatch(
  projectChat,
  /if \(isLocalRunnerSurface\.value && hasNativeDesktopBridge\(\)\)/,
  "local-runner chat must not silently fall back to backend WebSocket when Tauri is unavailable",
);

assert.doesNotMatch(
  projectChat,
  /<aside v-if="isLocalRunnerSurface" class="local-runner-panel">/,
  "main chat surface must not render local runner diagnostics beside the conversation",
);

assert.match(
  projectChat,
  /activeSettingsPanel === 'local-runner'[\s\S]*class="settings-local-runner-body"/,
  "local runner diagnostics must live in the settings center local-runner panel",
);

assert.match(
  projectChat,
  /class="settings-local-runner-body"[\s\S]*settings-parameter-section--local-runner-workspace[\s\S]*项目工作区[\s\S]*promptProjectWorkspaceDirectory[\s\S]*saveProjectWorkspaceDirectory\(\)/,
  "local-runner settings must expose a real project workspace picker and save action",
);

assert.match(
  projectChat,
  /hasSelectedProject &&\s*\(\s*showLocalRuntimeSettings \|\| isLocalRunnerSurface\s*\)/,
  "local runner mode must expose project workspace selection in chat settings",
);

assert.match(
  readFileSync(resolve(rootDir, "src/modules/project-chat/constants/settingsCenterConfig.js"), "utf8"),
  /id: "local-runner"[\s\S]*label: "本地运行"/,
  "settings center must expose a local runner panel",
);

assert.match(
  projectChatResponsiveCss,
  /\.chat-layout \{[\s\S]*height: 100dvh;[\s\S]*overflow: hidden;/,
  "chat layout must stay constrained to the viewport so parents cannot cover the conversation",
);

assert.match(
  projectChatResponsiveCss,
  /\.chat-layout \.chat-messages \{[\s\S]*flex: 1 1 auto;[\s\S]*min-height: 0;[\s\S]*overflow-y: auto;/,
  "chat messages must be the scrolling region inside the constrained layout",
);

console.log("local liuAgent chat checks passed");
