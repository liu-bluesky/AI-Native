import {
  hasNativeDesktopBridge,
  listNativeLocalRecords,
  writeNativeLocalRecord,
} from "@/utils/native-desktop-bridge.js";

const STORAGE_KEY = "local_projects_cache";
const RELATIONS_STORAGE_KEY = "local_project_relations";
const ENTITY_STORAGE_PREFIX = "local_entities_";
const OFFLINE_PROJECT_LIST_STORAGE_KEY = "liuagent:cached-project-list";
const HIDDEN_WORKSPACE_PROJECT_IDS_STORAGE_KEY =
  "local_hidden_workspace_project_ids";
const GLOBAL_PROJECT_CATALOG_VERSION = 1;
let projectCatalogSyncTimer = null;
const localRecordCache = new Map();
const localRecordWriteQueues = new Map();

function canUseStorage() {
  return typeof window !== "undefined" && Boolean(window.localStorage);
}

function canUseNativeProjectCatalog() {
  return typeof window !== "undefined";
}

function readLegacyLocalRecord(key, fallback) {
  if (!canUseStorage()) return fallback;
  try {
    const raw = window.localStorage.getItem(key);
    return raw === null ? fallback : JSON.parse(raw);
  } catch {
    return fallback;
  }
}

function writeLegacyLocalRecord(key, value) {
  if (!canUseStorage()) return;
  try {
    window.localStorage.setItem(key, JSON.stringify(value));
  } catch {}
}

function removeLegacyLocalRecord(key) {
  if (!canUseStorage()) return;
  try {
    window.localStorage.removeItem(key);
  } catch {}
}

function readLocalRecord(key, fallback) {
  if (localRecordCache.has(key)) return localRecordCache.get(key);
  const value = readLegacyLocalRecord(key, fallback);
  localRecordCache.set(key, value);
  return value;
}

function queueNativeLocalRecordWrite(key, value) {
  const previous = localRecordWriteQueues.get(key) || Promise.resolve();
  const next = previous
    .catch(() => undefined)
    .then(() => writeNativeLocalRecord(key, value));
  localRecordWriteQueues.set(key, next);
  return next.finally(() => {
    if (localRecordWriteQueues.get(key) === next) {
      localRecordWriteQueues.delete(key);
    }
  });
}

function writeLocalRecord(key, value) {
  localRecordCache.set(key, value);
  if (hasNativeDesktopBridge()) {
    void queueNativeLocalRecordWrite(key, value)
      .then((saved) => {
        if (saved === true) removeLegacyLocalRecord(key);
      })
      .catch(() => writeLegacyLocalRecord(key, value));
  } else {
    writeLegacyLocalRecord(key, value);
  }
  return value;
}

function mergeMigratedLocalRecord(key, nativeValue, legacyValue) {
  if (key === RELATIONS_STORAGE_KEY) {
    return {
      ...(nativeValue && typeof nativeValue === "object" ? nativeValue : {}),
      ...(legacyValue && typeof legacyValue === "object" ? legacyValue : {}),
    };
  }
  if (key === HIDDEN_WORKSPACE_PROJECT_IDS_STORAGE_KEY) {
    const nativeIds = Array.isArray(nativeValue) ? nativeValue : [];
    const legacyIds = Array.isArray(legacyValue) ? legacyValue : [];
    return [...new Set([...nativeIds, ...legacyIds])];
  }
  if (key === STORAGE_KEY || key.startsWith(ENTITY_STORAGE_PREFIX)) {
    return mergeProjectRecords(
      Array.isArray(nativeValue) ? nativeValue : [],
      Array.isArray(legacyValue) ? legacyValue : [],
    );
  }
  return nativeValue ?? legacyValue;
}

