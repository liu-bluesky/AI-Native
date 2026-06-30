import {
  cloneInteractionValue,
  normalizeChatSourceContext as normalizeChatSourceContextValue,
} from "@/modules/project-chat/mappers/chatSourceMappers.js";

export {
  formatChatPlatformLabel,
  formatChatSessionSourceLabel,
  isBotConversationSession,
  isGroupChatSession,
  normalizeChatSession,
  normalizeChatSourceContext,
  normalizeStringList,
  resolveChatSessionGroupLabel,
} from "@/modules/project-chat/mappers/chatSourceMappers.js";

function nowText() {
  return new Date().toLocaleString();
}

export function normalizeProcessLogLevel(value) {
  const normalized = String(value || "")
    .trim()
    .toLowerCase();
  if (["info", "success", "warning", "error"].includes(normalized)) {
    return normalized;
  }
  return "info";
}

export function normalizePersistedProcessLogEntries(value) {
  return Array.isArray(value)
    ? value
        .map((item, index) => ({
          id: String(item?.id || `persisted-process-log-${index}`).trim(),
          text: String(item?.text || item?.content || "").trim(),
          level: normalizeProcessLogLevel(item?.level),
          createdAt: String(item?.createdAt || item?.created_at || "").trim(),
        }))
        .filter((item) => item.text)
    : [];
}

export function normalizeOperationPhase(value) {
  const normalized = String(value || "")
    .trim()
    .toLowerCase();
  if (
    [
      "pending",
      "running",
      "waiting_user",
      "blocked",
      "completed",
      "failed",
    ].includes(normalized)
  ) {
    return normalized;
  }
  return "pending";
}

export function normalizeOperationActionType(value) {
  const normalized = String(value || "")
    .trim()
    .toLowerCase();
  if (
    ["open_url", "approve", "enter_text", "select", "none"].includes(normalized)
  ) {
    return normalized;
  }
  return "none";
}

export function buildMessageOperation(source = {}) {
  const rawOperationId = String(
    source.operationId || source.operation_id || source.id || "",
  ).trim();
  const rawKind = String(source.kind || source.operation_kind || "task").trim();
  const title = String(source.title || "执行步骤").trim() || "执行步骤";
  const summary = String(source.summary || "").trim();
  const detail = String(source.detail || "").trim();
  const phase = normalizeOperationPhase(source.phase || source.status);
  const actionType = normalizeOperationActionType(
    source.actionType || source.action_type,
  );
  const meta =
    source.meta && typeof source.meta === "object"
      ? { ...source.meta }
      : {
          request_id: String(
            source.requestId || source.request_id || "",
          ).trim(),
          approval_id: String(
            source.approvalId || source.approval_id || "",
          ).trim(),
          review_id: String(source.reviewId || source.review_id || "").trim(),
          prompt_key: String(
            source.promptKey || source.prompt_key || source.key || "",
          ).trim(),
          message: String(source.message || "").trim(),
          description: String(source.description || "").trim(),
          approval_mode: String(
            source.approvalMode || source.approval_mode || "",
          ).trim(),
          diff_summary:
            source.diffSummary && typeof source.diffSummary === "object"
              ? source.diffSummary
              : source.diff_summary && typeof source.diff_summary === "object"
                ? source.diff_summary
                : null,
          risk_signals: Array.isArray(source.riskSignals || source.risk_signals)
            ? source.riskSignals || source.risk_signals
            : [],
        };
  return {
    id:
      rawOperationId ||
      `${rawKind}:${title}:${summary}:${detail}:${phase}:${actionType}`,
    operationId: rawOperationId || "",
    kind: rawKind,
    title,
    summary,
    detail,
    phase,
    actionType,
    createdAt: String(
      source.createdAt || source.created_at || nowText(),
    ).trim(),
    updatedAt: String(
      source.updatedAt || source.updated_at || nowText(),
    ).trim(),
    meta,
  };
}

export function normalizePersistedOperations(value) {
  return Array.isArray(value)
    ? value.map((item) => buildMessageOperation(item)).filter((item) => item.title)
    : [];
}

