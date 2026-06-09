import { access, readFile } from "node:fs/promises";
import { constants } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const __dirname = dirname(fileURLToPath(import.meta.url));
const frontendRoot = join(__dirname, "..");
const requiredFiles = [
  "src-tauri/tauri.conf.json",
  "src-tauri/Cargo.toml",
  "src-tauri/build.rs",
  "src-tauri/src/main.rs",
  "src/utils/native-desktop-bridge.js",
  "src/utils/workspace-picker.js",
];

async function assertFile(pathname) {
  const fullPath = join(frontendRoot, pathname);
  await access(fullPath, constants.R_OK);
  return fullPath;
}

async function assertIncludes(pathname, patterns) {
  const fullPath = await assertFile(pathname);
  const content = await readFile(fullPath, "utf8");
  for (const pattern of patterns) {
    if (!content.includes(pattern)) {
      throw new Error(`${pathname} missing ${pattern}`);
    }
  }
}

for (const file of requiredFiles) {
  await assertFile(file);
}

await assertIncludes("src-tauri/src/main.rs", [
  "pick_workspace_directory",
  "detect_executors",
  "get_runtime_info",
  "list_workspace_files",
  "read_workspace_file",
  "preview_workspace_diff",
  "prepare_workspace_file_write",
  "classify_runner_command",
  "run_runner_command",
  "prepare_external_agent_launch",
  "run_external_agent_once",
  "start_external_agent_session",
  "get_external_agent_session",
  "list_external_agent_sessions",
  "cancel_external_agent_session",
  "hard_kill_external_agent_session",
  "child_process_id",
  "configure_command_process_group",
  "signal_external_agent_process_tree",
  "try_lock",
  "write_external_agent_session_input",
  "EXTERNAL_AGENT_SESSION_EVENT",
  "ExternalAgentSessionEvent",
  "emit_external_agent_session_event",
  "external_agent_session_event_payload",
  "external_agent_session_minimal_snapshot",
  "native_pty_system",
  "openpty",
  "spawn_command",
  "start_external_agent_pipe_session",
  "spawn_external_agent_process_waiter",
  "process_child",
  "external_agent_uses_stdout_final_output",
  "--output-last-message",
  '"-z".to_string()',
  "read_external_agent_stdout_final_output",
  "--ephemeral",
  "final_output",
  "stdin_open",
  "record_runner_permission_decision",
  "list_runner_permission_decisions",
  "is_allowed_runner_command",
  "tauri::generate_handler!",
]);
await assertIncludes("src-tauri/tauri.conf.json", [
  '"withGlobalTauri": true',
  '"devUrl": "http://127.0.0.1:3000"',
]);
await assertIncludes("src/utils/native-desktop-bridge.js", [
  '@tauri-apps/api/core',
  '@tauri-apps/api/event',
  "invokeTauriCommand",
  "listenTauriEvent",
  "NATIVE_EXTERNAL_AGENT_SESSION_EVENT",
  "subscribeNativeExternalAgentSessionEvents",
  "isTauriRuntime",
  "__TAURI__",
  "__TAURI_INTERNALS__",
  "resolveNativeGlobals",
  "window.parent",
  "window.top",
  "pick_workspace_directory",
  "detect_executors",
  "getRuntimeInfo",
  "list_workspace_files",
  "read_workspace_file",
  "preview_workspace_diff",
  "prepare_workspace_file_write",
  "listNativeWorkspaceFiles",
  "readNativeWorkspaceFile",
  "previewNativeWorkspaceDiff",
  "prepareNativeWorkspaceFileWrite",
  "classify_runner_command",
  "run_runner_command",
  "prepare_external_agent_launch",
  "run_external_agent_once",
  "start_external_agent_session",
  "get_external_agent_session",
  "list_external_agent_sessions",
  "cancel_external_agent_session",
  "hard_kill_external_agent_session",
  "write_external_agent_session_input",
  "record_runner_permission_decision",
  "list_runner_permission_decisions",
  "classifyNativeRunnerCommand",
  "runNativeRunnerCommand",
  "prepareNativeExternalAgentLaunch",
  "runNativeExternalAgentOnce",
  "startNativeExternalAgentSession",
  "getNativeExternalAgentSession",
  "listNativeExternalAgentSessions",
  "cancelNativeExternalAgentSession",
  "hardKillNativeExternalAgentSession",
  "writeNativeExternalAgentSessionInput",
  "normalizeExternalAgentSessionEvent",
  "finalOutput",
  "stdinOpen",
  "recordNativeRunnerPermissionDecision",
  "listNativeRunnerPermissionDecisions",
]);
await assertIncludes("src/views/projects/ProjectChat.vue", [
  "buildNativeExternalAgentTaskPrompt",
  "用户本次任务：",
  "直接处理“用户本次任务”",
  "task_prompt_preview",
  "prompt: taskPrompt",
  "displayPrompt",
  "executionPrompt",
  "slashCommandKind",
  "attachmentNames",
  "<task-prompt>",
  "nativeExternalAgentInteractionFormJson",
  "submitNativeExternalAgentInteraction",
  "sendNativeExternalAgentInputContent",
  "subscribeNativeExternalAgentSessionEvents",
  "startNativeExternalAgentSessionEventSubscription",
  "stopNativeExternalAgentSessionEventSubscription",
  "handleNativeExternalAgentSessionEvent",
  "finalizeNativeExternalAgentSessionOnce",
  "nativeExternalAgentTerminalText",
  "nativeExternalAgentTerminalControls",
  "sendNativeExternalAgentControl",
  "runner-session-detail__terminal-output",
  "detectTerminalChoiceInteraction",
  "ElCheckboxGroup",
  "ElInput",
]);
await assertIncludes("src-tauri/Cargo.toml", [
  'name = "ai-employee-factory-desktop"',
  'tauri = { version = "2"',
]);

