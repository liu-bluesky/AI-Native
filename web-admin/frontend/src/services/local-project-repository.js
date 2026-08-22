const STORAGE_KEY = "local_projects_cache";
const RELATIONS_STORAGE_KEY = "local_project_relations";
const ENTITY_STORAGE_PREFIX = "local_entities_";

function canUseStorage() {
  return typeof window !== "undefined" && Boolean(window.localStorage);
}

function readRelations() {
  if (!canUseStorage()) return {};
  try {
    const value = JSON.parse(window.localStorage.getItem(RELATIONS_STORAGE_KEY) || "{}");
    return value && typeof value === "object" ? value : {};
  } catch {
    return {};
  }
}

function writeRelations(relations) {
  if (canUseStorage()) {
    window.localStorage.setItem(RELATIONS_STORAGE_KEY, JSON.stringify(relations));
    window.dispatchEvent(new CustomEvent("local-project-relations-updated", { detail: relations }));
  }
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
    .filter((item) => item && typeof item === "object" && String(item.id || "").trim())
    .map((item) => ({ ...item, id: String(item.id).trim() }));
}

export function isLocalProjectMode() {
  return true;
}

export function readLocalProjects() {
  if (!canUseStorage()) return [];
  try {
    return normalizeProjects(JSON.parse(window.localStorage.getItem(STORAGE_KEY) || "[]"));
  } catch {
    return [];
  }
}

export function getLocalProject(projectId) {
  const id = String(projectId || "").trim();
  if (!id) return null;
  return readLocalProjects().find((project) => project.id === id) || null;
}

export function writeLocalProjects(projects) {
  const normalized = normalizeProjects(projects);
  if (canUseStorage()) {
    window.localStorage.setItem(STORAGE_KEY, JSON.stringify(normalized));
    window.dispatchEvent(new CustomEvent("local-projects-updated", { detail: normalized }));
  }
  return normalized;
}

export function upsertLocalProject(project) {
  const id = String(project?.id || "").trim();
  if (!id) return readLocalProjects();
  const next = readLocalProjects().filter((item) => item.id !== id);
  next.push({ ...project, id });
  return writeLocalProjects(next);
}

export function removeLocalProject(projectId) {
  const id = String(projectId || "").trim();
  return writeLocalProjects(readLocalProjects().filter((item) => item.id !== id));
}

export function filterLocalProjects(projects, filters = {}) {
  const name = String(filters.name || "").trim().toLowerCase();
  const createdBy = String(filters.createdBy || "").trim().toLowerCase();
  return normalizeProjects(projects).filter((project) => {
    const matchesName = !name || String(project.name || "").toLowerCase().includes(name);
    const matchesCreator = !createdBy || String(project.created_by || "").toLowerCase().includes(createdBy);
    return matchesName && matchesCreator;
  });
}

export function readLocalEntities(entityName) {
  if (!canUseStorage()) return [];
  const key = `${ENTITY_STORAGE_PREFIX}${String(entityName || "").trim()}`;
  if (key === ENTITY_STORAGE_PREFIX) return [];
  try {
    return normalizeProjects(
      JSON.parse(window.localStorage.getItem(key) || "[]"),
    );
  } catch {
    return [];
  }
}

export function writeLocalEntities(entityName, entities) {
  const key = `${ENTITY_STORAGE_PREFIX}${String(entityName || "").trim()}`;
  const normalized = normalizeProjects(entities);
  if (canUseStorage() && key !== ENTITY_STORAGE_PREFIX) {
    window.localStorage.setItem(key, JSON.stringify(normalized));
    window.dispatchEvent(
      new CustomEvent("local-entities-updated", {
        detail: { entityName, entities: normalized },
      }),
    );
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
