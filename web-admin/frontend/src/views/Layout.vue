<template>
  <div v-if="isEmbeddedMode" class="embedded-layout">
    <router-view />
  </div>

  <DesktopSystemShell
    v-else
    :dock-items="dockItems"
    :launcher-items="launcherItems"
    :windows="desktopWindows"
    :active-window-id="activeWindowId"
    :status-text="statusText"
    :show-launcher="launcherOpen"
    :wallpaper-appearance="wallpaperAppearance"
    @launch-app="handleLaunchApp"
    @focus-window="focusWindow"
    @close-window="closeWindow"
    @minimize-window="minimizeWindow"
    @maximize-window="maximizeWindow"
    @refresh-window="refreshWindow"
    @move-window="moveWindow"
    @resize-window="resizeWindow"
    @toggle-launcher="toggleLauncher"
    @clear-cache="clearDesktopCache"
    @unpin-dock-app="unpinDockApp"
    @reorder-dock-apps="reorderDockApps"
  >
    <template #window="{ window }">
      <div class="layout-window-frame" :class="{ 'is-workbench': window.appId === 'workbench' }">
        <iframe
          class="layout-window-frame__iframe"
          :src="window.embeddedUrl"
          :title="window.title"
        />
      </div>
    </template>
  </DesktopSystemShell>
</template>

<script setup>
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from "vue";
import { useRoute, useRouter } from "vue-router";
import DesktopSystemShell from "@/components/DesktopSystemShell.vue";
import { canAccessPath } from "@/utils/permissions.js";
import {
  buildEmbeddedAppUrl,
  canAccessDesktopApp,
  canPinDesktopApp,
  clearStoredDesktopWindowSession,
  clearDesktopRuntimeStorage,
  DESKTOP_DOCK_ITEMS,
  DESKTOP_LAUNCHER_ITEMS,
  getDesktopWallpaperConfig,
  getDesktopAppById,
  getStoredDesktopDockAppIds,
  getStoredDesktopDockOrder,
  getStoredDesktopWindowSession,
  getStoredProjectContextId,
  resolveDesktopWallpaperAppearance,
  resolveDesktopAppMeta,
  resolveDesktopLaunchPath,
  setStoredDesktopWindowSession,
  setStoredDesktopDockAppIds,
  setStoredDesktopDockOrder,
} from "@/utils/desktop-shell.js";
import {
  isDesktopBridgeMessage,
  normalizeDesktopBridgePath,
  notifyDesktopRouteChange,
} from "@/utils/desktop-app-bridge.js";

const DESKTOP_HOME_PATH = "/workbench";
const DESKTOP_SHELL_PATHS = new Set([DESKTOP_HOME_PATH, "/desktop"]);

const route = useRoute();
const router = useRouter();

const launcherItems = computed(() =>
  DESKTOP_LAUNCHER_ITEMS.filter((item) => canAccessDesktopApp(item)),
);
const desktopWindows = ref([]);
const activeWindowId = ref("");
const launcherOpen = ref(false);
const wallpaperConfig = ref(getDesktopWallpaperConfig());
const dockAppIds = ref(getStoredDesktopDockAppIds());
const dockOrder = ref(getStoredDesktopDockOrder());
const nextWindowOrder = ref(1);
const currentDesktopPath = ref(DESKTOP_HOME_PATH);
const suppressNextRouteWindowSync = ref(false);
const desktopSessionHydrated = ref(false);
const DESKTOP_WINDOW_SESSION_VERSION = 1;

const dockItems = computed(() => {
  const itemsById = new Map();
  for (const item of DESKTOP_DOCK_ITEMS) {
    if (!canAccessDesktopApp(item)) continue;
    itemsById.set(item.id, item);
  }
  for (const appId of dockAppIds.value) {
    if (itemsById.has(appId)) continue;
    const app = getDesktopAppById(appId);
    if (!canAccessDesktopApp(app)) continue;
    if (!app?.id || itemsById.has(app.id)) continue;
    itemsById.set(app.id, {
      ...app,
      dockPinned: true,
      dockRemovable: true,
    });
  }
  const orderedIds = [];
  const seen = new Set();
  for (const appId of dockOrder.value) {
    if (!itemsById.has(appId) || seen.has(appId)) continue;
    orderedIds.push(appId);
    seen.add(appId);
  }
  for (const appId of itemsById.keys()) {
    if (seen.has(appId)) continue;
    orderedIds.push(appId);
    seen.add(appId);
  }
  return orderedIds.map((appId) => itemsById.get(appId)).filter(Boolean);
});

const isEmbeddedMode = computed(() => {
  if (typeof window === "undefined") return false;
  return new URLSearchParams(window.location.search).get("embedded") === "1";
});

