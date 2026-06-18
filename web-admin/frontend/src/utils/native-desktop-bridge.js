import {
  invoke as invokeTauriCommand,
  isTauri as isTauriRuntime,
} from "@tauri-apps/api/core";
import { listen as listenTauriEvent } from "@tauri-apps/api/event";

const NATIVE_BRIDGE_NAMES = [
  "__AI_EMPLOYEE_DESKTOP__",
  "aiEmployeeDesktop",
];

const TAURI_COMMAND_NAMES = {
  pickWorkspaceDirectory: "pick_workspace_directory",
  detectExecutors: "detect_executors",
  getRuntimeInfo: "get_runtime_info",
  listWorkspaceFiles: "list_workspace_files",
  readWorkspaceFile: "read_workspace_file",
  previewWorkspaceDiff: "preview_workspace_diff",
  prepareWorkspaceFileWrite: "prepare_workspace_file_write",
  classifyRunnerCommand: "classify_runner_command",
  runRunnerCommand: "run_runner_command",
  prepareExternalAgentLaunch: "prepare_external_agent_launch",
  runExternalAgentOnce: "run_external_agent_once",
  startExternalAgentSession: "start_external_agent_session",
  getExternalAgentSession: "get_external_agent_session",
  listExternalAgentSessions: "list_external_agent_sessions",
  cancelExternalAgentSession: "cancel_external_agent_session",
  hardKillExternalAgentSession: "hard_kill_external_agent_session",
  writeExternalAgentSessionInput: "write_external_agent_session_input",
  recordRunnerPermissionDecision: "record_runner_permission_decision",
  listRunnerPermissionDecisions: "list_runner_permission_decisions",
};

export const NATIVE_EXTERNAL_AGENT_SESSION_EVENT =
  "ai-employee://external-agent-session";

function canUseWindow() {
  return typeof window !== "undefined";
}

function resolveNativeGlobals() {
  const candidates = [];
  const appendCandidate = (candidate) => {
    if (!candidate || candidates.includes(candidate)) return;
    candidates.push(candidate);
  };

  if (typeof globalThis !== "undefined") appendCandidate(globalThis);
  if (!canUseWindow()) return candidates;

  appendCandidate(window);
  try {
    appendCandidate(window.parent);
  } catch {
    // Cross-origin parent windows cannot expose the native bridge.
  }
  try {
    appendCandidate(window.top);
  } catch {
    // Cross-origin top windows cannot expose the native bridge.
  }
  return candidates;
}

function resolveTauriInvoke() {
  for (const nativeGlobal of resolveNativeGlobals()) {
    try {
      const tauriCore = nativeGlobal.__TAURI__?.core;
      if (typeof tauriCore?.invoke === "function") {
        return tauriCore.invoke.bind(tauriCore);
      }
      if (typeof nativeGlobal.__TAURI__?.invoke === "function") {
        return nativeGlobal.__TAURI__.invoke.bind(nativeGlobal.__TAURI__);
      }
      if (typeof nativeGlobal.__TAURI_INTERNALS__?.invoke === "function") {
        return nativeGlobal.__TAURI_INTERNALS__.invoke.bind(
          nativeGlobal.__TAURI_INTERNALS__,
        );
      }
    } catch {
      // Ignore inaccessible cross-origin window globals.
    }
  }
  return null;
}

function canUseTauriApi() {
  for (const nativeGlobal of resolveNativeGlobals()) {
    try {
      if (
        nativeGlobal?.isTauri === true ||
        nativeGlobal?.__TAURI__ ||
        nativeGlobal?.__TAURI_INTERNALS__
      ) {
        return true;
      }
    } catch {
      // Ignore inaccessible cross-origin window globals.
    }
  }
  try {
    return Boolean(isTauriRuntime());
  } catch {
    return false;
  }
}

function resolveBridge() {
  for (const nativeGlobal of resolveNativeGlobals()) {
    for (const key of NATIVE_BRIDGE_NAMES) {
      try {
        const candidate = nativeGlobal[key];
        if (candidate && typeof candidate === "object") return candidate;
      } catch {
        // Ignore inaccessible cross-origin window globals.
      }
    }
  }
  return null;
}

