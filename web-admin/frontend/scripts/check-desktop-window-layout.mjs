import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { fileURLToPath } from "node:url";

const rootDir = resolve(fileURLToPath(new URL("..", import.meta.url)));
const read = (path) => readFileSync(resolve(rootDir, path), "utf8");

const layout = read("src/views/Layout.vue");
const desktopShell = read("src/components/DesktopSystemShell.vue");
const desktopWindowHost = read("src/components/DesktopWindowHost.vue");
const projectChat = read("src/views/projects/ProjectChat.vue");
const chatComposer = read("src/modules/project-chat/components/composer/ChatComposer.vue");
const tauriConfig = read("src-tauri/tauri.conf.json");

assert.match(
  desktopShell,
  /\.desktop-system__launcher\s*\{[^}]*left:\s*50%;[^}]*width:\s*min\(380px, calc\(100% - 32px\)\);[^}]*box-sizing:\s*border-box;[^}]*transform:\s*translateX\(-50%\);/,
  "desktop launcher must be centered inside its workspace with safe horizontal insets",
);
assert.doesNotMatch(
  desktopShell,
  /\.desktop-system__launcher\s*\{[^}]*left:\s*0;/,
  "desktop launcher must not remain anchored to the left edge",
);
assert.match(
  desktopShell,
  /const dockRevealed = ref\(false\);/,
  "desktop dock must start hidden until the user reaches its trigger area",
);
assert.match(
  desktopShell,
  /\.desktop-system__dock-trigger\s*\{[^}]*left:\s*50%;[^}]*width:\s*168px;[^}]*transform:\s*translateX\(-50%\);/,
  "desktop dock trigger must be limited to the centered bottom area",
);
assert.doesNotMatch(
  desktopShell,
  /\.desktop-system__dock-trigger\s*\{[^}]*left:\s*0;[^}]*right:\s*0;/,
  "desktop dock trigger must not capture the full bottom edge",
);
assert.match(
  layout,
  /function resolveCenteredWindowBounds\([\s\S]*?\(viewportWidth - sizedBounds\.width\) \/ 2[\s\S]*?\(viewportHeight - sizedBounds\.height\) \/ 2/,
  "desktop windows must calculate default coordinates from the viewport center",
);
assert.match(
  layout,
  /function createWindowForPath\([\s\S]*?const bounds = resolveCenteredWindowBounds\([\s\S]*?x: bounds\.x,[\s\S]*?y: bounds\.y,/,
  "fresh desktop windows must use centered bounds",
);
assert.match(
  layout,
  /function createRestoredWindow\([\s\S]*?x: rawWindow\?\.x \?\? defaultBounds\.x,[\s\S]*?y: rawWindow\?\.y \?\? defaultBounds\.y,/,
  "restored windows must preserve saved coordinates and center only missing coordinates",
);
assert.doesNotMatch(
  layout,
  /x:\s*36 \+ offset|y:\s*32 \+ offset/,
  "desktop windows must not use the old fixed left-biased defaults",
);
assert.match(
  layout,
  /<DesktopWindowHost[\s\S]*?:window-id="window\.id"[\s\S]*?:source-path="window\.sourcePath"/,
  "desktop windows must mount their application as a component host",
);
assert.doesNotMatch(
  layout,
  /<iframe\b|embeddedUrl|buildEmbeddedAppUrl|embeddedFrameListeners/,
  "desktop window content must not use the legacy iframe runtime",
);
assert.match(
  layout,
  /:key="`\$\{window\.id\}:\$\{window\.instanceKey \|\| 0\}`"/,
  "desktop window refresh must recreate the page component instance",
);
assert.match(
  desktopWindowHost,
  /provide\(routerKey, windowRouter\)/,
  "each desktop window must receive a local route adapter",
);
assert.match(
  desktopWindowHost,
  /component\n\s+:is="activeComponent"/,
  "each desktop window must render its page component directly",
);
assert.doesNotMatch(
  desktopWindowHost,
  /createApp\(|createDesktopWindowRouter\(|childApp\.mount\(/,
  "desktop windows must not create nested Vue apps or routers",
);
assert.doesNotMatch(
  projectChat,
  /chat-window-drop-overlay|is-file-dragover/,
  "project chat must not show a window-level file-drop overlay",
);
assert.match(
  chatComposer,
  /class="chat-input-wrapper"[\s\S]*?@dragenter\.prevent\.stop[\s\S]*?@drop\.prevent\.stop/,
  "only the chat input wrapper must accept file drops",
);
assert.match(
  projectChat,
  /function isBrowserFileDragEvent\(event\)/,
  "project chat must verify that browser drag events carry files",
);
assert.match(
  projectChat,
  /event\.dataTransfer\.dropEffect = "copy"/,
  "the accepted input drop zone must advertise the copy operation",
);
assert.match(
  tauriConfig,
  /"dragDropEnabled"\s*:\s*false/,
  "Tauri must leave file drag/drop to the HTML5 input drop zone",
);

console.log("desktop window layout contract check passed");
