import { isNativeExternalAgentInternalDiagnostic } from "@/modules/project-chat/mappers/nativeAgentMappers.js";

export function normalizeRunnerEvidenceArray(value) {
  if (!value) return [];
  if (Array.isArray(value)) return value;
  if (typeof value === "object") return [value];
  const text = String(value || "").trim();
  return text ? [text] : [];
}

export function normalizeRunnerEvidenceItem(value, fallbackKind = "record") {
  if (value && typeof value === "object" && !Array.isArray(value)) {
    const path = String(
      value.path ||
        value.file_path ||
        value.filePath ||
        value.name ||
        value.relative_path ||
        "",
    ).trim();
    const title = String(
      value.title ||
        value.command ||
        value.summary ||
        value.status ||
        path ||
        fallbackKind,
    ).trim();
    // Runner 证据可能来自文件、命令、检查项等不同来源，这里统一成展示模型。
    return {
      kind:
        String(value.kind || value.type || fallbackKind).trim() || fallbackKind,
      title,
      path,
      status: String(value.status || value.state || value.result || "").trim(),
      summary: String(
        value.summary ||
          value.description ||
          value.message ||
          value.reason ||
          value.diff_stat ||
          value.output ||
          "",
      ).trim(),
      exitCode:
        (value.exit_code === null || value.exit_code === undefined) &&
        (value.exitCode === null || value.exitCode === undefined)
          ? ""
          : String(value.exit_code ?? value.exitCode).trim(),
    };
  }
  const text = String(value || "").trim();
  return {
    kind: fallbackKind,
    title: text,
    path: text,
    status: "",
    summary: "",
    exitCode: "",
  };
}

export function runnerEvidenceMetaText(item) {
  const status = String(item?.status || "").trim();
  const exitCode = String(item?.exitCode || item?.exit_code || "").trim();
  return [status, exitCode ? `exit=${exitCode}` : ""]
    .filter(Boolean)
    .join(" · ");
}

export function buildNativeExternalAgentFileEvidenceItems(snapshot = {}) {
  return [
    ...normalizeRunnerEvidenceArray(snapshot.files),
    ...normalizeRunnerEvidenceArray(
      snapshot.fileRecords || snapshot.file_records,
    ),
    ...normalizeRunnerEvidenceArray(
      snapshot.fileEvents || snapshot.file_events,
    ),
    ...normalizeRunnerEvidenceArray(
      snapshot.changedFiles || snapshot.changed_files,
    ),
    ...normalizeRunnerEvidenceArray(
      snapshot.diffSummary || snapshot.diff_summary,
    ),
  ]
    .map((item) => normalizeRunnerEvidenceItem(item, "file"))
    .filter((item) => item.title || item.path || item.summary)
    .slice(0, 80);
}

export function buildNativeExternalAgentVerificationItems(
  snapshot = {},
  selfCheckResults = [],
) {
  const explicit = [
    ...normalizeRunnerEvidenceArray(snapshot.verification),
    ...normalizeRunnerEvidenceArray(snapshot.verifications),
    ...normalizeRunnerEvidenceArray(snapshot.validation),
    ...normalizeRunnerEvidenceArray(snapshot.validations),
    ...normalizeRunnerEvidenceArray(snapshot.checks),
    ...normalizeRunnerEvidenceArray(
      snapshot.testResults || snapshot.test_results,
    ),
  ]
    .map((item) => normalizeRunnerEvidenceItem(item, "verification"))
    .filter((item) => item.title || item.summary || item.status);
  if (explicit.length) return explicit.slice(0, 80);
  // Runner 未提供显式验证记录时，用本机自检结果作为详情页验证兜底。
  return (Array.isArray(selfCheckResults) ? selfCheckResults : [])
    .map((item) => ({
      kind: "self-check",
      title: String(
        item?.label || item?.title || item?.command || "Runner 自检",
      ).trim(),
      path: "",
      status: String(item?.status || item?.tone || "").trim(),
      summary: String(
        item?.summary || item?.message || item?.reason || "",
      ).trim(),
      exitCode:
        item?.exitCode === null || item?.exitCode === undefined
          ? ""
          : String(item.exitCode).trim(),
    }))
    .filter((item) => item.title || item.summary || item.status);
}

export function buildNativeExternalAgentSessionOutputText(rows = []) {
  return (Array.isArray(rows) ? rows : [])
    .filter((item) => item.stream !== "stderr")
    .map((item) => item.content)
    .join("");
}

export function buildNativeExternalAgentSessionErrorText(rows = []) {
  return (Array.isArray(rows) ? rows : [])
    .filter(
      (item) =>
        item.stream === "stderr" &&
        !isNativeExternalAgentInternalDiagnostic(item.stream, item.content),
    )
    .map((item) => item.content)
    .join("");
}