export async function hydrateLocalProjectRepository() {
  if (!canUseStorage() || !hasNativeDesktopBridge()) return false;
  const legacyKeys = new Set([
    STORAGE_KEY,
    RELATIONS_STORAGE_KEY,
    HIDDEN_WORKSPACE_PROJECT_IDS_STORAGE_KEY,
  ]);
  for (let index = 0; index < window.localStorage.length; index += 1) {
    const key = window.localStorage.key(index) || "";
    if (
      key.startsWith(ENTITY_STORAGE_PREFIX) &&
      key !== `${ENTITY_STORAGE_PREFIX}employees`
    ) {
      legacyKeys.add(key);
    }
  }
  const legacyRecords = new Map(
    [...legacyKeys].map((key) => [key, readLocalRecord(key, key === RELATIONS_STORAGE_KEY ? {} : [])]),
  );
  try {
    const nativeRecords = await listNativeLocalRecords();
    for (const record of nativeRecords) {
      const key = String(record?.key || "").trim();
      if (!key) continue;
    }
    await Promise.all(
      [...legacyRecords.entries()]
        .map(async ([key, value]) => {
          const nativeValue = nativeRecords.find(
            (record) => String(record?.key || "").trim() === key,
          )?.value;
          const mergedValue = mergeMigratedLocalRecord(key, nativeValue, value);
          localRecordCache.set(key, mergedValue);
          const saved = await queueNativeLocalRecordWrite(key, mergedValue);
          if (saved === true) removeLegacyLocalRecord(key);
        }),
    );
    for (const record of nativeRecords) {
      const key = String(record?.key || "").trim();
      if (!key || legacyRecords.has(key)) continue;
      localRecordCache.set(key, record?.value);
      removeLegacyLocalRecord(key);
    }
    window.dispatchEvent(new CustomEvent("local-projects-updated"));
    window.dispatchEvent(new CustomEvent("local-entities-updated"));
    return true;
  } catch {
    return false;
  }
}

function projectCatalogEntries(projects = []) {
  return mergeProjectRecords(projects)
    .map((project) => ({
      id: String(project?.id || "").trim(),
      name: String(project?.name || "").trim(),
      description: String(project?.description || "").trim(),
      workspace_path: String(project?.workspace_path || "").trim(),
      deploy_settings: catalogDeploySettings(
        project?.deploy_settings ?? project?.deploySettings,
      ),
    }))
    .filter((project) => project.id);
}

function parseNativeProjectCatalogEntries(content = "") {
  try {
    const parsed = JSON.parse(String(content || ""));
    const projects = Array.isArray(parsed) ? parsed : parsed?.projects;
    return projectCatalogEntries(projects);
  } catch {
    return [];
  }
}

function mergeNativeProjectCatalogEntries(existingProjects = [], updates = []) {
  const merged = new Map();
  for (const project of projectCatalogEntries(existingProjects)) {
    merged.set(project.id, project);
  }
  for (const project of projectCatalogEntries(updates)) {
    const previous = merged.get(project.id) || {};
    merged.set(project.id, {
      id: project.id,
      name: project.name || previous.name || project.id,
      description: project.description || previous.description || "",
      workspace_path: project.workspace_path || previous.workspace_path || "",
      deploy_settings: pickDeploySettings(
        project.deploy_settings,
        previous.deploy_settings,
      ),
    });
  }
  return [...merged.values()];
}

function catalogDeploySettings(value) {
  if (!value || typeof value !== "object" || Array.isArray(value)) return {};
  try {
    return JSON.parse(
      JSON.stringify(value, (key, current) => {
        const lower = String(key || "").toLowerCase();
        if (
          lower.includes("password") ||
          lower.includes("secret") ||
          lower.includes("token")
        ) {
          return undefined;
        }
        return current;
      }),
    );
  } catch {
    return {};
  }
}

function isPlainObject(value) {
  return Boolean(value) && typeof value === "object" && !Array.isArray(value);
}

function textField(value, keys) {
  if (!isPlainObject(value)) return "";
  for (const key of keys) {
    const text = String(value?.[key] || "").trim();
    if (text) return text;
  }
  return "";
}