export function hasNativeDesktopBridge() {
  return Boolean(resolveBridge() || canUseTauriApi() || resolveTauriInvoke());
}

export async function invokeNativeDesktopBridge(method, payload = {}) {
  const normalizedMethod = String(method || "").trim();
  if (!normalizedMethod) return null;
  const bridge = resolveBridge();
  if (bridge) {
    const handler = bridge[normalizedMethod];
    if (typeof handler === "function") {
      return handler(payload && typeof payload === "object" ? payload : {});
    }
    if (typeof bridge.invoke === "function") {
      return bridge.invoke(
        normalizedMethod,
        payload && typeof payload === "object" ? payload : {},
      );
    }
  }
  const tauriInvoke = resolveTauriInvoke();
  const tauriCommand = TAURI_COMMAND_NAMES[normalizedMethod] || normalizedMethod;
  if (tauriInvoke && tauriCommand) {
    return tauriInvoke(
      tauriCommand,
      payload && typeof payload === "object" ? payload : {},
    );
  }
  if (canUseTauriApi() && tauriCommand) {
    return invokeTauriCommand(
      tauriCommand,
      payload && typeof payload === "object" ? payload : {},
    );
  }
  return null;
}

export async function pickNativeWorkspaceDirectory(options = {}) {
  const result = await invokeNativeDesktopBridge("pickWorkspaceDirectory", {
    title: String(options?.title || "选择工作区目录").trim(),
    initialPath: String(options?.initialPath || "").trim(),
  });
  if (!result) return null;
  if (typeof result === "string") return result.trim() || null;
  if (result.cancelled) return null;
  return String(result.path || result.workspacePath || "").trim() || null;
}

export async function detectNativeExecutors(options = {}) {
  const result = await invokeNativeDesktopBridge("detectExecutors", {
    workspacePath: String(options?.workspacePath || "").trim(),
  });
  if (!result || typeof result !== "object") return null;
  return {
    codex: normalizeExecutorStatus(result.codex),
    hermes: normalizeExecutorStatus(result.hermes),
    claudeCode: normalizeExecutorStatus(result.claudeCode || result.claude_code),
    workspace: normalizeWorkspaceStatus(result.workspace),
  };
}

export async function getNativeRuntimeInfo() {
  const result = await invokeNativeDesktopBridge("getRuntimeInfo");
  if (!result || typeof result !== "object") return null;
  return {
    platform: String(result.platform || "").trim(),
    arch: String(result.arch || "").trim(),
    desktopBridgeVersion: String(
      result.desktopBridgeVersion || result.desktop_bridge_version || "",
    ).trim(),
  };
}

export async function listNativeWorkspaceFiles(options = {}) {
  const workspacePath = String(
    options?.workspacePath || options?.workspace_path || "",
  ).trim();
  const path = String(options?.path || "").trim();
  const result = await invokeNativeDesktopBridge("listWorkspaceFiles", {
    workspacePath,
    path,
  });
  return normalizeWorkspaceFileList(result, { workspacePath, path });
}

export async function readNativeWorkspaceFile(options = {}) {
  const workspacePath = String(
    options?.workspacePath || options?.workspace_path || "",
  ).trim();
  const path = String(options?.path || "").trim();
  const result = await invokeNativeDesktopBridge("readWorkspaceFile", {
    workspacePath,
    path,
  });
  return normalizeWorkspaceFileReadResult(result, { workspacePath, path });
}

export async function previewNativeWorkspaceDiff(options = {}) {
  const workspacePath = String(
    options?.workspacePath || options?.workspace_path || "",
  ).trim();
  const path = String(options?.path || "").trim();
  const result = await invokeNativeDesktopBridge("previewWorkspaceDiff", {
    workspacePath,
    path,
  });
  return normalizeWorkspaceDiffPreview(result, { workspacePath, path });
}

export async function prepareNativeWorkspaceFileWrite(options = {}) {
  const workspacePath = String(
    options?.workspacePath || options?.workspace_path || "",
  ).trim();
  const path = String(options?.path || "").trim();
  const content = String(options?.content || "");
  const result = await invokeNativeDesktopBridge("prepareWorkspaceFileWrite", {
    workspacePath,
    path,
    content,
  });
  return normalizeWorkspaceFileWritePreparation(result, {
    workspacePath,
    path,
  });
}