export function buildNativeExternalAgentStdoutText(rows = []) {
  return (Array.isArray(rows) ? rows : [])
    .filter((item) =>
      ["stdout", "pty"].includes(String(item.stream || "").trim()),
    )
    .map((item) => String(item.content || ""))
    .join("")
    .trim();
}

export function buildNativeExternalAgentDiagnosticText(rows = []) {
  return (Array.isArray(rows) ? rows : [])
    .filter((item) =>
      ["stderr", "system", "stdin"].includes(String(item.stream || "").trim()),
    )
    .filter(
      (item) =>
        !isNativeExternalAgentInternalDiagnostic(item.stream, item.content),
    )
    .map((item) => {
      const stream = String(item.stream || "system").trim();
      return `[${stream}] ${String(item.content || "")}`;
    })
    .join("")
    .trim();
}

export function resolveNativeExternalAgentFinalAnswerText(
  snapshot = {},
  rows = [],
  stdoutFallback = "",
) {
  const explicit = String(snapshot?.finalOutput || "").trim();
  if (explicit) return explicit;
  const finalLog = [...(Array.isArray(rows) ? rows : [])]
    .reverse()
    .find((item) => String(item.stream || "").trim() === "final");
  if (finalLog?.content && String(finalLog.content).trim()) {
    return String(finalLog.content).trim();
  }
  return String(stdoutFallback || "").trim();
}

export function filterNativeExternalAgentSessionPermissionRecords(
  session = {},
  records = [],
) {
  const sessionId = String(session?.sessionId || "").trim();
  const workspacePath = String(session?.workspacePath || "").trim();
  return (Array.isArray(records) ? records : []).filter((record) => {
    const recordSessionId = String(
      record?.sessionId ||
        record?.session_id ||
        record?.runnerSessionId ||
        record?.runner_session_id ||
        "",
    ).trim();
    if (sessionId && recordSessionId) return recordSessionId === sessionId;
    const recordWorkspace = String(
      record?.workspacePath || record?.workspace_path || "",
    ).trim();
    if (workspacePath && recordWorkspace)
      return recordWorkspace === workspacePath;
    return !recordSessionId && !recordWorkspace;
  });
}

export function buildNativeExternalAgentDiagnosticItems(snapshot = {}) {
  return [
    ["session", snapshot.sessionId],
    ["status", snapshot.status],
    ["agent", snapshot.agentType],
    ["exit", snapshot.exitCode ?? ""],
    ["started", snapshot.startedAt || snapshot.started_at || ""],
    ["ended", snapshot.endedAt || snapshot.ended_at || ""],
    ["duration", snapshot.durationMs || snapshot.duration_ms || ""],
    ["stdin", snapshot.stdinOpen ? "open" : "closed"],
    ["blocked", snapshot.blockedReason],
  ]
    .map(([label, value]) => ({
      label,
      value: String(value ?? "").trim(),
    }))
    .filter((item) => item.value);
}

export function buildNativeExternalAgentFullLogText(rows = []) {
  return (Array.isArray(rows) ? rows : [])
    .map((item) => {
      const stream = String(item.stream || "stdout").trim();
      const content = String(item.content || "");
      return `[${stream}] ${content}`;
    })
    .join("")
    .trim();
}

export function formatNativeExternalAgentTerminalStatusText(
  status,
  canWriteStdin = false,
) {
  const normalizedStatus = String(status || "").trim();
  if (normalizedStatus === "running" && canWriteStdin) {
    return "正在运行，可直接输入或使用控制键";
  }
  if (normalizedStatus === "running") return "正在运行，等待执行器返回最终响应";
  if (normalizedStatus === "cancelling") return "正在取消";
  if (normalizedStatus === "completed") return "已完成";
  if (normalizedStatus === "failed") return "执行失败";
  if (normalizedStatus === "cancelled") return "已取消";
  return "等待启动";
}

export function calculateNativeExternalAgentLogStats(rows = []) {
  const normalizedRows = Array.isArray(rows) ? rows : [];
  const byStream = normalizedRows.reduce((acc, item) => {
    const stream =
      String(item?.stream || "stdout")
        .trim()
        .toLowerCase() || "stdout";
    acc[stream] = Number(acc[stream] || 0) + 1;
    return acc;
  }, {});
  // pty 是 stdout 的终端流变体，统计时合并到 stdout 方便展示。
  return {
    total: normalizedRows.length,
    stdout: Number(byStream.stdout || 0) + Number(byStream.pty || 0),
    stderr: Number(byStream.stderr || 0),
    stdin: Number(byStream.stdin || 0),
    system: Number(byStream.system || 0),
    final: Number(byStream.final || 0),
  };
}
