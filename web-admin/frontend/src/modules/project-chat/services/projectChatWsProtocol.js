import {
  hasAuthorizationPromptText,
  stripTerminalControlSequences,
} from "@/modules/project-chat/mappers/terminalMappers.js";

const HEARTBEAT_EVENT_TYPES = new Set(["ready", "pong"]);

const BACKGROUND_OPERATION_EVENT_TYPES = new Set([
  "operation_waiting",
  "operation_completed",
  "operation_resume_started",
  "authorization_waiting",
  "authorization_completed",
  "authorization_resume_started",
  "operation_task_state",
  "login_task_state",
  "workflow_state",
]);

const TASK_STATE_EVENT_TYPES = new Set([
  "workflow_state",
  "login_task_state",
  "operation_task_state",
]);

const WAITING_OPERATION_EVENT_TYPES = new Set([
  "authorization_waiting",
  "operation_waiting",
]);

const COMPLETED_OPERATION_EVENT_TYPES = new Set([
  "authorization_completed",
  "operation_completed",
]);

const RESUME_STARTED_EVENT_TYPES = new Set([
  "authorization_resume_started",
  "operation_resume_started",
]);

const TERMINAL_MIRROR_REQUEST_PATTERN =
  /^(?:mirror-input|mirror-start|mirror-stop)-/;

export function normalizeProjectChatWsEvent(eventData) {
  const source = eventData && typeof eventData === "object" ? eventData : {};
  // WebSocket 协议入口统一收敛大小写与空值，避免页面编排层重复解析字段。
  return {
    eventType: String(source.type || "")
      .trim()
      .toLowerCase(),
    requestId: String(source.request_id || "").trim(),
    taskId: String(source.task_id || "").trim(),
    chatSessionId: String(source.chat_session_id || "").trim(),
  };
}

export function isProjectChatHeartbeatEvent(eventType) {
  return HEARTBEAT_EVENT_TYPES.has(String(eventType || "").trim());
}

export function isBackgroundOperationEvent(eventType) {
  return BACKGROUND_OPERATION_EVENT_TYPES.has(String(eventType || "").trim());
}

export function isTaskStateEvent(eventType) {
  return TASK_STATE_EVENT_TYPES.has(String(eventType || "").trim());
}

export function isWaitingOperationEvent(eventType) {
  return WAITING_OPERATION_EVENT_TYPES.has(String(eventType || "").trim());
}

export function isCompletedOperationEvent(eventType) {
  return COMPLETED_OPERATION_EVENT_TYPES.has(String(eventType || "").trim());
}

export function isResumeStartedEvent(eventType) {
  return RESUME_STARTED_EVENT_TYPES.has(String(eventType || "").trim());
}

export function isTerminalMirrorControlRequest(requestId) {
  return TERMINAL_MIRROR_REQUEST_PATTERN.test(String(requestId || "").trim());
}

function resolveInteractionSchema(source) {
  return source?.interaction_schema && typeof source.interaction_schema === "object"
    ? source.interaction_schema
    : null;
}

export function normalizeBackgroundOperationContext(
  eventData,
  { detailMode = "state" } = {},
) {
  const source = eventData && typeof eventData === "object" ? eventData : {};
  const authorizationUrl = String(source.authorization_url || "").trim();
  const workflowKind = String(source.workflow_kind || "").trim();
  const interactionSchema = resolveInteractionSchema(source);
  const rawActionType = String(source.action_type || "").trim();
  const actionType =
    rawActionType === "open_url" && !authorizationUrl
      ? "none"
      : rawActionType ||
        (authorizationUrl
          ? "open_url"
          : interactionSchema
            ? "interaction_form"
            : "none");
  const rawDetailSource =
    detailMode === "waiting"
      ? String(source.detail || "").trim() ||
        [authorizationUrl, String(source.message || "").trim()]
          .filter(Boolean)
          .join("\n")
      : String(source.detail || source.message || "").trim();
  const rawDetail = stripTerminalControlSequences(rawDetailSource).trim();
  const isAuthWorkflow =
    workflowKind === "auth_login" || Boolean(authorizationUrl);
  const hasActionableAuthLink = Boolean(authorizationUrl);
  const hasAuthPrompt =
    isAuthWorkflow && hasAuthorizationPromptText(source, rawDetail);

  // 后台工作流事件的授权链接、交互 schema、actionType 规则必须保持一致。
  return {
    actionType,
    authorizationUrl,
    hasActionableAuthLink,
    hasAuthPrompt,
    interactionSchema,
    isAuthWorkflow,
    rawDetail,
    workflowKind,
  };
}

