import { clipText } from "@/modules/project-chat/mappers/mediaMappers.js";

function compactAgentRuntimeJson(value, maxChars = 240) {
  try {
    return clipText(JSON.stringify(value), maxChars).replace(/\n/g, " ");
  } catch (_error) {
    return "";
  }
}

function agentRuntimeEventPayload(eventData = {}) {
  const event =
    eventData?.event && typeof eventData.event === "object"
      ? eventData.event
      : {};
  if (event?.payload && typeof event.payload === "object") {
    return event.payload;
  }
  if (eventData?.payload && typeof eventData.payload === "object") {
    return eventData.payload;
  }
  return {};
}

function agentRuntimeToolCallPayload(payload = {}) {
  const toolCall =
    payload?.tool_call && typeof payload.tool_call === "object"
      ? payload.tool_call
      : payload;
  return toolCall && typeof toolCall === "object" ? toolCall : {};
}

function agentRuntimeToolNameFromPayload(payload = {}) {
  const toolCall = agentRuntimeToolCallPayload(payload);
  return String(
    payload?.tool_name ||
      toolCall?.tool_name ||
      toolCall?.name ||
      toolCall?.function?.name ||
      "",
  ).trim();
}

function agentRuntimeToolArgsFromPayload(payload = {}) {
  const resolvedArgs =
    payload?.resolved_arguments &&
    typeof payload.resolved_arguments === "object" &&
    !Array.isArray(payload.resolved_arguments)
      ? payload.resolved_arguments
      : null;
  if (resolvedArgs) return resolvedArgs;
  const directArgs =
    payload?.args &&
    typeof payload.args === "object" &&
    !Array.isArray(payload.args)
      ? payload.args
      : null;
  if (directArgs) return directArgs;
  const toolCall = agentRuntimeToolCallPayload(payload);
  const rawArguments = String(
    toolCall?.arguments || toolCall?.function?.arguments || "",
  ).trim();
  if (!rawArguments || rawArguments[0] !== "{") return {};
  try {
    const parsed = JSON.parse(rawArguments);
    return parsed && typeof parsed === "object" && !Array.isArray(parsed)
      ? parsed
      : {};
  } catch (_error) {
    return {};
  }
}

function agentRuntimeModelToolArgsFromPayload(payload = {}) {
  const modelArgs =
    payload?.model_arguments &&
    typeof payload.model_arguments === "object" &&
    !Array.isArray(payload.model_arguments)
      ? payload.model_arguments
      : null;
  if (modelArgs) return modelArgs;
  return agentRuntimeToolArgsFromPayload(payload);
}

function parseJsonObjectText(value) {
  const text = String(value || "").trim();
  if (!text || text[0] !== "{") return null;
  try {
    const parsed = JSON.parse(text);
    return parsed && typeof parsed === "object" && !Array.isArray(parsed)
      ? parsed
      : null;
  } catch (_error) {
    return null;
  }
}

function structuredCommandResultPreview(rawResult = {}) {
  if (!rawResult || typeof rawResult !== "object") return "";
  const stdout = String(rawResult?.stdout || "").trim();
  const parsed = parseJsonObjectText(stdout);
  if (!parsed) return "";
  const lines = [];
  const addField = (label, ...keys) => {
    for (const key of keys) {
      const value = parsed?.[key];
      if (value === null || value === undefined || value === "") continue;
      lines.push(`${label}: ${String(value).trim()}`);
      return;
    }
  };
  addField("status", "status", "login_status");
  addField("user", "name", "user_name", "display_name", "email");
  addField("identity", "identity", "as", "login_identity");
  addField("brand", "brand");
  addField("expires_at", "expires_at", "expire_at", "expired_at");
  addField("refresh_expires_at", "refresh_expires_at", "refresh_expire_at");
  if (lines.length) {
    return lines.slice(0, 8).join("\n  └ ");
  }
  return "";
}

function agentRuntimeObservationPreview(payload = {}) {
  const rawResult =
    payload?.raw_result && typeof payload.raw_result === "object"
      ? payload.raw_result
      : {};
  const structuredPreview = structuredCommandResultPreview(rawResult);
  if (structuredPreview) return structuredPreview;
  const candidates = [
    rawResult?.error,
    rawResult?.stderr,
    payload?.error,
    payload?.stderr_preview,
    payload?.message,
    rawResult?.message,
    payload?.summary,
    payload?.output_preview,
    payload?.stdout_preview,
    rawResult?.stdout,
    payload?.result,
  ];
  return clipText(
    candidates
      .map((item) =>
        typeof item === "string"
          ? item.trim()
          : item === null || item === undefined
            ? ""
            : compactAgentRuntimeJson(item, 180),
      )
      .filter(Boolean)
      .join("\n"),
    360,
  );
}

