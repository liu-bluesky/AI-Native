import { getStoredAuthProfile } from "@/utils/auth-storage.js";
import {
  PLUGIN_INSTALL_DRAFT_STORAGE_PREFIX,
  STATISTICS_ANALYSIS_DRAFT_STORAGE_PREFIX,
} from "@/modules/project-chat/constants/projectChatConstants.js";

const LOCAL_CONNECTOR_STORAGE_PREFIX = "project_chat.local_connector";
const GUIDE_TOUR_STORAGE_PREFIX = "project_chat.guide_tour";
const PROJECT_SELECTION_STORAGE_KEY = "project_id";

function chatSessionStorageKey(projectId) {
  const normalized = String(projectId || "").trim();
  return normalized ? `project_chat_session_${normalized}` : "";
}

function taskTreeSessionStorageKey(projectId) {
  const normalized = String(projectId || "").trim();
  return normalized ? `project_chat_task_tree_session_${normalized}` : "";
}

function workSessionStorageKey(projectId) {
  const normalized = String(projectId || "").trim();
  return normalized ? `project_chat_work_session_${normalized}` : "";
}

export function resolveCurrentUsername() {
  const profile = getStoredAuthProfile();
  return String(profile.username || "anonymous").trim() || "anonymous";
}

export function guideTourStorageKey(surface, username, roleId) {
  return [
    GUIDE_TOUR_STORAGE_PREFIX,
    String(surface || "").trim() || "chat",
    String(username || "").trim() || "anonymous",
    String(roleId || "").trim() || "user",
  ].join(".");
}

export function hasSeenGuideTour(surface, username, roleId) {
  if (typeof window === "undefined") return true;
  return (
    localStorage.getItem(guideTourStorageKey(surface, username, roleId)) === "1"
  );
}

export function markGuideTourSeen(surface, username, roleId) {
  if (typeof window === "undefined") return;
  localStorage.setItem(guideTourStorageKey(surface, username, roleId), "1");
}

export function readSelectedProjectId() {
  if (typeof window === "undefined") return "";
  return String(
    localStorage.getItem(PROJECT_SELECTION_STORAGE_KEY) || "",
  ).trim();
}

// 保持历史 project_id key 不变，只把浏览器存储副作用收敛到 service 层。
export function writeSelectedProjectId(projectId) {
  if (typeof window === "undefined") return;
  const normalized = String(projectId || "").trim();
  if (normalized) {
    localStorage.setItem(PROJECT_SELECTION_STORAGE_KEY, normalized);
    return;
  }
  localStorage.removeItem(PROJECT_SELECTION_STORAGE_KEY);
}

export function clearSelectedProjectId() {
  writeSelectedProjectId("");
}

function consumeJsonDraft(storageKey, expectedPrefix, normalizePayload) {
  const normalizedKey = String(storageKey || "").trim();
  if (!normalizedKey || !normalizedKey.startsWith(expectedPrefix)) {
    return null;
  }
  if (typeof window === "undefined") return null;
  try {
    const raw = window.localStorage.getItem(normalizedKey);
    if (!raw) return null;
    // 草稿是从其它页面跳转过来的一次性载荷，读取后必须立刻清理，避免重复填充输入框。
    window.localStorage.removeItem(normalizedKey);
    const parsed = JSON.parse(raw);
    if (!parsed || typeof parsed !== "object") return null;
    return normalizePayload(parsed);
  } catch {
    try {
      window.localStorage.removeItem(normalizedKey);
    } catch {
      // ignore cleanup errors
    }
    return null;
  }
}

export function consumeStatisticsAnalysisDraft(storageKey) {
  return consumeJsonDraft(
    storageKey,
    STATISTICS_ANALYSIS_DRAFT_STORAGE_PREFIX,
    (parsed) => ({
      prompt: String(parsed.prompt || "").trim(),
      scope: String(parsed.scope || "").trim(),
      project_id: String(parsed.project_id || "").trim(),
      link: String(parsed.link || "").trim(),
    }),
  );
}

export function consumePluginInstallDraft(storageKey) {
  return consumeJsonDraft(
    storageKey,
    PLUGIN_INSTALL_DRAFT_STORAGE_PREFIX,
    (parsed) => ({
      prompt: String(parsed.prompt || "").trim(),
      source: String(parsed.source || "").trim(),
    }),
  );
}

function writeProjectSessionMemory(key, sessionId) {
  if (typeof window === "undefined" || !key) return;
  const normalized = String(sessionId || "").trim();
  if (normalized) {
    localStorage.setItem(key, normalized);
    return;
  }
  localStorage.removeItem(key);
}