const statusText = computed(() => {
  if (!desktopWindows.value.length) return "Desktop Ready";
  const activeWindow = desktopWindows.value.find((item) => item.id === activeWindowId.value);
  if (!activeWindow) return "Desktop Running";
  if (activeWindow.minimized) return `${activeWindow.title} Minimized`;
  return `${activeWindow.title} Active`;
});
const wallpaperAppearance = computed(() =>
  resolveDesktopWallpaperAppearance(wallpaperConfig.value),
);
const DESKTOP_WINDOW_MIN_WIDTH = 720;
const DESKTOP_WINDOW_MIN_HEIGHT = 480;
const DESKTOP_WINDOW_MINIMIZE_DURATION = 680;
const windowMotionTimers = new Map();

function createWindowMotionState() {
  return {
    motionActive: false,
    motionPhase: "",
    motionTransitionEnabled: false,
    motionTranslateX: 0,
    motionTranslateY: 0,
    motionScale: 1,
    motionOpacity: 1,
    motionBlur: 0,
    motionDuration: DESKTOP_WINDOW_MINIMIZE_DURATION,
  };
}

function clearWindowMotionTimer(windowId) {
  const timerId = windowMotionTimers.get(windowId);
  if (timerId) {
    globalThis.clearTimeout(timerId);
    windowMotionTimers.delete(windowId);
  }
}

function resetWindowMotion(window) {
  return {
    ...window,
    ...createWindowMotionState(),
  };
}

function getDockTargetRect(appId) {
  if (typeof document === "undefined") return null;
  const normalizedAppId = String(appId || "").trim();
  if (normalizedAppId) {
    const dockItem = document.querySelector(
      `[data-dock-app-id="${normalizedAppId}"] .desktop-system__dock-item`,
    );
    if (dockItem) {
      return dockItem.getBoundingClientRect();
    }
  }
  const dock = document.querySelector(".desktop-system__dock");
  return dock?.getBoundingClientRect?.() || null;
}

function resolveMinimizeMotion(window) {
  const viewportWidth =
    typeof globalThis.window !== "undefined"
      ? globalThis.window.innerWidth || 1440
      : 1440;
  const viewportHeight =
    typeof globalThis.window !== "undefined"
      ? globalThis.window.innerHeight || 900
      : 900;
  const dockRect = getDockTargetRect(window.appId);
  const windowWidth = Number(
    window.maximized ? viewportWidth : window.width || DESKTOP_WINDOW_MIN_WIDTH,
  );
  const windowHeight = Number(
    window.maximized ? viewportHeight : window.height || DESKTOP_WINDOW_MIN_HEIGHT,
  );
  const baseX = Number(window.maximized ? 0 : window.x || 0);
  const baseY = Number(window.maximized ? 0 : window.y || 0);
  const windowCenterX = baseX + windowWidth / 2;
  const windowCenterY = baseY + windowHeight / 2;
  const motionScale = dockRect
    ? Math.min(dockRect.width / windowWidth, 0.18)
    : 0.12;
  const targetCenterX = dockRect
    ? dockRect.left + dockRect.width / 2
    : viewportWidth / 2;
  const targetCenterY = dockRect
    ? dockRect.top - 4 - (windowHeight * motionScale) / 2
    : viewportHeight + 36;
  return {
    motionTranslateX: targetCenterX - windowCenterX,
    motionTranslateY: targetCenterY - windowCenterY,
    motionScale,
    motionOpacity: 1,
    motionBlur: 0,
    motionDuration: DESKTOP_WINDOW_MINIMIZE_DURATION,
  };
}

function playOpenWindowMotion(windowId) {
  const targetId = String(windowId || "").trim();
  if (!targetId) return;
  const targetWindow = desktopWindows.value.find((item) => item.id === targetId);
  if (!targetWindow) return;
  clearWindowMotionTimer(targetId);
  const motion = resolveMinimizeMotion(targetWindow);
  desktopWindows.value = desktopWindows.value.map((item) =>
    item.id === targetId
      ? {
          ...item,
          minimized: false,
          motionActive: true,
          motionPhase: "open",
          motionTransitionEnabled: false,
          ...motion,
        }
      : item,
  );

  void nextTick(() => {
    desktopWindows.value = desktopWindows.value.map((item) =>
      item.id === targetId
        ? {
            ...item,
            motionActive: true,
            motionPhase: "open",
            motionTransitionEnabled: true,
            motionTranslateX: 0,
            motionTranslateY: 0,
            motionScale: 1,
            motionOpacity: 1,
            motionBlur: 0,
            motionDuration: DESKTOP_WINDOW_MINIMIZE_DURATION,
          }
        : item,
    );
  });

  const timerId = window.setTimeout(() => {
    desktopWindows.value = desktopWindows.value.map((item) =>
      item.id === targetId ? resetWindowMotion(item) : item,
    );
    windowMotionTimers.delete(targetId);
  }, DESKTOP_WINDOW_MINIMIZE_DURATION);
  windowMotionTimers.set(targetId, timerId);
}

