import {
  getLocalProject,
  getLocalProjectRelations,
  upsertLocalProject,
  updateLocalProjectRelations,
} from "@/services/local-project-repository.js";
import { readSelectedProjectId } from "@/modules/project-chat/services/projectChatStorage.js";
import {
  hasNativeDesktopBridge,
  readNativeWorkspaceFile,
  writeNativeWorkspaceFile,
} from "@/utils/native-desktop-bridge.js";

const MANAGED_BLOCK_PREFIX = "<!-- ai-employee:";

function cleanText(value) {
  return String(value || "").trim();
}

function normalizeLines(value) {
  return (Array.isArray(value) ? value : [])
    .map((item) => cleanText(item))
    .filter(Boolean);
}

function safeFileSegment(value, fallback) {
  const normalized = cleanText(value)
    .replace(/[<>:"/\\|?*\u0000-\u001F]/g, "-")
    .replace(/\s+/g, "-")
    .replace(/-+/g, "-")
    .replace(/^-+|-+$/g, "");
  return normalized || fallback;
}

function blockMarkers(kind, id) {
  const key = `${kind}:${id}`;
  return {
    start: `${MANAGED_BLOCK_PREFIX}${key}:start -->`,
    end: `${MANAGED_BLOCK_PREFIX}${key}:end -->`,
  };
}

function mergeManagedBlock(existingContent, kind, id, blockContent) {
  const existing = String(existingContent || "").trimEnd();
  const { start, end } = blockMarkers(kind, id);
  const nextBlock = `${start}\n${blockContent.trim()}\n${end}`;
  const startIndex = existing.indexOf(start);
  if (startIndex === -1) {
    return existing ? `${existing}\n\n${nextBlock}\n` : `${nextBlock}\n`;
  }
  const endIndex = existing.indexOf(end, startIndex);
  if (endIndex === -1) {
    throw new Error("本地定义文件中的 AI Employee 区块不完整，请先修复后再保存");
  }
  return `${existing.slice(0, startIndex)}${nextBlock}${existing.slice(endIndex + end.length)}\n`;
}

async function readDirectoryFile(directory, path) {
  try {
    const result = await readNativeWorkspaceFile({ workspacePath: directory, path });
    return String(result?.content || "");
  } catch (error) {
    const message = cleanText(error?.detail || error?.message || error);
    if (/不存在|not found|no such file/i.test(message)) return "";
    throw error;
  }
}

async function mergeDirectoryFile({ directory, path, kind, id, content }) {
  const current = await readDirectoryFile(directory, path);
  const merged = mergeManagedBlock(current, kind, id, content);
  return writeNativeWorkspaceFile({ workspacePath: directory, path, content: merged });
}

function renderList(items) {
  return items.length ? items.map((item) => `- ${item}`).join("\n") : "- 未配置";
}

function renderAgentDefinition(employee, skills, rules) {
  const title = cleanText(employee.name) || employee.id;
  return `# ${title}

## 基础信息
- ID: ${employee.id}
- 描述: ${cleanText(employee.description) || "未填写"}
- 核心目标: ${cleanText(employee.goal) || "未填写"}
- 语气: ${cleanText(employee.tone) || "professional"}
- 输出详略: ${cleanText(employee.verbosity) || "concise"}
- 语言: ${cleanText(employee.language) || "zh-CN"}

## 提示词与工作方式
### 风格提示
${renderList(normalizeLines(employee.style_hints))}

### 默认工作流
${renderList(normalizeLines(employee.default_workflow))}

### 工具使用策略
${cleanText(employee.tool_usage_policy) || "按任务需要选择已绑定技能，并遵循已绑定规则。"}

## 绑定技能
${renderList(skills.map((item) => `${cleanText(item.name) || item.id} (${item.id})`))}

## 绑定规则
${renderList(rules.map((item) => `${cleanText(item.title) || item.id} (${item.id})`))}`;
}

function renderSkillDefinition(skill, employee) {
  const name = cleanText(skill.name) || skill.id;
  const description = cleanText(skill.description || skill.content);
  return `# ${name}

## 说明
${description || "此技能由 AI Employee 本地智能体配置引用。"}

## 被智能体使用
- ${cleanText(employee.name) || employee.id} (${employee.id})`;
}

function renderRuleDefinition(rule, employee) {
  const title = cleanText(rule.title || rule.name) || rule.id;
  const content = cleanText(rule.content || rule.body || rule.description);
  return `# ${title}

## 领域
${cleanText(rule.domain) || "通用"}

## 规则正文
${content || "此规则由 AI Employee 本地智能体配置引用。"}

## 被智能体使用
- ${cleanText(employee.name) || employee.id} (${employee.id})`;
}

function resolveDirectories(projectId) {
  const project = getLocalProject(projectId) || {};
  const relations = getLocalProjectRelations(projectId);
  const settings = relations.chat_settings && typeof relations.chat_settings === "object"
    ? relations.chat_settings
    : {};
  const workspacePath = cleanText(project.workspace_path || relations.workspace_path);
  if (!workspacePath) {
    throw new Error("请先在 AI 对话中选择项目并配置项目工作区目录");
  }
  const defaultRoot = `${workspacePath.replace(/[\\/]+$/, "")}/.ai-employee`;
  const directories = {
    agent: cleanText(settings.agent_directory || project.agent_directory) || `${defaultRoot}/agents`,
    skill: cleanText(settings.skill_directory || project.skill_directory) || `${defaultRoot}/skills`,
    rule: cleanText(settings.rule_directory || project.rule_directory) || `${defaultRoot}/rules`,
  };
  return { project, relations, settings, directories };
}

export async function saveLocalAgentDirectoryResources({ employee, skills = [], rules = [] } = {}) {
  const id = cleanText(employee?.id);
  if (!id) throw new Error("缺少智能体 ID");
  if (!hasNativeDesktopBridge()) {
    throw new Error("本地目录同步仅支持桌面端，请在桌面应用中创建智能体");
  }

  const projectId = cleanText(employee?.project_id) || cleanText(readSelectedProjectId());
  if (!projectId) throw new Error("请先在 AI 对话中选择项目");
  const { project, relations, settings, directories } = resolveDirectories(projectId);
  const agentPath = `${safeFileSegment(id, "agent")}/AGENT.md`;
  const writtenAgent = await mergeDirectoryFile({
    directory: directories.agent,
    path: agentPath,
    kind: "agent",
    id,
    content: renderAgentDefinition(employee, skills, rules),
  });

  const writtenSkills = [];
  for (const skill of skills) {
    const skillId = cleanText(skill?.id);
    if (!skillId) continue;
    const path = `${safeFileSegment(skillId, "skill")}/SKILL.md`;
    await mergeDirectoryFile({
      directory: directories.skill,
      path,
      kind: "skill",
      id,
      content: renderSkillDefinition(skill, employee),
    });
    writtenSkills.push({ id: skillId, file_path: `${directories.skill}/${path}` });
  }

  const writtenRules = [];
  for (const rule of rules) {
    const ruleId = cleanText(rule?.id);
    if (!ruleId) continue;
    const path = `${safeFileSegment(ruleId, "rule")}.md`;
    await mergeDirectoryFile({
      directory: directories.rule,
      path,
      kind: "rule",
      id: `${ruleId}:${id}`,
      content: renderRuleDefinition(rule, employee),
    });
    writtenRules.push({ id: ruleId, file_path: `${directories.rule}/${path}` });
  }

  const projectEmployees = Array.isArray(relations.employees) ? relations.employees : [];
  const nextEmployee = {
    ...employee,
    project_id: projectId,
    directory_path: directories.agent,
    file_path: `${directories.agent}/${agentPath}`,
    updated_at: new Date().toISOString(),
  };
  updateLocalProjectRelations(projectId, {
    ...relations,
    employees: [...projectEmployees.filter((item) => cleanText(item?.id) !== id), nextEmployee],
    chat_settings: { ...settings, agent_directory: directories.agent, skill_directory: directories.skill, rule_directory: directories.rule },
    workspace_path: cleanText(project.workspace_path || relations.workspace_path),
  });
  upsertLocalProject({
    ...project,
    id: projectId,
    agent_directory: directories.agent,
    skill_directory: directories.skill,
    rule_directory: directories.rule,
  });

  return { employee: nextEmployee, writtenAgent, writtenSkills, writtenRules, directories };
}
