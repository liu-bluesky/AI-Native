import {
  getLocalProject,
  getLocalProjectRelations,
  upsertLocalProject,
  updateLocalProjectRelations,
} from "@/services/local-project-repository.js";
import { readSelectedProjectId } from "@/modules/project-chat/services/projectChatStorage.js";
import {
  hasNativeDesktopBridge,
  deleteNativeWorkspaceFile,
  listNativeWorkspaceFiles,
  readNativeWorkspaceFile,
  writeNativeWorkspaceFile,
} from "@/utils/native-desktop-bridge.js";
import { isWorkspaceFileMissing } from "@/utils/workspace-file-errors.js";

const MANAGED_BLOCK_PREFIX = "<!-- ai-employee:";
const AGENT_METADATA_PREFIX = "<!-- ai-employee:agent-metadata:";

function encodeAgentMetadata(value) {
  try {
    return encodeURIComponent(JSON.stringify(value));
  } catch {
    return "";
  }
}

function decodeAgentMetadata(value) {
  try {
    const decoded = JSON.parse(decodeURIComponent(String(value || "")));
    return decoded && typeof decoded === "object" && !Array.isArray(decoded)
      ? decoded
      : null;
  } catch {
    return null;
  }
}

function cleanText(value) {
  if (value == null) return "";
  if (typeof value === "string") return value.trim();
  if (typeof value === "number" || typeof value === "boolean") {
    return String(value);
  }
  if (Array.isArray(value)) {
    return value.map(cleanText).filter(Boolean).join("\n");
  }
  try {
    return JSON.stringify(value, null, 2);
  } catch {
    return "";
  }
}