export async function classifyNativeRunnerCommand(options = {}) {
  const payload = normalizeRunnerCommandPayload(options);
  const result = await invokeNativeDesktopBridge("classifyRunnerCommand", payload);
  return normalizeRunnerCommandClassification(result, payload);
}

export async function runNativeRunnerCommand(options = {}) {
  const payload = normalizeRunnerCommandPayload(options);
  const result = await invokeNativeDesktopBridge("runRunnerCommand", {
    ...payload,
    timeoutMs: Number(options?.timeoutMs || options?.timeout_ms || 5000),
    dryRun: Boolean(options?.dryRun || options?.dry_run),
  });
  return normalizeRunnerCommandResult(result, payload);
}

export async function prepareNativeExternalAgentLaunch(options = {}) {
  const payload = {
    agentType: String(options?.agentType || options?.agent_type || "").trim(),
    workspacePath: String(
      options?.workspacePath || options?.workspace_path || "",
    ).trim(),
    prompt: String(options?.prompt || ""),
  };
  const result = await invokeNativeDesktopBridge(
    "prepareExternalAgentLaunch",
    payload,
  );
  return normalizeExternalAgentLaunchPlan(result, payload);
}

export async function runNativeExternalAgentOnce(options = {}) {
  const payload = {
    agentType: String(options?.agentType || options?.agent_type || "").trim(),
    workspacePath: String(
      options?.workspacePath || options?.workspace_path || "",
    ).trim(),
    prompt: String(options?.prompt || ""),
    timeoutMs: Number(options?.timeoutMs || options?.timeout_ms || 60000),
  };
  const result = await invokeNativeDesktopBridge("runExternalAgentOnce", payload);
  return normalizeExternalAgentRunResult(result, payload);
}

export async function startNativeExternalAgentSession(options = {}) {
  const payload = {
    agentType: String(options?.agentType || options?.agent_type || "").trim(),
    workspacePath: String(
      options?.workspacePath || options?.workspace_path || "",
    ).trim(),
    prompt: String(options?.prompt || ""),
  };
  const result = await invokeNativeDesktopBridge(
    "startExternalAgentSession",
    payload,
  );
  return normalizeExternalAgentSessionSnapshot(result, payload);
}

export async function getNativeExternalAgentSession(options = {}) {
  const payload = {
    sessionId: String(options?.sessionId || options?.session_id || "").trim(),
    sinceSeq: Number(options?.sinceSeq ?? options?.since_seq ?? 0),
  };
  const result = await invokeNativeDesktopBridge(
    "getExternalAgentSession",
    payload,
  );
  return normalizeExternalAgentSessionSnapshot(result, payload);
}

export async function listNativeExternalAgentSessions(options = {}) {
  const limit = Number(options?.limit || 20);
  const result = await invokeNativeDesktopBridge("listExternalAgentSessions", {
    limit,
  });
  if (!Array.isArray(result)) return [];
  return result
    .map((item) => normalizeExternalAgentSessionSnapshot(item))
    .filter((item) => item.sessionId);
}

export async function cancelNativeExternalAgentSession(options = {}) {
  const payload = {
    sessionId: String(options?.sessionId || options?.session_id || "").trim(),
  };
  const result = await invokeNativeDesktopBridge(
    "cancelExternalAgentSession",
    payload,
  );
  return normalizeExternalAgentSessionSnapshot(result, payload);
}

export async function hardKillNativeExternalAgentSession(options = {}) {
  const payload = {
    sessionId: String(options?.sessionId || options?.session_id || "").trim(),
  };
  const result = await invokeNativeDesktopBridge(
    "hardKillExternalAgentSession",
    payload,
  );
  return normalizeExternalAgentSessionSnapshot(result, payload);
}

