import ELK from "elkjs/lib/elk.bundled.js";

const elk = new ELK();
const NODE_WIDTH = 320;
const NODE_HEIGHT = 150;

function normalizeText(value) {
  return String(value || "").replace(/\s+/g, " ").trim();
}

function truncate(value, maxLength = 120) {
  const text = normalizeText(value);
  return text.length > maxLength ? `${text.slice(0, maxLength)}…` : text;
}

function groupDescriptor(step) {
  const type = String(step?.step_type || "observation").trim();
  const title = normalizeText(step?.title);
  if (type === "observation") {
    if (/本轮目标|开始执行|上下文|准备正式模型|提炼/.test(title)) {
      return { key: "preparation", title: "输入与上下文准备", visualType: "context_build" };
    }
    return { key: "runtime-events", title: "运行事件与状态", visualType: "observation" };
  }
  if (type === "model_call") {
    return { key: "model-call", title: "模型调用", visualType: "model_call" };
  }
  return {
    key: `single:${step.step_id}`,
    title: title || type,
    visualType: type,
  };
}

function aggregateStatus(steps) {
  if (steps.some((step) => step.status === "failed")) return "failed";
  if (steps.some((step) => step.status === "blocked")) return "blocked";
  if (steps.some((step) => step.status === "running")) return "running";
  if (steps.some((step) => step.status === "pending")) return "pending";
  return steps.at(-1)?.status || "completed";
}

function buildStages(steps) {
  const sortedSteps = [...steps].sort(
    (left, right) => Number(left.sort_order || 0) - Number(right.sort_order || 0),
  );
  const groups = [];
  for (const step of sortedSteps) {
    const descriptor = groupDescriptor(step);
    const previous = groups.at(-1);
    if (previous && previous.key === descriptor.key && !descriptor.key.startsWith("single:")) {
      previous.steps.push(step);
      continue;
    }
    groups.push({ ...descriptor, steps: [step] });
  }
  return groups.map((group, index) => {
    const primaryStep = group.steps.at(-1);
    const summary =
      primaryStep?.summary ||
      primaryStep?.detail_preview ||
      primaryStep?.title ||
      group.title;
    return {
      id: `execution-stage-${index + 1}`,
      width: NODE_WIDTH,
      height: NODE_HEIGHT,
      data: {
        order: index + 1,
        title: group.title,
        summary: truncate(summary),
        visualType: group.visualType,
        status: aggregateStatus(group.steps),
        eventCount: group.steps.length,
        toolName: normalizeText(primaryStep?.tool_name),
        durationMs: group.steps.reduce(
          (total, step) => total + Math.max(0, Number(step.duration_ms || 0)),
          0,
        ),
        stepIds: group.steps.map((step) => step.step_id),
        steps: group.steps,
        primaryStep,
      },
    };
  });
}

function buildStageEdges(stages, edges) {
  const stageByStepId = new Map();
  for (const stage of stages) {
    for (const stepId of stage.data.stepIds) stageByStepId.set(stepId, stage.id);
  }
  const stageEdges = [];
  const seen = new Set();
  for (const edge of edges) {
    const source = stageByStepId.get(edge.source_step_id);
    const target = stageByStepId.get(edge.target_step_id);
    const key = `${source}->${target}`;
    if (!source || !target || source === target || seen.has(key)) continue;
    seen.add(key);
    stageEdges.push({ id: `execution-edge-${stageEdges.length + 1}`, source, target });
  }
  if (!stageEdges.length && stages.length > 1) {
    for (let index = 1; index < stages.length; index += 1) {
      stageEdges.push({
        id: `execution-edge-${index}`,
        source: stages[index - 1].id,
        target: stages[index].id,
      });
    }
  }
  return stageEdges;
}

export async function buildExecutionFlow(steps = [], edges = []) {
  const stages = buildStages(Array.isArray(steps) ? steps : []);
  const stageEdges = buildStageEdges(stages, Array.isArray(edges) ? edges : []);
  if (!stages.length) return { nodes: [], edges: [] };

  const layout = await elk.layout({
    id: "execution-flow",
    layoutOptions: {
      "elk.algorithm": "layered",
      "elk.direction": "DOWN",
      "elk.edgeRouting": "ORTHOGONAL",
      "elk.spacing.nodeNode": "52",
      "elk.layered.spacing.nodeNodeBetweenLayers": "72",
      "elk.layered.nodePlacement.strategy": "NETWORK_SIMPLEX",
    },
    children: stages.map((stage) => ({
      id: stage.id,
      width: stage.width,
      height: stage.height,
    })),
    edges: stageEdges.map((edge) => ({
      id: edge.id,
      sources: [edge.source],
      targets: [edge.target],
    })),
  });

  const positionById = new Map(
    (layout.children || []).map((node) => [node.id, { x: node.x || 0, y: node.y || 0 }]),
  );
  return {
    nodes: stages.map((stage) => ({
      id: stage.id,
      type: "execution",
      position: positionById.get(stage.id) || { x: 0, y: 0 },
      data: stage.data,
      draggable: false,
      connectable: false,
      selectable: true,
      focusable: true,
      width: NODE_WIDTH,
      height: NODE_HEIGHT,
    })),
    edges: stageEdges,
  };
}