function isObjectString(value) {
  return value === "[object Object]";
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
    if (isWorkspaceFileMissing(error)) return "";
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

function renderContent(value, fallback = "") {
  const text = cleanText(value);
  return !text || isObjectString(text) ? fallback : text;
}

function renderAgentDefinition(employee, skills, rules) {
  const title = cleanText(employee.name) || employee.id;
  const metadata = encodeAgentMetadata({
    version: 1,
    agent: employee,
    skill_ids: skills.map((item) => cleanText(item?.id)).filter(Boolean),
    rule_ids: rules.map((item) => cleanText(item?.id)).filter(Boolean),
  });
  return `${metadata ? `${AGENT_METADATA_PREFIX}${metadata} -->\n` : ""}# ${title}

## 基础信息
- ID: ${employee.id}
- 角色: ${cleanText(employee.role) || "未指定"}
- 描述: ${cleanText(employee.description) || "未填写"}
- 核心目标: ${cleanText(employee.goal) || "未填写"}
- 语气: ${cleanText(employee.tone) || "professional"}
- 输出详略: ${cleanText(employee.verbosity) || "concise"}
- 语言: ${cleanText(employee.language) || "zh-CN"}

## 提示词与工作方式
### 执行指令
${renderList(normalizeLines(employee.instructions))}

### 风格提示
${renderList(normalizeLines(employee.style_hints))}

### 默认工作流
${renderList(normalizeLines(employee.default_workflow))}

### 工具使用策略
${renderContent(employee.tool_usage_policy, "按任务需要选择已绑定技能，并遵循已绑定规则。")}

## 绑定技能
${renderList(skills.map((item) => `${cleanText(item.name) || item.id} (${item.id})`))}

## 绑定规则
${renderList(rules.map((item) => `${cleanText(item.title) || item.id} (${item.id})`))}`;
}

function renderSkillDefinition(skill, employee) {
  const name = cleanText(skill.name) || skill.id;
  const markdown = cleanText(
    skill.markdown ||
      skill.content ||
      skill.definition ||
      skill.instructions ||
      skill.description,
  );
  if (!markdown) {
    const error = new Error(`技能「${name}」缺少独立 Markdown 内容`);
    error.code = "employee.skill_markdown_missing";
    error.recoverable = true;
    error.skill = {
      id: cleanText(skill?.id),
      name,
    };
    throw error;
  }
  return markdown;
}

function renderRuleDefinition(rule, employee) {
  const title = cleanText(rule.title || rule.name) || rule.id;
  const content = renderContent(rule.content || rule.body || rule.description);
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

function parseListItemIds(content, heading) {
  const section = String(content || "").match(
    new RegExp(`## ${heading}\\s*\\n([\\s\\S]*?)(?=\\n## |$)`, "i"),
  );
  if (!section) return [];
  return String(section[1] || "")
    .split("\n")
    .map((line) => line.match(/\(([^()]+)\)\s*$/)?.[1] || "")
    .map(cleanText)
    .filter(Boolean);
}

function parseLegacyAgentDefinition(content, fallbackId) {
  const readField = (label) =>
    cleanText(
      String(content || "").match(
        new RegExp(`^- ${label}:\\s*(.+)$`, "m"),
      )?.[1],
    );
  const title = cleanText(String(content || "").match(/^#\s+(.+)$/m)?.[1]);
  return {
    id: readField("ID") || fallbackId,
    name: title || fallbackId,
    role: readField("角色"),
    description: readField("描述") === "未填写" ? "" : readField("描述"),
    goal: readField("核心目标") === "未填写" ? "" : readField("核心目标"),
    tone: readField("语气") || "professional",
    verbosity: readField("输出详略") || "concise",
    language: readField("语言") || "zh-CN",
    skills: parseListItemIds(content, "绑定技能"),
    rules: parseListItemIds(content, "绑定规则"),
  };
}

function parseAgentDefinition(content, fallbackId) {
  const marker = String(content || "").match(
    /<!--\s*ai-employee:agent-metadata:([\s\S]*?)\s*-->/i,
  );
  const metadata = decodeAgentMetadata(marker?.[1]);
  const agent = metadata?.agent;
  if (agent && typeof agent === "object" && !Array.isArray(agent)) {
    return {
      ...agent,
      id: cleanText(agent.id) || fallbackId,
      skills: Array.isArray(agent.skills)
        ? agent.skills.map(cleanText).filter(Boolean)
        : Array.isArray(metadata.skill_ids)
          ? metadata.skill_ids.map(cleanText).filter(Boolean)
          : [],
      rules: Array.isArray(agent.rules)
        ? agent.rules.map(cleanText).filter(Boolean)
        : Array.isArray(metadata.rule_ids)
          ? metadata.rule_ids.map(cleanText).filter(Boolean)
          : [],
    };
  }
  return parseLegacyAgentDefinition(content, fallbackId);
}

function agentIndexRecord(agent) {
  return {
    id: cleanText(agent?.id),
    name: cleanText(agent?.name),
    description: cleanText(agent?.description),
    project_id: cleanText(agent?.project_id),
    directory_path: cleanText(agent?.directory_path),
    file_path: cleanText(agent?.file_path),
    updated_at: cleanText(agent?.updated_at),
  };
}

function sameAgentIndex(left, right) {
  return JSON.stringify(left || []) === JSON.stringify(right || []);
}

function repairLocalAgentIndex(projectId, agents, relations = {}) {
  const normalizedProjectId = cleanText(projectId);
  const index = agents.map(agentIndexRecord).filter((item) => item.id);
  const currentIndex = Array.isArray(relations.agent_index)
    ? relations.agent_index.map(agentIndexRecord).filter((item) => item.id)
    : [];
  const selectedIds = Array.isArray(relations?.chat_settings?.selected_employee_ids)
    ? relations.chat_settings.selected_employee_ids.map(cleanText).filter(Boolean)
    : [];
  const availableIds = new Set(index.map((item) => item.id));
  const nextSelectedIds = selectedIds.filter((id) => availableIds.has(id));
  const legacyEmployees = Array.isArray(relations.employees) ? relations.employees : [];
  if (
    sameAgentIndex(index, currentIndex) &&
    !legacyEmployees.length &&
    JSON.stringify(nextSelectedIds) === JSON.stringify(selectedIds)
  ) {
    return;
  }
  updateLocalProjectRelations(normalizedProjectId, {
    ...relations,
    agent_index: index,
    employees: [],
    chat_settings: {
      ...(relations.chat_settings || {}),
      selected_employee_ids: nextSelectedIds,
    },
  });
}

export function getLocalAgentDirectories(projectId) {
  return resolveDirectories(projectId).directories;
}

export async function listLocalProjectAgents({ projectId = "" } = {}) {
  const resolvedProjectId = cleanText(projectId) || cleanText(readSelectedProjectId());
  if (!resolvedProjectId) return [];
  const { relations, directories } = resolveDirectories(resolvedProjectId);
  if (!hasNativeDesktopBridge()) return [];

  let items = [];
  try {
    const listing = await listNativeWorkspaceFiles({ workspacePath: directories.agent });
    items = Array.isArray(listing?.items) ? listing.items : [];
  } catch (error) {
    if (!/目录不存在|not exist|no such file/i.test(String(error?.message || error))) {
      throw error;
    }
  }
  const agents = [];
  for (const item of items) {
    if (String(item?.kind || "") !== "directory") continue;
    const directoryId = safeFileSegment(item?.name, "agent");
    try {
      const file = await readNativeWorkspaceFile({
        workspacePath: directories.agent,
        path: `${directoryId}/AGENT.md`,
      });
      const agent = parseAgentDefinition(file?.content, directoryId);
      const id = cleanText(agent?.id);
      if (!id) continue;
      agents.push({
        ...agent,
        id,
        project_id: resolvedProjectId,
        directory_path: directories.agent,
        file_path: `${directories.agent.replace(/[\\/]+$/, "")}/${directoryId}/AGENT.md`,
        updated_at: cleanText(agent?.updated_at) || new Date(item?.modifiedAtEpochMs || item?.modified_at_epoch_ms || Date.now()).toISOString(),
      });
    } catch (error) {
      if (!isWorkspaceFileMissing(error)) {
        console.warn("读取项目智能体定义失败", error);
      }
    }
  }
  agents.sort((left, right) => cleanText(left.name).localeCompare(cleanText(right.name), "zh-CN"));
  repairLocalAgentIndex(resolvedProjectId, agents, relations);
  return agents;
}

export async function updateLocalProjectAgent(agentId, patch = {}, { projectId = "" } = {}) {
  const id = cleanText(agentId);
  if (!id) throw new Error("缺少智能体 ID");
  const resolvedProjectId = cleanText(projectId) || cleanText(readSelectedProjectId());
  const agents = await listLocalProjectAgents({ projectId: resolvedProjectId });
  const existing = agents.find((item) => cleanText(item?.id) === id);
  if (!existing) throw new Error("项目目录中未找到该智能体定义");
  const { directories } = resolveDirectories(resolvedProjectId);
  const directoryId = cleanText(existing.file_path)
    .replace(/\\/g, "/")
    .split("/")
    .slice(-2, -1)[0];
  if (!directoryId) throw new Error("智能体定义路径无效");
  const next = {
    ...existing,
    ...(patch && typeof patch === "object" ? patch : {}),
    id,
    project_id: resolvedProjectId,
    updated_at: new Date().toISOString(),
  };
  await mergeDirectoryFile({
    directory: directories.agent,
    path: `${directoryId}/AGENT.md`,
    kind: "agent",
    id,
    content: renderAgentDefinition(
      next,
      (Array.isArray(next.skills) ? next.skills : []).map((skillId) => ({ id: skillId })),
      (Array.isArray(next.rules) ? next.rules : []).map((ruleId) => ({ id: ruleId })),
    ),
  });
  return (await listLocalProjectAgents({ projectId: resolvedProjectId })).find(
    (item) => cleanText(item?.id) === id,
  );
}

export async function deleteLocalProjectAgent(agentId, { projectId = "" } = {}) {
  const id = cleanText(agentId);
  if (!id) throw new Error("缺少智能体 ID");
  const resolvedProjectId = cleanText(projectId) || cleanText(readSelectedProjectId());
  const agents = await listLocalProjectAgents({ projectId: resolvedProjectId });
  const existing = agents.find((item) => cleanText(item?.id) === id);
  if (!existing) return false;
  const { directories } = resolveDirectories(resolvedProjectId);
  const directoryId = cleanText(existing.file_path)
    .replace(/\\/g, "/")
    .split("/")
    .slice(-2, -1)[0];
  if (!directoryId) throw new Error("智能体定义路径无效");
  await deleteNativeWorkspaceFile({
    workspacePath: directories.agent,
    path: `${directoryId}/AGENT.md`,
  });
  await listLocalProjectAgents({ projectId: resolvedProjectId });
  return true;
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
  const missingSkills = skills
    .map((skill) => {
      try {
        renderSkillDefinition(skill, employee);
        return null;
      } catch (error) {
        if (error?.code !== "employee.skill_markdown_missing") throw error;
        return error.skill || {
          id: cleanText(skill?.id),
          name: cleanText(skill?.name) || cleanText(skill?.id),
        };
      }
    })
    .filter(Boolean);
  if (missingSkills.length) {
    const error = new Error("创建前发现技能缺少独立 Markdown 内容");
    error.code = "employee.skill_markdown_missing";
    error.recoverable = true;
    error.skills = missingSkills;
    throw error;
  }
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

  const nextEmployee = {
    ...employee,
    project_id: projectId,
    directory_path: directories.agent,
    file_path: `${directories.agent}/${agentPath}`,
    updated_at: new Date().toISOString(),
  };
  updateLocalProjectRelations(projectId, {
    ...relations,
    agent_index: [
      ...(Array.isArray(relations.agent_index) ? relations.agent_index : []).filter(
        (item) => cleanText(item?.id) !== id,
      ),
      agentIndexRecord(nextEmployee),
    ],
    employees: [],
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
