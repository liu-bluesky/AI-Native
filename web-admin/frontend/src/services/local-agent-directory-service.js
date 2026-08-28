import {
  getLocalProject,
  getLocalProjectRelations,
  upsertLocalProject,
  updateLocalProjectRelations,
} from "@/services/local-project-repository.js";
import { readSelectedProjectId } from "@/modules/project-chat/services/projectChatStorage.js";
import {
  hasNativeDesktopBridge,
  deleteNativeWorkspaceDirectory,
  listNativeWorkspaceFiles,
  readNativeWorkspaceFile,
  writeNativeWorkspaceFile,
} from "@/utils/native-desktop-bridge.js";
import { isWorkspaceFileMissing } from "@/utils/workspace-file-errors.js";

const AGENT_METADATA_FILE = ".ai-employee.json";

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
    .replace(/[. ]+$/g, "")
    .replace(/-+/g, "-")
    .replace(/^-+|-+$/g, "");
  const candidate = normalized || fallback;
  return /^(con|prn|aux|nul|com[1-9]|lpt[1-9])$/i.test(candidate)
    ? `${candidate}-file`
    : candidate;
}

function shortStableId(value) {
  const normalized = cleanText(value);
  const suffix = normalized.match(/([a-z0-9]{6,12})$/i)?.[1];
  if (suffix) return suffix.toLowerCase();
  let hash = 2166136261;
  for (const character of normalized) {
    hash ^= character.codePointAt(0) || 0;
    hash = Math.imul(hash, 16777619);
  }
  return (hash >>> 0).toString(36).padStart(6, "0").slice(-8);
}

function readableResourceName(value, id, fallback) {
  const label = safeFileSegment(value, fallback).slice(0, 48).replace(/-+$/g, "") || fallback;
  return `${label}--${shortStableId(id)}`;
}

function agentDirectoryName(employee) {
  return readableResourceName(employee?.name, employee?.id, "agent");
}

function skillDirectoryName(skill) {
  return readableResourceName(skill?.name, skill?.id, "skill");
}

