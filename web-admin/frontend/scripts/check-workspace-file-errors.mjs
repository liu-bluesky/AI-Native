import assert from "node:assert/strict";
import { isWorkspaceFileMissing } from "../src/utils/workspace-file-errors.js";

const missingErrors = [
  "No such file or directory (os error 2)",
  "The system cannot find the file specified. (os error 2)",
  "The system cannot find the path specified.",
  "系统找不到指定的文件。 (os error 2)",
  "系统找不到指定的路径。",
  { message: "ENOENT: no such file or directory" },
  { detail: "文件不存在" },
];

for (const error of missingErrors) {
  assert.equal(isWorkspaceFileMissing(error), true, String(error));
}

const otherErrors = [
  "Access is denied. (os error 5)",
  "Permission denied",
  "目标路径不是文件",
];

for (const error of otherErrors) {
  assert.equal(isWorkspaceFileMissing(error), false, String(error));
}

console.log("workspace file error checks passed");