function clampWindowBounds(payload) {
  const viewportWidth =
    typeof window === "undefined" ? 1440 : window.innerWidth || 1440;
  const viewportHeight =
    typeof window === "undefined" ? 900 : window.innerHeight || 900;
  const maxWidth = Math.max(DESKTOP_WINDOW_MIN_WIDTH, viewportWidth);
  const maxHeight = Math.max(DESKTOP_WINDOW_MIN_HEIGHT, viewportHeight);
  const width = Math.min(
    Math.max(Number(payload?.width || DESKTOP_WINDOW_MIN_WIDTH), DESKTOP_WINDOW_MIN_WIDTH),
    maxWidth,
  );
  const height = Math.min(
    Math.max(Number(payload?.height || DESKTOP_WINDOW_MIN_HEIGHT), DESKTOP_WINDOW_MIN_HEIGHT),
    maxHeight,
  );
  const x = Math.min(
    Math.max(Number(payload?.x || 0), 0),
    Math.max(0, viewportWidth - width),
  );
  const y = Math.min(
    Math.max(Number(payload?.y || 0), 0),
    Math.max(0, viewportHeight - height),
  );
  return { x, y, width, height };
}

function createDesktopSessionSnapshot() {
  return {
    version: DESKTOP_WINDOW_SESSION_VERSION,
    activeWindowId: activeWindowId.value,
    currentDesktopPath: currentDesktopPath.value,
    nextWindowOrder: nextWindowOrder.value,
    windows: desktopWindows.value.map((item) => ({
      id: item.id,
      appId: item.appId,
      title: item.title,
      eyebrow: item.eyebrow,
      summary: item.summary,
      sourcePath: item.sourcePath,
      width: item.width,
      height: item.height,
      x: item.x,
      y: item.y,
      zIndex: item.zIndex,
      minimized: item.minimized,
      maximized: item.maximized,
      restoredX: item.restoredX,
      restoredY: item.restoredY,
      restoredWidth: item.restoredWidth,
      restoredHeight: item.restoredHeight,
    })),
  };
}

function persistDesktopSession() {
  if (typeof window === "undefined" || isEmbeddedMode.value || !desktopSessionHydrated.value) {
    return;
  }
  if (!desktopWindows.value.length) {
    clearStoredDesktopWindowSession();
    return;
  }
  setStoredDesktopWindowSession(createDesktopSessionSnapshot());
}

function createRestoredWindow(rawWindow, index, usedIds) {
  const sourcePath = normalizeDesktopBridgePath(rawWindow?.sourcePath || rawWindow?.path);
  if (!sourcePath) return null;
  const meta = resolveDesktopAppMeta(sourcePath);
  const baseId =
    String(rawWindow?.id || "").trim()
    || `desktop-window-${meta.appId}-${Date.now()}-${index}`;
  let nextId = baseId;
  let suffix = 1;
  while (usedIds.has(nextId)) {
    nextId = `${baseId}-${suffix}`;
    suffix += 1;
  }
  const defaultOffset = index * 28;
  const bounds = clampWindowBounds({
    x: rawWindow?.x ?? (36 + defaultOffset),
    y: rawWindow?.y ?? (32 + defaultOffset),
    width: rawWindow?.width ?? meta.width,
    height: rawWindow?.height ?? meta.height,
  });
  const restoredBounds = clampWindowBounds({
    x: rawWindow?.restoredX ?? bounds.x,
    y: rawWindow?.restoredY ?? bounds.y,
    width: rawWindow?.restoredWidth ?? bounds.width,
    height: rawWindow?.restoredHeight ?? bounds.height,
  });
  return {
    id: nextId,
    appId: String(rawWindow?.appId || "").trim() || meta.appId,
    title: String(rawWindow?.title || "").trim() || meta.appName,
    eyebrow: String(rawWindow?.eyebrow || "").trim() || meta.appEyebrow,
    summary: String(rawWindow?.summary || "").trim() || meta.appSummary,
    sourcePath,
    embeddedUrl: buildEmbeddedAppUrl(sourcePath, { windowId: nextId }),
    width: bounds.width,
    height: bounds.height,
    x: bounds.x,
    y: bounds.y,
    zIndex: Math.max(1, Number(rawWindow?.zIndex || index + 1)),
    minimized: rawWindow?.minimized === true,
    maximized: rawWindow?.maximized === true,
    restoredX: restoredBounds.x,
    restoredY: restoredBounds.y,
    restoredWidth: restoredBounds.width,
    restoredHeight: restoredBounds.height,
    ...createWindowMotionState(),
  };
}