function readProjectSessionMemory(key) {
  if (typeof window === "undefined" || !key) return "";
  return String(localStorage.getItem(key) || "").trim();
}

function clearProjectSessionMemory(key) {
  if (typeof window === "undefined" || !key) return;
  localStorage.removeItem(key);
}

// 只记录项目维度最近一次会话 ID，完整运行态快照由 runtime storage 单独维护。
export function rememberChatSession(projectId, sessionId) {
  writeProjectSessionMemory(chatSessionStorageKey(projectId), sessionId);
}

export function restoreChatSession(projectId) {
  return readProjectSessionMemory(chatSessionStorageKey(projectId));
}

export function clearChatSessionMemory(projectId) {
  clearProjectSessionMemory(chatSessionStorageKey(projectId));
}

export function rememberTaskTreeSession(projectId, sessionId) {
  writeProjectSessionMemory(taskTreeSessionStorageKey(projectId), sessionId);
}

export function restoreTaskTreeSession(projectId) {
  return readProjectSessionMemory(taskTreeSessionStorageKey(projectId));
}

export function clearTaskTreeSessionMemory(projectId) {
  clearProjectSessionMemory(taskTreeSessionStorageKey(projectId));
}

export function rememberWorkSession(projectId, sessionId) {
  writeProjectSessionMemory(workSessionStorageKey(projectId), sessionId);
}

export function restoreWorkSession(projectId) {
  return readProjectSessionMemory(workSessionStorageKey(projectId));
}

export function clearWorkSessionMemory(projectId) {
  clearProjectSessionMemory(workSessionStorageKey(projectId));
}

export function localConnectorPreferenceStorageKey() {
  return `${LOCAL_CONNECTOR_STORAGE_PREFIX}.selected.${resolveCurrentUsername()}`;
}

export function localConnectorWorkspaceStorageKey(projectId, connectorId) {
  return [
    LOCAL_CONNECTOR_STORAGE_PREFIX,
    "workspace",
    resolveCurrentUsername(),
    String(projectId || "").trim() || "default",
    String(connectorId || "").trim() || "default",
  ].join(".");
}

export function readPreferredLocalConnectorId() {
  if (typeof window === "undefined") return "";
  return String(
    localStorage.getItem(localConnectorPreferenceStorageKey()) || "",
  ).trim();
}

export function writePreferredLocalConnectorId(connectorId) {
  if (typeof window === "undefined") return;
  const normalized = String(connectorId || "").trim();
  const key = localConnectorPreferenceStorageKey();
  if (normalized) {
    localStorage.setItem(key, normalized);
    return;
  }
  localStorage.removeItem(key);
}

export function readPreferredLocalWorkspacePath(projectId, connectorId) {
  if (typeof window === "undefined") return "";
  const normalizedProjectId = String(projectId || "").trim();
  const normalizedConnectorId = String(connectorId || "").trim();
  if (!normalizedProjectId || !normalizedConnectorId) return "";
  return String(
    localStorage.getItem(
      localConnectorWorkspaceStorageKey(
        normalizedProjectId,
        normalizedConnectorId,
      ),
    ) || "",
  ).trim();
}

export function writePreferredLocalWorkspacePath(
  projectId,
  connectorId,
  workspacePath,
) {
  if (typeof window === "undefined") return;
  const normalizedProjectId = String(projectId || "").trim();
  const normalizedConnectorId = String(connectorId || "").trim();
  if (!normalizedProjectId || !normalizedConnectorId) return;
  const normalizedWorkspacePath = String(workspacePath || "").trim();
  const key = localConnectorWorkspaceStorageKey(
    normalizedProjectId,
    normalizedConnectorId,
  );
  if (normalizedWorkspacePath) {
    localStorage.setItem(key, normalizedWorkspacePath);
    return;
  }
  localStorage.removeItem(key);
}

export function skillResourceDirectoryStorageKey(projectId) {
  return [
    LOCAL_CONNECTOR_STORAGE_PREFIX,
    "skill_dir",
    resolveCurrentUsername(),
    String(projectId || "").trim() || "default",
  ].join(".");
}

export function readPreferredSkillResourceDirectory(projectId) {
  if (typeof window === "undefined") return "";
  return String(
    localStorage.getItem(skillResourceDirectoryStorageKey(projectId)) || "",
  ).trim();
}

export function writePreferredSkillResourceDirectory(projectId, directoryPath) {
  if (typeof window === "undefined") return;
  const normalized = String(directoryPath || "").trim();
  const key = skillResourceDirectoryStorageKey(projectId);
  if (normalized) {
    localStorage.setItem(key, normalized);
    return;
  }
  localStorage.removeItem(key);
}