export async function writeNativeExternalAgentSessionInput(options = {}) {
  const payload = {
    sessionId: String(options?.sessionId || options?.session_id || "").trim(),
    input: String(options?.input || ""),
    appendNewline: options?.appendNewline ?? options?.append_newline ?? true,
  };
  const result = await invokeNativeDesktopBridge(
    "writeExternalAgentSessionInput",
    payload,
  );
  return normalizeExternalAgentSessionSnapshot(result, payload);
}

export async function subscribeNativeExternalAgentSessionEvents(handler) {
  if (typeof handler !== "function" || !canUseTauriApi()) {
    return () => {};
  }
  try {
    const unlisten = await listenTauriEvent(
      NATIVE_EXTERNAL_AGENT_SESSION_EVENT,
      (event) => {
        handler(normalizeExternalAgentSessionEvent(event?.payload));
      },
    );
    return typeof unlisten === "function" ? unlisten : () => {};
  } catch (err) {
    console.warn("subscribe native external agent session events failed", err);
    return () => {};
  }
}

export async function recordNativeRunnerPermissionDecision(options = {}) {
  const payload = normalizeRunnerPermissionDecisionPayload(options);
  const result = await invokeNativeDesktopBridge(
    "recordRunnerPermissionDecision",
    { input: payload },
  );
  return normalizeRunnerPermissionDecisionRecord(result, payload);
}

export async function listNativeRunnerPermissionDecisions(options = {}) {
  const limit = Number(options?.limit || 20);
  const result = await invokeNativeDesktopBridge(
    "listRunnerPermissionDecisions",
    { limit },
  );
  if (!Array.isArray(result)) return [];
  return result
    .map((item) => normalizeRunnerPermissionDecisionRecord(item))
    .filter((item) => item.decisionId);
}

function normalizeExecutorStatus(value) {
  if (value === true) return { installed: true, path: "", version: "" };
  if (!value || typeof value !== "object") {
    return { installed: false, path: "", version: "" };
  }
  return {
    installed: Boolean(value.installed || value.available),
    path: String(value.path || value.executablePath || "").trim(),
    version: String(value.version || "").trim(),
    reason: String(value.reason || "").trim(),
  };
}

function normalizeRunnerCommandPayload(options = {}) {
  return {
    command: String(options?.command || "").trim(),
    args: Array.isArray(options?.args)
      ? options.args.map((item) => String(item || "").trim()).filter(Boolean)
      : [],
    workspacePath: String(
      options?.workspacePath || options?.workspace_path || "",
    ).trim(),
  };
}

function normalizeRunnerPermissionDecisionPayload(options = {}) {
  return {
    decisionId: String(options?.decisionId || options?.decision_id || "").trim(),
    command: String(options?.command || "").trim(),
    args: Array.isArray(options?.args)
      ? options.args.map((item) => String(item || "").trim()).filter(Boolean)
      : [],
    workspacePath: String(
      options?.workspacePath || options?.workspace_path || "",
    ).trim(),
    decision: String(options?.decision || "").trim(),
    reason: String(options?.reason || "").trim(),
    scope: String(options?.scope || "").trim(),
    source: String(options?.source || "").trim(),
    riskLevel: String(options?.riskLevel || options?.risk_level || "").trim(),
  };
}

function normalizeRunnerCommandClassification(value, fallback = {}) {
  if (!value || typeof value !== "object") {
    return {
      allowed: false,
      riskLevel: "unavailable",
      requiresApproval: false,
      command: fallback.command || "",
      args: fallback.args || [],
      workspacePath: fallback.workspacePath || "",
      blockedReason: "桌面端原生 Runner 不可用",
      summary: "",
    };
  }
  return {
    allowed: Boolean(value.allowed),
    riskLevel: String(value.riskLevel || value.risk_level || "").trim(),
    requiresApproval: Boolean(value.requiresApproval || value.requires_approval),
    command: String(value.command || fallback.command || "").trim(),
    args: Array.isArray(value.args) ? value.args.map((item) => String(item)) : [],
    workspacePath: String(
      value.workspacePath || value.workspace_path || fallback.workspacePath || "",
    ).trim(),
    blockedReason: String(
      value.blockedReason || value.blocked_reason || "",
    ).trim(),
    summary: String(value.summary || "").trim(),
  };
}