function formatAgentRuntimeToolCallTranscript(payload = {}) {
  const toolName = agentRuntimeToolNameFromPayload(payload) || "tool";
  const args = agentRuntimeToolArgsFromPayload(payload);
  const modelArgs = agentRuntimeModelToolArgsFromPayload(payload);
  const command = String(args?.command || "").trim();
  if (toolName === "project_host_run_command" && command) {
    const cwd = String(args?.cwd || "").trim();
    return {
      level: "info",
      text: cwd ? `Ran ${command}\n  └ cwd=${cwd}` : `Ran ${command}`,
    };
  }
  const resolvedPreview = Object.keys(args).length
    ? compactAgentRuntimeJson(args, 260)
    : "";
  const modelPreview = Object.keys(modelArgs).length
    ? compactAgentRuntimeJson(modelArgs, 260)
    : "";
  const hasRuntimeInjection =
    modelPreview && resolvedPreview && modelPreview !== resolvedPreview;
  return {
    level: "info",
    text: [
      `Called ${toolName}`,
      modelPreview ? `  ├ Model arguments: ${modelPreview}` : "",
      resolvedPreview
        ? `  ${hasRuntimeInjection ? "└ Resolved arguments" : "└ Arguments"}: ${resolvedPreview}`
        : "",
    ]
      .filter(Boolean)
      .join("\n"),
  };
}

export function formatAgentRuntimeEventSummary(eventData = {}) {
  const eventType = String(eventData?.event_type || "").trim();
  const payload = agentRuntimeEventPayload(eventData);
  if (eventType === "run_started") return "运行任务已启动";
  if (eventType === "query_engine_started") return "模型与工具循环已启动";
  if (eventType === "llm_step_completed") {
    const stepIndex = String(payload?.step_index || "").trim();
    const toolCount = Number(payload?.tool_call_count || 0);
    return `模型步骤${stepIndex ? ` ${stepIndex}` : ""}完成${
      toolCount ? `，发现 ${toolCount} 个工具调用` : ""
    }`;
  }
  if (eventType === "model_output_normalized") {
    const parsedCount = Number(payload?.parsed_text_tool_call_count || 0);
    const strippedCount = Number(payload?.stripped_protocol_block_count || 0);
    if (parsedCount > 0) {
      return `已从模型文本中解析 ${parsedCount} 个工具调用`;
    }
    if (strippedCount > 0 || payload?.leak_detected) {
      return "已隐藏模型输出中的内部工具协议";
    }
    return "模型输出已完成可见内容清洗";
  }
  if (eventType === "tool_call_started") {
    const toolName = String(payload?.tool_name || "").trim();
    const args = agentRuntimeToolArgsFromPayload(payload);
    const argsPreview = Object.keys(args).length
      ? compactAgentRuntimeJson(args, 260)
      : "";
    if (!toolName) return argsPreview ? `开始调用工具(${argsPreview})` : "开始调用工具";
    return argsPreview
      ? `开始调用工具：${toolName}(${argsPreview})`
      : `开始调用工具：${toolName}`;
  }
  if (eventType === "permission_decision") {
    const decision =
      payload?.decision && typeof payload.decision === "object"
        ? payload.decision
        : {};
    const behavior = String(decision?.behavior || "")
      .trim()
      .toLowerCase();
    if (behavior === "ask") return "工具调用等待授权";
    if (behavior === "deny") return "工具调用被权限策略拒绝";
    return "工具调用权限已确认";
  }
  if (eventType === "tool_observation_created") {
    const toolName = String(payload?.tool_name || "").trim();
    const status = String(payload?.status || "").trim();
    return [toolName ? `工具返回结果：${toolName}` : "工具返回结果", status]
      .filter(Boolean)
      .join(" · ");
  }
  if (eventType === "tool_round_completed")
    return "工具执行轮次已处理，正在判断下一步";
  if (eventType === "completion_decision") {
    const action = String(payload?.action || "").trim();
    return action ? `完成策略判断：${action}` : "完成策略已判断";
  }
  if (eventType === "query_engine_waiting_operation") {
    return "操作仍在进行中，等待完成后恢复";
  }
  if (eventType === "query_engine_blocked") return "运行任务已暂停";
  if (eventType === "query_engine_completed") return "运行任务已完成";
  if (eventType === "query_engine_failed") return "运行任务失败";
  if (eventType === "run_finished") return "运行任务已结束";
  return eventType || "运行时事件";
}