function collectDeployBindingTargets(settings) {
  if (!isPlainObject(settings)) return [];
  const targets = [];
  const pushTarget = (value) => {
    if (!isPlainObject(value)) return;
    const transport = isPlainObject(value.transport) ? value.transport : {};
    const executor = isPlainObject(value.remote_executor) ? value.remote_executor : {};
    targets.push({
      ftp_credential_id:
        textField(value, ["ftp_credential_id", "ftpCredentialId"]) ||
        textField(transport, ["ftp_credential_id", "ftpCredentialId"]),
      remote_path:
        textField(value, ["remote_path", "remotePath"]) ||
        textField(transport, ["remote_path", "remotePath"]),
      deploy_command:
        textField(value, ["deploy_command", "deployCommand"]) ||
        textField(executor, ["deploy_command", "deployCommand"]),
    });
  };

  const profiles = Array.isArray(settings.profiles) ? settings.profiles : [];
  for (const profile of profiles) {
    if (!isPlainObject(profile)) continue;
    const components = Array.isArray(profile.components) ? profile.components : [];
    if (components.length) {
      for (const component of components) {
        const componentTargets = Array.isArray(component?.targets)
          ? component.targets
          : [];
        if (componentTargets.length) {
          componentTargets.forEach(pushTarget);
        } else {
          pushTarget(component);
        }
      }
    } else {
      pushTarget(profile);
    }
  }
  if (!targets.length) pushTarget(settings);
  return targets;
}

function deploySettingsBindingScore(settings) {
  if (!isPlainObject(settings)) return -1;
  const targets = collectDeployBindingTargets(settings);
  let credentialCount = 0;
  let remotePathCount = 0;
  let commandCount = 0;
  for (const target of targets) {
    if (target.ftp_credential_id) credentialCount += 1;
    if (target.remote_path) remotePathCount += 1;
    if (target.deploy_command) commandCount += 1;
  }
  const profileCount = Array.isArray(settings.profiles) ? settings.profiles.length : 0;
  return (
    credentialCount * 100 +
    remotePathCount * 100 +
    commandCount * 10 +
    (Array.isArray(settings.profiles) ? 1 : 0) +
    Math.min(profileCount, 9)
  );
}

function hasStoredDeploySettings(value) {
  return isPlainObject(value) && Object.keys(value).length > 0;
}

export function pickDeploySettings(incoming, existing) {
  const incomingScore = deploySettingsBindingScore(incoming);
  const existingScore = deploySettingsBindingScore(existing);
  if (incomingScore > existingScore) return incoming;
  if (existingScore > incomingScore) return existing;
  if (incomingScore >= 0) return incoming;
  if (existingScore >= 0) return existing;
  if (hasStoredDeploySettings(incoming)) return incoming;
  if (hasStoredDeploySettings(existing)) return existing;
  return {};
}

async function writeNativeProjectCatalog(projects = []) {
  if (!canUseNativeProjectCatalog()) return;
  try {
    const {
      hasNativeDesktopBridge,
      readNativeGlobalProjectCatalogFile,
      writeNativeGlobalProjectCatalogFile,
    } = await import("@/utils/native-desktop-bridge.js");
    if (!hasNativeDesktopBridge()) return;
    const existingCatalog = await readNativeGlobalProjectCatalogFile();
    const mergedProjects = mergeNativeProjectCatalogEntries(
      parseNativeProjectCatalogEntries(existingCatalog?.content),
      projects,
    );
    await writeNativeGlobalProjectCatalogFile(
      JSON.stringify(
        {
          version: GLOBAL_PROJECT_CATALOG_VERSION,
          projects: mergedProjects,
        },
        null,
        2,
      ),
    );
    await writeNativeFtpCredentials(readLocalEntities("ftp_credentials"));
  } catch (error) {
    console.warn("同步桌面全局项目目录失败", error);
  }
}

