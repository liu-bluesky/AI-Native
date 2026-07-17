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
  /supervision-search-card[\s\S]*execution-card/,
  "supervision page must keep only search and execution flow as its primary regions",
);
assert.doesNotMatch(
  pageSource,
  /supervision-hero|answer-list-panel|answer-summary-card|最近回答/,
  "supervision page must not restore removed hero, answer list, summary, or recent-answer UI",
);
assert.doesNotMatch(
  pageSource,
  /max-width:\s*1680px/,
  "supervision page must use the available desktop width without the old fixed cap",
);
assert.match(
  pageSource,
  /请输入回答 ID[\s\S]*本机监管库中没有找到该回答 ID/,
  "supervision search must require an answer ID and report exact misses",
);
assert.match(
  sqliteStoreSource,
  /model_input_tokens[\s\S]*model_output_tokens[\s\S]*model_total_tokens[\s\S]*model_token_source/,
  "SQLite supervision steps must store provider token usage separately from estimates",
);
assert.match(
  sqliteStoreSource,
  /model_name[\s\S]*provider_id[\s\S]*provider_name[\s\S]*agent_supervision_steps/,
  "SQLite supervision steps must persist structured model identity",
);
assert.match(
  pageSource,
  /当前模型[\s\S]*modelSummary\.names[\s\S]*供应商：[\s\S]*modelSummary\.providers/,
  "supervision must show the structured model name as a top title",
);
assert.match(
  pageSource,
  /storedName[\s\S]*step\?\.provider_name[\s\S]*providerNameById\.value\.get\(providerId\)/,
  "supervision must prefer the persisted provider name and recover old answers from the exact provider config",
);
assert.doesNotMatch(
  pageSource,
  /providers:\s*uniqueValues\("provider_id"\)/,
  "supervision supplier title must never display the provider id as its name",
);
assert.match(
  pageSource,
  /供应商：[\s\S]*未采集供应商名称/,
  "supervision must keep the supplier field visible when a real name is unavailable",
);
assert.match(
  pageSource,
  /fetchProjectChatProviders[\s\S]*provider\?\.id[\s\S]*provider\?\.name/,
  "supervision must use the same provider source as project chat for historical name recovery",
);
assert.match(
  projectChatSource,
  /providerName[\s\S]*providers\.value[\s\S]*item\?\.name\s*\|\|\s*""/,
  "project chat must resolve the provider display name from the exact local provider record",
);
assert.doesNotMatch(
  pageSource,
  /detail_preview[^\n]*(model_name|provider_id)|split\([^\n]*(provider=|model=)/,
  "supervision must not parse model identity from detail text",
);
assert.match(
  pageSource,
  /实际输入 Token[\s\S]*实际输出 Token[\s\S]*实际总 Token[\s\S]*Token 来源/,
  "supervision details must show actual provider token usage and its source",
);
assert.match(
  pageSource,
  /上下文 Token（预估）/,
  "supervision must label locally estimated context tokens explicitly",
);
assert.match(
  pageSource,
  /实际输入累计[\s\S]*实际输出累计[\s\S]*上下文输入累计（预估）/,
  "supervision must show answer-level actual token totals separately from estimates",
);
assert.match(
  pageSource,
  /全链路实际 Token/,
  "supervision must label the complete answer-level provider usage total",
);
assert.match(
  pageSource,
  /step_type[\s\S]*model_call[\s\S]*model_token_source[\s\S]*provider_response_usage/,
  "answer-level token totals must aggregate provider usage from model calls only",
);
assert.match(
  pageSource,
  /已采集实际 Token（非全量）/,
  "supervision must disclose incomplete provider usage coverage",
);
assert.match(
  pageSource,
  /actualRounds[\s\S]*modelRounds/,
  "supervision must show provider usage coverage by model round",
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
  /请求输入[\s\S]*上下文构建[\s\S]*规划与决策[\s\S]*执行循环[\s\S]*回答与结果/,
  "execution flow must expose five stable supervision stages",
);
assert.match(
  flowNodeSource,
  /contextMessageCount[\s\S]*contextInputTokens/,
  "execution cycle nodes must disclose their context size and token estimate",
);
assert.match(
  pageSource,
  /selectedContextMessages[\s\S]*本节点执行上下文/,
  "cycle details must render the context snapshot and token estimate",
);
assert.match(pageSource, /上下文 Token/, "cycle details must label the context token estimate");
assert.match(
  sqliteStoreSource,
  /context_snapshot_json[\s\S]*context_message_count[\s\S]*context_input_tokens[\s\S]*model_step_index/,
  "SQLite supervision steps must persist per-cycle context snapshots",
);
assert.match(
  projectChatSource,
  /agentExecutionCycles[\s\S]*contextSnapshot[\s\S]*toolCallIds/,
  "project chat must retain model cycles with their own context snapshots",
);
assert.match(
  sqliteStoreSource,
  /repair_supervision_projection_for_project/,
  "supervision queries must repair missing projections from SQLite runtime snapshots",
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
  { step_id: "context", step_type: "context_build", status: "completed", sort_order: 1, title: "上下文构建" },
  { step_id: "plan", step_type: "plan", status: "completed", sort_order: 2, title: "执行计划" },
  { step_id: "model", step_type: "model_call", status: "completed", sort_order: 3, title: "模型循环第 1 轮", model_step_index: 1, context_message_count: 8, context_input_tokens: 1200 },
  { step_id: "tool", step_type: "tool_call", status: "completed", sort_order: 4, title: "工具：read_file", model_step_index: 1, context_message_count: 8, context_input_tokens: 1200 },
  { step_id: "answer", step_type: "final_answer", status: "completed", sort_order: 5, title: "最终回答" },
];
const sampleEdges = sampleSteps.slice(1).map((step, index) => ({
  source_step_id: sampleSteps[index].step_id,
  target_step_id: step.step_id,
}));
const sampleFlow = await buildExecutionFlow(sampleSteps, sampleEdges);
assert.equal(sampleFlow.nodes.length, 7, "five main stages must include two execution cycle nodes");
assert.equal(sampleFlow.edges.length, 6, "main stages and cycle nodes must form one connected path");
assert.deepEqual(
  sampleFlow.nodes.slice(0, 5).map((node) => node.data.title),
  ["请求输入", "上下文构建", "规划与决策", "执行循环", "回答与结果"],
  "the five supervision stages must remain stable",
);
assert.equal(
  sampleFlow.nodes.filter((node) => node.data.nodeKind === "cycle").length,
  2,
  "execution must expose every model and tool node instead of collapsing the loop",
);
assert.ok(
  sampleFlow.nodes.some(
    (node) => node.data.contextMessageCount === 8 && node.data.contextInputTokens === 1200,
  ),
  "execution cycle nodes must retain their own context metrics",
);

console.log("agent supervision checks passed");
