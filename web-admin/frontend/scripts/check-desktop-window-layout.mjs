import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { fileURLToPath } from "node:url";

const rootDir = resolve(fileURLToPath(new URL("..", import.meta.url)));
const read = (path) => readFileSync(resolve(rootDir, path), "utf8");

const layout = read("src/views/Layout.vue");
const desktopShell = read("src/components/DesktopSystemShell.vue");

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

console.log("desktop window layout contract check passed");
