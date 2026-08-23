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
const nativeDesktopBridge = read("src/utils/native-desktop-bridge.js");

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
  "desktop window refresh must recreate the child application instance",
);
assert.match(
  desktopWindowHost,
  /createDesktopWindowRouter\(props\.windowId\)/,
  "each desktop window must receive an isolated memory router",
);
assert.match(
  desktopWindowHost,
  /childApp\.unmount\(\)/,
  "closing a desktop window must unmount its child application",
);
assert.match(
  layout,
  /subscribeNativeDesktopDragDrop\(handleNativeDesktopDragDrop\)/,
  "the desktop shell must own the native file drop subscription",
);
assert.match(
  layout,
  /new CustomEvent\(DESKTOP_WINDOW_FILE_DRAG_DROP_EVENT_NAME/,
  "the desktop shell must forward native drops to the target window",
);
assert.match(
  projectChat,
  /DESKTOP_WINDOW_FILE_DRAG_DROP_EVENT_NAME/,
  "project chat must receive directed desktop drop events",
);
assert.match(
  projectChat,
  /targetWindowId !== desktopWindowId/,
  "project chat must ignore drops that belong to another desktop window",
);
assert.match(
  projectChat,
  /readNativeLocalFile\(normalizedPath\)/,
  "project chat must convert native file paths into browser File data",
);
assert.match(
  nativeDesktopBridge,
  /getCurrentWebviewWindow\(\)\.onDragDropEvent/,
  "the native bridge must subscribe to Tauri WebviewWindow drag-drop events",
);
assert.match(
  nativeDesktopBridge,
  /getCurrentWebview\(\)\.onDragDropEvent/,
  "the native bridge must subscribe to Tauri Webview drag-drop events",
);
assert.match(
  nativeDesktopBridge,
  /getCurrentWindow\(\)\.onDragDropEvent/,
  "the native bridge must still subscribe through Tauri's window drag-drop API",
);
assert.match(
  nativeDesktopBridge,
  /export function nativeDragDropCssPoints/,
  "the native bridge must convert physical drag coordinates into CSS pixels",
);
assert.match(
  layout,
  /nativeDragDropCssPoints\(payload\?\.position\)/,
  "the desktop shell must hit-test native drops with CSS pixels",
);
assert.match(
  layout,
  /fileDropWindowId/,
  "the desktop shell must expose the current file-drop target window",
);
assert.match(
  desktopShell,
  /is-file-drop-target/,
  "the desktop window chrome must highlight the file-drop target",
);
assert.match(
  desktopShell,
  /desktop-system__window-drop-overlay/,
  "the desktop window chrome must show a window-level drop overlay",
);
assert.doesNotMatch(
  projectChat,
  /positionMatchesInput/,
  "project chat must accept native file drops anywhere in the window",
);
assert.match(
  projectChat,
  /chat-window-drop-overlay/,
  "project chat must show a window-level drop overlay",
);
assert.match(
  projectChat,
  /subscribeNativeDesktopDragDrop/,
  "project chat must subscribe to native drag-drop events even inside a desktop window",
);
assert.match(
  projectChat,
  /nativeDragHitsThisChat/,
  "project chat must hit-test native drops against its own window",
);
assert.match(
  layout,
  /lastNativeDragDropWindowId \|\|\s*activeWindowId\.value/,
  "desktop shell must keep the last hovered window when drop coordinates miss",
);
assert.match(
  layout,
  /desktopWindows\.value\.find\(\(item\) => !item\.minimized\)\?\.id/,
  "desktop shell must fall back to the first visible window when no drag target is known",
);
assert.match(
  nativeDesktopBridge,
  /tauri:\/\/drag-enter/,
  "the native bridge must subscribe to raw Tauri drag-enter events",
);
assert.match(
  nativeDesktopBridge,
  /kind:\s*"AnyLabel"/,
  "the native bridge must listen with AnyLabel so WebviewWindow drag events match",
);
assert.match(
  nativeDesktopBridge,
  /Math\.abs\(point\.x\) < 0\.5 && Math\.abs\(point\.y\) < 0\.5/,
  "the native bridge must treat origin coordinates as an unknown drag position",
);
assert.match(
  nativeDesktopBridge,
  /const NATIVE_DRAG_LEAVE_GRACE_MS = 180/,
  "the native bridge must delay native leave so window/webview leave cannot clear the overlay in the same frame",
);
assert.match(
  projectChat,
  /if \(!points\.length\) return true;/,
  "project chat must treat unknown native drag coordinates as a hit",
);
assert.match(
  projectChat,
  /if \(!hits\) \{\s*return;/,
  "project chat must not clear the drop overlay when another window owns the drag",
);
assert.match(
  desktopShell,
  /grid-area:\s*1 \/ 1 \/ -1 \/ -1/,
  "the desktop window drop overlay must cover the full window grid",
);

console.log("desktop window layout contract check passed");
