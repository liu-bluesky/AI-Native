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

assert.match(
  source,
  /function isChatHistoryTruncateNotFound\(err\)[\s\S]*?Number\(err\?\.status \|\| 0\) !== 404[\s\S]*?message not found/,
  "message delete must identify truncate 404 responses as a local-only delete case",
);

assert.match(
  source,
  /catch \(err\) \{[\s\S]*?if \(isChatHistoryTruncateNotFound\(err\)\) \{[\s\S]*?applyDeleteTargetLocally\(target\);[\s\S]*?clearPersistedChatRuntime\(projectId, chatSessionId\);[\s\S]*?rememberCurrentChatSessionMessages\(\);[\s\S]*?ElMessage\.success\(buildDeleteSuccessText\(item\)\);[\s\S]*?return;/,
  "message delete must remove locally paused turns when the server has no persisted message to truncate",
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
