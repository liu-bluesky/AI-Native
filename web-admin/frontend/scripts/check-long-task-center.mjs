import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const scriptDir = dirname(fileURLToPath(import.meta.url));
const read = (path) => readFileSync(resolve(scriptDir, path), "utf8");
const store = read("../src/utils/local-ai-task-store.js");
const taskManager = read("../src/views/tasks/TaskManager.vue");
const projectChat = read("../src/views/projects/ProjectChat.vue");
const desktopWindowHost = read("../src/components/DesktopWindowHost.vue");
const desktopSystemShell = read("../src/components/DesktopSystemShell.vue");

assert.match(store, /const LONG_RUNNING_TASK_KIND = "long_running"/);
assert.match(store, /if \(!isLongRunningLocalAiTask\(task\)\) return false/);
assert.match(store, /options\.longTaskOnly/);
assert.match(taskManager, /listLocalAiTasks\(\{ longTaskOnly: true \}\)/);
assert.match(
  taskManager,
  /listLocalAiTasks\(\{ activeOnly: true, longTaskOnly: true \}\)/,
);
assert.match(projectChat, /function isLongRunningLocalAiTaskRequest/);
assert.match(projectChat, /taskKind: "long_running"/);
assert.match(projectChat, /const localTask = shouldTrackLongTask/);
assert.doesNotMatch(
  projectChat,
  /settings-center-stage__body settings-center-stage__body--chat"\s+@wheel\.stop/,
);
assert.match(
  desktopWindowHost,
  /\.desktop-window-host__mount\s*\{[^}]*overflow-y:\s*auto;[^}]*scrollbar-gutter:\s*stable;/s,
);
assert.match(
  desktopWindowHost,
  /\.desktop-window-host__mount--chat\s*\{[^}]*overflow:\s*hidden;/s,
);
assert.match(
  desktopSystemShell,
  /\.desktop-system__window-frame\s*\{[^}]*height:\s*100%;[^}]*min-height:\s*0;[^}]*overflow:\s*hidden;/s,
);
assert.match(taskManager, /\.task-manager\s*\{[^}]*overflow:\s*visible;/s);

console.log("long task center checks passed");