function normalizeRunnerCommandResult(value, fallback = {}) {
  const classification = normalizeRunnerCommandClassification(value, fallback);
  if (!value || typeof value !== "object") {
    return {
      ...classification,
      stdout: "",
      stderr: "",
      exitCode: -1,
      durationMs: 0,
      timedOut: false,
    };
  }
  return {
    ...classification,
    stdout: String(value.stdout || ""),
    stderr: String(value.stderr || ""),
    exitCode: Number(value.exitCode ?? value.exit_code ?? -1),
    durationMs: Number(value.durationMs ?? value.duration_ms ?? 0),
    timedOut: Boolean(value.timedOut || value.timed_out),
  };
}

function normalizeExternalAgentLaunchPlan(value, fallback = {}) {
  if (!value || typeof value !== "object") {
    return {
      agentType: fallback.agentType || "",
      label: "",
      command: "",
      args: [],
      workspacePath: fallback.workspacePath || "",
      installed: false,
      executablePath: "",
      version: "",
      riskLevel: "unavailable",
      requiresApproval: false,
      canLaunch: false,
      blockedReason: "桌面端原生启动计划不可用",
      summary: "",
    };
  }
  return {
    agentType: String(value.agentType || value.agent_type || fallback.agentType || "").trim(),
    label: String(value.label || "").trim(),
    command: String(value.command || "").trim(),
    args: Array.isArray(value.args)
      ? value.args.map((item) => String(item || "").trim()).filter(Boolean)
      : [],
    workspacePath: String(
      value.workspacePath || value.workspace_path || fallback.workspacePath || "",
    ).trim(),
    installed: Boolean(value.installed),
    executablePath: String(
      value.executablePath || value.executable_path || "",
    ).trim(),
    version: String(value.version || "").trim(),
    riskLevel: String(value.riskLevel || value.risk_level || "").trim(),
    requiresApproval: Boolean(
      value.requiresApproval || value.requires_approval,
    ),
    canLaunch: Boolean(value.canLaunch || value.can_launch),
    blockedReason: String(
      value.blockedReason || value.blocked_reason || "",
    ).trim(),
    summary: String(value.summary || "").trim(),
  };
}

function normalizeExternalAgentRunResult(value, fallback = {}) {
  const plan = normalizeExternalAgentLaunchPlan(value, fallback);
  if (!value || typeof value !== "object") {
    return {
      ...plan,
      stdout: "",
      stderr: "",
      exitCode: -1,
      durationMs: 0,
      timedOut: false,
      truncated: false,
    };
  }
  return {
    ...plan,
    stdout: String(value.stdout || ""),
    stderr: String(value.stderr || ""),
    exitCode: Number(value.exitCode ?? value.exit_code ?? -1),
    durationMs: Number(value.durationMs ?? value.duration_ms ?? 0),
    timedOut: Boolean(value.timedOut || value.timed_out),
    truncated: Boolean(value.truncated),
  };
}

function normalizeExternalAgentSessionSnapshot(value, fallback = {}) {
  if (!value || typeof value !== "object") {
    return {
      sessionId: fallback.sessionId || "",
      agentType: fallback.agentType || "",
      label: "",
      command: "",
      args: [],
      workspacePath: fallback.workspacePath || "",
      status: "unavailable",
      exitCode: null,
      startedAtEpochMs: 0,
      updatedAtEpochMs: 0,
      logs: [],
      nextSeq: Number(fallback.sinceSeq || 0),
      finalOutput: "",
      blockedReason: "桌面端 Runner 会话不可用",
      summary: "",
      stdinOpen: false,
    };
  }
  return {
    sessionId: String(value.sessionId || value.session_id || fallback.sessionId || "").trim(),
    agentType: String(value.agentType || value.agent_type || fallback.agentType || "").trim(),
    label: String(value.label || "").trim(),
    command: String(value.command || "").trim(),
    args: Array.isArray(value.args)
      ? value.args.map((item) => String(item || "").trim()).filter(Boolean)
      : [],
    workspacePath: String(
      value.workspacePath || value.workspace_path || fallback.workspacePath || "",
    ).trim(),
    status: String(value.status || "").trim(),
    exitCode:
      value.exitCode === null || value.exit_code === null
        ? null
        : Number(value.exitCode ?? value.exit_code ?? -1),
    startedAtEpochMs: Number(
      value.startedAtEpochMs ?? value.started_at_epoch_ms ?? 0,
    ),
    updatedAtEpochMs: Number(
      value.updatedAtEpochMs ?? value.updated_at_epoch_ms ?? 0,
    ),
    logs: Array.isArray(value.logs)
      ? value.logs.map((item) => normalizeExternalAgentSessionLog(item))
      : [],
    nextSeq: Number(value.nextSeq ?? value.next_seq ?? fallback.sinceSeq ?? 0),
    finalOutput: String(value.finalOutput || value.final_output || ""),
    blockedReason: String(
      value.blockedReason || value.blocked_reason || "",
    ).trim(),
    summary: String(value.summary || "").trim(),
    stdinOpen: Boolean(value.stdinOpen ?? value.stdin_open),
  };
}