async function importNativeBridge(scenario) {
  return import(
    new URL(
      `../src/utils/native-desktop-bridge.js?contract-check=${scenario}-${Date.now()}`,
      import.meta.url,
    ),
  );
}

const originalWindow = globalThis.window;
try {
  const browserWindow = {};
  browserWindow.parent = browserWindow;
  browserWindow.top = browserWindow;
  globalThis.window = browserWindow;
  const browserBridge = await importNativeBridge("browser");
  if (browserBridge.hasNativeDesktopBridge()) {
    throw new Error("plain browser was incorrectly detected as Tauri");
  }

  const invokedCommands = [];
  const parentWindow = {
    isTauri: true,
    __TAURI__: {
      core: {
        async invoke(command) {
          invokedCommands.push(command);
          return {
            platform: "test-platform",
            arch: "test-arch",
            desktopBridgeVersion: "test-version",
          };
        },
      },
    },
  };
  globalThis.window = {
    parent: parentWindow,
    top: parentWindow,
  };
  const nativeBridge = await importNativeBridge("iframe");
  if (!nativeBridge.hasNativeDesktopBridge()) {
    throw new Error("iframe child failed to detect parent Tauri runtime");
  }
  const runtimeInfo = await nativeBridge.getNativeRuntimeInfo();
  if (
    runtimeInfo?.platform !== "test-platform" ||
    runtimeInfo?.arch !== "test-arch" ||
    runtimeInfo?.desktopBridgeVersion !== "test-version"
  ) {
    throw new Error("iframe child failed to invoke parent Tauri command");
  }
  if (!invokedCommands.includes("get_runtime_info")) {
    throw new Error("iframe child did not call get_runtime_info");
  }
} finally {
  if (originalWindow === undefined) {
    delete globalThis.window;
  } else {
    globalThis.window = originalWindow;
  }
}

console.log("tauri shell contract ok");