export function buildBackgroundTaskStateOperation({
  eventData,
  eventType,
  taskId,
  chatSessionId,
  resumeCommand,
}) {
  const source = eventData && typeof eventData === "object" ? eventData : {};
  const context = normalizeBackgroundOperationContext(source);
  const taskStatus = String(source.status || "").trim();
  const isTerminalFailure =
    ["failed", "timeout", "cancelled"].includes(taskStatus) &&
    !context.hasAuthPrompt;
  const operationId =
    eventType === "workflow_state" || eventType === "operation_task_state"
      ? context.isAuthWorkflow
        ? `auth:${taskId || String(source.workflow_id || "active").trim()}`
        : `workflow:${context.workflowKind || "generic"}:${String(source.workflow_id || taskId || "active").trim()}`
      : `auth:${taskId || "active"}`;

  return {
    context,
    taskStatus,
    operation: {
      operationId,
      kind: context.isAuthWorkflow ? "auth" : "request",
      title:
        String(
          source.status_label || source.workflow_label || "后台工作流",
        ).trim() || "后台工作流",
      summary:
        context.hasAuthPrompt &&
        ["failed", "timeout", "cancelled"].includes(taskStatus)
          ? "等待你在浏览器完成授权"
          : context.interactionSchema && taskStatus === "waiting_user_action"
            ? "等待你选择授权业务域"
            : String(source.summary || "").trim() ||
              "工作流已创建，等待后续结果",
      detail: context.rawDetail,
      phase:
        (taskStatus === "waiting_user_action" || context.hasAuthPrompt) &&
        (!context.isAuthWorkflow ||
          context.hasActionableAuthLink ||
          context.interactionSchema ||
          context.hasAuthPrompt)
          ? "waiting_user"
          : isTerminalFailure
            ? "failed"
            : taskStatus === "succeeded"
              ? "completed"
              : "running",
      actionType: context.actionType,
      meta: {
        task_id: taskId,
        chat_session_id: chatSessionId,
        resume_command: resumeCommand,
        authorization_url: context.authorizationUrl,
        interaction_schema: context.interactionSchema,
        task_status: taskStatus,
        workflow_kind: context.workflowKind,
        workflow_id: String(source.workflow_id || "").trim(),
        workflow_state: { ...source },
      },
    },
  };
}

export function buildWaitingBackgroundOperation({
  eventData,
  taskId,
  chatSessionId,
  resumeCommand,
}) {
  const source = eventData && typeof eventData === "object" ? eventData : {};
  const context = normalizeBackgroundOperationContext(source, {
    detailMode: "waiting",
  });
  return {
    context,
    operation: {
      operationId: context.isAuthWorkflow
        ? `auth:${taskId || "active"}`
        : `workflow:${context.workflowKind || "external_operation"}:${taskId || "active"}`,
      kind: context.isAuthWorkflow ? "auth" : "request",
      title:
        String(source.status_label || source.workflow_label || "等待操作").trim() ||
        "等待操作",
      summary:
        context.isAuthWorkflow && context.hasActionableAuthLink
          ? "等待你在浏览器完成授权"
          : context.interactionSchema
            ? "等待你选择授权业务域"
            : context.isAuthWorkflow
              ? "授权流程已启动，等待结构化授权链接返回"
              : "等待你完成操作",
      detail: context.rawDetail,
      phase:
        context.isAuthWorkflow &&
        !context.hasActionableAuthLink &&
        !context.interactionSchema
          ? "running"
          : "waiting_user",
      actionType: context.actionType,
      meta: {
        task_id: taskId,
        chat_session_id: chatSessionId,
        resume_command: resumeCommand,
        authorization_url: context.authorizationUrl,
        interaction_schema: context.interactionSchema,
        workflow_kind: context.workflowKind,
        workflow_state: { ...source },
      },
    },
  };
}

