import { ref } from "vue";

const ACTIVE_SERVER_ORIGIN_KEY = "server_profile.active_origin";
const SERVER_PROFILES_KEY = "server_profile.items";
const DEFAULT_PROFILE_ID = "same-origin";

export const serverProfileVersion = ref(0);

function bumpServerProfileVersion() {
  serverProfileVersion.value += 1;
}

export function normalizeServerOrigin(value) {
  const raw = String(value || "").trim();
  if (!raw || raw === "/") return "";
  try {
    const parsed = new URL(raw);
    if (!["http:", "https:"].includes(parsed.protocol)) return "";
    return parsed.origin.replace(/\/+$/, "");
  } catch {
    return "";
  }
}

export function validateServerOrigin(value) {
  const raw = String(value || "").trim();
  if (!raw) {
    return { ok: false, origin: "", message: "请输入服务端地址" };
  }
  if (!/^https?:\/\//i.test(raw)) {
    return { ok: false, origin: "", message: "服务端地址必须以 http:// 或 https:// 开头" };
  }
  const origin = normalizeServerOrigin(raw);
  if (!origin) {
    return { ok: false, origin: "", message: "服务端地址格式不正确" };
  }
  try {
    const parsedRaw = new URL(raw);
    const hasApiPath = /^\/api(?:\/|$)/.test(parsedRaw.pathname || "");
    if (hasApiPath) {
      return { ok: false, origin: "", message: "只填写服务端根地址，不要包含 /api 路径" };
    }
  } catch {
    return { ok: false, origin: "", message: "服务端地址格式不正确" };
  }
  return { ok: true, origin, message: "" };
}

function browserOrigin() {
  if (typeof window === "undefined" || !window.location?.origin) return "";
  return normalizeServerOrigin(window.location.origin);
}

export function getActiveServerOrigin() {
  if (typeof localStorage === "undefined") return "";
  return normalizeServerOrigin(localStorage.getItem(ACTIVE_SERVER_ORIGIN_KEY) || "");
}

export function resolveServerOrigin() {
  return getActiveServerOrigin() || browserOrigin();
}

export function isSameOriginServer(origin = resolveServerOrigin()) {
  const resolved = normalizeServerOrigin(origin);
  const current = browserOrigin();
  return !resolved || !current || resolved === current;
}

export function buildApiBaseUrl(origin = resolveServerOrigin()) {
  const normalized = normalizeServerOrigin(origin);
  if (!normalized || isSameOriginServer(normalized)) return "/api";
  return `${normalized}/api`;
}

export function buildServerUrl(pathname = "", origin = resolveServerOrigin()) {
  const path = String(pathname || "").trim();
  const cleanPath = path.startsWith("/") ? path : `/${path}`;
  const normalized = normalizeServerOrigin(origin);
  if (!normalized || isSameOriginServer(normalized)) return cleanPath;
  return `${normalized}${cleanPath}`;
}

export function buildWsBaseUrl(origin = resolveServerOrigin()) {
  const normalized = normalizeServerOrigin(origin) || browserOrigin();
  if (!normalized) return "";
  const parsed = new URL(normalized);
  parsed.protocol = parsed.protocol === "https:" ? "wss:" : "ws:";
  return parsed.origin;
}

function normalizeProfile(payload = {}) {
  const origin = normalizeServerOrigin(payload.origin);
  if (!origin) return null;
  return {
    id: String(payload.id || origin).trim() || origin,
    name: String(payload.name || "").trim() || origin,
    origin,
    last_used_at: String(payload.last_used_at || "").trim(),
  };
}

export function getServerProfiles() {
  if (typeof localStorage === "undefined") return [];
  try {
    const parsed = JSON.parse(localStorage.getItem(SERVER_PROFILES_KEY) || "[]");
    if (!Array.isArray(parsed)) return [];
    return parsed.map((item) => normalizeProfile(item)).filter(Boolean);
  } catch {
    localStorage.removeItem(SERVER_PROFILES_KEY);
    return [];
  }
}

export function saveServerProfile(payload = {}) {
  if (typeof localStorage === "undefined") return null;
  const profile = normalizeProfile({
    ...payload,
    last_used_at: payload.last_used_at || new Date().toISOString(),
  });
  if (!profile) return null;
  const profiles = getServerProfiles();
  const next = [
    profile,
    ...profiles.filter((item) => item.origin !== profile.origin),
  ].slice(0, 12);
  localStorage.setItem(SERVER_PROFILES_KEY, JSON.stringify(next));
  bumpServerProfileVersion();
  return profile;
}

export function setActiveServerOrigin(origin, options = {}) {
  if (typeof localStorage === "undefined") return "";
  const normalized = normalizeServerOrigin(origin);
  if (normalized && !isSameOriginServer(normalized)) {
    localStorage.setItem(ACTIVE_SERVER_ORIGIN_KEY, normalized);
  } else {
    localStorage.removeItem(ACTIVE_SERVER_ORIGIN_KEY);
  }
  const effectiveOrigin = normalized || browserOrigin();
  if (options.saveProfile !== false && effectiveOrigin) {
    saveServerProfile({
      id: options.id || (isSameOriginServer(effectiveOrigin) ? DEFAULT_PROFILE_ID : effectiveOrigin),
      name: options.name || (isSameOriginServer(effectiveOrigin) ? "当前网页服务" : effectiveOrigin),
      origin: effectiveOrigin,
    });
  }
  bumpServerProfileVersion();
  return effectiveOrigin;
}

export function getServerScopedStorageKey(key, origin = resolveServerOrigin()) {
  const normalized = normalizeServerOrigin(origin) || browserOrigin() || "same-origin";
  return `auth:${normalized}:${key}`;
}

export function isUsingCustomServerOrigin() {
  return Boolean(getActiveServerOrigin());
}
