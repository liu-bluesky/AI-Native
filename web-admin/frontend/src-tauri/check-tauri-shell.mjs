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
  "src-tauri/src/bot/mod.rs",
  "src-tauri/src/bot/runtime.rs",
  "src-tauri/src/bot/types.rs",
  "src-tauri/src/bot/feishu.rs",
  "src-tauri/bot_workers/feishu_sdk_listener.py",
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
  "read_global_bot_connector_config_file",
  "write_global_bot_connector_config_file",
  "bot_start_local_chat",
  "bot_start_feishu_local_listener",
  "bot_stop_feishu_local_listener",
  "bot_list_feishu_local_listeners",
  "bot_reply_feishu_message",
  "bot_scan_feishu_chats",
  "bot_download_feishu_message_resource",
  "bot_get_feishu_message",
  "liuagent_prepare_agent_invocation",
  "record_runner_permission_decision",
  "list_runner_permission_decisions",
  "is_allowed_runner_command",
  "tauri::generate_handler!",
]);
await assertIncludes("src-tauri/tauri.conf.json", [
  '"withGlobalTauri": true',
  '"devUrl": "http://127.0.0.1:3000"',
  '"resources"',
  '"bot_workers/feishu_sdk_listener.py"',
]);
await assertIncludes("src/utils/native-desktop-bridge.js", [
  '@tauri-apps/api/core',
  '@tauri-apps/api/event',
  "invokeTauriCommand",
  "listenTauriEvent",
  "subscribeNativeLiuAgentRuntimeEvents",
  "liuagent-runtime-event",
  "liuagent://runtime-event",
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
  "read_global_bot_connector_config_file",
  "write_global_bot_connector_config_file",
  "bot_start_local_chat",
  "bot_start_feishu_local_listener",
  "bot_stop_feishu_local_listener",
  "bot_list_feishu_local_listeners",
  "bot_reply_feishu_message",
  "bot_scan_feishu_chats",
  "bot_download_feishu_message_resource",
  "bot_get_feishu_message",
  "liuagent_prepare_agent_invocation",
  "record_runner_permission_decision",
  "list_runner_permission_decisions",
  "classifyNativeRunnerCommand",
  "runNativeRunnerCommand",
  "readGlobalBotConnectorConfigFile",
  "writeGlobalBotConnectorConfigFile",
  "startNativeBotLocalChat",
  "startNativeFeishuLocalBotListener",
  "stopNativeFeishuLocalBotListener",
  "listNativeFeishuLocalBotListeners",
  "replyNativeFeishuBotMessage",
  "scanNativeFeishuBotChats",
  "downloadNativeFeishuMessageResource",
  "getNativeFeishuMessage",
  "prepareNativeLiuAgentInvocation",
  "prepareNativeExternalAgentLaunch",
  "startNativeExternalAgentSession",
  "getNativeExternalAgentSession",
  "listNativeExternalAgentSessions",
  "cancelNativeExternalAgentSession",
  "hardKillNativeExternalAgentSession",
  "removedNativeExternalAgentError",
  "recordNativeRunnerPermissionDecision",
  "listNativeRunnerPermissionDecisions",
  "listNativeWorkspaceFileChanges",
  "acceptNativeWorkspaceFileChange",
  "revertNativeWorkspaceFileChange",
]);
await assertIncludes("src/views/projects/ProjectChat.vue", [
  "startNativeLiuAgentLocalChat",
  "subscribeNativeLiuAgentRuntimeEvents",
  "startNativeLiuAgentRuntimeEventSubscription",
  "handleNativeLiuAgentRuntimeEvent",
  "localLiuAgentPermissionRequestFromChatResult",
  "message-process-entry",
  "chat-approval-banner--local-agent",
  "currentLocalLiuAgentPermissionPrompt",
  "readGlobalBotConnectorConfigFile",
  "startNativeBotLocalChat",
  "syncLocalFeishuBotListeners",
  "handleNativeFeishuLocalBotEvent",
  "replyNativeFeishuBotMessage",
  "buildLocalFeishuBotAttachments",
  "runtime_migration_status",
  "desktop_frontend_local_listener",
  "ElCheckboxGroup",
  "ElInput",
  "acceptReviewedWorkspaceFile",
  "revertReviewedWorkspaceFile",
]);
await assertIncludes("src/modules/project-chat/components/file-changes/FileChangesDrawer.vue", [
  "文件变更审查",
  "确认保存",
  "放弃修改",
  "撤回已保存",
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