export function buildPendingInteractionOperation(value) {
  if (!value || typeof value !== "object") return null;
  const operationId = String(value.operation_id || value.operationId || "").trim();
  if (!operationId) return null;
  return buildMessageOperation({
    operationId,
    kind: String(value.kind || "request").trim() || "request",
    title: String(value.title || "需要你继续操作").trim(),
    summary: String(value.summary || "等待你完成当前交互").trim(),
    detail: String(value.detail || "").trim(),
    phase: String(value.phase || "waiting_user").trim(),
    actionType: String(value.action_type || value.actionType || "interaction_form").trim(),
    meta: {
      task_id: String(value.task_id || "").trim(),
      chat_session_id: String(value.chat_session_id || "").trim(),
      resume_command: String(value.resume_command || "").trim(),
      authorization_url: String(value.authorization_url || "").trim(),
      workflow_kind: String(value.workflow_kind || "").trim(),
      workflow_id: String(value.workflow_id || "").trim(),
      interaction_id: String(value.interaction_id || operationId).trim(),
      interaction_schema:
        value.interaction_schema && typeof value.interaction_schema === "object"
          ? cloneInteractionValue(value.interaction_schema)
          : null,
      workflow_state:
        value.workflow_state && typeof value.workflow_state === "object"
          ? cloneInteractionValue(value.workflow_state)
          : {},
    },
  });
}

export function findMessageOperationMatchIndex(items, operation) {
  const operationPermissionMeta =
    operation?.meta && typeof operation.meta === "object" ? operation.meta : {};
  if (String(operationPermissionMeta.agent_runtime_permission || "").trim() === "true") {
    const runId = String(operationPermissionMeta.run_id || "").trim();
    const signature = String(operationPermissionMeta.command_signature || "").trim();
    if (runId && signature) {
      const byCommandSignature = items.findIndex((item) => {
        const meta = item?.meta && typeof item.meta === "object" ? item.meta : {};
        return (
          String(meta.agent_runtime_permission || "").trim() === "true" &&
          String(meta.run_id || "").trim() === runId &&
          String(meta.command_signature || "").trim() === signature
        );
      });
      if (byCommandSignature >= 0) return byCommandSignature;
    }
  }
  const taskId = String(operationPermissionMeta.task_id || "").trim();
  const chatSessionId = String(operationPermissionMeta.chat_session_id || "").trim();
  const canonicalTaskKind = String(operation?.kind || "")
    .trim()
    .toLowerCase();
  const operationWorkflowKind = String(operationPermissionMeta.workflow_kind || "")
    .trim()
    .toLowerCase();
  if (taskId && ["auth", "request", "approval"].includes(canonicalTaskKind)) {
    const byTaskId = items.findIndex((item) => {
      const meta = item?.meta && typeof item.meta === "object" ? item.meta : {};
      const itemTaskId = String(meta.task_id || "").trim();
      if (!itemTaskId || itemTaskId !== taskId) return false;
      const itemChatSessionId = String(meta.chat_session_id || "").trim();
      if (chatSessionId && itemChatSessionId && itemChatSessionId !== chatSessionId) {
        return false;
      }
      const itemKind = String(item?.kind || "")
        .trim()
        .toLowerCase();
      const itemWorkflowKind = String(meta.workflow_kind || "")
        .trim()
        .toLowerCase();
      return (
        itemKind === canonicalTaskKind ||
        itemKind === "auth" ||
        canonicalTaskKind === "auth" ||
        itemWorkflowKind === operationWorkflowKind ||
        itemWorkflowKind === "auth_login" ||
        operationWorkflowKind === "auth_login"
      );
    });
    if (byTaskId >= 0) return byTaskId;
  }
  const byId = items.findIndex((item) => item.id === operation.id);
  if (byId >= 0) return byId;
  const operationId = String(operation?.operationId || "").trim();
  if (operationId) {
    const byOperationId = items.findIndex(
      (item) => String(item?.operationId || "").trim() === operationId,
    );
    if (byOperationId >= 0) return byOperationId;
  }
  const operationKind = String(operation?.kind || "")
    .trim()
    .toLowerCase();
  if (operationKind !== "request") return -1;
  const requestId = String(operation?.meta?.request_id || "").trim();
  if (requestId) {
    const byRequestId = items.findIndex(
      (item) =>
        String(item?.kind || "")
          .trim()
          .toLowerCase() === "request" &&
        String(item?.meta?.request_id || "").trim() === requestId,
    );
    if (byRequestId >= 0) return byRequestId;
  }
  return items.findIndex(
    (item) =>
      String(item?.kind || "")
        .trim()
        .toLowerCase() === "request" &&
      String(item?.title || "").trim() ===
        String(operation?.title || "").trim(),
  );
}