function scheduleNativeProjectCatalogSync(projects = []) {
  if (!canUseNativeProjectCatalog()) return;
  if (projectCatalogSyncTimer !== null) {
    window.clearTimeout(projectCatalogSyncTimer);
  }
  const snapshot = Array.isArray(projects) ? [...projects] : [];
  projectCatalogSyncTimer = window.setTimeout(() => {
    projectCatalogSyncTimer = null;
    void writeNativeProjectCatalog(snapshot);
  }, 0);
}

export function syncLocalProjectsToNativeCatalog() {
  const projects = readLocalProjects();
  return writeNativeProjectCatalog(projects).then(() => projects);
}

const GLOBAL_FTP_CREDENTIALS_VERSION = 1;
let ftpCredentialsSyncTimer = null;

function ftpCredentialEntries(entities = []) {
  return (Array.isArray(entities) ? entities : [])
    .map((item) => ({
      id: String(item?.id || "").trim(),
      name: String(item?.name || item?.id || "").trim(),
      host: String(item?.host || "").trim(),
      port: item?.port ?? "",
      username: String(item?.username || "").trim(),
      password: String(item?.password || ""),
      max_upload_threads: Number(item?.max_upload_threads || 4) || 4,
      enabled: item?.enabled !== false,
    }))
    .filter((item) => item.id);
}

async function writeNativeFtpCredentials(entities = []) {
  if (!canUseNativeProjectCatalog()) return;
  try {
    const { hasNativeDesktopBridge, writeNativeGlobalFtpCredentialsFile } =
      await import("@/utils/native-desktop-bridge.js");
    if (!hasNativeDesktopBridge()) return;
    await writeNativeGlobalFtpCredentialsFile(
      JSON.stringify(
        {
          version: GLOBAL_FTP_CREDENTIALS_VERSION,
          credentials: ftpCredentialEntries(entities),
        },
        null,
        2,
      ),
    );
  } catch (error) {
    console.warn("同步桌面 FTP 连接失败", error);
  }
}

function scheduleNativeFtpCredentialsSync(entities = []) {
  if (!canUseNativeProjectCatalog()) return;
  if (ftpCredentialsSyncTimer !== null) {
    window.clearTimeout(ftpCredentialsSyncTimer);
  }
  const snapshot = Array.isArray(entities) ? [...entities] : [];
  ftpCredentialsSyncTimer = window.setTimeout(() => {
    ftpCredentialsSyncTimer = null;
    void writeNativeFtpCredentials(snapshot);
  }, 0);
}

export function syncLocalFtpCredentialsToNative() {
  return writeNativeFtpCredentials(readLocalEntities("ftp_credentials"));
}

function readRelations() {
  const value = readLocalRecord(RELATIONS_STORAGE_KEY, {});
  return value && typeof value === "object" ? value : {};
}

function writeRelations(relations) {
  if (canUseStorage()) {
    writeLocalRecord(RELATIONS_STORAGE_KEY, relations);
    window.dispatchEvent(new CustomEvent("local-project-relations-updated", { detail: relations }));
  }
  scheduleNativeProjectCatalogSync(readLocalProjects());
  return relations;
}

export function getLocalProjectRelations(projectId) {
  const id = String(projectId || "").trim();
  if (!id) return {};
  return readRelations()[id] || {};
}

export function readAllLocalProjectRelations() {
  return readRelations();
}

export function updateLocalProjectRelations(projectId, patch = {}) {
  const id = String(projectId || "").trim();
  if (!id) return {};
  const relations = readRelations();
  relations[id] = { ...getLocalProjectRelations(id), ...patch };
  writeRelations(relations);
  return relations[id];
}

function normalizeProjects(value) {
  if (!Array.isArray(value)) return [];
  return value
    .filter(
      (item) =>
        item &&
        typeof item === "object" &&
        String(item.id || item.project_id || item.projectId || "").trim(),
    )
    .map((item) => ({
      ...item,
      id: String(item.id || item.project_id || item.projectId).trim(),
    }));
}

