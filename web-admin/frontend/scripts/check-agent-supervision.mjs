import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";

import { buildExecutionFlow } from "../src/modules/agent-supervision/utils/executionFlowLayout.js";

const scriptDir = dirname(fileURLToPath(import.meta.url));
const readSource = (path) => readFileSync(resolve(scriptDir, path), "utf8");

const sqliteStoreSource = readSource("../src-tauri/src/project_chat_store.rs");
const tauriMainSource = readSource("../src-tauri/src/main.rs");
const nativeBridgeSource = readSource("../src/utils/native-desktop-bridge.js");
const serviceSource = readSource(
  "../src/modules/agent-supervision/services/agentSupervisionStorage.js",
);
const pageSource = readSource("../src/views/desktop/AgentSupervision.vue");
const flowNodeSource = readSource(
  "../src/components/agent-supervision/ExecutionFlowNode.vue",
);
const flowLayoutSource = readSource(
  "../src/modules/agent-supervision/utils/executionFlowLayout.js",
);
const packageSource = readSource("../package.json");
const routerSource = readSource("../src/router/index.js");
const desktopShellSource = readSource("../src/utils/desktop-shell.js");
const projectChatSource = readSource("../src/views/projects/ProjectChat.vue");

for (const table of [
  "agent_supervision_answers",
  "agent_supervision_runs",
  "agent_supervision_steps",
  "agent_supervision_edges",
]) {
  assert.match(
    sqliteStoreSource,
    new RegExp(`CREATE TABLE IF NOT EXISTS ${table}`),
    `SQLite supervision schema must contain ${table}`,
  );
}