export function mergeMessageOperations(existingOperations, nextOperations) {
  const merged = Array.isArray(existingOperations)
    ? existingOperations.slice()
    : [];
  (Array.isArray(nextOperations) ? nextOperations : []).forEach((operation) => {
    const matchIndex = findMessageOperationMatchIndex(merged, operation);
    if (matchIndex >= 0) {
      const existingMeta =
        merged[matchIndex]?.meta && typeof merged[matchIndex].meta === "object"
          ? merged[matchIndex].meta
          : {};
      const operationMeta =
        operation?.meta && typeof operation.meta === "object" ? operation.meta : {};
      merged[matchIndex] = {
        ...merged[matchIndex],
        ...operation,
        id: merged[matchIndex].operationId
          ? merged[matchIndex].id
          : operation.id,
        operationId:
          merged[matchIndex].operationId || operation.operationId || "",
        createdAt: merged[matchIndex].createdAt || operation.createdAt,
        updatedAt: operation.updatedAt || nowText(),
        meta: {
          ...existingMeta,
          ...operationMeta,
          command:
            String(operationMeta.command || "").trim() ||
            String(existingMeta.command || "").trim(),
          cwd:
            String(operationMeta.cwd || "").trim() ||
            String(existingMeta.cwd || "").trim(),
          arguments_preview:
            String(operationMeta.arguments_preview || "").trim() ||
            String(existingMeta.arguments_preview || "").trim(),
          output_preview:
            String(operationMeta.output_preview || "").trim() ||
            String(existingMeta.output_preview || "").trim(),
          stdout_preview:
            String(operationMeta.stdout_preview || "").trim() ||
            String(existingMeta.stdout_preview || "").trim(),
          stderr_preview:
            String(operationMeta.stderr_preview || "").trim() ||
            String(existingMeta.stderr_preview || "").trim(),
          error:
            String(operationMeta.error || "").trim() ||
            String(existingMeta.error || "").trim(),
          risk_level:
            String(operationMeta.risk_level || "").trim() ||
            String(existingMeta.risk_level || "").trim(),
          authorization_url:
            String(operationMeta.authorization_url || "").trim() ||
            String(existingMeta.authorization_url || "").trim(),
          user_code:
            String(operationMeta.user_code || "").trim() ||
            String(existingMeta.user_code || "").trim(),
          interaction_schema:
            operationMeta.interaction_schema || existingMeta.interaction_schema || null,
        },
      };
    } else {
      merged.push(operation);
    }
  });
  return merged.slice(-24);
}

function shouldExpandProcessByDefault(processLog, operations) {
  const phases = (Array.isArray(operations) ? operations : []).map((item) =>
    normalizeOperationPhase(item?.phase || item?.status),
  );
  return phases.includes("running") || phases.includes("waiting_user");
}

export function mapHistoryMessage(item) {
  const attachments = Array.isArray(item?.attachments) ? item.attachments : [];
  const images = Array.isArray(item?.images) ? item.images : [];
  const videos = Array.isArray(item?.videos) ? item.videos : [];
  const rawSourceContext =
    item?.source_context && typeof item.source_context === "object"
      ? item.source_context
      : {};
  const sourceContext = normalizeChatSourceContextValue(item || {});
  const hasAiRequestContext = Boolean(
    rawSourceContext.ai_request_context &&
      typeof rawSourceContext.ai_request_context === "object",
  );
  const runtimeTrace =
    sourceContext.agent_runtime_trace &&
    typeof sourceContext.agent_runtime_trace === "object"
      ? sourceContext.agent_runtime_trace
      : {};
  const processLog = normalizePersistedProcessLogEntries(
    runtimeTrace.process_log,
  );
  const operations = mergeMessageOperations(
    normalizePersistedOperations(runtimeTrace.operations),
    [buildPendingInteractionOperation(sourceContext.pending_interaction)].filter(Boolean),
  );
  return {
    id: String(item?.id || ""),
    role: String(item?.role || "assistant"),
    content: String(item?.content || ""),
    reasoningContent: String(
      item?.reasoningContent || item?.reasoning_content || "",
    ).trim(),
    displayMode: String(item?.display_mode || "").trim(),
    terminalLog: Array.isArray(runtimeTrace.terminal_log)
      ? runtimeTrace.terminal_log
          .map((line) => String(line || "").trim())
          .filter(Boolean)
      : [],
    processExpanded: shouldExpandProcessByDefault(processLog, operations),
    audit: null,
    taskTreeAudit: null,
    processLog,
    statusNotes: [],
    operations,
    images,
    videos,
    attachments,
    source_context: sourceContext,
    hasAiRequestContext,
    time: String(item?.created_at || ""),
  };
}
