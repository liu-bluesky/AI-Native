import ELK from "elkjs/lib/elk.bundled.js";

const elk = new ELK();
const STAGE_NODE_WIDTH = 360;
const STAGE_NODE_HEIGHT = 144;
const CYCLE_NODE_WIDTH = 320;
const CYCLE_NODE_HEIGHT = 156;

const MAIN_STAGES = [
  { key: "request", title: "请求输入", visualType: "request" },
  { key: "context", title: "上下文构建", visualType: "context_build" },
  { key: "plan", title: "规划与决策", visualType: "plan" },
  { key: "execution", title: "执行循环", visualType: "operation" },
  { key: "answer", title: "回答与结果", visualType: "final_answer" },
];

function normalizeText(value) {
  return String(value || "").replace(/\s+/g, " ").trim();
}

function truncate(value, maxLength = 120) {
  const text = normalizeText(value);
  return text.length > maxLength ? `${text.slice(0, maxLength)}…` : text;
}

function aggregateStatus(steps) {
  if (steps.some((step) => step.status === "failed")) return "failed";
  if (steps.some((step) => step.status === "blocked")) return "blocked";
  if (steps.some((step) => step.status === "running")) return "running";
  if (steps.some((step) => step.status === "pending")) return "pending";
  return steps.length ? steps.at(-1)?.status || "completed" : "completed";
}

function mainStageKey(step) {
  const type = String(step?.step_type || "observation").trim();
  const title = normalizeText(step?.title);
  if (type === "request") return "request";
  if (type === "context_build" || /上下文|提示词|prompt/i.test(title)) return "context";
  if (type === "plan") return "plan";
  if (type === "final_answer") return "answer";
  return "execution";
}

function stageSummary(stage, steps, executionSteps) {
  if (stage.key === "context") {
    const contextualStep = [...steps, ...executionSteps].find(
      (step) => Number(step?.context_message_count || 0) > 0,
    );
    if (contextualStep) {
      const messages = Number(contextualStep.context_message_count || 0);
      const tokens = Number(contextualStep.context_input_tokens || 0);
      return `${messages} 条模型消息${tokens ? `，约 ${tokens.toLocaleString()} Token` : ""}`;
    }
  }
  if (stage.key === "execution") {
    const cycleCount = new Set(
      executionSteps.map((step) => Number(step?.model_step_index || 0)).filter(Boolean),
    ).size;
    return cycleCount
      ? `${cycleCount} 轮模型循环，${executionSteps.length} 个执行节点`
      : executionSteps.length
        ? `${executionSteps.length} 个执行节点`
        : "未采集到执行循环";
  }
  const primaryStep = steps.at(-1);
  return truncate(
    primaryStep?.summary || primaryStep?.detail_preview || primaryStep?.title || "暂无独立记录",
  );
}

function buildFlowNodes(steps) {
  const sortedSteps = [...steps].sort(
    (left, right) => Number(left.sort_order || 0) - Number(right.sort_order || 0),
  );
  const grouped = new Map(MAIN_STAGES.map((stage) => [stage.key, []]));
  for (const step of sortedSteps) grouped.get(mainStageKey(step)).push(step);
  const executionSteps = grouped.get("execution");
  const stageNodes = MAIN_STAGES.map((stage, index) => {
    const stageSteps = grouped.get(stage.key);
    const primaryStep =
      stage.key === "context" && !stageSteps.length
        ? executionSteps.find((step) => Number(step?.context_message_count || 0) > 0) || null
        : stageSteps.at(-1) || null;
    return {
      id: `main-stage-${stage.key}`,
      width: STAGE_NODE_WIDTH,
      height: STAGE_NODE_HEIGHT,
      data: {
        nodeKind: "stage",
        stageKey: stage.key,
        order: index + 1,
        title: stage.title,
        summary: stageSummary(stage, stageSteps, executionSteps),
        visualType: stage.visualType,
        status: aggregateStatus(stageSteps),
        eventCount: stageSteps.length,
        durationMs: stageSteps.reduce(
          (total, step) => total + Math.max(0, Number(step.duration_ms || 0)),
          0,
        ),
        stepIds: stageSteps.map((step) => step.step_id),
        steps: stageSteps,
        primaryStep,
      },
    };
  });
  const cycleNodes = executionSteps.map((step, index) => ({
    id: `execution-cycle-${index + 1}`,
    width: CYCLE_NODE_WIDTH,
    height: CYCLE_NODE_HEIGHT,
    data: {
      nodeKind: "cycle",
      stageKey: "execution",
      order: `4.${index + 1}`,
      title: step.title || "执行节点",
      summary: truncate(step.summary || step.detail_preview || step.title),
      visualType: step.step_type || "operation",
      status: step.status || "completed",
      eventCount: 1,
      toolName: normalizeText(step.tool_name),
      durationMs: Math.max(0, Number(step.duration_ms || 0)),
      contextMessageCount: Math.max(0, Number(step.context_message_count || 0)),
      contextInputTokens: Math.max(0, Number(step.context_input_tokens || 0)),
      modelInputTokens: Math.max(0, Number(step.model_input_tokens || 0)),
      modelOutputTokens: Math.max(0, Number(step.model_output_tokens || 0)),
      modelTotalTokens: Math.max(0, Number(step.model_total_tokens || 0)),
      modelTokenSource: normalizeText(step.model_token_source),
      modelStepIndex: Math.max(0, Number(step.model_step_index || 0)),
      stepIds: [step.step_id],
      steps: [step],
      primaryStep: step,
    },
  }));
  return { stageNodes, cycleNodes };
}

function buildFlowEdges(stageNodes, cycleNodes) {
  const beforeExecution = stageNodes.slice(0, 4);
  const answerStage = stageNodes[4];
  const orderedNodes = cycleNodes.length
    ? [...beforeExecution, ...cycleNodes, answerStage]
    : [...stageNodes];
  return orderedNodes.slice(1).map((target, index) => ({
    id: `execution-edge-${index + 1}`,
    source: orderedNodes[index].id,
    target: target.id,
  }));
}

export async function buildExecutionFlow(steps = []) {
  const normalizedSteps = Array.isArray(steps) ? steps : [];
  if (!normalizedSteps.length) return { nodes: [], edges: [] };
  const { stageNodes, cycleNodes } = buildFlowNodes(normalizedSteps);
  const nodes = [...stageNodes, ...cycleNodes];
  const flowEdges = buildFlowEdges(stageNodes, cycleNodes);
  const layout = await elk.layout({
    id: "execution-flow",
    layoutOptions: {
      "elk.algorithm": "layered",
      "elk.direction": "DOWN",
      "elk.edgeRouting": "ORTHOGONAL",
      "elk.spacing.nodeNode": "44",
      "elk.layered.spacing.nodeNodeBetweenLayers": "64",
      "elk.layered.nodePlacement.strategy": "NETWORK_SIMPLEX",
    },
    children: nodes.map((node) => ({
      id: node.id,
      width: node.width,
      height: node.height,
    })),
    edges: flowEdges.map((edge) => ({
      id: edge.id,
      sources: [edge.source],
      targets: [edge.target],
    })),
  });
  const positionById = new Map(
    (layout.children || []).map((node) => [node.id, { x: node.x || 0, y: node.y || 0 }]),
  );
  return {
    nodes: nodes.map((node) => ({
      id: node.id,
      type: "execution",
      position: positionById.get(node.id) || { x: 0, y: 0 },
      data: node.data,
      draggable: false,
      connectable: false,
      selectable: true,
      focusable: true,
      width: node.width,
      height: node.height,
    })),
    edges: flowEdges,
  };
}