export function normalizeWorkspacePath(value = "") {
  const normalized = String(value || "")
    .trim()
    .replace(/\\/g, "/")
    .replace(/\/{2,}/g, "/");
  if (!normalized || normalized === "/") return normalized;
  return normalized.replace(/\/+$/, "");
}

function workspaceIdentity(value = "") {
  const normalized = normalizeWorkspacePath(value);
  if (/^[A-Za-z]:\//.test(normalized)) {
    return normalized.toLowerCase();
  }
  return normalized;
}

export function getWorkspaceFolderName(workspacePath = "") {
  const normalized = normalizeWorkspacePath(workspacePath);
  if (!normalized) return "";
  const segments = normalized.split("/").filter(Boolean);
  return segments[segments.length - 1] || normalized;
}

function resolveWorkspacePath(project = {}) {
  return String(project?.workspace_path || project?.workspacePath || "").trim();
}

function projectLastOpenedAt(project = {}) {
  const value = String(
    project?.last_opened_at || project?.lastOpenedAt || "",
  ).trim();
  const timestamp = Date.parse(value);
  return Number.isFinite(timestamp) ? timestamp : 0;
}

export function isProjectNamePlaceholder(value, projectId = "") {
  const name = String(value || "").trim();
  const id = String(projectId || "").trim();
  return !name || (!!id && name === id);
}

function resolveProjectName(project = {}, projectId = "") {
  const id = String(
    projectId || project?.id || project?.project_id || project?.projectId || "",
  ).trim();
  const candidates = [
    project?.name,
    project?.project_name,
    project?.projectName,
    project?.project_label,
    project?.projectLabel,
  ];
  for (const candidate of candidates) {
    const name = String(candidate || "").trim();
    if (!isProjectNamePlaceholder(name, id)) return name;
  }
  return "";
}

function normalizeProjectRecord(project = {}) {
  const id = String(
    project?.id || project?.project_id || project?.projectId || "",
  ).trim();
  if (!id) return null;
  const workspacePath = resolveWorkspacePath(project);
  return {
    ...project,
    id,
    name: resolveProjectName(project, id) || getWorkspaceFolderName(workspacePath),
    description: String(project?.description || "").trim(),
    type: String(project?.type || project?.project_type || "mixed").trim(),
    workspace_path: workspacePath,
    ai_entry_file: String(project?.ai_entry_file || project?.aiEntryFile || "").trim(),
    mcp_instruction: String(
      project?.mcp_instruction || project?.mcpInstruction || "",
    ).trim(),
    created_by: String(project?.created_by || project?.createdBy || "").trim(),
    can_manage: project?.can_manage !== false,
    mcp_enabled: project?.mcp_enabled !== false,
    feedback_upgrade_enabled: project?.feedback_upgrade_enabled !== false,
    is_offline_cached: Boolean(project?.is_offline_cached),
    last_opened_at: String(
      project?.last_opened_at || project?.lastOpenedAt || "",
    ).trim(),
    deploy_settings: pickDeploySettings(
      project?.deploy_settings,
      project?.deploySettings,
    ),
  };
}

