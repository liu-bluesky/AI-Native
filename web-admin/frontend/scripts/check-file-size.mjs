import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");

// 只做已登记大文件的回涨检查，不用固定行数硬限制驱动拆分。
// 是否拆分由职责边界、数据流深度、验证难度和 UI/CSS 风险共同决定。
const regressionBaselines = {
  "src/views/Layout.vue": 1133,
  "src/views/agent-templates/AgentTemplateList.vue": 1818,
  "src/views/employees/EmployeeForm.vue": 1084,
  "src/views/employees/EmployeeList.vue": 2123,
  "src/views/evolution/FeedbackTicketList.vue": 975,
  "src/views/llm/ModelProviderManager.vue": 1225,
  "src/views/projects/ProjectDetail.vue": 8739,
  "src/views/projects/ProjectChat.vue": 23809,
  "src/views/projects/ProjectList.vue": 995,
  "src/views/projects/ProjectVoiceLibrary.vue": 1056,
  "src/views/public/ChangelogPage.vue": 833,
  "src/views/public/IntroPage.vue": 3660,
  "src/views/public/MarketPage.vue": 1133,
  "src/views/skills/SkillDetail.vue": 1265,
  "src/views/system/DictionaryManager.vue": 819,
  "src/views/system/StatisticsDashboard.vue": 2789,
  "src/views/system/SystemConfig.vue": 3238,
  "src/views/tasks/TaskManager.vue": 918,
  "src/views/users/UserList.vue": 1026,
};

function walk(dir) {
  const entries = fs.readdirSync(dir, { withFileTypes: true });
  return entries.flatMap((entry) => {
    const filePath = path.join(dir, entry.name);
    if (entry.name === "node_modules" || entry.name === "dist") return [];
    if (entry.isDirectory()) return walk(filePath);
    if (!entry.isFile()) return [];
    return [filePath];
  });
}

function countLines(filePath) {
  const content = fs.readFileSync(filePath, "utf8");
  if (!content) return 0;
  return content.split(/\r?\n/).length;
}

function toRelative(filePath) {
  return path.relative(ROOT, filePath).split(path.sep).join("/");
}

const regressions = [];

for (const filePath of walk(path.join(ROOT, "src"))) {
  const relativePath = toRelative(filePath);
  const baseline = regressionBaselines[relativePath];
  if (!baseline) continue;
  const lineCount = countLines(filePath);
  if (lineCount > baseline) {
    regressions.push({
      path: relativePath,
      lineCount,
      baseline,
    });
  }
}

if (regressions.length) {
  console.error("File size regression check failed:");
  for (const item of regressions) {
    console.error(
      `- ${item.path}: ${item.lineCount} lines, baseline ${item.baseline}`,
    );
  }
  process.exit(1);
}

console.log("File size regression check passed.");