assert.match(
  sqliteStoreSource,
  /write_supervision_projection\s*\(/,
  "runtime writes must create the supervision projection",
);
assert.match(
  sqliteStoreSource,
  /agent_supervision_search_answers/,
  "SQLite store must expose answer search",
);
assert.match(
  sqliteStoreSource,
  /agent_supervision_get_answer/,
  "SQLite store must expose answer details",
);
assert.match(
  tauriMainSource,
  /project_chat_store::agent_supervision_search_answers/,
  "Tauri must register supervision answer search",
);
assert.match(
  tauriMainSource,
  /project_chat_store::agent_supervision_get_answer/,
  "Tauri must register supervision answer details",
);
assert.match(
  nativeBridgeSource,
  /agent_supervision_search_answers/,
  "native bridge must map supervision answer search",
);
assert.match(
  nativeBridgeSource,
  /agent_supervision_get_answer/,
  "native bridge must map supervision answer details",
);

assert.match(
  serviceSource,
  /searchNativeAgentSupervisionAnswers/,
  "supervision service must query the native SQLite bridge",
);
assert.match(
  serviceSource,
  /getNativeAgentSupervisionAnswer/,
  "supervision service must read details from the native SQLite bridge",
);
assert.doesNotMatch(
  `${serviceSource}\n${pageSource}`,
  /localStorage|sessionStorage|\/api\/|axios|fetch\s*\(/,
  "supervision must not use browser storage or server APIs",
);

assert.match(
  routerSource,
  /path:\s*['"]ai\/supervision['"]/,
  "router must expose the supervision page",
);
assert.match(
  routerSource,
  /normalizedPath\.startsWith\(['"]\/ai\/supervision['"]\)/,
  "router must allow the local supervision app in desktop offline mode",
);
assert.match(
  desktopShellSource,
  /id:\s*["']agent-supervision["']/,
  "desktop launcher must register the supervision app",
);
assert.match(
  desktopShellSource,
  /label:\s*["']智能体监管["']/,
  "desktop launcher must use the agreed menu name",
);
assert.match(
  pageSource,
  /<VueFlow/,
  "supervision page must render the execution graph with Vue Flow",
);
assert.doesNotMatch(
  pageSource,
  /echarts|GraphChart|buildGraphOption/,
  "supervision execution flow must not fall back to ECharts",
);
for (const dependency of [
  "@vue-flow/core",
  "@vue-flow/background",
  "@vue-flow/controls",
  "@vue-flow/minimap",
  "elkjs",
]) {
  assert.match(
    packageSource,
    new RegExp(`"${dependency.replace("/", "\\/")}"`),
    `supervision flow dependency must include ${dependency}`,
  );
}
assert.match(
  pageSource,
  /fetchAllVisibleProjects/,
  "supervision project selector must use the same project source as project chat",
);
assert.match(
  pageSource,
  /<el-select[\s\S]*v-model="projectId"/,
  "supervision must select a project from a dropdown",
);
assert.match(
  pageSource,
  /<MiniMap[\s\S]*pannable[\s\S]*zoomable/,
  "execution flow must provide a navigable minimap",
);
assert.match(
  pageSource,
  /<Controls[\s\S]*show-interactive="false"/,
  "execution flow must provide zoom and fit controls without edit actions",
);
assert.match(
  flowLayoutSource,
  /"elk\.algorithm": "layered"[\s\S]*"elk\.direction": "DOWN"/,
  "execution flow must use ELK layered vertical layout",
);
assert.match(
  flowLayoutSource,
  /输入与上下文准备[\s\S]*运行事件与状态[\s\S]*模型调用/,
  "execution flow must group low-level events into readable stages",
);
assert.match(
  flowNodeSource,
  /eventCount > 1[\s\S]*个原始事件/,
  "execution stage nodes must disclose grouped raw event counts",
);
assert.match(
  pageSource,
  /selectedGroupSteps[\s\S]*阶段内原始事件/,
  "grouped stages must keep every raw event inspectable in the detail panel",
);
assert.match(
  sqliteStoreSource,
  /repair_supervision_projection_for_project/,
  "supervision queries must repair missing projections from SQLite runtime snapshots",
);
assert.match(
  pageSource,
  /仅查询桌面本地 SQLite/,
  "supervision page must state its local-only data boundary",
);
assert.match(
  projectChatSource,
  /查看执行监管/,
  "assistant answers must link to supervision details",
);
assert.match(
  projectChatSource,
  /appId:\s*["']agent-supervision["']/,
  "chat entry must open the supervision desktop app",
);

const sampleSteps = [
  { step_id: "request", step_type: "request", status: "completed", sort_order: 0, title: "用户问题" },
  { step_id: "goal", step_type: "observation", status: "completed", sort_order: 1, title: "本轮目标" },
  { step_id: "context", step_type: "observation", status: "completed", sort_order: 2, title: "提炼本轮执行需要的历史信息" },
  { step_id: "model-start", step_type: "model_call", status: "completed", sort_order: 3, title: "模型步骤 1 请求中" },
  { step_id: "model-end", step_type: "model_call", status: "completed", sort_order: 4, title: "模型步骤 1 已完成" },
  { step_id: "answer", step_type: "final_answer", status: "completed", sort_order: 5, title: "最终回答" },
];
const sampleEdges = sampleSteps.slice(1).map((step, index) => ({
  source_step_id: sampleSteps[index].step_id,
  target_step_id: step.step_id,
}));
const sampleFlow = await buildExecutionFlow(sampleSteps, sampleEdges);
assert.equal(sampleFlow.nodes.length, 4, "low-level preparation and model events must collapse into stages");
assert.equal(sampleFlow.edges.length, 3, "collapsed stages must preserve a connected execution path");
assert.deepEqual(
  sampleFlow.nodes.map((node) => node.data.eventCount),
  [1, 2, 2, 1],
  "stage nodes must retain their raw event counts",
);
for (let index = 1; index < sampleFlow.nodes.length; index += 1) {
  assert.ok(
    sampleFlow.nodes[index].position.y > sampleFlow.nodes[index - 1].position.y,
    "ELK must place execution stages in readable top-to-bottom order",
  );
}

console.log("agent supervision checks passed");
