const DESKTOP_BRIDGE_SOURCE = "ai-employee-desktop-app";
const DESKTOP_BRIDGE_ACK_TYPE = "open-path-ack";
const DESKTOP_BRIDGE_ACK_TIMEOUT = 360;
export const DESKTOP_BRIDGE_EVENT_NAME = "ai-employee-desktop-bridge";
export const DESKTOP_WINDOW_FILE_DRAG_DROP_EVENT_NAME = "desktop-window-file-drag-drop";
let desktopBridgeRequestSeed = 0;

function canUseWindow() {
  return typeof window !== "undefined";
}

export function isEmbeddedDesktopApp() {
  if (!canUseWindow()) return false;
  const params = new URLSearchParams(window.location.search);
  return params.get("embedded") === "1" && window.parent && window.parent !== window;
}

function desktopWindowIdFromRouter(router) {
  return String(
    router?.__aiEmployeeDesktopWindow?.windowId || "",
  ).trim();
}

function dispatchDesktopBridgeEvent(type, payload = {}) {
  if (!canUseWindow() || typeof window.CustomEvent !== "function") return false;
  const event = new CustomEvent(DESKTOP_BRIDGE_EVENT_NAME, {
    cancelable: true,
    detail: {
      source: DESKTOP_BRIDGE_SOURCE,
      type: String(type || "").trim(),
      payload: payload && typeof payload === "object" ? payload : {},
    },
  });
  window.dispatchEvent(event);
  return event.defaultPrevented;
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
    let hashRoute = parsed.hash.startsWith("#/") ? parsed.hash.slice(1) : "";
    if (hashRoute) {
      const hashUrl = new URL(hashRoute, window.location.origin);
      hashUrl.searchParams.delete("embedded");
      hashUrl.searchParams.delete("desktop_window_id");
      hashUrl.searchParams.delete("desktop_reload_key");
      hashRoute = `${hashUrl.pathname}${hashUrl.search}`;
    }
    parsed.searchParams.delete("embedded");
    parsed.searchParams.delete("desktop_window_id");
    parsed.searchParams.delete("desktop_reload_key");
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

export function notifyDesktopRouteChange(path, meta = {}, router = null) {
  const normalizedPath = normalizeDesktopBridgePath(path);
  if (!normalizedPath) return false;
  const params = canUseWindow() ? new URLSearchParams(window.location.search) : new URLSearchParams();
  const windowId = desktopWindowIdFromRouter(router) || params.get("desktop_window_id") || "";
  const payload = {
    path: normalizedPath,
    windowId,
    title: String(meta.title || "").trim(),
    summary: String(meta.summary || "").trim(),
    eyebrow: String(meta.eyebrow || "").trim(),
    appId: String(meta.appId || "").trim(),
  };
  if (desktopWindowIdFromRouter(router)) {
    return dispatchDesktopBridgeEvent("route-change", payload);
  }
  return postDesktopBridgeMessage("route-change", payload);
}

function createDesktopBridgeRequestId() {
  desktopBridgeRequestSeed += 1;
  return `desktop-bridge-${Date.now()}-${desktopBridgeRequestSeed}`;
}

export function requestDesktopOpenPath(path, options = {}, router = null) {
  const normalizedPath = normalizeDesktopBridgePath(path);
  if (!normalizedPath) return false;
  const payload = {
    path: normalizedPath,
    mode: String(options.mode || "new-window").trim() || "new-window",
    appId: String(options.appId || "").trim(),
    title: String(options.title || "").trim(),
    summary: String(options.summary || "").trim(),
    eyebrow: String(options.eyebrow || "").trim(),
    params: options.params && typeof options.params === "object" ? options.params : {},
    targetWindowId: String(options.targetWindowId || "").trim(),
    requestId: String(options.requestId || "").trim(),
    sourceWindowId: desktopWindowIdFromRouter(router),
  };
  if (desktopWindowIdFromRouter(router)) {
    return dispatchDesktopBridgeEvent("open-path", payload);
  }
  return postDesktopBridgeMessage("open-path", payload);
}

export function requestDesktopPinApp(appId, options = {}, router = null) {
  const normalizedAppId = String(appId || "").trim();
  if (!normalizedAppId) return false;
  const payload = {
    appId: normalizedAppId,
    title: String(options.title || "").trim(),
    windowId: desktopWindowIdFromRouter(router),
  };
  if (desktopWindowIdFromRouter(router)) {
    return dispatchDesktopBridgeEvent("pin-app", payload);
  }
  return postDesktopBridgeMessage("pin-app", payload);
}

export function notifyDesktopWallpaperChange(router = null) {
  const payload = { windowId: desktopWindowIdFromRouter(router) };
  if (desktopWindowIdFromRouter(router)) {
    return dispatchDesktopBridgeEvent("wallpaper-change", payload);
  }
  return postDesktopBridgeMessage("wallpaper-change", payload);
}

export function openRouteInDesktop(router, target, options = {}) {
  const resolved = typeof target === "string" ? target : router.resolve(target).fullPath;
  const shouldReplace = options.replace === true;
  const desktopMode = String(options.mode || "").trim();
  if (desktopMode && desktopWindowIdFromRouter(router)) {
    const handled = requestDesktopOpenPath(resolved, options, router);
    if (handled) return Promise.resolve();
  }
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