function restoreDesktopSession() {
  const snapshot = getStoredDesktopWindowSession();
  if (!snapshot || !Array.isArray(snapshot.windows) || !snapshot.windows.length) {
    desktopWindows.value = [];
    activeWindowId.value = "";
    currentDesktopPath.value = DESKTOP_HOME_PATH;
    nextWindowOrder.value = 1;
    return;
  }
  const usedIds = new Set();
  const restoredWindows = [];
  let maxZIndex = 0;
  snapshot.windows.forEach((item, index) => {
    const restoredWindow = createRestoredWindow(item, index, usedIds);
    if (!restoredWindow) return;
    usedIds.add(restoredWindow.id);
    maxZIndex = Math.max(maxZIndex, Number(restoredWindow.zIndex || 0));
    restoredWindows.push(restoredWindow);
  });
  if (!restoredWindows.length) {
    clearStoredDesktopWindowSession();
    desktopWindows.value = [];
    activeWindowId.value = "";
    currentDesktopPath.value = DESKTOP_HOME_PATH;
    nextWindowOrder.value = 1;
    return;
  }
  const highestWindow = [...restoredWindows].sort(
    (left, right) => Number(right.zIndex || 0) - Number(left.zIndex || 0),
  )[0];
  const restoredActiveId = restoredWindows.some(
    (item) => item.id === String(snapshot.activeWindowId || "").trim(),
  )
    ? String(snapshot.activeWindowId || "").trim()
    : highestWindow?.id || "";
  desktopWindows.value = restoredWindows;
  activeWindowId.value = restoredActiveId;
  currentDesktopPath.value =
    normalizeDesktopBridgePath(snapshot.currentDesktopPath)
    || restoredWindows.find((item) => item.id === restoredActiveId)?.sourcePath
    || DESKTOP_HOME_PATH;
  nextWindowOrder.value = Math.max(
    Number(snapshot.nextWindowOrder || 1),
    maxZIndex + 1,
    1,
  );
}

watch(
  () => route.fullPath,
  (fullPath) => {
    if (isEmbeddedMode.value || !desktopSessionHydrated.value) return;
    if (suppressNextRouteWindowSync.value) {
      suppressNextRouteWindowSync.value = false;
      return;
    }
    syncRouteAsWindow(fullPath);
  },
  { immediate: true },
);

function ensureDesktopHomeRoute() {
  if (isEmbeddedMode.value) return;
  if (route.path === DESKTOP_HOME_PATH) return;
  suppressNextRouteWindowSync.value = true;
  void router.replace(DESKTOP_HOME_PATH);
}

function createWindowForPath(path, payload = {}) {
  const meta = resolveDesktopAppMeta(path);
  const countForApp = desktopWindows.value.filter((item) => item.appId === meta.appId).length;
  const offset = countForApp * 28;
  const id = `desktop-window-${meta.appId}-${Date.now()}`;
  const nextWindow = {
    id,
    appId: String(payload.appId || "").trim() || meta.appId,
    title: String(payload.title || "").trim() || meta.appName,
    eyebrow: String(payload.eyebrow || "").trim() || meta.appEyebrow,
    summary: String(payload.summary || "").trim() || meta.appSummary,
    sourcePath: path,
    embeddedUrl: buildEmbeddedAppUrl(path, { windowId: id }),
    width: Number(payload.width || meta.width),
    height: Number(payload.height || meta.height),
    x: 36 + offset,
    y: 32 + offset,
    zIndex: nextWindowOrder.value,
    minimized: false,
    maximized: false,
    restoredX: 36 + offset,
    restoredY: 32 + offset,
    restoredWidth: Number(payload.width || meta.width),
    restoredHeight: Number(payload.height || meta.height),
    ...createWindowMotionState(),
  };
  nextWindowOrder.value += 1;
  desktopWindows.value = [...desktopWindows.value, nextWindow];
  activeWindowId.value = nextWindow.id;
  currentDesktopPath.value = path;
  ensureDesktopHomeRoute();
  if (payload.animateFromDock !== false) {
    playOpenWindowMotion(nextWindow.id);
  }
}

