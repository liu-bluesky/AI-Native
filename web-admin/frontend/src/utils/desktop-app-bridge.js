const DESKTOP_BRIDGE_SOURCE = "ai-employee-desktop-app";
const DESKTOP_BRIDGE_ACK_TYPE = "open-path-ack";
const DESKTOP_BRIDGE_ACK_TIMEOUT = 360;
let desktopBridgeRequestSeed = 0;

function canUseWindow() {
  return typeof window !== "undefined";
}

export function isEmbeddedDesktopApp() {
  if (!canUseWindow()) return false;
  const params = new URLSearchParams(window.location.search);
  return params.get("embedded") === "1" && window.parent && window.parent !== window;
}

export function isDesktopBridgeMessage(payload) {
  return (
    payload
    && typeof payload === "object"
    && payload.source === DESKTOP_BRIDGE_SOURCE
    && typeof payload.type === "string"
  );
}

export function normalizeDesktopBridgePath(path) {
  const normalized = String(path || "").trim();
  if (!normalized) return "";
  try {
    const parsed = new URL(normalized, window.location.origin);
    const hashRoute = parsed.hash.startsWith("#/") ? parsed.hash.slice(1) : "";
    parsed.searchParams.delete("embedded");
    parsed.searchParams.delete("desktop_window_id");
    if (parsed.origin === window.location.origin) {
      if (hashRoute) {
        return hashRoute;
      }
      return `${parsed.pathname}${parsed.search}`;
    }
  } catch {
    return normalized;
  }
  return normalized;
}

export function postDesktopBridgeMessage(type, payload = {}) {
  if (!isEmbeddedDesktopApp()) return false;
  window.parent.postMessage(
    {
      source: DESKTOP_BRIDGE_SOURCE,
      type: String(type || "").trim(),
      payload: payload && typeof payload === "object" ? payload : {},
    },
    window.location.origin,
  );
  return true;
}

export function notifyDesktopRouteChange(path, meta = {}) {
  const normalizedPath = normalizeDesktopBridgePath(path);
  if (!normalizedPath) return false;
  const params = canUseWindow() ? new URLSearchParams(window.location.search) : new URLSearchParams();
  return postDesktopBridgeMessage("route-change", {
    path: normalizedPath,
    windowId: params.get("desktop_window_id") || "",
    title: String(meta.title || "").trim(),
    summary: String(meta.summary || "").trim(),
    eyebrow: String(meta.eyebrow || "").trim(),
    appId: String(meta.appId || "").trim(),
  });
}

function createDesktopBridgeRequestId() {
  desktopBridgeRequestSeed += 1;
  return `desktop-bridge-${Date.now()}-${desktopBridgeRequestSeed}`;
}

export function requestDesktopOpenPath(path, options = {}) {
  const normalizedPath = normalizeDesktopBridgePath(path);
  if (!normalizedPath) return false;
  return postDesktopBridgeMessage("open-path", {
    path: normalizedPath,
    mode: String(options.mode || "new-window").trim() || "new-window",
    appId: String(options.appId || "").trim(),
    title: String(options.title || "").trim(),
    summary: String(options.summary || "").trim(),
    eyebrow: String(options.eyebrow || "").trim(),
    params: options.params && typeof options.params === "object" ? options.params : {},
    requestId: String(options.requestId || "").trim(),
  });
}

export function requestDesktopPinApp(appId, options = {}) {
  const normalizedAppId = String(appId || "").trim();
  if (!normalizedAppId) return false;
  return postDesktopBridgeMessage("pin-app", {
    appId: normalizedAppId,
    title: String(options.title || "").trim(),
  });
}

export function notifyDesktopWallpaperChange() {
  return postDesktopBridgeMessage("wallpaper-change", {});
}

export function openRouteInDesktop(router, target, options = {}) {
  const resolved = typeof target === "string" ? target : router.resolve(target).fullPath;
  const shouldReplace = options.replace === true;
  const desktopMode = String(options.mode || "").trim();
  if (desktopMode && isEmbeddedDesktopApp()) {
    const requestId = createDesktopBridgeRequestId();
    const posted = requestDesktopOpenPath(resolved, {
      ...options,
      requestId,
    });
    if (posted) {
      return new Promise((resolve) => {
        let settled = false;
        const cleanup = () => {
          window.removeEventListener("message", handleAck);
          window.clearTimeout(timerId);
        };
        const finish = (handledByDesktop) => {
          if (settled) return;
          settled = true;
          cleanup();
          if (handledByDesktop) {
            resolve();
            return;
          }
          resolve(shouldReplace ? router.replace(target) : router.push(target));
        };
        const handleAck = (event) => {
          if (event.origin !== window.location.origin) return;
          if (!isDesktopBridgeMessage(event.data)) return;
          if (event.data.type !== DESKTOP_BRIDGE_ACK_TYPE) return;
          if (String(event.data.payload?.requestId || "").trim() !== requestId) return;
          finish(true);
        };
        const timerId = window.setTimeout(() => {
          finish(false);
        }, DESKTOP_BRIDGE_ACK_TIMEOUT);
        window.addEventListener("message", handleAck);
      });
    }
  }
  return shouldReplace ? router.replace(target) : router.push(target);
}