function normalizeExternalAgentSessionLog(value) {
  if (!value || typeof value !== "object") {
    return {
      seq: 0,
      stream: "",
      content: "",
      kind: "log",
      title: "",
      createdAtEpochMs: 0,
    };
  }
  return {
    seq: Number(value.seq || 0),
    // stream 即 raw_channel（来源通道，调试用）。
    stream: String(value.stream || "").trim(),
    content: String(value.content || ""),
    // 统一事件类型：reasoning/plan/tool_call/tool_result/message/final/error/log。
    kind: String(value.kind || "log").trim() || "log",
    // 工具名 / 步骤标题（可空）。
    title: String(value.title || "").trim(),
    createdAtEpochMs: Number(
      value.createdAtEpochMs ?? value.created_at_epoch_ms ?? 0,
    ),
  };
}

function normalizeExternalAgentSessionEvent(value) {
  const payload = value && typeof value === "object" ? value : {};
  const snapshot = normalizeExternalAgentSessionSnapshot(payload.snapshot || {});
  const log = payload.log ? normalizeExternalAgentSessionLog(payload.log) : null;
  return {
    eventType: String(payload.eventType || payload.event_type || "").trim(),
    sessionId: String(
      payload.sessionId ||
        payload.session_id ||
        snapshot.sessionId ||
        "",
    ).trim(),
    status: String(payload.status || snapshot.status || "").trim(),
    stream: String(payload.stream || log?.stream || "").trim(),
    log,
    snapshot,
  };
}

function normalizeRunnerPermissionDecisionRecord(value, fallback = {}) {
  if (!value || typeof value !== "object") {
    return {
      decisionId: fallback.decisionId || "",
      command: fallback.command || "",
      args: fallback.args || [],
      workspacePath: fallback.workspacePath || "",
      decision: fallback.decision || "",
      reason: fallback.reason || "",
      scope: fallback.scope || "",
      source: fallback.source || "",
      riskLevel: fallback.riskLevel || "",
      createdAtEpochMs: 0,
    };
  }
  return {
    decisionId: String(
      value.decisionId || value.decision_id || fallback.decisionId || "",
    ).trim(),
    command: String(value.command || fallback.command || "").trim(),
    args: Array.isArray(value.args)
      ? value.args.map((item) => String(item || "").trim()).filter(Boolean)
      : fallback.args || [],
    workspacePath: String(
      value.workspacePath || value.workspace_path || fallback.workspacePath || "",
    ).trim(),
    decision: String(value.decision || fallback.decision || "").trim(),
    reason: String(value.reason || fallback.reason || "").trim(),
    scope: String(value.scope || fallback.scope || "").trim(),
    source: String(value.source || fallback.source || "").trim(),
    riskLevel: String(
      value.riskLevel || value.risk_level || fallback.riskLevel || "",
    ).trim(),
    createdAtEpochMs: Number(
      value.createdAtEpochMs || value.created_at_epoch_ms || 0,
    ),
  };
}

