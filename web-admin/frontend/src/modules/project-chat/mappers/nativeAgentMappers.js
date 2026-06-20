import { formatRelativeDateTime } from "@/utils/date.js";

export function nativeExecutorOptionLabel(baseLabel, status) {
  const label = String(baseLabel || "Runner").trim() || "Runner";
  if (!status?.installed) return label;
  const version = String(status.version || "").trim();
  return version ? `${label} · ${version}` : `${label} · 已安装`;
}

export function normalizeNativeExternalAgentSessionId(value) {
  if (value && typeof value === "object") {
    return String(value.sessionId || value.session_id || "").trim();
  }
  return String(value || "").trim();
}

export function normalizeNativeExternalAgentRuntimeSnapshot(value) {
  if (!value || typeof value !== "object") return null;
  const session =
    value.session && typeof value.session === "object" ? value.session : null;
  const sessionId = String(
    value.session_id ||
      value.sessionId ||
      session?.sessionId ||
      session?.session_id ||
      "",
  ).trim();
  if (!sessionId) return null;
  // 本地运行态只保留最近日志，避免持久化 payload 随终端输出无限增长。
  return {
    session_id: sessionId,
    chat_session_id: String(
      value.chat_session_id || value.chatSessionId || "",
    ).trim(),
    message_id: String(value.message_id || value.messageId || "").trim(),
    running: Boolean(value.running),
    session,
    logs: Array.isArray(value.logs) ? value.logs.slice(-500) : [],
  };
}

export function isLiveNativeExternalAgentStatus(status) {
  return ["running", "cancelling", "waiting_permission"].includes(
    String(status || "").trim(),
  );
}

export function isNativeExternalAgentPermissionExpired(record) {
  return Boolean(
    record?.permissionExpired ||
      record?.permission_expired ||
      String(record?.blockedReason || record?.blocked_reason || "").includes(
        "权限确认超时",
      ),
  );
}

export function formatDurationMs(value) {
  const duration = Number(value || 0);
  if (!Number.isFinite(duration) || duration <= 0) return "0ms";
  if (duration < 1000) return `${Math.round(duration)}ms`;
  return `${(duration / 1000).toFixed(duration < 10_000 ? 1 : 0)}s`;
}

export function runnerSelfCheckStatusLabel(item) {
  if (!item) return "未检查";
  if (item.tone === "success") return "通过";
  if (item.tone === "blocked") return "已拦截";
  if (item.timedOut) return "超时";
  if (Number(item.exitCode) !== 0) return `退出 ${item.exitCode}`;
  return "需检查";
}

export function runnerSelfCheckTagType(item) {
  if (item?.tone === "success") return "success";
  if (item?.tone === "blocked") return "danger";
  return "warning";
}

export function buildNativeRunnerSelfCheckCommands(workspacePath = "") {
  const commands = [
    { id: "node-version", label: "Node", command: "node", args: ["--version"] },
    { id: "npm-version", label: "npm", command: "npm", args: ["--version"] },
  ];
  if (String(workspacePath || "").trim()) {
    commands.push({
      id: "git-status",
      label: "Git 工作区",
      command: "git",
      args: ["status", "--short"],
    });
  }
  return commands;
}

export function normalizeNativeRunnerSelfCheckItem(
  definition,
  classification,
  result,
) {
  const blockedReason = String(
    result?.blockedReason || classification?.blockedReason || "",
  ).trim();
  const stderr = String(result?.stderr || "").trim();
  const stdout = String(result?.stdout || "").trim();
  const allowed = Boolean(classification?.allowed);
  const exitCode = Number(result?.exitCode ?? -1);
  const ok = allowed && result && !result.timedOut && exitCode === 0;
  const summary = blockedReason || stderr || stdout.split(/\r?\n/)[0] || "";
  // 自检结果同时用于状态标签和审计展示，统一 tone 避免页面重复判断。
  return {
    id: definition.id,
    label: definition.label,
    command: [definition.command, ...(definition.args || [])].join(" "),
    allowed,
    exitCode,
    timedOut: Boolean(result?.timedOut),
    riskLevel: String(
      classification?.riskLevel || result?.riskLevel || "",
    ).trim(),
    summary: summary || (ok ? "命令执行成功" : "命令无输出"),
    tone: ok ? "success" : blockedReason ? "blocked" : "warning",
  };
}

export function runnerPermissionDecisionLabel(record) {
  const decision = String(record?.decision || "").trim();
  if (decision === "approve_once") return "批准一次";
  if (decision === "approve_session") return "本会话批准";
  if (decision === "reject") return "已拒绝";
  return "已记录";
}

export function runnerPermissionRecordSummary(record) {
  const command = [
    String(record?.command || "").trim(),
    ...(Array.isArray(record?.args) ? record.args : []),
  ]
    .filter(Boolean)
    .join(" ");
  const reason = String(record?.reason || "").trim();
  return [command, reason].filter(Boolean).join(" · ") || "命令审批决定";
}

export function runnerPermissionRecordTime(record) {
  const timestamp = Number(record?.createdAtEpochMs || 0);
  if (!timestamp) return "";
  return formatRelativeDateTime(new Date(timestamp).toISOString());
}

export function nativeExternalAgentRecordStatusLabel(record) {
  if (isNativeExternalAgentPermissionExpired(record)) return "授权已超时";
  const status = String(record?.status || "").trim();
  if (status === "running") return "运行中";
  if (status === "cancelling") return "取消中";
  if (status === "idle") return "可继续对话";
  if (status === "completed") return "已完成";
  if (status === "cancelled") return "已取消";
  if (status === "failed") return "失败";
  if (status === "blocked") return "已阻塞";
  return status || "未知";
}

