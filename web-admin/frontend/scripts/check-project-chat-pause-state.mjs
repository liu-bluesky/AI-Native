import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { dirname, resolve } from "node:path";

const scriptDir = dirname(fileURLToPath(import.meta.url));
const componentPath = resolve(
  scriptDir,
  "../src/views/projects/ProjectChat.vue",
);
const pendingRequestsComposablePath = resolve(
  scriptDir,
  "../src/modules/project-chat/composables/useProjectChatPendingRequests.js",
);
const terminalComposablePath = resolve(
  scriptDir,
  "../src/modules/project-chat/composables/useProjectChatTerminal.js",
);
const composerComponentPath = resolve(
  scriptDir,
  "../src/modules/project-chat/components/composer/ChatComposer.vue",
);
const tauriMainPath = resolve(scriptDir, "../src-tauri/src/main.rs");
const apiProjectsPath = resolve(scriptDir, "../../api/routers/projects.py");
const source = readFileSync(componentPath, "utf8");
const restoreLocalLiuAgentRuntimeStateSource =
  source.match(
    /async function restoreLocalLiuAgentRuntimeState[\s\S]*?\n}\n\nfunction hasLiveTerminalOperation/,
  )?.[0] || "";
const applyLocalLiuAgentModelStepFailureSource =
  source.match(
    /function applyLocalLiuAgentModelStepFailure[\s\S]*?\n}\n\nfunction shouldUpsertLocalLiuAgentRuntimeOperation/,
  )?.[0] || "";
const pendingRequestsSource = readFileSync(pendingRequestsComposablePath, "utf8");
const terminalSource = readFileSync(terminalComposablePath, "utf8");
const composerSource = readFileSync(composerComponentPath, "utf8");
const tauriSource = readFileSync(tauriMainPath, "utf8");
const apiProjectsSource = readFileSync(apiProjectsPath, "utf8");

assert.match(
  source,
  /function stopGeneration\(\)[\s\S]*?cancelActiveLocalLiuAgentRun\(\)[\s\S]*?const currentRequestId = getActiveRequestId\(\);[\s\S]*?if \(currentChatSessionNativeExternalAgentRunning\.value\)/,
  "stopGeneration must cancel local liuAgent first, then active pending request before Runner fallback",
);

