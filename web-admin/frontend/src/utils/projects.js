import {
  filterLocalProjects,
  readLocalProjects,
} from "@/services/local-project-repository.js";

const PROJECT_OPTIONS_PAGE_SIZE = 100;
const PROJECT_OPTIONS_MAX_PAGES = 50;

function normalizeProjectItems(payload) {
  if (Array.isArray(payload?.projects)) return payload.projects;
  if (Array.isArray(payload?.items)) return payload.items;
  if (Array.isArray(payload)) return payload;
  return [];
}

function normalizePagination(payload) {
  const pagination = payload?.pagination || {};
  return {
    total: Math.max(
      0,
      Number(pagination.total ?? payload?.total ?? 0) || 0,
    ),
    page: Math.max(1, Number(pagination.page ?? 1) || 1),
    pageSize: Math.max(
      1,
      Number(
        pagination.page_size ??
          pagination.pageSize ??
          PROJECT_OPTIONS_PAGE_SIZE,
      ) || PROJECT_OPTIONS_PAGE_SIZE,
    ),
  };
}

export async function fetchAllVisibleProjects(options = {}) {
  const filters = options?.filters && typeof options.filters === "object"
    ? options.filters
    : options;
  return filterLocalProjects(readLocalProjects(), filters);
}