export function formatAgentRuntimeEventPhase(eventData = {}) {
  const eventType = String(eventData?.event_type || "").trim();
  const payload = agentRuntimeEventPayload(eventData);
  if (eventType === "completion_decision") {
    const action = String(payload?.action || "")
      .trim()
      .toLowerCase();
    if (action === "complete") return "completed";
    if (action === "fail") return "failed";
    if (action === "blocked") return "blocked";
    if (action === "request_user") return "waiting_user";
    if (action === "wait_background") return "running";
  }
  if (["query_engine_completed", "run_finished"].includes(eventType)) {
    return "completed";
  }
  if (["query_engine_failed", "run_failed"].includes(eventType)) {
    return "failed";
  }
  if (eventType === "query_engine_blocked") return "blocked";
  if (eventType === "permission_decision") {
    const decision =
      payload?.decision && typeof payload.decision === "object"
        ? payload.decision
        : {};
    const behavior = String(decision?.behavior || "")
      .trim()
      .toLowerCase();
    if (behavior === "ask") return "waiting_user";
    if (behavior === "deny") return "blocked";
    if (
      ["allow_once", "allow_session", "allow_always", "allow"].includes(
        behavior,
      )
    ) {
      return "completed";
    }
  }
  return "running";
}

export function formatAgentRuntimeTranscriptEntry(eventData = {}) {
  const eventType = String(eventData?.event_type || "").trim();
  const payload = agentRuntimeEventPayload(eventData);
  if (eventType === "llm_step_completed") {
    const contentPreview = String(payload?.content_preview || "").trim();
    const toolCallCount = Number(payload?.tool_call_count || 0);
    return contentPreview && toolCallCount > 0
      ? { level: "info", text: contentPreview }
      : null;
  }
  if (eventType === "model_output_normalized") {
    const parsedCount = Number(payload?.parsed_text_tool_call_count || 0);
    const strippedCount = Number(payload?.stripped_protocol_block_count || 0);
    const leakKinds = Array.isArray(payload?.leak_kinds)
      ? payload.leak_kinds
          .map((item) => String(item || "").trim())
          .filter(Boolean)
      : [];
    if (parsedCount > 0) {
      return {
        level: "info",
        text: `Parsed ${parsedCount} text tool call${
          parsedCount === 1 ? "" : "s"
        } and hid internal protocol.`,
      };
    }
    if (strippedCount > 0 || payload?.leak_detected) {
      return {
        level: "warning",
        text: leakKinds.length
          ? `Hidden internal tool protocol\n  └ ${leakKinds.join(", ")}`
          : "Hidden internal tool protocol",
      };
    }
    return null;
  }
  if (eventType === "tool_call_started") {
    return formatAgentRuntimeToolCallTranscript(payload);
  }
  if (eventType === "permission_decision") {
    const decision =
      payload?.decision && typeof payload.decision === "object"
        ? payload.decision
        : {};
    const behavior = String(decision?.behavior || "")
      .trim()
      .toLowerCase();
    const toolName = agentRuntimeToolNameFromPayload(payload) || "tool";
    if (behavior === "ask") {
      return { level: "warning", text: `Waiting for approval: ${toolName}` };
    }
    if (behavior === "deny") {
      const reason = String(decision?.reason || "").trim();
      return {
        level: "error",
        text: reason
          ? `Blocked ${toolName}\n  └ ${reason}`
          : `Blocked ${toolName}`,
      };
    }
    return null;
  }
  if (eventType === "permission_action_applied") {
    const action = String(payload?.action || "")
      .trim()
      .toLowerCase();
    if (!action) return null;
    return {
      level: action === "deny" ? "error" : "info",
      text: action === "deny" ? "Approval denied" : "Approval applied",
    };
  }
  if (eventType === "tool_observation_created") {
    const toolName = agentRuntimeToolNameFromPayload(payload) || "tool";
    const status = String(payload?.status || "").trim();
    const level = ["failed", "error", "blocked"].includes(status.toLowerCase())
      ? "error"
      : "success";
    const preview = agentRuntimeObservationPreview(payload);
    return {
      level,
      text: preview
        ? `Result ${toolName}${status ? ` · ${status}` : ""}\n  └ ${preview}`
        : `Result ${toolName}${status ? ` · ${status}` : ""}`,
    };
  }
  if (eventType === "query_engine_waiting_operation") {
    return {
      level: "warning",
      text: "Waiting for the current operation to finish before continuing.",
    };
  }
  if (eventType === "query_engine_blocked") {
    return { level: "warning", text: "Execution paused before the next step." };
  }
  if (eventType === "query_engine_failed" || eventType === "run_failed") {
    const error = String(payload?.error || payload?.message || "").trim();
    return {
      level: "error",
      text: error ? `Execution failed\n  └ ${error}` : "Execution failed",
    };
  }
  return null;
}
