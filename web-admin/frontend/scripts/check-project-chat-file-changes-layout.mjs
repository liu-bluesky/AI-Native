import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const scriptDir = dirname(fileURLToPath(import.meta.url));
const projectChat = readFileSync(
  resolve(scriptDir, "../src/views/projects/ProjectChat.vue"),
  "utf8",
);
const composerStart = projectChat.indexOf("<ChatComposer");
const contextBarStart = projectChat.indexOf("<ChatContextBar");
const messageActionsStart = projectChat.indexOf('class="message-actions"');

assert.ok(contextBarStart >= 0, "ProjectChat must render ChatContextBar");
assert.ok(composerStart >= 0, "ProjectChat must render ChatComposer");
assert.ok(messageActionsStart >= 0, "ProjectChat must render message actions");
assert.doesNotMatch(
  projectChat,
  /class="file-changes-trigger"/,
  "file changes must not render as a standalone row in the composer flow",
);
assert.doesNotMatch(
  projectChat.slice(contextBarStart, composerStart),
  /open-file-changes|show-file-changes|pending-file-change-count/,
  "the page context bar must not own the file changes action",
);
assert.match(
  projectChat.slice(messageActionsStart, composerStart),
  /message-file-changes-link[\s\S]*?openMessageFileChanges\(item\)/,
  "each assistant answer must expose its own file changes action",
);
assert.match(
  projectChat,
  /activeFileChangesPaths[\s\S]*?visibleWorkspaceChangedFiles[\s\S]*?normalizeWorkspaceReviewPath/,
  "the drawer must filter review items by the active answer paths",
);
assert.match(
  projectChat,
  /messageProcessEntryChangedFilePaths[\s\S]*?changed_files[\s\S]*?messageChangedFilePaths/,
  "answer file paths must come from successful file tool process logs",
);
assert.match(
  projectChat,
  /\["write_file", "apply_patch", "delete_file"\]\.includes\(toolName\)[\s\S]*?revealWorkspaceFileChangesAfterMutation/,
  "successful file tools must refresh and reveal the review drawer",
);

console.log("project chat file changes layout check passed");
