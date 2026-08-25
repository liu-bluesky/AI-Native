export const DESKTOP_WINDOW_MANAGER_STATE_EVENT =
  "desktop-window-manager-state";
export const DESKTOP_WINDOW_MANAGER_ACTION_EVENT =
  "desktop-window-manager-action";

let latestDesktopWindowManagerState = {
  activeWindowId: "",
  windows: [],
};

function canUseWindow() {
  return typeof window !== "undefined";
}

function normalizeWindow(windowItem = {}) {
  return {
    id: String(windowItem?.id || "").trim(),
    appId: String(windowItem?.appId || "").trim(),
    title: String(windowItem?.title || "").trim(),
    eyebrow: String(windowItem?.eyebrow || "").trim(),
    minimized: Boolean(windowItem?.minimized),
    maximized: Boolean(windowItem?.maximized),
    zIndex: Number(windowItem?.zIndex || 0),
  };
}

export function readDesktopWindowManagerState() {
  return latestDesktopWindowManagerState;
}

export function publishDesktopWindowManagerState(payload = {}) {
  const windows = Array.isArray(payload?.windows)
    ? payload.windows.map(normalizeWindow).filter((item) => item.id)
    : [];
  latestDesktopWindowManagerState = {
    activeWindowId: String(payload?.activeWindowId || "").trim(),
    windows,
  };
  if (!canUseWindow()) return latestDesktopWindowManagerState;
  window.dispatchEvent(
    new CustomEvent(DESKTOP_WINDOW_MANAGER_STATE_EVENT, {
      detail: latestDesktopWindowManagerState,
    }),
  );
  return latestDesktopWindowManagerState;
}

export function requestDesktopWindowManagerAction(action, windowId) {
  const normalizedAction = String(action || "").trim();
  const normalizedWindowId = String(windowId || "").trim();
  if (!canUseWindow() || !normalizedAction || !normalizedWindowId) return false;
  window.dispatchEvent(
    new CustomEvent(DESKTOP_WINDOW_MANAGER_ACTION_EVENT, {
      detail: {
        action: normalizedAction,
        windowId: normalizedWindowId,
      },
    }),
  );
  return true;
}