assert.match(
  source,
  /const activeRun = \{[\s\S]*?userMessageId: userMessage\.id,[\s\S]*?rootGoal: displayUserMessageContent \|\| finalUserPrompt,[\s\S]*?workspacePath,/,
  "local liuAgent active runs must retain the original task goal for cancellation",
);

assert.match(
  source,
  /async function cancelActiveLocalLiuAgentRun\(\)[\s\S]*?await pauseNativeLiuAgentLocalChat\(\{[\s\S]*?projectId:[\s\S]*?chatSessionId,[\s\S]*?workspacePath:[\s\S]*?reason: "manual_pause"[\s\S]*?pauseOpenMessageOperations\(row\);[\s\S]*?summary: "任务已暂停，可以继续执行"[\s\S]*?phase: "blocked"[\s\S]*?local_liuagent_recoverable: "true"[\s\S]*?local_liuagent_resuming: "false"/,
  "pausing a local task must synchronously checkpoint and expose recovery without a safe-boundary wait",
);

assert.doesNotMatch(
  source,
  /async function cancelActiveLocalLiuAgentRun\(\)[\s\S]*?clearLocalLiuAgentPendingPermissionsForChatSession/,
  "pausing must preserve pending permission state instead of converting it into another business action",
);

assert.match(
  source,
  /async function pauseLocalLiuAgentPendingPermissionsForChatSession[\s\S]*?pauseNativeLiuAgentLocalChat\(\{[\s\S]*?reason: "manual_pause"[\s\S]*?pauseOpenMessageOperations\(row\)[\s\S]*?preserveVisibleContent: true/,
  "pausing while waiting for permission must preserve the authorization node without executing another decision",
);

assert.doesNotMatch(
  source,
  /async function cancelActiveLocalLiuAgentRun\(\)[\s\S]*?row\.content\s*=/,
  "pausing a local task must not overwrite assistant content or execution details",
);

assert.match(
  source,
  /function pauseOpenMessageOperations\(row\)[\s\S]*?phase: "blocked"[\s\S]*?paused: true/,
  "open execution operations must be preserved and marked paused",
);

assert.match(
  source,
  /function cancelActiveLocalLiuAgentRun\(\)[\s\S]*?status: "paused",[\s\S]*?rootGoal:[\s\S]*?String\(run\.rootGoal \|\| ""\)\.trim\(\)/,
  "pausing a local task must preserve its original goal and write paused status",
);

assert.doesNotMatch(
  source,
  /function cancelActiveLocalLiuAgentRun\(\)[\s\S]*?status: "blocked",[\s\S]*?rootGoal: message,/,
  "pausing a local task must not overwrite its goal with the stop message",
);

assert.match(
  source,
  /function cancelActiveLocalLiuAgentRun\(\)[\s\S]*?queuedFollowupMessages\.value = \[\];[\s\S]*?activeFollowupAssistantMessageId = "";/,
  "pausing a local task must detach queued followups from the paused card",
);

assert.match(
  source,
  /if \(activeRun\.cancelled\) \{[\s\S]*?summary: "任务已暂停，可以继续执行"[\s\S]*?phase: "blocked"[\s\S]*?local_liuagent_recoverable: "true"[\s\S]*?local_liuagent_resuming: "false"/,
  "the local task card must remain recoverable when the paused worker returns",
);

assert.match(
  source,
  /if \(runtimePauseCode === "runtime\.paused"\) \{[\s\S]*?checkpoint_ready: true,[\s\S]*?recoverable: true/,
  "manual pause must keep the explicit checkpoint recovery path",
);

assert.doesNotMatch(
  source,
  /\["runtime\.paused", "runtime\.interrupted"\]\.includes\(runtimePauseCode\)/,
  "runtime interruptions must not return through the manual pause branch",
);

assert.match(
  source,
  /key: "local_liuagent_resume"[\s\S]*?label: "继续执行"[\s\S]*?hasNativeDesktopBridge\(\)/,
  "continue execution must remain a desktop-only operation",
);

assert.match(
  source,
  /async function submitLocalLiuAgentResume\(operation, options = \{\}\)[\s\S]*?sendLocalLiuAgentChatRequest\(\{[\s\S]*?persistUserMessage: false,[\s\S]*?resumeFromCheckpoint: true,/,
  "checkpoint resume must explicitly enter the dedicated resume display mode",
);

assert.match(
  source,
  /const LOCAL_LIUAGENT_RECOVERY_PLACEHOLDERS = new Set\([\s\S]*?function isLocalLiuAgentRecoveryPlaceholderContent\(value\)[\s\S]*?function clearLocalLiuAgentRecoveryPlaceholderContent\(row\)[\s\S]*?row\.content = "";/,
  "recovery status copy must be recognized and cleared instead of treated as assistant content",
);

assert.match(
  source,
  /async function restoreLocalLiuAgentRuntimeState[\s\S]*?clearLocalLiuAgentRecoveryPlaceholderContent\(row\);/,
  "runtime restoration must clear placeholders persisted by older versions",
);

assert.doesNotMatch(
  restoreLocalLiuAgentRuntimeStateSource,
  /已恢复上次暂停的本地 liuAgent 会话，可以从 checkpoint 继续执行。/,
  "runtime restoration must not write recovery status into assistant content",
);

assert.match(
  source,
  /async function submitLocalLiuAgentResume\(operation, options = \{\}\)[\s\S]*?const previousVisibleContent = isLocalLiuAgentRecoveryPlaceholderContent\(row\.content\)[\s\S]*?clearLocalLiuAgentRecoveryPlaceholderContent\(row\);[\s\S]*?`上次有效结果：\$\{previousVisibleContent \|\| "无"\}`/,
  "checkpoint resume must exclude recovery placeholders from model context",
);

assert.match(
  source,
  /const continuationPrompt = \[[\s\S]*?这不是让你回复恢复状态说明[\s\S]*?必须继续调用必要工具并推进原始目标[\s\S]*?需要用户授权或输入[\s\S]*?无法自行解决的阻塞/,
  "checkpoint resume must require real tool execution instead of a recovery-status reply",
);

assert.match(
  source,
  /async function sendLocalLiuAgentChatRequest\([\s\S]*?if \(resumeFromCheckpoint\) \{[\s\S]*?clearLocalLiuAgentRecoveryPlaceholderContent\(assistantMessage\);[\s\S]*?upsertMessageOperation/,
  "the local runtime request must defensively clear stale recovery content before resuming",
);

assert.doesNotMatch(
  applyLocalLiuAgentModelStepFailureSource,
  /row\.content\s*=/,
  "a failed model step must remain runtime progress instead of becoming final assistant content",
);

assert.match(
  source,
  /function isLocalLiuAgentRecoverableModelStepFailure\(payload = \{\}\) \{[\s\S]*?payload\?\.ok === false &&[\s\S]*?payload\?\.status[\s\S]*?=== "failed";[\s\S]*?if \(!isLocalLiuAgentRecoverableModelStepFailure\(payload\)\) return false;[\s\S]*?模型步骤中断，正在准备从 checkpoint 恢复[\s\S]*?const phase = "running"/,
  "all failed model steps must use one checkpoint recovery standard",
);

assert.doesNotMatch(
  applyLocalLiuAgentModelStepFailureSource,
  /408|425|429|500|502|503|504|network disconnected|connection refused|connection reset/,
  "model-step recovery must not classify HTTP statuses or network error text",
);

assert.match(
  source,
  /const LOCAL_LIUAGENT_AUTO_RESUME_MAX_RETRIES = 3;[\s\S]*?function localLiuAgentAutoResumeDelayMs[\s\S]*?retry-after[\s\S]*?function scheduleLocalLiuAgentAutomaticResume/,
  "runtime interruptions must use bounded checkpoint auto-resume with retry-after support",
);

assert.match(
  source,
  /const shouldAutoResume =[\s\S]*?runtimeErrorCode === "runtime\.interrupted"[\s\S]*?autoResumeRetryNumber < LOCAL_LIUAGENT_AUTO_RESUME_MAX_RETRIES/,
  "only recoverable runtime interruptions within the retry budget may auto-resume",
);

assert.match(
  source,
  /if \(!assistantMessage\.content && !ok && !shouldAutoResume\) \{[\s\S]*?assistantMessage\.content = `执行失败：\$\{String\(result\?\.error/,
  "retry exhaustion must render a final visible failure answer",
);

assert.match(
  source,
  /if \(!ok && !shouldAutoResume\) \{[\s\S]*?showManualCloseErrorDialog/,
  "temporary interruptions must not open a terminal failure dialog before automatic recovery is exhausted",
);

assert.match(
  source,
  /shouldAutoResume[\s\S]*?连接暂时中断，[\s\S]*?秒后自动继续[\s\S]*?scheduleLocalLiuAgentAutomaticResume\(\{/,
  "the message operation must report scheduled recovery and actually invoke checkpoint resume",
);

assert.match(
  source,
  /status: ok \? "done" : shouldAutoResume \? "in_progress" : "blocked"/,
  "requirements and offline state must remain in progress while automatic recovery is pending",
);

assert.match(
  source,
  /if \(!resumeFromCheckpoint\) \{[\s\S]*?"本轮目标"[\s\S]*?桌面端本地智能体/,
  "checkpoint resume must not append the original task header again",
);

assert.match(
  source,
  /resumeFromCheckpoint[\s\S]*?"已恢复 checkpoint，正在继续当前任务"[\s\S]*?"继续执行\\n  - 已读取本地 checkpoint\\n  - 正在从暂停节点继续推理\\n  - 已有执行详情保持不变"/,
  "checkpoint resume must use recovery-specific progress instead of new-task startup copy",
);

assert.match(
  source,
  /function pickLocalLiuAgentRecoverableOperation\(row\)[\s\S]*?local_liuagent_recoverable[\s\S]*?operationActionButtons\(operation\)\.length > 0[\s\S]*?function messageFooterActionOperation\(row\)[\s\S]*?pickLocalLiuAgentRecoverableOperation\(row\)/,
  "desktop recovery must be promoted to the always-visible message footer action area",
);

assert.match(
  source,
  /if \(activeRun\.cancelled\) \{[\s\S]*?preserveVisibleContent: true,[\s\S]*?checkpoint_ready: true,[\s\S]*?recoverable: true/,
  "checkpoint completion must persist the preserved execution trace as recoverable",
);

assert.doesNotMatch(
  source,
  /function stopGeneration\(\)[\s\S]*?backgroundCurrentNativeExternalAgentSession\(\)/,
  "composer pause must kill the active task instead of backgrounding it",
);

assert.match(
  source,
  /function stopGeneration\(\)[\s\S]*?currentChatSessionNativeExternalAgentRunning\.value[\s\S]*?cancelActiveNativeExternalAgentSession\(\)/,
  "composer pause must cancel the current Runner session when no pending websocket request remains",
);

assert.match(
  source,
  /function cancelActiveNativeExternalAgentSession\(\)[\s\S]*?return cancelNativeExternalAgentSessionById\(sessionId\);/,
  "active Runner cancellation must report whether a Runner session was killed",
);

assert.match(
  source,
  /function sendCancelRequestNow\(requestId\)[\s\S]*?activeClient\.send\(\{ type: "cancel", request_id: normalizedRequestId \}\)[\s\S]*?return true;/,
  "websocket cancel must support synchronous dispatch before the stream is closed",
);

assert.match(
  source,
  /function sendCancelRequestInBackground\(requestId\)[\s\S]*?window\.setTimeout\([\s\S]*?sendCancelRequestNow\(normalizedRequestId\);/,
  "background websocket cancel must reuse the synchronous cancel sender",
);

assert.match(
  source,
  /function closeIdleChatWsAfterFastCancel\(\)[\s\S]*?pendingRequests\.size > 0[\s\S]*?wsClient\.value\.close\(1000, "generation cancelled"\);/,
  "fast pause must close the idle websocket stream after local cancellation",
);

assert.match(
  source,
  /if \(cancelPendingChatRequestFast\(currentRequestId, pending\)\) \{[\s\S]*?sendCancelRequestNow\(currentRequestId\);[\s\S]*?closeIdleChatWsAfterFastCancel\(\);/,
  "stopGeneration must finish local cancellation, notify the backend, then release the websocket stream",
);

assert.match(
  pendingRequestsSource,
  /activeRequestId !== normalizedRequestId &&\s*pendingRequests\.has\(activeRequestId\)/,
  "clearTrackedPendingRequest must not preserve stale activeGenerationRequestId values",
);

assert.match(
  source,
  /function resolvePendingRequestFast[\s\S]*?persistRememberedChatSessionMessages\(\s*pending\.projectId,\s*chatSessionId,\s*\);[\s\S]*?settlePending\(pending,\s*"resolve"/,
  "fast pause must persist the stopped runtime before the caller continues",
);

assert.doesNotMatch(
  source,
  /function resolvePendingRequestFast[\s\S]*?schedulePersistChatRuntime\(\);[\s\S]*?pending\.resolve/,
  "fast pause must not rely on delayed runtime persistence",
);

assert.match(
  source,
  /pendingState = \{[\s\S]*?cancelled: false,[\s\S]*?\};[\s\S]*?if \(pendingState\?\.cancelled\) \{[\s\S]*?cancelled: true/,
  "sendProjectChatRequest must return an explicit cancelled result",
);

assert.match(
  source,
  /requestCancelled = Boolean\(sendResult\?\.cancelled\);[\s\S]*?if \(requestCancelled\) return;[\s\S]*?if \(selectedProjectId\.value && !requestCancelled\)/,
  "doSend must skip success finalization and session refresh after local pause",
);

assert.match(
  source,
  /requestKind: "followup_replan",[\s\S]*?requestCancelled = Boolean\(sendResult\?\.cancelled\);[\s\S]*?if \(requestCancelled\) return;[\s\S]*?if \(selectedProjectId\.value && !requestCancelled\)/,
  "followup replan must skip session refresh after local pause",
);

assert.match(
  source,
  /const workingStatusStartedAtBySession = new Map\(\);/,
  "working status elapsed time must be stored per chat session",
);

assert.match(
  source,
  /function startWorkingStatusTimer\([\s\S]*?workingStatusRunKey\(chatSessionId[\s\S]*?workingStatusStartedAtBySession\.get\(key\)[\s\S]*?workingStatusStartedAtBySession\.set\(key, startedAt\)/,
  "working status timer must reuse a session-specific start time",
);

assert.match(
  source,
  /hasPendingRequestForChatSession\(currentChatSessionId\.value\)[\s\S]*?currentChatSessionNativeExternalAgentRunning\.value/,
  "visible running state must be scoped to the current chat session",
);

assert.match(
  terminalSource,
  /function clearExecutionTransportState\(assistantIndex = -1\)[\s\S]*?terminalPanelStatus\.value = "idle";[\s\S]*?terminalMirrorConnected\.value = false;[\s\S]*?hostTerminalSessionId\.value = "";[\s\S]*?terminalStructuredInteraction\.value = null;/,
  "terminal transport cleanup helper must clear terminal transport state",
);

assert.match(
  source,
  /function clearActiveExecutionTransportState\(assistantIndex = -1\)[\s\S]*?clearExecutionTransportState\(assistantIndex\);[\s\S]*?terminalStructuredInteractionRefreshPending = false;/,
  "pause paths must share a synchronous terminal transport cleanup helper",
);

assert.match(
  source,
  /function applyNativeExternalAgentFastKilledSession\(\s*sessionId = "",\s*chatSessionId = "",\s*\)[\s\S]*?nativeExternalAgentLaunchingChatSessionIds\.value[\s\S]*?nativeExternalAgentBackgroundedChatSessionIds\.value[\s\S]*?clearActiveExecutionTransportState\(rowIndex\);[\s\S]*?clearActiveNativeExternalAgentSessionBinding\(\s*normalizedSessionId,\s*normalizedChatSessionId,\s*\);[\s\S]*?syncChatLoadingWithCurrentSession\(\);/,
  "Runner fast pause must clear launch/background bindings and transport state before resync",
);

assert.match(
  source,
  /function cancelPendingChatRequestFast\(requestId, pending\)[\s\S]*?clearActiveExecutionTransportState\(pending\?\.assistantIndex \?\? -1\);[\s\S]*?resolvePendingRequestFast/,
  "normal fast pause must use the shared terminal transport cleanup helper",
);

assert.doesNotMatch(
  source,
  /class="(?:agent-workflow-status__stop|chat-working-status__stop)"[\s\S]*?>[\s\S]*?停止[\s\S]*?<\/el-button>/,
  "status strips must not expose a duplicate stop button",
);

assert.match(
  composerSource,
  /content="暂停当前回答"[\s\S]*?class="pause-generation-button"[\s\S]*?\$emit\('stop-generation'\)[\s\S]*?<span>暂停<\/span>/,
  "composer pause button must remain the single visible pause entry",
);

assert.match(
  source,
  /@stop-generation="stopGeneration"/,
  "ProjectChat must bind the composer pause event to stopGeneration",
);

assert.doesNotMatch(
  source,
  /isChatHistoryTruncateNotFound|chat\/history.*truncate/,
  "message delete must not retain a server-history compatibility branch",
);

assert.match(
  source,
  /async function deleteMessageAt\(messageIndex\)[\s\S]*?applyDeleteTargetLocally\(target\);[\s\S]*?rememberCurrentChatSessionMessages\(\);[\s\S]*?persistCurrentChatRuntimeNow\(projectId, chatSessionId\);[\s\S]*?ElMessage\.success\(buildDeleteSuccessText\(item\)\);/,
  "message delete must update the desktop-local runtime directly",
);

if (/fn cancel_external_agent_session\(/.test(tauriSource)) {
  assert.match(
    tauriSource,
    /child_process_id: Option<u32>/,
    "Runner state must record the native child pid for cancellation without waiting on the child mutex",
  );

  assert.match(
    tauriSource,
    /fn signal_external_agent_process_tree\(child_process_id: Option<u32>\)[\s\S]*?libc::kill\(pgid, libc::SIGTERM\)[\s\S]*?libc::kill\(pgid, libc::SIGKILL\)/,
    "Runner cancellation must signal the process group instead of only the parent process",
  );

  assert.match(
    tauriSource,
    /fn cancel_external_agent_session\([\s\S]*?signal_external_agent_process_tree\(child_process_id\);[\s\S]*?child\.try_lock\(\)[\s\S]*?process_child\.try_lock\(\)/,
    "Runner cancellation must not block on waiter-held child mutexes",
  );

  assert.doesNotMatch(
    tauriSource,
    /fn cancel_external_agent_session\([\s\S]*?child\.lock\(\)[\s\S]*?fn hard_kill_external_agent_session/,
    "Runner cancellation must not use blocking child.lock() before hard kill",
  );

  assert.match(
    tauriSource,
    /fn spawn_external_agent_log_reader[\s\S]*?is_external_agent_terminal_status\(&state\.status\)[\s\S]*?continue;/,
    "Runner log reader must ignore late output after a session is already terminal",
  );
}

assert.match(
  apiProjectsSource,
  /if str\(payload\.get\("type"\)[\s\S]*?== "cancel":[\s\S]*?cancel_events\[request_id\]\.set\(\)[\s\S]*?task = active_tasks\.get\(request_id\)[\s\S]*?task\.cancel\(\)/,
  "backend websocket cancel handling must cancel the active task, not only set the cooperative event",
);

function createHarness() {
  const pendingRequests = new Map();
  const state = {
    activeGenerationRequestId: "",
    currentChatSessionId: "chat-1",
    chatLoading: true,
    persisted: [],
    now: 1000,
    workingStatusStartedAt: 0,
  };
  const workingStatusStartedAtBySession = new Map();

  function getActiveRequestId() {
    const currentSessionId = String(state.currentChatSessionId || "").trim();
    if (currentSessionId) {
      const currentEntries = Array.from(pendingRequests.entries()).filter(
        ([, pending]) =>
          String(pending?.chatSessionId || "").trim() === currentSessionId,
      );
      if (currentEntries.length > 0) {
        return currentEntries[currentEntries.length - 1][0];
      }
    }
    const activeRequestId = String(state.activeGenerationRequestId || "").trim();
    if (
      activeRequestId &&
      pendingRequests.has(activeRequestId) &&
      !currentSessionId
    ) {
      return activeRequestId;
    }
    if (currentSessionId) return null;
    const entries = Array.from(pendingRequests.entries());
    if (entries.length > 0) {
      return entries[entries.length - 1][0];
    }
    return null;
  }

  function clearTrackedPendingRequest(requestId) {
    const normalizedRequestId = String(requestId || "").trim();
    const activeRequestId = String(state.activeGenerationRequestId || "").trim();
    if (
      normalizedRequestId &&
      activeRequestId &&
      activeRequestId !== normalizedRequestId &&
      pendingRequests.has(activeRequestId)
    ) {
      return;
    }
    state.activeGenerationRequestId = getActiveRequestId() || "";
  }

  function cancelRequest(requestId) {
    pendingRequests.delete(requestId);
    clearTrackedPendingRequest(requestId);
  }

  function isChatSessionBusy(chatSessionId = state.currentChatSessionId) {
    const normalizedSessionId = String(chatSessionId || "").trim();
    if (!normalizedSessionId) return false;
    return Array.from(pendingRequests.values()).some(
      (pending) => String(pending?.chatSessionId || "").trim() === normalizedSessionId,
    );
  }

  function syncChatLoadingWithCurrentSession() {
    state.chatLoading = isChatSessionBusy();
  }

  function persistRememberedChatSessionMessages(projectId, chatSessionId) {
    state.persisted.push({ projectId, chatSessionId, chatLoading: state.chatLoading });
  }

  function workingStatusSessionKey(chatSessionId = state.currentChatSessionId) {
    return String(chatSessionId || "").trim() || "__current__";
  }

  function startWorkingStatusTimer() {
    const key = workingStatusSessionKey();
    let startedAt = Number(workingStatusStartedAtBySession.get(key) || 0);
    if (!startedAt) {
      startedAt = state.now;
      workingStatusStartedAtBySession.set(key, startedAt);
    }
    state.workingStatusStartedAt = startedAt;
  }

  function stopWorkingStatusTimer() {
    state.workingStatusStartedAt = 0;
  }

  function resolvePendingRequestFast(requestId, pending, content = "") {
    pendingRequests.delete(requestId);
    clearTrackedPendingRequest(requestId);
    syncChatLoadingWithCurrentSession();
    persistRememberedChatSessionMessages(pending.projectId, pending.chatSessionId);
    pending.resolve(String(content || "").trim());
  }

  function cancelPendingChatRequestFast(requestId, pending) {
    pending.cancelled = true;
    resolvePendingRequestFast(requestId, pending, "已停止生成。");
  }

  return {
    pendingRequests,
    state,
    clearTrackedPendingRequest,
    cancelRequest,
    cancelPendingChatRequestFast,
    startWorkingStatusTimer,
    stopWorkingStatusTimer,
    workingStatusStartedAtBySession,
  };
}

{
  const harness = createHarness();
  harness.pendingRequests.set("request-current", { chatSessionId: "chat-1" });
  harness.state.activeGenerationRequestId = "request-stale";
  harness.cancelRequest("request-current");
  assert.equal(
    harness.state.activeGenerationRequestId,
    "",
    "cancelling the current request must clear a stale activeGenerationRequestId",
  );
}

{
  const harness = createHarness();
  harness.pendingRequests.set("request-other", { chatSessionId: "chat-2" });
  harness.pendingRequests.set("request-current", { chatSessionId: "chat-1" });
  harness.state.currentChatSessionId = "";
  harness.state.activeGenerationRequestId = "request-other";
  harness.cancelRequest("request-current");
  assert.equal(
    harness.state.activeGenerationRequestId,
    "request-other",
    "cancelling an unrelated request must preserve a still-pending active request",
  );
}

{
  const harness = createHarness();
  let resolved = "";
  const pending = {
    projectId: "project-1",
    chatSessionId: "chat-1",
    cancelled: false,
    resolve: (value) => {
      resolved = value;
    },
  };
  harness.pendingRequests.set("request-current", pending);
  harness.state.activeGenerationRequestId = "request-current";
  harness.cancelPendingChatRequestFast("request-current", pending);
  assert.equal(pending.cancelled, true, "fast pause must mark the request cancelled");
  assert.equal(resolved, "已停止生成。", "fast pause must resolve the waiting sender");
  assert.equal(harness.state.chatLoading, false, "fast pause must clear loading synchronously");
  assert.deepEqual(
    harness.state.persisted,
    [{ projectId: "project-1", chatSessionId: "chat-1", chatLoading: false }],
    "fast pause must persist after loading is cleared",
  );
}

{
  const harness = createHarness();
  harness.state.currentChatSessionId = "chat-1";
  harness.state.now = 1000;
  harness.startWorkingStatusTimer();
  harness.state.currentChatSessionId = "chat-2";
  harness.state.now = 5000;
  harness.stopWorkingStatusTimer();
  harness.startWorkingStatusTimer();
  assert.equal(
    harness.state.workingStatusStartedAt,
    5000,
    "switching to another running session must start or restore its own timer",
  );
  harness.state.currentChatSessionId = "chat-1";
  harness.stopWorkingStatusTimer();
  harness.startWorkingStatusTimer();
  assert.equal(
    harness.state.workingStatusStartedAt,
    1000,
    "switching back to a still-running session must preserve its original timer",
  );
}

async function simulateDoSend(sendResult) {
  const calls = [];
  let requestCancelled = false;
  try {
    requestCancelled = Boolean(sendResult?.cancelled);
    if (requestCancelled) return calls;
    calls.push("upsert:done");
  } finally {
    calls.push("sync");
    if (!requestCancelled) {
      calls.push("fetchSessions");
      calls.push("sync");
    }
    if (!requestCancelled) {
      calls.push("drainFollowups");
    }
  }
  return calls;
}

assert.deepEqual(
  await simulateDoSend({ cancelled: true }),
  ["sync"],
  "cancelled sends must not upsert done records, refresh sessions, or drain followups",
);

assert.deepEqual(
  await simulateDoSend({ cancelled: false }),
  ["upsert:done", "sync", "fetchSessions", "sync", "drainFollowups"],
  "completed sends should keep the normal success finalization path",
);

console.log("project chat pause state checks ok");
