import api from "@/utils/api.js";

export function fetchProjectMcpRuntimeCatalog(projectId, serverId = "") {
  const normalizedProjectId = String(projectId || "").trim();
  const normalizedServerId = String(serverId || "").trim();
  return api.get(
    `/projects/${encodeURIComponent(normalizedProjectId)}/mcp-runtime/catalog`,
    {
      params: normalizedServerId ? { server_id: normalizedServerId } : {},
    },
  );
}