function syncRouteAsWindow(fullPath) {
  if (isEmbeddedMode.value) return;
  const path = normalizeDesktopBridgePath(fullPath);
  if (
    !path
    || path === "/"
    || path === "/intro"
    || path === "/login"
    || path === "/register"
  ) {
    return;
  }

  if (DESKTOP_SHELL_PATHS.has(path)) {
    currentDesktopPath.value = path;
    return;
  }

  currentDesktopPath.value = path;
  const meta = resolveDesktopAppMeta(path);
  const existing = desktopWindows.value.find((item) => item.sourcePath === path)
    || (
      meta.appId !== "project-detail"
        ? desktopWindows.value.find((item) => item.appId === meta.appId)
        : null
    );
  if (existing) {
    if (existing.sourcePath !== path) {
      desktopWindows.value = desktopWindows.value.map((item) =>
        item.id === existing.id
          ? {
              ...item,
              sourcePath: path,
              embeddedUrl: buildEmbeddedAppUrl(path, { windowId: existing.id }),
              title: meta.appName,
              eyebrow: meta.appEyebrow,
              summary: meta.appSummary,
              appId: meta.appId,
            }
          : item,
      );
    }
    focusWindow(existing.id, {
      animateFromDock: existing.minimized,
    });
    ensureDesktopHomeRoute();
    return;
  }
  createWindowForPath(path, {
    animateFromDock: false,
  });
}

function handleLaunchApp(item) {
  launcherOpen.value = false;
  const app = getDesktopAppById(item?.id || item?.appId);
  if (!canAccessDesktopApp(app)) return;
  const normalizedAppId = String(app.id || "").trim();
  const existingWindow = desktopWindows.value.find((entry) => entry.appId === normalizedAppId);
  if (existingWindow) {
    focusWindow(existingWindow.id, {
      animateFromDock: existingWindow.minimized,
    });
    return;
  }
  const launchPath = resolveDesktopLaunchPath(normalizedAppId);
  openPathAsWindow(launchPath, {
    mode: "focus-or-open",
    appId: normalizedAppId,
    title: app.label,
    summary: app.summary,
    eyebrow: app.eyebrow,
  });
}

function focusWindow(windowId, options = {}) {
  const targetId = String(windowId || "").trim();
  if (!targetId) return;
  const shouldAnimateFromDock = options.animateFromDock === true;
  clearWindowMotionTimer(targetId);
  launcherOpen.value = false;
  const targetWindow = desktopWindows.value.find((item) => item.id === targetId);
  const wasMinimized = Boolean(targetWindow?.minimized);
  activeWindowId.value = targetId;
  nextWindowOrder.value += 1;
  desktopWindows.value = desktopWindows.value.map((item) =>
    item.id === targetId
      ? {
          ...resetWindowMotion(item),
          minimized: false,
          zIndex: nextWindowOrder.value,
        }
      : item,
  );
  if (shouldAnimateFromDock || wasMinimized) {
    playOpenWindowMotion(targetId);
  }
}

function closeWindow(windowId) {
  const targetId = String(windowId || "").trim();
  clearWindowMotionTimer(targetId);
  const remaining = desktopWindows.value.filter((item) => item.id !== targetId);
  if (remaining.length === desktopWindows.value.length) return;

  desktopWindows.value = remaining;
  if (!remaining.length) {
    activeWindowId.value = "";
    currentDesktopPath.value = DESKTOP_HOME_PATH;
    ensureDesktopHomeRoute();
    return;
  }

  const nextActive = [...remaining].sort((left, right) => Number(right.zIndex || 0) - Number(left.zIndex || 0))[0];
  activeWindowId.value = nextActive.id;
}

function minimizeWindow(windowId) {
  const targetId = String(windowId || "").trim();
  const targetWindow = desktopWindows.value.find((item) => item.id === targetId);
  if (!targetWindow || targetWindow.minimized) return;
  clearWindowMotionTimer(targetId);
  const minimizeMotion = resolveMinimizeMotion(targetWindow);
  desktopWindows.value = desktopWindows.value.map((item) =>
    item.id === targetId
      ? {
          ...item,
          minimized: false,
          motionActive: true,
          motionPhase: "minimize",
          motionTransitionEnabled: true,
          ...minimizeMotion,
        }
      : item,
  );

  const timerId = window.setTimeout(() => {
    desktopWindows.value = desktopWindows.value.map((item) =>
      item.id === targetId
        ? {
            ...resetWindowMotion(item),
            minimized: true,
          }
        : item,
    );
    windowMotionTimers.delete(targetId);
  }, DESKTOP_WINDOW_MINIMIZE_DURATION);
  windowMotionTimers.set(targetId, timerId);

  if (activeWindowId.value !== targetId) return;
  const nextActive = [...desktopWindows.value]
    .filter((item) => item.id !== targetId && !item.minimized)
    .sort((left, right) => Number(right.zIndex || 0) - Number(left.zIndex || 0))[0];
  if (nextActive) {
    focusWindow(nextActive.id);
    return;
  }
  activeWindowId.value = "";
  currentDesktopPath.value = DESKTOP_HOME_PATH;
}