function mergeProjectRecord(existing = {}, incoming = {}) {
  const merged = { ...existing, ...incoming };
  merged.id = String(existing.id || incoming.id || "").trim();
  // The primary project cache is merged first; relation and offline data only fill gaps.
  merged.workspace_path =
    resolveWorkspacePath(existing) || resolveWorkspacePath(incoming);
  merged.name =
    resolveProjectName(existing, merged.id) ||
    resolveProjectName(incoming, merged.id) ||
    getWorkspaceFolderName(merged.workspace_path);
  merged.description = String(incoming.description || existing.description || "").trim();
  merged.type = String(incoming.type || existing.type || "mixed").trim();
  merged.ai_entry_file = String(
    incoming.ai_entry_file || existing.ai_entry_file || "",
  ).trim();
  merged.mcp_instruction = String(
    incoming.mcp_instruction || existing.mcp_instruction || "",
  ).trim();
  merged.created_by = String(incoming.created_by || existing.created_by || "").trim();
  merged.can_manage = incoming.can_manage ?? existing.can_manage ?? true;
  merged.mcp_enabled = incoming.mcp_enabled ?? existing.mcp_enabled ?? true;
  merged.feedback_upgrade_enabled =
    incoming.feedback_upgrade_enabled ?? existing.feedback_upgrade_enabled ?? true;
  merged.is_offline_cached = Boolean(
    existing.is_offline_cached || incoming.is_offline_cached,
  );
  merged.last_opened_at =
    projectLastOpenedAt(incoming) >= projectLastOpenedAt(existing)
      ? String(incoming.last_opened_at || incoming.lastOpenedAt || existing.last_opened_at || "").trim()
      : String(existing.last_opened_at || existing.lastOpenedAt || "").trim();
  merged.deploy_settings = pickDeploySettings(
    incoming.deploy_settings,
    existing.deploy_settings,
  );
  return merged;
}

function mergeProjectRecords(...lists) {
  const merged = new Map();
  for (const list of lists.flat()) {
    const item = normalizeProjectRecord(list);
    if (!item) continue;
    const existing = merged.get(item.id);
    merged.set(item.id, existing ? mergeProjectRecord(existing, item) : item);
  }
  return [...merged.values()];
}

export function mergeLocalProjectSources(
  cachedProjects = [],
  relationProjects = [],
  offlineProjects = [],
) {
  const merged = mergeProjectRecords(cachedProjects, relationProjects);
  const knownIds = new Set(
    merged.map((project) => String(project?.id || "").trim()).filter(Boolean),
  );
  const offlineFill = (Array.isArray(offlineProjects) ? offlineProjects : [])
    .map((project) => normalizeProjectRecord(project))
    .filter((project) => project && !knownIds.has(project.id));
  return mergeProjectRecords(merged, offlineFill);
}

function readOfflineProjectListSnapshot() {
  const parsed = readLocalRecord(OFFLINE_PROJECT_LIST_STORAGE_KEY, []);
  if (Array.isArray(parsed)) return normalizeProjects(parsed);
  return Array.isArray(parsed?.projects) ? normalizeProjects(parsed.projects) : [];
}

export function isLocalProjectMode() {
  return true;
}

export function readLocalProjects() {
  try {
    const cachedProjects = normalizeProjects(
      readLocalRecord(STORAGE_KEY, []),
    );
    const relationProjects = Object.entries(readAllLocalProjectRelations()).map(
      ([id, relation]) =>
        normalizeProjectRecord({
          id,
          ...(relation && typeof relation === "object" ? relation : {}),
        }),
    );
    return mergeLocalProjectSources(
      cachedProjects,
      relationProjects,
      readOfflineProjectListSnapshot(),
    );
  } catch {
    return [];
  }
}

function readHiddenWorkspaceProjectIds() {
  try {
    const parsed = readLocalRecord(HIDDEN_WORKSPACE_PROJECT_IDS_STORAGE_KEY, []);
    return new Set(
      (Array.isArray(parsed) ? parsed : [])
        .map((value) => String(value || "").trim())
        .filter(Boolean),
    );
  } catch {
    return new Set();
  }
}

function writeHiddenWorkspaceProjectIds(ids) {
  const normalized = Array.from(ids || [])
    .map((value) => String(value || "").trim())
    .filter(Boolean);
  if (canUseStorage()) {
    writeLocalRecord(
      HIDDEN_WORKSPACE_PROJECT_IDS_STORAGE_KEY,
      normalized,
    );
    window.dispatchEvent(
      new CustomEvent("local-workspace-projects-updated", { detail: normalized }),
    );
  }
  return normalized;
}

