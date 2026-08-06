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
  /fileChangesScopeMode[\s\S]*?visibleWorkspaceChangedFiles[\s\S]*?normalizeWorkspaceReviewPath/,
  "answer filtering must be an explicit scope mode instead of replacing the workspace list",
);
assert.match(
  projectChat,
  /function setMessageFileChangesScope[\s\S]*?fileChangesScopeMode\.value = "all"/,
  "opening an answer must default to the complete workspace change list",
);
assert.match(
  projectChat,
  /messageProcessEntryChangedFilePaths[\s\S]*?changed_files[\s\S]*?messageChangedFilePaths/,
  "answer file paths must come from successful file tool process logs",
);
const revealStart = projectChat.indexOf(
  "async function revealWorkspaceFileChangesAfterMutation",
);
const revealEnd = projectChat.indexOf(
  "function handleNativeLiuAgentRuntimeEvent",
  revealStart,
);
assert.ok(revealStart >= 0 && revealEnd > revealStart, "file change refresh helper must exist");
const revealSource = projectChat.slice(revealStart, revealEnd);
assert.doesNotMatch(
  revealSource,
  /fileChangesDialogVisible\.value\s*=\s*true/,
  "runtime file mutations must not automatically open the file changes drawer",
);
assert.doesNotMatch(
  revealSource,
  /setMessageFileChangesScope/,
  "runtime refresh must not silently switch the drawer into answer-only scope",
);
assert.match(
  projectChat,
  /watch\(fileChangesDialogVisible[\s\S]*?resetFileChangesScope/,
  "closing the drawer must clear the answer scope",
);
assert.match(
  projectChat,
  /@show-all="showAllWorkspaceFileChanges"[\s\S]*?@show-message="showMessageFileChangesOnly"/,
  "users must be able to switch explicitly between all files and answer-only files",
);

console.log("project chat file changes layout check passed");
