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
const processTools = readFileSync(
  resolve(rootDir, "src-tauri/src/liuagent_core/tools/process.rs"),
  "utf8",
);
const gateway = readFileSync(
  resolve(rootDir, "src-tauri/src/liuagent_core/gateway.rs"),
  "utf8",
);
const bridge = readFileSync(resolve(rootDir, "src/utils/native-desktop-bridge.js"), "utf8");
const projectChat = readFileSync(resolve(rootDir, "src/views/projects/ProjectChat.vue"), "utf8");
const messageMappers = readFileSync(
  resolve(rootDir, "src/modules/project-chat/mappers/messageMappers.js"),
  "utf8",
);
const projectChatResponsiveCss = readFileSync(
  resolve(rootDir, "src/modules/project-chat/styles/project-chat-style-15.css"),
  "utf8",
);
const settingsCenterConfig = readFileSync(
  resolve(rootDir, "src/modules/project-chat/constants/settingsCenterConfig.js"),
  "utf8",
);
const style06 = readFileSync(
  resolve(rootDir, "src/modules/project-chat/styles/project-chat-style-06.css"),
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
  /async fn liuagent_classify_permission_reply\([\s\S]*classify_local_permission_reply\(request\)/,
  "Tauri must expose the model-backed Runtime permission reply classifier",
);

assert.match(
  tauriMain,
  /liuagent_start_local_chat,[\s\S]*liuagent_classify_permission_reply,/,
  "the permission reply classifier must be registered in the Tauri invoke handler",
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
  /"original_request"[\s\S]*"intent_analysis"[\s\S]*"related_context"[\s\S]*"contextual_plan"[\s\S]*"model_input_snapshots"[\s\S]*"actions_taken"[\s\S]*"current_state_delta"[\s\S]*"current_state"/,
  "local chat requirement records must include the two-loop requirement schema fields",
);

assert.match(
  runtime,
  /model_input_snapshots\.push\(build_task_processing_snapshot\([\s\S]*model_runner\(&request\)/,
  "local chat must capture task-processing model input snapshots before each model request",
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
  /emit_tool_call_started_event\([\s\S]*?let result = if tool\.name\.trim\(\) == "run_command" \{[\s\S]*?execute_tool_with_command_output_sink\(tool_request, Some\(&command_stream_sink\)\)[\s\S]*?\} else \{[\s\S]*?tool_runner\(tool_request\)/,
  "Agent Loop must emit a tool_call_started event before executing a local tool",
);

assert.match(
  runtime,
  /"tool_index": tool_index,[\s\S]*"tool_count": tool_count,[\s\S]*"arguments_preview": arguments_preview/,
  "tool_call_started events must include index, total count, and argument preview for step-by-step UI",
);

assert.match(
  projectChat,
  /function shouldHideProcessLogEntry\(row, entry\)[\s\S]*?eventType === "model_call_started"\) return true;[\s\S]*?eventType === "model_step"[\s\S]*?return payload\?\.ok !== false;/,
  "ProjectChat must retain model lifecycle events in state but hide successful internal steps from users",
);

assert.doesNotMatch(
  projectChat,
  /正在整理结果并判断是否完成|正在理解目标并制定下一步|已完成根据工具结果规划下一步|将继续执行必要的检查、修改或验证/,
  "ProjectChat must not generate fixed model-stage progress templates for users",
);

assert.match(
  projectChat,
  /type === "tool_call_started"[\s\S]*?localLiuAgentToolTraceSubject\(payload\)[\s\S]*?toolIndex[\s\S]*?toolCount[\s\S]*?argumentsPreview/,
  "ProjectChat must render tool_call_started as a Codex-style running detail with index and argument preview",
);

assert.match(
  projectChat,
  /function localLiuAgentToolResultLabel[\s\S]*?read_file[\s\S]*?Read file[\s\S]*?apply_patch[\s\S]*?Apply patch/,
  "ProjectChat must translate local tool names into user-facing Codex-style result labels",
);

assert.match(
  projectChat,
  /type === "command_output_chunk"[\s\S]*?Output \(\$\{stream\}\)/,
  "ProjectChat must render streamed command output as explicit stdout/stderr chunks",
);

assert.match(
  projectChat,
  /function messageProcessEntryKind\(entry = \{\}\)[\s\S]*?inferMessageProcessEntryKind\(entry\)/,
  "message-process-stream must use a typed renderer instead of plain text-only entries",
);

assert.match(
  projectChat,
  /function messageProcessDisplayEntries\(row\)[\s\S]*?messageProcessEntrySpanKey\(entry\)[\s\S]*?mergeMessageProcessSpanEntry\(group, entry\)/,
  "message-process-stream must group entries with the same tool_call_id into render spans",
);

assert.match(
  projectChat,
  /v-for="entry in messageProcessDisplayEntries\([\s\S]*?messageProcessEntryChildRows\(entry\)/,
  "message-process-stream must render grouped span child rows for tool started/result/output details",
);

assert.match(
  projectChat,
  /function messageProcessEntryDiffLines\(entry = \{\}\)[\s\S]*?tone = "hunk"[\s\S]*?tone = "add"[\s\S]*?tone = "remove"/,
  "typed process entries must classify diff lines for add/remove/hunk styling",
);

assert.match(
  projectChat,
  /function clipFileReadProcessText\(value = ""\)[\s\S]*?lines\.slice\(0, 80\)[\s\S]*?lines\.slice\(-40\)[\s\S]*?已省略/,
  "long read_file snippets must preserve both the beginning and the tail so later JS/content is not hidden",
);

assert.match(
  projectChat,
  /function shouldUpsertLocalLiuAgentRuntimeOperation\(event = \{\}, operation = null\)[\s\S]*?type === "approval_required"[\s\S]*?shouldShowMessageOperationCard\(operation\)/,
  "local liuAgent runtime events must only create message operations for real user interactions",
);

assert.match(
  projectChat,
  /function localLiuAgentRuntimeEventProcessLogEntry\(event = \{\}, operation = null\)[\s\S]*?kind: localLiuAgentRuntimeEventProcessKind\(event\)[\s\S]*?payload: \{/,
  "local liuAgent runtime events must preserve structured payloads in processLog entries",
);

assert.match(
  projectChat,
  /function applyLocalLiuAgentReasoningContent\(row, event = \{\}\)[\s\S]*?event\?\.type[\s\S]*?model_step[\s\S]*?payload\?\.reasoning_content[\s\S]*?row\.reasoningContent = reasoningContent/,
  "local liuAgent model_step events must persist reasoningContent onto assistant rows for follow-up history",
);

assert.match(
  projectChat,
  /function applyLiuAgentPlanEvent\(row, eventData = \{\}, requestId = ""\)[\s\S]*?if \(phase !== "running"\) \{[\s\S]*?activeComposerPlan\.value = null;[\s\S]*?activeComposerPlanOwnerId\.value = "";[\s\S]*?return true;/,
  "terminal execution plans must release the composer plan instead of leaving completed steps active",
);

assert.match(
  projectChat,
  /result\?\.assistantReasoningContent \|\| result\?\.assistant_reasoning_content[\s\S]*?assistantMessage\.reasoningContent = assistantReasoningContent/,
  "local liuAgent final result must persist assistant reasoningContent even when live events are missed",
);

assert.match(
  messageMappers,
  /reasoningContent: String\([\s\S]*?item\?\.reasoningContent \|\| item\?\.reasoning_content/,
  "project chat history rows must include reasoningContent when building follow-up history",
);

assert.match(
  projectChat,
  /class="message-process-entry__diff-line"[\s\S]*?:class="`is-\$\{line\.tone\}`"/,
  "message-process-stream must render typed diff lines with semantic classes",
);

assert.match(
  style06,
  /\.message-process-entry__diff-line\.is-add[\s\S]*?\.message-process-entry__diff-line\.is-remove[\s\S]*?\.message-process-entry__diff-line\.is-hunk/,
  "typed process diff styles must include add/remove/hunk classes",
);

assert.match(
  style06,
  /\.message-process-entry__children[\s\S]*?\.message-process-entry__child[\s\S]*?\.message-process-entry__child-summary/,
  "typed process span styles must include compact child rows",
);

assert.match(
  projectChat,
  /messageProcessLogEntries\(row\)\.slice\(-8\)[\s\S]*?return items\.slice\(-12\)/,
  "live progress must keep enough recent execution details visible for drift detection",
);

assert.doesNotMatch(
  projectChat,
  /本轮运行轨迹/,
  "message process must not render the legacy live-progress timeline alongside the Codex-style process stream",
);

assert.match(
  projectChat,
  /function shouldShowMessageOperationCard\(operation\)[\s\S]*?hasVisibleOperationInteractionForm\(operation\)[\s\S]*?operationActionButtons\(operation\)\.length > 0[\s\S]*?function isVisibleProcessOperation\(operation\)[\s\S]*?!shouldShowMessageOperationCard\(operation\)/,
  "message operations must be reserved for actionable cards instead of duplicating process-stream display details",
);

assert.match(
  projectChat,
  /currentLocalLiuAgentPermissionPrompt[\s\S]*class="chat-approval-banner chat-approval-banner--local-agent"[\s\S]*submitCurrentLocalLiuAgentPermissionAction\('local_liuagent_allow_once'\)/,
  "local liuAgent authorization must render as a single queued banner above the composer",
);

assert.match(
  projectChat,
  /const localLiuAgentPendingPermissionVersion = ref\(0\)[\s\S]*function setLocalLiuAgentPendingPermission\(requestId, pending = \{\}\)[\s\S]*localLiuAgentPendingPermissionVersion\.value \+= 1[\s\S]*function deleteLocalLiuAgentPendingPermission\(requestId\)[\s\S]*localLiuAgentPendingPermissionVersion\.value \+= 1/,
  "local liuAgent pending permission queue must be reactive when items are added or removed",
);

assert.match(
  projectChat,
  /function isChatSessionBusy\(chatSessionId = currentChatSessionId\.value\)[\s\S]*hasPendingRequestForChatSession\(normalizedSessionId\)[\s\S]*Boolean\(localLiuAgentActiveRunForChatSession\(normalizedSessionId\)\)[\s\S]*const canSend = computed\(\(\) => \{[\s\S]*currentChatSessionLocalLiuAgentWaitingPermission\.value[\s\S]*return false[\s\S]*const isComposerDisabled = computed\(\(\) => \{[\s\S]*currentChatSessionLocalLiuAgentWaitingPermission\.value[\s\S]*return true/,
  "composer must be unsendable while a local liuAgent authorization is queued without treating the queue as global chat loading",
);

assert.doesNotMatch(
  projectChat,
  /已恢复上次本机工具授权请求，请在输入框上方继续处理。|需要你确认本机工具授权后继续执行。|还需要你确认下一项本机操作后继续执行。/,
  "local liuAgent authorization wait states must not be rendered as assistant result text before execution completes",
);

assert.match(
  projectChat,
  /const nextPermissionRequest = localLiuAgentPermissionRequestFromChatResult\(result\)[\s\S]*setLocalLiuAgentPendingPermission\(nextRequestId,[\s\S]*本机工具执行再次暂停，等待你在输入框上方处理下一项授权/,
  "authorized local liuAgent continuations that hit another permission must enqueue the next prompt instead of ending the run",
);

assert.match(
  projectChat,
  /function shouldUpsertLocalLiuAgentRuntimeOperation\(event = \{\}, operation = null\)[\s\S]*type === "approval_required"\) return false/,
  "local liuAgent approval_required events must not create duplicate message operation cards",
);

assert.match(
  projectChat,
  /String\(event\?\.type \|\| ""\)\.trim\(\) === "tool_result"[\s\S]*permission\.required[\s\S]*continue;/,
  "permission.required tool_result payloads must not be rendered as raw process JSON",
);

const operationCardVisibilityBlock = projectChat.slice(
  projectChat.indexOf("function shouldShowMessageOperationCard(operation)"),
  projectChat.indexOf("function isVisibleProcessOperation(operation)"),
);
assert.doesNotMatch(
  operationCardVisibilityBlock,
  /messageOperationInteractionFormJson\(operation\)/,
  "operation-card visibility filtering must not initialize interaction form models",
);
assert.doesNotMatch(
  operationCardVisibilityBlock,
  /operationPlanSteps\(operation\)|kind === "terminal"|local_liuagent_operation/,
  "operation-card visibility must not show pure plan, terminal, or local runtime display records",
);
assert.match(
  projectChat,
  /function messageProcessOperations\(row\)[\s\S]*?!isMessageFooterActionOperation\(row, item\)/,
  "operations already rendered as footer actions must not be duplicated in the message operations area",
);

assert.match(
  projectChat,
  /function handleNativeLiuAgentRuntimeEvent\(event = \{\}\) \{[\s\S]*?scrollToBottom\(\{ force: false \}\);[\s\S]*?\}/,
  "runtime progress events must only auto-scroll when the message viewport is already sticky to the bottom",
);

assert.doesNotMatch(
  settingsCenterConfig,
  /id:\s*"local-runner"|label:\s*"本地运行"|授权记录/,
  "chat settings sidebar must not expose the unused local runner menu",
);

assert.match(
  projectChat,
  /v-if="settingsInternalItems\.length > 1"[\s\S]*?菜单导览/,
  "settings guide button should be hidden when there is no left menu to guide",
);

assert.match(
  projectChat,
  /function syncSettingsRouteState\(\)[\s\S]*?activeSettingsPanel\.value = "chat"/,
  "settings route state must collapse removed panels back to chat settings",
);

assert.match(
  projectChat,
  /v-if="hasSelectedProject"[\s\S]*?class="settings-module-row settings-module-row--stacked"[\s\S]*?AI 入口文件/,
  "AI entry file setting must stay visible in chat settings for selected projects",
);

assert.match(
  projectChat,
  /if \(workspacePath !== savedWorkspacePath\) \{[\s\S]*?saveProjectWorkspaceDirectory\(workspacePath,\s*\{[\s\S]*?silent: true,[\s\S]*?rethrow: true,/,
  "Creating AIENTRY.md must persist a draft workspace path before using the backend workspace file API",
);

assert.match(
  projectChat,
  /const executionWorkspacePath = computed\(\(\) =>[\s\S]*projectWorkspaceDraftNormalized\.value \|\|[\s\S]*projectWorkspaceResolved\.value \|\|[\s\S]*legacyConnectorWorkspacePath\.value/,
  "local-runner execution workspace must prefer the project workspace over stale connector/external agent paths",
);

assert.match(
  projectChat,
  /workspacePathDraft\.value = String\([\s\S]*projectWorkspacePath\.value \|\|[\s\S]*settings\.connector_workspace_path/,
  "project settings hydration must seed the local workspace draft from the project workspace before legacy connector settings",
);

assert.match(
  projectChat,
  /async function saveProjectWorkspaceDirectory[\s\S]*workspacePathDraft\.value = persisted;[\s\S]*connector_workspace_path: persisted,[\s\S]*workspace_path: persisted,/,
  "saving the project workspace must refresh local runner workspace state immediately",
);

assert.match(
  projectChat,
  /function localLiuAgentWorkspacePath\(\) \{\s*return executionWorkspacePath\.value;\s*\}/,
  "local liuAgent chat requests must use the canonical execution workspace",
);

assert.match(
  bridge,
  /export async function prepareNativeLiuAgentInvocation/,
  "frontend bridge must export prepareNativeLiuAgentInvocation",
);

assert.match(
  projectChat,
  /await sendLocalLiuAgentChatRequest\(\{/,
  "desktop local chat sends must use the local liuAgent runtime path",
);

assert.doesNotMatch(
  projectChat,
  /shouldPrepareRemoteAttachmentPayload/,
  "desktop local chat must not keep the old remote attachment preprocessing switch",
);

assert.match(
  projectChat,
  /function shouldAttemptProviderFileUpload\(\) \{[\s\S]*selectedProviderId\.value \|\| defaultProviderId\.value/,
  "provider-file upload attempts must be based on the selected provider instead of the llm_model_types attachment_mode",
);

assert.doesNotMatch(
  projectChat,
  /uploadFileToProviderWithBackendProxy|\/llm\/providers\/\$\{encodeURIComponent\(providerId\)\}\/upload-file/,
  "desktop local provider-file upload must not call the backend upload proxy",
);

assert.match(
  projectChat,
  /async function uploadFileToProviderWithNativeRuntime[\s\S]*uploadNativeLiuAgentProviderFile/,
  "local-runner provider-file uploads must use the native desktop bridge",
);

assert.match(
  projectChat,
  /nativeDesktopBridgeAvailable\.value = hasNativeDesktopBridge\(\);[\s\S]*if \(!nativeDesktopBridgeAvailable\.value\) \{[\s\S]*throw new Error\("桌面端原生桥未接入，无法上传给模型供应商"\);[\s\S]*await uploadFileToProviderWithNativeRuntime/,
  "provider-file upload must require the native desktop bridge instead of falling back to backend upload",
);

assert.match(
  projectChat,
  /const localLiuAgentAttachments =\s*await buildLocalLiuAgentAttachments\(uploadFiles\.value\);/s,
  "desktop local chat must build structured attachments for the liuAgent path",
);

assert.doesNotMatch(
  projectChat,
  /const base64Images = \[\];/,
  "desktop local chat must not keep a dead remote image payload variable",
);

assert.doesNotMatch(
  projectChat,
  /if \(shouldPrepareRemoteAttachmentPayload && docFiles\.length > 0\)/,
  "desktop local chat must not keep remote document preprocessing",
);

assert.match(
  projectChat,
  /routingMode: "provider_file"[\s\S]*extractionStatus: "provider_file_ready"[\s\S]*providerFileId/,
  "local-runner attachment routing must preserve provider_file attachments after native upload",
);

assert.match(
  projectChat,
  /const hasUploadingAttachments = computed[\s\S]*"uploading"[\s\S]*"error"[\s\S]*if \(hasUploadingAttachments\.value\) \{[\s\S]*return false/,
  "composer must block sends while provider-file uploads are pending or failed",
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
  /isLocalRunnerSurface|isDesktopLocalSession/,
  "desktop local chat must not keep the old local/web surface switch",
);

assert.match(
  projectChat,
  /const showAgentWorkflowStatusStrip = computed\(\s*\(\) => false,\s*\);/,
  "desktop local composer must not show global agent workflow failures above the input",
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
  /deleteLocalLiuAgentPendingPermission\(requestId\);\s*removeLocalLiuAgentPermissionOperation\(row, requestId\);/,
  "ProjectChat must remove the queued local liuAgent permission immediately after a permission decision",
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
  /const showWorkingStatusBar = computed\(\(\) => \{[\s\S]*if \(isLocalRunnerSurface|isDesktopLocalSession\)/,
  "local-runner mode must not be excluded from the working status bar",
);

assert.match(
  projectChat,
  /status: ok \? "done" : "blocked"[\s\S]*await syncLocalLiuAgentRuntimeOutbox\(/,
  "ProjectChat must sync local runtime outbox after local chat completes or fails",
);

assert.match(
  projectChat,
  /deleteLocalLiuAgentActiveRun\(activeChatSessionId\);\s*syncChatLoadingWithCurrentSession\(\);\s*scrollToBottom\(\);\s*void \(async \(\) => \{[\s\S]*persistLocalLiuAgentFinalMessages/,
  "local liuAgent must reveal the final answer before background persistence finishes",
);

assert.match(
  projectChat,
  /function applyLocalLiuAgentConversationLifecycle\([\s\S]*hasRuntimeEntries[\s\S]*if \(hasRuntimeEntries\) return false;/,
  "conversation lifecycle fallback must not replace the live runtime process log",
);

assert.doesNotMatch(
  projectChat,
  /if \(!ok\) \{\s*throw new Error\(String\(result\?\.error \|\| "桌面端本地对话失败"\)\);\s*\}/,
  "local-runner ok=false results must stay inside the assistant bubble instead of entering the global request failure path",
);

assert.match(
  projectChat,
  /assistantMessage\.content = `执行失败：\$\{errorMessage\}`;[\s\S]*source: "desktop_local_agent"/,
  "desktop local thrown errors must be rendered in the assistant bubble and recorded as desktop local events",
);

assert.doesNotMatch(
  projectChat,
  /ElMessage\.error\(errorMessage \|\| "对话失败"\)/,
  "desktop local chat must not use the old web-chat global error toast path",
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
  /if \((isLocalRunnerSurface|isDesktopLocalSession)\.value && hasNativeDesktopBridge\(\)\)/,
  "local-runner chat must not silently fall back to backend WebSocket when Tauri is unavailable",
);

assert.doesNotMatch(
  projectChat,
  /<aside v-if="(isLocalRunnerSurface|isDesktopLocalSession)" class="local-runner-panel">/,
  "main chat surface must not render local runner diagnostics beside the conversation",
);

assert.doesNotMatch(
  settingsCenterConfig,
  /id: "local-runner"[\s\S]*label: "本地运行"/,
  "settings center must not expose the local runner panel in the chat settings sidebar",
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

assert.match(
  processTools,
  /"kill" => \{[\s\S]*require_approval\([\s\S]*"command\.process\.kill"[\s\S]*process_kill\(&session\)/,
  "process kill must freeze the exact tool call behind the Runtime permission gate",
);

assert.match(
  runtime,
  /禁止模型先用自然语言询问‘是否确认’[\s\S]*只恢复原 tool_call_id、工具名和完整参数/,
  "the model prompt must delegate confirmations to the Runtime instead of conversational re-confirmation",
);

assert.doesNotMatch(
  projectChat,
  /function localLiuAgentPermissionReplyAction|normalizeLocalLiuAgentPermissionReply|确认关闭[\s\S]*local_liuagent_allow_once/,
  "permission intent must not be classified by a frontend phrase list or regular expression",
);

assert.match(
  runtime,
  /pub fn classify_local_permission_reply\([\s\S]*你是桌面 Runtime 的授权意图分类器[\s\S]*"approve" => "approve_once"[\s\S]*"deny" => "deny"/,
  "the configured model must classify approval intent against the frozen Runtime action",
);

assert.match(
  bridge,
  /classifyNativeLiuAgentPermissionReply[\s\S]*liuagentClassifyPermissionReply/,
  "the desktop bridge must expose the Runtime permission intent classifier",
);

assert.match(
  projectChat,
  /currentChatSessionLocalLiuAgentWaitingPermission\.value[\s\S]*submitCurrentLocalLiuAgentPermissionReplyIfNeeded\(draftText\.value\)/,
  "pending permission replies must be consumed before creating a new model request",
);

console.log("local liuAgent chat checks passed");