function ruleDirectoryName(rule) {
  return readableResourceName(rule?.title || rule?.name, rule?.id, "rule");
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

function renderList(items) {
  return items.length ? items.map((item) => `- ${item}`).join("\n") : "- 未配置";
}

function renderContent(value, fallback = "") {
  const text = cleanText(value);
  return !text || isObjectString(text) ? fallback : text;
}

function renderAgentDefinition(employee, skills, rules) {
  const title = cleanText(employee.name) || employee.id;
  return `# ${title}

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
${renderList(rules.map((item) => `${cleanText(item.title) || item.id} (${item.id})`))}
`;
}

function renderAgentMetadata(employee, skills, rules, directoryName) {
  return `${JSON.stringify({
    version: 2,
    kind: "agent",
    directory_name: directoryName,
    agent: employee,
    skill_ids: skills.map((item) => cleanText(item?.id)).filter(Boolean),
    rule_ids: rules.map((item) => cleanText(item?.id)).filter(Boolean),
  }, null, 2)}\n`;
}

function renderSkillDefinition(skill) {
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
  return markdown.endsWith("\n") ? markdown : `${markdown}\n`;
}

function hasSkillDefinition(skill) {
  return Boolean(
    cleanText(
      skill?.markdown ||
        skill?.content ||
        skill?.definition ||
        skill?.instructions ||
        skill?.description,
    ),
  );
}

function renderRuleDefinition(rule) {
  const title = cleanText(rule.title || rule.name) || rule.id;
  const content = renderContent(rule.content || rule.body || rule.description);
  return `# ${title}

## 领域
${cleanText(rule.domain) || "通用"}

## 规则正文
${content || "未填写"}
`;
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

function parseAgentMetadata(value, fallbackId) {
  const metadata = value && typeof value === "object" && !Array.isArray(value) ? value : null;
  const agent = metadata?.agent;
  if (!agent || typeof agent !== "object" || Array.isArray(agent)) return null;
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

function parseAgentDefinition(content, fallbackId, metadata) {
  const sidecarAgent = parseAgentMetadata(metadata, fallbackId);
  if (sidecarAgent) return sidecarAgent;
  const marker = String(content || "").match(
    /<!--\s*ai-employee:agent-metadata:([\s\S]*?)\s*-->/i,
  );
  const legacyAgent = parseAgentMetadata(decodeAgentMetadata(marker?.[1]), fallbackId);
  return legacyAgent || parseLegacyAgentDefinition(content, fallbackId);
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

function directoryNameFromFilePath(filePath) {
  return cleanText(filePath)
    .replace(/\\/g, "/")
    .split("/")
    .slice(-2, -1)[0];
}

async function removeAgentDefinitionDirectory(directory, directoryName) {
  if (!directoryName) {
    throw new Error("智能体目录信息缺失，无法安全删除");
  }
  try {
    await deleteNativeWorkspaceDirectory({
      workspacePath: directory,
      path: directoryName,
    });
  } catch (error) {
    if (!isWorkspaceFileMissing(error)) throw error;
  }
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
  const agentsById = new Map();
  for (const item of items) {
    if (String(item?.kind || "") !== "directory") continue;
    const directoryName = cleanText(item?.name);
    if (!directoryName) continue;
    try {
      const file = await readNativeWorkspaceFile({
        workspacePath: directories.agent,
        path: `${directoryName}/AGENT.md`,
      });
      const metadataContent = await readDirectoryFile(
        directories.agent,
        `${directoryName}/${AGENT_METADATA_FILE}`,
      );
      let metadata = null;
      try {
        metadata = metadataContent ? JSON.parse(metadataContent) : null;
      } catch {
        console.warn("本地智能体侧车配置格式无效，已回退读取 Markdown", directoryName);
      }
      const agent = parseAgentDefinition(file?.content, directoryName, metadata);
      const id = cleanText(agent?.id);
      if (!id) continue;
      const candidate = {
        ...agent,
        id,
        project_id: resolvedProjectId,
        directory_name: directoryName,
        directory_path: directories.agent,
        file_path: `${directories.agent.replace(/[\\/]+$/, "")}/${directoryName}/AGENT.md`,
        updated_at: cleanText(agent?.updated_at) || new Date(item?.modifiedAtEpochMs || item?.modified_at_epoch_ms || Date.now()).toISOString(),
      };
      const existing = agentsById.get(id);
      if (!existing || (metadata && !existing._has_sidecar)) {
        agentsById.set(id, { ...candidate, _has_sidecar: Boolean(metadata) });
      }
    } catch (error) {
      if (!isWorkspaceFileMissing(error)) {
        console.warn("读取项目智能体定义失败", error);
      }
    }
  }
  const agents = Array.from(agentsById.values()).map(({ _has_sidecar, ...agent }) => agent);
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
  const next = {
    ...existing,
    ...(patch && typeof patch === "object" ? patch : {}),
    id,
    project_id: resolvedProjectId,
    updated_at: new Date().toISOString(),
  };
  await saveLocalAgentDirectoryResources({
    employee: next,
    skills: (Array.isArray(next.skills) ? next.skills : []).map((skillId) => ({ id: skillId, name: skillId, description: "已绑定技能，请在技能目录中维护定义。" })),
    rules: (Array.isArray(next.rules) ? next.rules : []).map((ruleId) => ({ id: ruleId, title: ruleId, description: "已绑定规则，请在规则目录中维护正文。" })),
    preserveExistingResources: true,
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
  await removeAgentDefinitionDirectory(
    directories.agent,
    cleanText(existing.directory_name) || directoryNameFromFilePath(existing.file_path),
  );
  await listLocalProjectAgents({ projectId: resolvedProjectId });
  return true;
}

export async function saveLocalAgentDirectoryResources({
  employee,
  skills = [],
  rules = [],
  preserveExistingResources = false,
} = {}) {
  const id = cleanText(employee?.id);
  if (!id) throw new Error("缺少智能体 ID");
  if (!hasNativeDesktopBridge()) {
    throw new Error("本地目录同步仅支持桌面端，请在桌面应用中创建智能体");
  }

  const projectId = cleanText(employee?.project_id) || cleanText(readSelectedProjectId());
  if (!projectId) throw new Error("请先在 AI 对话中选择项目");
  const { project, relations, settings, directories } = resolveDirectories(projectId);
  const definedSkills = preserveExistingResources
    ? skills
    : skills.filter(hasSkillDefinition);
  if (!preserveExistingResources && definedSkills.length !== skills.length) {
    throw new Error("存在缺少独立 Markdown 内容的技能，无法保存智能体");
  }
  const normalizedEmployee = {
    ...employee,
    skills: definedSkills.map((skill) => cleanText(skill?.id)).filter(Boolean),
    rules: rules.map((rule) => cleanText(rule?.id)).filter(Boolean),
    project_id: projectId,
    updated_at: new Date().toISOString(),
  };
  const existingAgents = await listLocalProjectAgents({ projectId });
  const existing = existingAgents.find((item) => cleanText(item?.id) === id);
  const directoryName = agentDirectoryName(normalizedEmployee);
  const previousDirectoryName = cleanText(existing?.directory_name) || directoryNameFromFilePath(existing?.file_path);

  const skillWrites = (preserveExistingResources ? [] : definedSkills).map((skill) => ({
    skill,
    directoryName: skillDirectoryName(skill),
    path: `${skillDirectoryName(skill)}/SKILL.md`,
    content: renderSkillDefinition(skill),
  }));
  const ruleWrites = (preserveExistingResources ? [] : rules)
    .filter((rule) => cleanText(rule?.id))
    .map((rule) => ({
      rule,
      directoryName: ruleDirectoryName(rule),
      path: `${ruleDirectoryName(rule)}/RULE.md`,
      content: renderRuleDefinition(rule),
    }));

  const writtenSkills = [];
  for (const item of skillWrites) {
    await writeNativeWorkspaceFile({
      workspacePath: directories.skill,
      path: item.path,
      content: item.content,
    });
    writtenSkills.push({
      id: cleanText(item.skill?.id),
      file_path: `${directories.skill}/${item.path}`,
    });
  }

  const writtenRules = [];
  for (const item of ruleWrites) {
    await writeNativeWorkspaceFile({
      workspacePath: directories.rule,
      path: item.path,
      content: item.content,
    });
    writtenRules.push({
      id: cleanText(item.rule?.id),
      file_path: `${directories.rule}/${item.path}`,
    });
  }

  const agentPath = `${directoryName}/AGENT.md`;
  await writeNativeWorkspaceFile({
    workspacePath: directories.agent,
    path: agentPath,
    content: renderAgentDefinition(normalizedEmployee, definedSkills, rules),
  });
  const writtenAgent = await writeNativeWorkspaceFile({
    workspacePath: directories.agent,
    path: `${directoryName}/${AGENT_METADATA_FILE}`,
    content: renderAgentMetadata(normalizedEmployee, definedSkills, rules, directoryName),
  });
  if (previousDirectoryName && previousDirectoryName !== directoryName) {
    await removeAgentDefinitionDirectory(directories.agent, previousDirectoryName);
  }

  const nextEmployee = {
    ...normalizedEmployee,
    directory_name: directoryName,
    directory_path: directories.agent,
    file_path: `${directories.agent}/${agentPath}`,
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