function normalizeWorkspaceStatus(value) {
  if (!value || typeof value !== "object") {
    return {
      configured: false,
      exists: false,
      isDirectory: false,
      path: "",
      reason: "",
    };
  }
  const path = String(value.path || "").trim();
  const configured = Boolean(value.configured || path);
  const exists = Boolean(value.exists);
  const isDirectory = Boolean(value.isDirectory || value.is_directory);
  return {
    configured,
    exists,
    isDirectory,
    path,
    reason: String(value.reason || "").trim(),
  };
}

function normalizeWorkspaceFileList(value, fallback = {}) {
  if (!value || typeof value !== "object") {
    return {
      root: fallback.workspacePath || "",
      path: fallback.path || "",
      items: [],
    };
  }
  return {
    root: String(value.root || fallback.workspacePath || "").trim(),
    path: String(value.path || fallback.path || "").trim(),
    items: Array.isArray(value.items)
      ? value.items.map(normalizeWorkspaceFileItem).filter((item) => item.name)
      : [],
  };
}

function normalizeWorkspaceFileItem(value) {
  const kind = String(value?.kind || "").trim();
  return {
    name: String(value?.name || "").trim(),
    path: String(value?.path || "").trim(),
    kind: kind === "directory" ? "directory" : "file",
    size: Number(value?.size || 0),
    modifiedAtEpochMs: Number(
      value?.modifiedAtEpochMs || value?.modified_at_epoch_ms || 0,
    ),
  };
}

function normalizeWorkspaceFileReadResult(value, fallback = {}) {
  if (!value || typeof value !== "object") {
    return {
      root: fallback.workspacePath || "",
      path: fallback.path || "",
      name: "",
      size: 0,
      modifiedAtEpochMs: 0,
      encoding: "",
      content: "",
    };
  }
  return {
    root: String(value.root || fallback.workspacePath || "").trim(),
    path: String(value.path || fallback.path || "").trim(),
    name: String(value.name || "").trim(),
    size: Number(value.size || 0),
    modifiedAtEpochMs: Number(
      value.modifiedAtEpochMs || value.modified_at_epoch_ms || 0,
    ),
    encoding: String(value.encoding || "").trim(),
    content: String(value.content || ""),
  };
}

function normalizeWorkspaceDiffPreview(value, fallback = {}) {
  if (!value || typeof value !== "object") {
    return {
      root: fallback.workspacePath || "",
      path: fallback.path || "",
      available: false,
      summary: "",
      diff: "",
      status: "",
      exitCode: -1,
      truncated: false,
      reason: "桌面端原生 diff 预览不可用",
    };
  }
  return {
    root: String(value.root || fallback.workspacePath || "").trim(),
    path: String(value.path || fallback.path || "").trim(),
    available: Boolean(value.available),
    summary: String(value.summary || ""),
    diff: String(value.diff || ""),
    status: String(value.status || ""),
    exitCode: Number(value.exitCode ?? value.exit_code ?? -1),
    truncated: Boolean(value.truncated),
    reason: String(value.reason || "").trim(),
  };
}

function normalizeWorkspaceFileWritePreparation(value, fallback = {}) {
  if (!value || typeof value !== "object") {
    return {
      root: fallback.workspacePath || "",
      path: fallback.path || "",
      exists: false,
      currentSize: 0,
      nextSize: 0,
      currentLineCount: 0,
      nextLineCount: 0,
      changed: false,
      riskLevel: "unavailable",
      requiresApproval: false,
      summary: "桌面端原生写入准备不可用",
      reason: "",
    };
  }
  return {
    root: String(value.root || fallback.workspacePath || "").trim(),
    path: String(value.path || fallback.path || "").trim(),
    exists: Boolean(value.exists),
    currentSize: Number(value.currentSize ?? value.current_size ?? 0),
    nextSize: Number(value.nextSize ?? value.next_size ?? 0),
    currentLineCount: Number(
      value.currentLineCount ?? value.current_line_count ?? 0,
    ),
    nextLineCount: Number(value.nextLineCount ?? value.next_line_count ?? 0),
    changed: Boolean(value.changed),
    riskLevel: String(value.riskLevel || value.risk_level || "").trim(),
    requiresApproval: Boolean(
      value.requiresApproval || value.requires_approval,
    ),
    summary: String(value.summary || "").trim(),
    reason: String(value.reason || "").trim(),
  };
}