function maximizeWindow(windowId) {
  const targetId = String(windowId || "").trim();
  desktopWindows.value = desktopWindows.value.map((item) =>
    item.id === targetId
      ? {
          ...item,
          maximized: !item.maximized,
          x: item.maximized ? Number(item.restoredX ?? 36) : 0,
          y: item.maximized ? Number(item.restoredY ?? 32) : 0,
          width: item.maximized
            ? Number(
                item.restoredWidth
                  ?? resolveDesktopAppMeta(item.sourcePath).width,
              )
            : Number(item.width || resolveDesktopAppMeta(item.sourcePath).width),
          height: item.maximized
            ? Number(
                item.restoredHeight
                  ?? resolveDesktopAppMeta(item.sourcePath).height,
              )
            : Number(
                item.height || resolveDesktopAppMeta(item.sourcePath).height,
              ),
          restoredX: item.maximized ? item.restoredX : item.x,
          restoredY: item.maximized ? item.restoredY : item.y,
          restoredWidth: item.maximized ? item.restoredWidth : item.width,
          restoredHeight: item.maximized ? item.restoredHeight : item.height,
        }
      : item,
  );
  focusWindow(targetId);
}

function refreshWindow(windowId) {
  const targetId = String(windowId || "").trim();
  if (!targetId) return;
  const targetWindow = desktopWindows.value.find((item) => item.id === targetId);
  if (!targetWindow) return;
  desktopWindows.value = desktopWindows.value.map((item) =>
    item.id === targetId
      ? {
          ...item,
          embeddedUrl: buildEmbeddedAppUrl(item.sourcePath, {
            windowId: item.id,
            reloadKey: `${Date.now()}`,
          }),
        }
      : item,
  );
  focusWindow(targetId);
}

function moveWindow(payload) {
  const targetId = String(payload?.windowId || "").trim();
  if (!targetId) return;
  const targetWindow = desktopWindows.value.find((item) => item.id === targetId);
  if (!targetWindow || targetWindow.maximized) return;
  const nextBounds = clampWindowBounds({
    x: payload?.x,
    y: payload?.y,
    width: targetWindow.width,
    height: targetWindow.height,
  });
  desktopWindows.value = desktopWindows.value.map((item) =>
    item.id === targetId && !item.maximized
      ? {
          ...item,
          x: nextBounds.x,
          y: nextBounds.y,
          restoredX: nextBounds.x,
          restoredY: nextBounds.y,
        }
      : item,
  );
}

function resizeWindow(payload) {
  const targetId = String(payload?.windowId || "").trim();
  if (!targetId) return;
  const targetWindow = desktopWindows.value.find((item) => item.id === targetId);
  if (!targetWindow || targetWindow.maximized) return;
  const direction = String(payload?.direction || "").trim();
  let nextBounds = clampWindowBounds(payload);
  const rightEdge = Number(targetWindow.x || 0) + Number(targetWindow.width || DESKTOP_WINDOW_MIN_WIDTH);
  const bottomEdge =
    Number(targetWindow.y || 0) + Number(targetWindow.height || DESKTOP_WINDOW_MIN_HEIGHT);
  if (direction.includes("w")) {
    nextBounds = {
      ...nextBounds,
      x: Math.max(0, rightEdge - nextBounds.width),
    };
  }
  if (direction.includes("n")) {
    nextBounds = {
      ...nextBounds,
      y: Math.max(0, bottomEdge - nextBounds.height),
    };
  }
  desktopWindows.value = desktopWindows.value.map((item) =>
    item.id === targetId && !item.maximized
      ? {
          ...item,
          x: nextBounds.x,
          y: nextBounds.y,
          width: nextBounds.width,
          height: nextBounds.height,
          restoredX: nextBounds.x,
          restoredY: nextBounds.y,
          restoredWidth: nextBounds.width,
          restoredHeight: nextBounds.height,
        }
      : item,
  );
}