function chooseWorkspaceProject(existing, candidate) {
  if (!existing) return candidate;
  return projectLastOpenedAt(candidate) > projectLastOpenedAt(existing)
    ? candidate
    : existing;
}

export function getLocalWorkspaceProjectByPath(workspacePath = "") {
  const key = workspaceIdentity(workspacePath);
  if (!key) return null;
  return (
    readLocalProjects()
      .map(normalizeProjectRecord)
      .filter(
        (project) =>
          project && workspaceIdentity(project.workspace_path) === key,
      )
      .sort(
        (left, right) => projectLastOpenedAt(right) - projectLastOpenedAt(left),
      )[0] || null
  );
}

export function readLocalWorkspaceProjects() {
  const hiddenIds = readHiddenWorkspaceProjectIds();
  const byWorkspacePath = new Map();
  for (const project of readLocalProjects()) {
    const normalized = normalizeProjectRecord(project);
    if (!normalized || hiddenIds.has(normalized.id)) continue;
    const key = workspaceIdentity(normalized.workspace_path);
    if (!key) continue;
    const workspaceProject = {
      ...normalized,
      name:
        normalized.name ||
        getWorkspaceFolderName(normalized.workspace_path) ||
        "未命名文件夹",
    };
    byWorkspacePath.set(
      key,
      chooseWorkspaceProject(byWorkspacePath.get(key), workspaceProject),
    );
  }
  return [...byWorkspacePath.values()].sort(
    (left, right) => projectLastOpenedAt(right) - projectLastOpenedAt(left),
  );
}

function createLocalWorkspaceProjectId() {
  return `local-workspace-${Date.now()}-${Math.random()
    .toString(36)
    .slice(2, 10)}`;
}

export function openLocalWorkspaceProject(workspacePath = "") {
  const path = String(workspacePath || "").trim();
  const key = workspaceIdentity(path);
  if (!key) return null;
  const matchingProjects = readLocalProjects()
    .map(normalizeProjectRecord)
    .filter(
      (project) => project && workspaceIdentity(project.workspace_path) === key,
    )
    .sort((left, right) => projectLastOpenedAt(right) - projectLastOpenedAt(left));
  const existing = matchingProjects[0] || null;
  const id = String(existing?.id || createLocalWorkspaceProjectId()).trim();
  const hiddenIds = readHiddenWorkspaceProjectIds();
  const restoredIds = matchingProjects.map((project) => project.id);
  const restored = restoredIds.some((projectId) => hiddenIds.delete(projectId));
  if (restored) {
    writeHiddenWorkspaceProjectIds(hiddenIds);
  }
  upsertLocalProject({
    ...(existing || {}),
    id,
    name: resolveProjectName(existing, id) || getWorkspaceFolderName(path),
    workspace_path: path,
    created_by: existing?.created_by || "local",
    can_manage: existing?.can_manage ?? true,
    last_opened_at: new Date().toISOString(),
  });
  return getLocalProject(id);
}

export function renameLocalWorkspaceProject(projectId, name) {
  const id = String(projectId || "").trim();
  const current = getLocalProject(id);
  const nextName = String(name || "").trim();
  if (
    !current ||
    !resolveWorkspacePath(current) ||
    isProjectNamePlaceholder(nextName, id)
  ) {
    return null;
  }
  upsertLocalProject({
    ...current,
    id,
    name: nextName,
    updated_at: new Date().toISOString(),
  });
  return getLocalProject(id);
}

