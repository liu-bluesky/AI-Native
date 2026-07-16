import assert from "node:assert/strict";
import { existsSync, readFileSync } from "node:fs";
import { resolve } from "node:path";
import { fileURLToPath } from "node:url";

const rootDir = resolve(fileURLToPath(new URL("..", import.meta.url)));
const read = (path) => readFileSync(resolve(rootDir, path), "utf8");

const projectChat = read("src/views/projects/ProjectChat.vue");
const globalAssistant = read("src/components/GlobalAiAssistant.vue");
const projectWorkLog = read("src/views/desktop/ProjectWorkLog.vue");
const desktopRuntime = read("src/utils/desktop-agent-runtime.js");
const desktopRuntimePaths = read("src-tauri/src/liuagent_core/paths.rs");
const backendConfig = read("../api/core/config.py");
const backendProjects = read("../api/routers/projects.py");
const backendOrchestratorFactory = read("../api/services/runtime/orchestrator_factory.py");
const backendToolExecutor = read("../api/services/tool_executor.py");

assert.equal(
  existsSync(resolve(rootDir, "../api/services/agent_runtime")),
  false,
  "backend agent runtime source must be removed after desktop migration",
);

assert.match(
  projectChat,
  /async function doSend[\s\S]*await sendLocalLiuAgentChatRequest\(/,
  "project chat must execute new turns through the desktop liuAgent runtime",
);
assert.match(
  projectChat,
  /async function sendGlobalChatWithoutProject[\s\S]*await sendLocalLiuAgentChatRequest\(/,
  "project chat without a selected project must use the desktop liuAgent runtime",
);
assert.doesNotMatch(
  projectChat,
  /api\.post\(["']\/projects\/chat\/global["']/,
  "ProjectChat must not route text generation through the backend global agent",
);
assert.match(
  projectChat,
  /LOCAL_LIUAGENT_TRUSTED_WORKSPACES_STORAGE_KEY/,
  "desktop workspace trust must be stored locally",
);
assert.match(
  projectChat,
  /local_liuagent_allow_always/,
  "desktop permission UI must provide a persistent workspace trust action",
);
assert.doesNotMatch(
  projectChat,
  /trustAgentRuntimeWorkspaceRequest/,
  "desktop workspace trust must not call the backend agent runtime API",
);

assert.match(
  globalAssistant,
  /runGlobalAssistantLocalChat[\s\S]*startNativeLiuAgentLocalChat\(/,
  "global assistant text generation must use the desktop liuAgent runtime",
);
assert.match(
  globalAssistant,
  /subscribeNativeLiuAgentRuntimeEvents/,
  "global assistant must subscribe to desktop runtime events",
);
assert.match(
  globalAssistant,
  /pauseNativeLiuAgentLocalChat/,
  "global assistant stop action must pause the desktop runtime",
);
assert.match(
  globalAssistant,
  /recoverNativeLiuAgentRuntimeState/,
  "global assistant must recover desktop runtime state before continuation",
);

assert.match(
  projectWorkLog,
  /runDesktopAgentTextTask\(/,
  "project work-log AI summaries must use the desktop agent runtime",
);
assert.doesNotMatch(
  projectWorkLog,
  /api\.post\(["']\/projects\/chat\/global["']/,
  "project work-log AI summaries must not use the backend global agent",
);

assert.match(
  desktopRuntime,
  /startNativeLiuAgentLocalChat\(/,
  "shared desktop task helper must invoke the native liuAgent runtime",
);
assert.match(
  desktopRuntime,
  /\/desktop-runtime/,
  "shared desktop task helper must resolve desktop model credentials",
);
assert.match(
  desktopRuntimePaths,
  /DESKTOP_RUNTIME_DIR_NAME: &str = "desktop-agent-runtime"/,
  "desktop runtime data must use an isolated storage namespace",
);
assert.match(
  desktopRuntimePaths,
  /MIGRATION_MARKER_FILE/,
  "legacy desktop runtime data migration must be versioned and idempotent",
);
const desktopLegacyEntries = desktopRuntimePaths.match(
  /const DESKTOP_OWNED_LEGACY_ENTRIES:[\s\S]*?= &\[([\s\S]*?)\];/,
)?.[1] || "";
assert.doesNotMatch(
  desktopLegacyEntries,
  /"task-runs"|"events"|"transcripts"|"permissions"/,
  "desktop migration must not copy backend-owned runtime records",
);
assert.match(
  desktopRuntimePaths,
  /copy_legacy_desktop_permission_files[\s\S]*metadata\.is_file\(\)/,
  "legacy permission migration must copy only desktop session files, not backend subdirectories",
);
assert.doesNotMatch(
  backendConfig,
  /BACKEND_AGENT_RUNTIME_NEW_RUNS_ENABLED|AGENT_RUNTIME_STALE_RUN/,
  "backend runtime feature flags must be removed",
);
assert.equal(
  (backendProjects.match(/_backend_agent_runtime_new_runs_enabled\(\)/g) || []).length,
  5,
  "all four retired backend entry points must remain blocked",
);
assert.doesNotMatch(
  backendOrchestratorFactory,
  /services\.agent_runtime/,
  "backend orchestrator boundary must not import removed runtime code",
);
assert.match(
  backendOrchestratorFactory,
  /BackendAgentRuntimeRetiredError/,
  "backend orchestrator boundary must reject retired execution paths",
);
assert.doesNotMatch(
  backendToolExecutor,
  /agent_runtime\.builtin_tools|execute_builtin_tool|is_local_builtin_tool/,
  "backend ToolExecutor must not retain Python builtin tool fallbacks",
);

console.log("desktop agent migration contract check passed");
