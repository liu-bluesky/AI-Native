import api from "@/utils/api.js";

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
  const pageSize = Math.max(
    1,
    Math.min(
      Number(options.pageSize || PROJECT_OPTIONS_PAGE_SIZE) ||
        PROJECT_OPTIONS_PAGE_SIZE,
      100,
    ),
  );
  const maxPages = Math.max(
    1,
    Number(options.maxPages || PROJECT_OPTIONS_MAX_PAGES) ||
      PROJECT_OPTIONS_MAX_PAGES,
  );
  const projects = [];
  const seenProjectIds = new Set();

  for (let page = 1; page <= maxPages; page += 1) {
    const payload = await api.get("/projects", {
      params: {
        page,
        page_size: pageSize,
      },
    });
    const items = normalizeProjectItems(payload);
    items.forEach((item) => {
      const id = String(item?.id || "").trim();
      if (!id || seenProjectIds.has(id)) return;
      seenProjectIds.add(id);
      projects.push(item);
    });

    const pagination = normalizePagination(payload);
    if (!items.length) break;
    if (pagination.total > 0 && projects.length >= pagination.total) break;
    if (items.length < pageSize) break;
  }

  return projects;
}