export function nativeExternalAgentRecordTagType(record) {
  if (isNativeExternalAgentPermissionExpired(record)) return "warning";
  const status = String(record?.status || "").trim();
  if (status === "completed") return "success";
  if (status === "running") return "warning";
  if (status === "idle") return "success";
  if (status === "failed" || status === "blocked") return "danger";
  return "info";
}

export function nativeExternalAgentRecordSummary(record) {
  if (isNativeExternalAgentPermissionExpired(record)) {
    return "权限确认超时，Runner 已取消等待，可重新发送消息";
  }
  const label = String(
    record?.label || record?.agentType || "Runner",
  ).trim();
  const exitCode =
    record?.exitCode === null || record?.exitCode === undefined
      ? "-"
      : String(record.exitCode);
  const workspace = String(record?.workspacePath || "").trim();
  // 历史记录摘要只保留短路径，避免长 workspace 把侧栏列表挤变形。
  return [
    label,
    `exit=${exitCode}`,
    workspace ? workspace.split("/").filter(Boolean).slice(-2).join("/") : "",
  ]
    .filter(Boolean)
    .join(" · ");
}

export function nativeExternalAgentRecordTime(record) {
  const timestamp = Number(
    record?.updatedAtEpochMs || record?.startedAtEpochMs || 0,
  );
  if (!timestamp) return "";
  return formatRelativeDateTime(new Date(timestamp).toISOString());
}

export function isNativeExternalAgentInternalDiagnostic(stream, content) {
  const normalizedStream = String(stream || "")
    .trim()
    .toLowerCase();
  const text = String(content || "").trim();
  if (!text) return true;
  if (normalizedStream !== "stderr") return false;
  if (isNativeExternalAgentMacosSystemNoise(text)) return true;
  // 外部 Runner 会把内部诊断写到 stderr，这些内容不应进入用户可见终端流。
  // 1) codex 内部诊断（ISO 时间戳带 T、codex_core 等）
  if (
    /^tokens used\b/i.test(text) ||
    /^codex$/i.test(text) ||
    /failed to record rollout items/i.test(text) ||
    /codex_core::session/i.test(text) ||
    /^202\d-\d\d-\d\dT.*\bERROR\b/.test(text)
  ) {
    return true;
  }
  // 2) hermes ACP 进程的 Python logging 诊断：`YYYY-MM-DD HH:MM:SS [LEVEL] logger: msg`。
  //    真正的 agent 输出走 ACP stdout 的 session/update（raw_channel=hermes），不在此通道。
  if (
    /^\d{4}-\d\d-\d\d[ T][\d:.,]+\s*\[(?:INFO|WARN|WARNING|DEBUG|ERROR|TRACE|CRITICAL|NOTSET)\]/i.test(
      text,
    )
  ) {
    return true;
  }
  return false;
}

export function isNativeExternalAgentMacosSystemNoise(content) {
  const text = String(content || "").trim();
  if (!text) return false;
  return (
    /TSM AdjustCapsLockLEDForKeyTransitionHandling/.test(text) ||
    /_ISSetPhysicalKeyboardCapsLockLED/.test(text) ||
    /IMKCFRunLoopWakeUpReliable/.test(text)
  );
}

export function shouldShowNativeExternalAgentBlockedReason(
  snapshot,
  finalOutput = "",
) {
  const blockedReason = String(snapshot?.blockedReason || "").trim();
  if (!blockedReason) return false;
  if (
    finalOutput.trim() &&
    /没有可恢复的本机进程句柄|已停止标记为运行中/.test(blockedReason)
  ) {
    return false;
  }
  return true;
}

export function buildNativeExternalAgentCommandPreview(snapshot) {
  const command = String(snapshot?.command || "").trim();
  const args = Array.isArray(snapshot?.args) ? snapshot.args : [];
  if (!command) return "";
  const visibleArgs = args.map((arg) => {
    const value = String(arg || "");
    if (
      value.includes("用户本次任务：") ||
      value.includes("你正在 AI 员工工厂桌面端中作为Runner")
    ) {
      return "<task-prompt>";
    }
    if (value.length > 240) return `${value.slice(0, 120)}...<truncated>`;
    return value;
  });
  return [command, ...visibleArgs].filter(Boolean).join(" ");
}

function normalizeStringList(value, limit = 100) {
  const items = Array.isArray(value) ? value : [];
  return items
    .map((item) => String(item || "").trim())
    .filter(Boolean)
    .slice(0, limit);
}

export function buildExternalAgentWarmupKey({
  projectId = "",
  agentType = "codex_cli",
  localConnectorId = "",
  workspacePath = "",
  sandboxMode = "workspace-write",
  skillResourceDirectory = "",
  systemPrompt = "",
  employeeIds = [],
} = {}) {
  // warmup key 只描述会影响Runner 会话复用的输入，保持序列化顺序稳定。
  return JSON.stringify({
    projectId: String(projectId || "").trim(),
    agentType: String(agentType || "codex_cli").trim(),
    localConnectorId: String(localConnectorId || "").trim(),
    workspacePath: String(workspacePath || "").trim(),
    sandboxMode: String(sandboxMode || "workspace-write").trim(),
    skillResourceDirectory: String(skillResourceDirectory || "").trim(),
    systemPrompt: String(systemPrompt || "").trim(),
    employeeIds: normalizeStringList(employeeIds),
  });
}
