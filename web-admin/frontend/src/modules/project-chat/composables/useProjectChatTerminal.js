import { ref } from "vue";
import { sanitizeTerminalOutputLines } from "@/modules/project-chat/mappers/terminalMappers.js";

/**
 * 管理终端面板、终端镜像、终端审批和结构化交互的状态。
 * 页面层负责 UI 编排，本 composable 只持有状态变量。
 */
export function useProjectChatTerminal() {
  // --- 终端面板 ---
  const terminalPanelExpanded = ref(false);
  const terminalPanelLines = ref([]);
  const terminalPanelStatus = ref("idle");
  const terminalPanelRef = ref(null);

  // --- 终端镜像 ---
  const terminalMirrorConnected = ref(false);
  const hostTerminalSessionId = ref("");
  const hostTerminalWorkspacePath = ref("");
  const activeTerminalMirrorAssistantIndex = ref(-1);

  // --- 终端审批 ---
  const terminalApprovalDialogVisible = ref(false);
  const terminalApprovalHandledKey = ref("");
  const terminalApprovalFallbackPrompt = ref(null);

  // --- 结构化交互 ---
  const terminalStructuredInteraction = ref(null);
  const terminalStructuredFormModel = ref({ choices: [], choice: "" });
  const terminalDismissedStructuredInteractionKeys = ref(new Set());
  const terminalStructuredSubmissionHint = ref(null);

  /** 清除当前终端/镜像/交互的运行状态，迁出后由页面传入 assistantIndex */
  function clearExecutionTransportState(assistantIndex = -1) {
    terminalPanelStatus.value = "idle";
    terminalMirrorConnected.value = false;
    hostTerminalSessionId.value = "";
    terminalStructuredInteraction.value = null;
    const normalizedAssistantIndex = Number(assistantIndex);
    if (
      !Number.isFinite(normalizedAssistantIndex) ||
      normalizedAssistantIndex < 0 ||
      normalizedAssistantIndex === Number(activeTerminalMirrorAssistantIndex.value)
    ) {
      activeTerminalMirrorAssistantIndex.value = -1;
    }
  }

  function appendTerminalPanelLine(text) {
    const linesToAppend = sanitizeTerminalOutputLines(text);
    if (!linesToAppend.length) return;
    const lines = Array.isArray(terminalPanelLines.value)
      ? terminalPanelLines.value.slice()
      : [];
    linesToAppend.forEach((line) => {
      if (!line || (lines.length && lines[lines.length - 1] === line)) return;
      lines.push(line);
    });
    if (lines.length > 400) {
      lines.splice(0, lines.length - 400);
    }
    terminalPanelLines.value = lines;
  }

  return {
    // 面板
    terminalPanelExpanded,
    terminalPanelLines,
    terminalPanelStatus,
    terminalPanelRef,
    // 镜像
    terminalMirrorConnected,
    hostTerminalSessionId,
    hostTerminalWorkspacePath,
    activeTerminalMirrorAssistantIndex,
    // 审批
    terminalApprovalDialogVisible,
    terminalApprovalHandledKey,
    terminalApprovalFallbackPrompt,
    // 结构化交互
    terminalStructuredInteraction,
    terminalStructuredFormModel,
    terminalDismissedStructuredInteractionKeys,
    terminalStructuredSubmissionHint,
    // 操作
    clearExecutionTransportState,
    appendTerminalPanelLineState: appendTerminalPanelLine,
    resetTerminalPanelState() {
      terminalPanelLines.value = [];
      terminalPanelStatus.value = "idle";
      terminalMirrorConnected.value = false;
      hostTerminalSessionId.value = "";
      hostTerminalWorkspacePath.value = "";
      activeTerminalMirrorAssistantIndex.value = -1;
      terminalApprovalDialogVisible.value = false;
      terminalApprovalHandledKey.value = "";
    },
  };
}