export function removeLocalWorkspaceProject(projectId) {
  const id = String(projectId || "").trim();
  if (!id) return [];
  const hiddenIds = readHiddenWorkspaceProjectIds();
  const target = getLocalProject(id);
  const targetWorkspacePath = workspaceIdentity(target?.workspace_path);
  const matchingProjectIds = readLocalProjects()
    .map(normalizeProjectRecord)
    .filter(
      (project) =>
        project &&
        targetWorkspacePath &&
        workspaceIdentity(project.workspace_path) === targetWorkspacePath,
    )
    .map((project) => project.id);
  for (const matchingId of matchingProjectIds.length ? matchingProjectIds : [id]) {
    hiddenIds.add(matchingId);
  }
  return writeHiddenWorkspaceProjectIds(hiddenIds);
}

export function getLocalProject(projectId) {
  const id = String(projectId || "").trim();
  if (!id) return null;
  return readLocalProjects().find((project) => project.id === id) || null;
}

export function writeLocalProjects(projects) {
  const normalized = mergeProjectRecords(projects);
  if (canUseStorage()) {
    writeLocalRecord(STORAGE_KEY, normalized);
    window.dispatchEvent(new CustomEvent("local-projects-updated", { detail: normalized }));
  }
  scheduleNativeProjectCatalogSync(normalized);
  return normalized;
}

export function upsertLocalProject(project) {
  const id = String(project?.id || "").trim();
  if (!id) return readLocalProjects();
  const currentProjects = readLocalProjects();
  const existing = currentProjects.find((item) => item.id === id) || null;
  const next = currentProjects.filter((item) => item.id !== id);
  const nextProject = { ...(existing || {}), ...project, id };
  nextProject.name =
    resolveProjectName(project, id) ||
    resolveProjectName(existing, id) ||
    "";
  nextProject.deploy_settings = pickDeploySettings(
    project?.deploy_settings ?? project?.deploySettings,
    existing?.deploy_settings,
  );
  next.push(nextProject);
  return writeLocalProjects(next);
}

export function removeLocalProject(projectId) {
  const id = String(projectId || "").trim();
  return writeLocalProjects(readLocalProjects().filter((item) => item.id !== id));
}

export function filterLocalProjects(projects, filters = {}) {
  const name = String(filters.name || "").trim().toLowerCase();
  const createdBy = String(filters.createdBy || "").trim().toLowerCase();
  return normalizeProjects(projects)
    .map(normalizeProjectRecord)
    .filter(Boolean)
    .filter((project) => {
    const matchesName = !name || String(project.name || "").toLowerCase().includes(name);
    const matchesCreator = !createdBy || String(project.created_by || "").toLowerCase().includes(createdBy);
    return matchesName && matchesCreator;
    });
}

export function readLocalEntities(entityName) {
  const key = `${ENTITY_STORAGE_PREFIX}${String(entityName || "").trim()}`;
  if (key === ENTITY_STORAGE_PREFIX) return [];
  try {
    return normalizeProjects(readLocalRecord(key, []));
  } catch {
    return [];
  }
}

export function writeLocalEntities(entityName, entities) {
  const key = `${ENTITY_STORAGE_PREFIX}${String(entityName || "").trim()}`;
  const normalized = normalizeProjects(entities);
  if (canUseStorage() && key !== ENTITY_STORAGE_PREFIX) {
    writeLocalRecord(key, normalized);
    window.dispatchEvent(
      new CustomEvent("local-entities-updated", {
        detail: { entityName, entities: normalized },
      }),
    );
  }
  if (String(entityName || "").trim() === "ftp_credentials") {
    scheduleNativeFtpCredentialsSync(normalized);
  }
  return normalized;
}

export function upsertLocalEntity(entityName, entity) {
  const id = String(entity?.id || "").trim();
  if (!id) return null;
  const normalizedEntity = { ...entity, id };
  const next = readLocalEntities(entityName).filter((item) => item.id !== id);
  next.push(normalizedEntity);
  writeLocalEntities(entityName, next);
  return normalizedEntity;
}

export function removeLocalEntity(entityName, entityId) {
  const id = String(entityId || "").trim();
  return writeLocalEntities(
    entityName,
    readLocalEntities(entityName).filter((item) => item.id !== id),
  );
}