export function interactionSubmitAckPayload(eventData = {}) {
  return eventData?.interaction_ack &&
    typeof eventData.interaction_ack === "object"
    ? eventData.interaction_ack
    : {};
}

export function interactionSubmitAckSummary(eventData = {}) {
  const ack = interactionSubmitAckPayload(eventData);
  return (
    String(
      ack.summary || eventData?.summary || eventData?.guard_message || "",
    ).trim() || "已提交结构化交互，正在继续执行"
  );
}

export function isInteractionSubmitAckDone(eventData = {}) {
  const requestKind = String(eventData?.request_kind || "")
    .trim()
    .toLowerCase();
  const completedReason = String(
    eventData?.completed_reason || eventData?.guard_reason || "",
  )
    .trim()
    .toLowerCase();
  return (
    requestKind === "interaction_submit_ack" ||
    completedReason === "interaction_submit_ack" ||
    eventData?.suppress_request_operation === true
  );
}

export function formatGuardSummary(eventData) {
  const completedReason = String(eventData?.completed_reason || "")
    .trim()
    .toLowerCase();
  const reason = String(eventData?.guard_reason || "").trim();
  const message = String(eventData?.guard_message || "").trim();
  const details =
    eventData?.guard_details && typeof eventData.guard_details === "object"
      ? eventData.guard_details
      : {};
  if (completedReason === "background_task_pending") return "";
  if (completedReason === "waiting_user_action") return "";
  if (message) return message;
  if (reason === "tool_budget_exceeded") {
    return `工具调用达到预算上限（${Number(details.tool_rounds || 0)}/${Number(details.max_tool_rounds || 0)} 轮）`;
  }
  if (reason === "repeated_tool_signature") {
    return `检测到重复工具调用且没有正文输出（${Number(details.repeated_tool_signature_rounds || 0)}/${Number(details.repeated_tool_call_threshold || 0)} 次）`;
  }
  if (reason === "tool_only_loops") {
    return `连续多轮只有工具调用没有正文输出（${Number(details.tool_only_loops || 0)}/${Number(details.tool_only_threshold || 0)} 轮）`;
  }
  if (reason === "missing_final_response_after_tool") {
    return "工具执行已经完成，但模型没有继续生成最终回答。本轮未完成，请重新运行或检查模型续写链路。";
  }
  if (reason === "max_loops") {
    return `达到最大处理轮次（${Number(details.loop_count || 0)}/${Number(details.max_loops || 0)} 轮）`;
  }
  return "";
}

export function normalizeDoneEventExecutionState(eventData = {}) {
  if (isInteractionSubmitAckDone(eventData)) {
    return {
      phase: "running",
      level: "info",
      summary: interactionSubmitAckSummary(eventData),
      keepExecutionOpen: false,
      suppressRequestOperation: true,
    };
  }
  const guardSummary = formatGuardSummary(eventData);
  const completedReason = String(eventData?.completed_reason || "")
    .trim()
    .toLowerCase();
  // done 事件是否真正结束请求由协议字段决定，页面只消费归一化后的状态。
  if (completedReason === "waiting_user_action") {
    return {
      phase: "waiting_user",
      level: "info",
      summary:
        String(eventData?.guard_message || eventData?.summary || "").trim() ||
        "等待你完成当前操作",
      keepExecutionOpen: false,
    };
  }
  if (completedReason === "background_task_pending") {
    return {
      phase: "running",
      level: "info",
      summary:
        String(eventData?.guard_message || eventData?.summary || "").trim() ||
        "后台任务仍在继续执行",
      keepExecutionOpen: true,
    };
  }
  return {
    phase: guardSummary ? "blocked" : "completed",
    level: guardSummary ? "warning" : "success",
    summary: guardSummary || "本轮执行已结束",
    keepExecutionOpen: false,
  };
}