watch(
  () => route.fullPath,
  (fullPath) => {
    const normalizedPath = normalizeDesktopBridgePath(fullPath);
    if (!normalizedPath) return;
    const projectDetailMatch = normalizedPath.match(/^\/projects\/([^/?#]+)/);
    if (projectDetailMatch?.[1]) {
      const projectId = decodeURIComponent(projectDetailMatch[1]);
      if (projectId) {
        window.localStorage.setItem("project_id", projectId);
      }
      return;
    }
    if (!normalizedPath.startsWith("/materials")) return;
    const resolvedUrl = new URL(normalizedPath, window.location.origin);
    const projectId = String(resolvedUrl.searchParams.get("project_id") || "").trim() || getStoredProjectContextId();
    if (projectId) {
      window.localStorage.setItem("project_id", projectId);
    }
  },
  { immediate: true },
);

function toggleLauncher() {
  launcherOpen.value = !launcherOpen.value;
}

function persistDockAppIds(nextIds) {
  dockAppIds.value = setStoredDesktopDockAppIds(nextIds);
}

function persistDockOrder(nextOrder) {
  dockOrder.value = setStoredDesktopDockOrder(nextOrder);
}

function syncDockOrderWithState(nextPinnedIds = dockAppIds.value) {
  const requiredIds = DESKTOP_DOCK_ITEMS.map((item) => item.id);
  const nextOrder = [];
  const seen = new Set();
  for (const appId of dockOrder.value) {
    if (seen.has(appId)) continue;
    if (requiredIds.includes(appId) || nextPinnedIds.includes(appId)) {
      nextOrder.push(appId);
      seen.add(appId);
    }
  }
  for (const appId of [...requiredIds, ...nextPinnedIds]) {
    if (seen.has(appId)) continue;
    nextOrder.push(appId);
    seen.add(appId);
  }
  persistDockOrder(nextOrder);
  return nextOrder;
}

function pinDockApp(appId) {
  const app = getDesktopAppById(appId);
  if (!app?.id) return;
  if (!canPinDesktopApp(app.id)) return;
  if (dockAppIds.value.includes(app.id)) return;
  const nextPinnedIds = [...dockAppIds.value, app.id];
  persistDockAppIds(nextPinnedIds);
  syncDockOrderWithState(nextPinnedIds);
}

function unpinDockApp(item) {
  const appId = String(item?.id || item?.appId || "").trim();
  if (!appId) return;
  const nextPinnedIds = dockAppIds.value.filter((id) => id !== appId);
  persistDockAppIds(nextPinnedIds);
  syncDockOrderWithState(nextPinnedIds);
}

function reorderDockApps(nextOrder) {
  if (!Array.isArray(nextOrder) || !nextOrder.length) return;
  const allowedIds = new Set(dockItems.value.map((item) => item.id));
  const filtered = nextOrder.filter((appId) => allowedIds.has(appId));
  if (!filtered.length) return;
  persistDockOrder(filtered);
}

async function clearDesktopCache() {
  for (const windowId of windowMotionTimers.keys()) {
    clearWindowMotionTimer(windowId);
  }
  launcherOpen.value = false;
  desktopWindows.value = [];
  activeWindowId.value = "";
  currentDesktopPath.value = DESKTOP_HOME_PATH;
  nextWindowOrder.value = 1;
  clearDesktopRuntimeStorage({ preserveWallpaper: true, preserveDock: true });
  dockAppIds.value = getStoredDesktopDockAppIds();
  dockOrder.value = getStoredDesktopDockOrder();
  wallpaperConfig.value = getDesktopWallpaperConfig();
  if (typeof window !== "undefined" && "caches" in window) {
    const keys = await window.caches.keys();
    await Promise.all(keys.map((key) => window.caches.delete(key)));
  }
  if (typeof window !== "undefined") {
    window.sessionStorage?.clear();
  }
  ensureDesktopHomeRoute();
}

function updateWindowFromEmbeddedPath(path, payload = {}) {
  const normalizedPath = normalizeDesktopBridgePath(path);
  if (!normalizedPath) return;

  const normalizedAppId = String(payload.appId || "").trim();
  const sourceWindowId = String(payload.windowId || "").trim();
  const targetWindow =
    desktopWindows.value.find((item) => item.id === sourceWindowId)
    || desktopWindows.value.find((item) => item.id === activeWindowId.value)
    || desktopWindows.value.find((item) => item.sourcePath === currentDesktopPath.value)
    || desktopWindows.value.find((item) => item.appId === normalizedAppId);
  if (!targetWindow) return;

  const meta = resolveDesktopAppMeta(normalizedPath);
  desktopWindows.value = desktopWindows.value.map((item) =>
    item.id === targetWindow.id
      ? {
          ...item,
          appId: normalizedAppId || meta.appId,
          title: String(payload.title || "").trim() || meta.appName,
          eyebrow: String(payload.eyebrow || "").trim() || meta.appEyebrow,
          summary: String(payload.summary || "").trim() || meta.appSummary,
          sourcePath: normalizedPath,
          embeddedUrl: buildEmbeddedAppUrl(normalizedPath, { windowId: targetWindow.id }),
        }
      : item,
  );
  currentDesktopPath.value = normalizedPath;
}

function openPathAsWindow(path, payload = {}) {
  const normalizedPath = normalizeDesktopBridgePath(path);
  if (!normalizedPath) return false;
  if (!canAccessPath(normalizedPath)) return false;

  const meta = resolveDesktopAppMeta(normalizedPath);
  const mode = String(payload.mode || "new-window").trim() || "new-window";
  const requestedAppId = String(payload.appId || "").trim() || meta.appId;
  const existing = mode !== "new-window"
    ? desktopWindows.value.find((item) => item.appId === requestedAppId)
      || desktopWindows.value.find((item) => item.sourcePath === normalizedPath)
    : null;
  if (existing) {
    const nextMeta = resolveDesktopAppMeta(normalizedPath);
    desktopWindows.value = desktopWindows.value.map((item) =>
      item.id === existing.id
        ? {
            ...item,
            appId: requestedAppId,
            title: String(payload.title || "").trim() || nextMeta.appName,
            eyebrow: String(payload.eyebrow || "").trim() || nextMeta.appEyebrow,
            summary: String(payload.summary || "").trim() || nextMeta.appSummary,
            sourcePath: normalizedPath,
            embeddedUrl: buildEmbeddedAppUrl(normalizedPath, { windowId: existing.id }),
          }
        : item,
    );
    focusWindow(existing.id, {
      animateFromDock: existing.minimized,
    });
    currentDesktopPath.value = normalizedPath;
    ensureDesktopHomeRoute();
    return true;
  }
  createWindowForPath(normalizedPath, payload);
  return true;
}

function acknowledgeDesktopOpenPath(event, payload = {}, handled = true) {
  const requestId = String(payload?.requestId || "").trim();
  if (!requestId || typeof event?.source?.postMessage !== "function") return;
  event.source.postMessage(
    {
      source: "ai-employee-desktop-app",
      type: "open-path-ack",
      payload: {
        requestId,
        handled: handled === true,
      },
    },
    event.origin,
  );
}

function handleDesktopBridgeMessage(event) {
  if (event.origin !== window.location.origin) return;
  if (!isDesktopBridgeMessage(event.data)) return;
  const { type, payload } = event.data;
  if (type === "route-change") {
    updateWindowFromEmbeddedPath(payload?.path, payload);
    return;
  }
  if (type === "open-path") {
    const handled = openPathAsWindow(payload?.path, payload);
    acknowledgeDesktopOpenPath(event, payload, handled);
    return;
  }
  if (type === "pin-app") {
    pinDockApp(payload?.appId);
    return;
  }
  if (type === "wallpaper-change") {
    wallpaperConfig.value = getDesktopWallpaperConfig();
  }
}

onMounted(() => {
  if (typeof window === "undefined") return;
  if (isEmbeddedMode.value) return;
  restoreDesktopSession();
  desktopSessionHydrated.value = true;
  syncRouteAsWindow(route.fullPath);
  window.addEventListener("message", handleDesktopBridgeMessage);
  window.addEventListener("storage", handleStorageChange);
});

onBeforeUnmount(() => {
  if (typeof window === "undefined") return;
  if (isEmbeddedMode.value) return;
  for (const windowId of windowMotionTimers.keys()) {
    clearWindowMotionTimer(windowId);
  }
  window.removeEventListener("message", handleDesktopBridgeMessage);
  window.removeEventListener("storage", handleStorageChange);
});

function handleStorageChange(event) {
  const key = String(event?.key || "").trim();
  if (key === "desktop_window_session") {
    restoreDesktopSession();
    return;
  }
  if (key === "desktop_wallpaper_config") {
    wallpaperConfig.value = getDesktopWallpaperConfig();
    return;
  }
  if (key === "desktop_dock_app_ids") {
    dockAppIds.value = getStoredDesktopDockAppIds();
    syncDockOrderWithState(dockAppIds.value);
    return;
  }
  if (key === "desktop_dock_order") {
    dockOrder.value = getStoredDesktopDockOrder();
  }
}

watch(
  () => route.fullPath,
  (fullPath) => {
    if (!isEmbeddedMode.value) return;
    notifyDesktopRouteChange(fullPath, resolveDesktopAppMeta(fullPath));
  },
  { immediate: true },
);

watch(
  [desktopWindows, activeWindowId, currentDesktopPath, nextWindowOrder],
  () => {
    persistDesktopSession();
  },
  { deep: true },
);
</script>

<style scoped>
.embedded-layout {
  min-height: 100vh;
  overflow: auto;
  background: #f8fafc;
}

.layout-window-frame {
  min-height: 100%;
  height: 100%;
  border-radius: 22px;
  overflow: hidden;
  background: rgba(255, 255, 255, 0.72);
}

.layout-window-frame__iframe {
  width: 100%;
  height: 100%;
  border: 0;
  display: block;
  background: #f8fafc;
}
</style>
