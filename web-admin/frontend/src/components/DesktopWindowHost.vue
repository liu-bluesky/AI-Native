<template>
  <div class="desktop-window-host">
    <div
      ref="mountPoint"
      class="desktop-window-host__mount"
      :class="{ 'desktop-window-host__mount--chat': isChatRoute }"
    >
      <component
        :is="activeComponent"
        v-if="activeComponent"
        :key="routeState.fullPath"
      />
    </div>
    <div v-if="error" class="desktop-window-host__error">{{ error }}</div>
  </div>
</template>

<script setup>
import { computed, defineAsyncComponent, onBeforeUnmount, provide, reactive, ref, watch } from "vue";
import { routeLocationKey, routerKey, routerViewLocationKey } from "vue-router";
import { normalizeDesktopBridgePath } from "@/utils/desktop-app-bridge.js";

const props = defineProps({
  windowId: { type: String, required: true },
  sourcePath: { type: String, required: true },
});

const emit = defineEmits(["route-change"]);
const mountPoint = ref(null);
const error = ref("");

const componentForPath = [
  { match: (path) => path === "/workbench", component: defineAsyncComponent(() => import("@/views/desktop/DesktopWorkbench.vue")) },
  { match: (path) => path === "/desktop/task-manager", component: defineAsyncComponent(() => import("@/views/desktop/DesktopTaskManager.vue")) },
  { match: (path) => path === "/work-logs", component: defineAsyncComponent(() => import("@/views/desktop/ProjectWorkLog.vue")) },
  { match: (path) => path === "/tasks", component: defineAsyncComponent(() => import("@/views/tasks/TaskManager.vue")) },
  { match: (path) => path === "/feedback", component: defineAsyncComponent(() => import("@/views/desktop/DesktopFeedback.vue")) },
  { match: (path) => path === "/settings-center", component: defineAsyncComponent(() => import("@/views/desktop/SettingsLauncher.vue")) },
  { match: (path) => path === "/desktop/background", component: defineAsyncComponent(() => import("@/views/desktop/DesktopWallpaperSettings.vue")) },
  { match: (path) => path === "/ai/chat" || path.startsWith("/ai/chat/settings"), component: defineAsyncComponent(() => import("@/views/projects/ProjectChat.vue")) },
  { match: (path) => path === "/ai/supervision", component: defineAsyncComponent(() => import("@/views/desktop/AgentSupervision.vue")) },
  { match: (path) => path === "/projects", component: defineAsyncComponent(() => import("@/views/projects/ProjectList.vue")) },
  { match: (path) => /^\/projects\/[^/]+$/.test(path), component: defineAsyncComponent(() => import("@/views/projects/ProjectDetail.vue")) },
  { match: (path) => path === "/memory" || path.startsWith("/memory/"), component: defineAsyncComponent(() => import("@/views/memory/MemoryManager.vue")) },
  { match: (path) => path === "/system/config", component: defineAsyncComponent(() => import("@/views/system/SystemConfig.vue")) },
  { match: (path) => path === "/system/bot-connectors", component: defineAsyncComponent(() => import("@/views/system/SystemBotConnectors.vue")) },
  { match: (path) => path === "/system/ftp-credentials", component: defineAsyncComponent(() => import("@/views/system/SystemFtpCredentials.vue")) },
  { match: (path) => path === "/changelog-entries", component: defineAsyncComponent(() => import("@/views/system/ChangelogManager.vue")) },
  { match: (path) => path === "/llm/providers", component: defineAsyncComponent(() => import("@/views/llm/ModelProviderManager.vue")) },
  { match: (path) => path === "/account", component: defineAsyncComponent(() => import("@/views/account/AccountCenter.vue")) },
  { match: (path) => path === "/account/settings", component: defineAsyncComponent(() => import("@/views/users/UserSettings.vue")) },
];

function parseRoute(path) {
  const normalized = normalizeDesktopBridgePath(path) || "/workbench";
  const url = new URL(normalized, "http://desktop.local");
  const routePath = url.pathname || "/workbench";
  const query = Object.fromEntries(url.searchParams.entries());
  const params = {};
  const projectMatch = routePath.match(/^\/projects\/([^/]+)$/);
  const memoryMatch = routePath.match(/^\/memory\/([^/]+)$/);
  if (projectMatch) params.id = decodeURIComponent(projectMatch[1]);
  if (memoryMatch) params.id = decodeURIComponent(memoryMatch[1]);
  return {
    path: routePath,
    fullPath: `${routePath}${url.search}${url.hash}`,
    query,
    params,
    hash: url.hash,
    name: undefined,
    matched: [],
    meta: {},
  };
}

const routeState = reactive(parseRoute(props.sourcePath));
const currentRoute = ref(routeState);

function resolveTarget(location) {
  if (typeof location === "string") return location;
  if (!location || typeof location !== "object") return routeState.fullPath;
  const targetPath = String(location.path || routeState.path || "/workbench");
  const targetQuery = location.query && typeof location.query === "object"
    ? new URLSearchParams(location.query).toString()
    : "";
  return `${targetPath}${targetQuery ? `?${targetQuery}` : ""}${String(location.hash || "")}`;
}

function navigate(location) {
  const nextPath = normalizeDesktopBridgePath(resolveTarget(location)) || "/workbench";
  const nextRoute = parseRoute(nextPath);
  Object.assign(routeState, nextRoute);
  currentRoute.value = routeState;
  emit("route-change", { path: routeState.fullPath, windowId: props.windowId });
  return Promise.resolve(routeState);
}

const windowRouter = {
  currentRoute,
  push: navigate,
  replace: navigate,
  back: () => Promise.resolve(),
  forward: () => Promise.resolve(),
  go: () => Promise.resolve(),
  resolve: (location) => parseRoute(resolveTarget(location)),
  isReady: () => Promise.resolve(),
};

provide(routerKey, windowRouter);
provide(routeLocationKey, routeState);
provide(routerViewLocationKey, currentRoute);

const activeComponent = computed(() =>
  componentForPath.find((entry) => entry.match(routeState.path))?.component || null,
);
const isChatRoute = computed(() =>
  routeState.path === "/ai/chat" || routeState.path.startsWith("/ai/chat/settings"),
);

watch(
  () => props.sourcePath,
  (path) => {
    const nextRoute = parseRoute(path);
    Object.assign(routeState, nextRoute);
    currentRoute.value = routeState;
    error.value = "";
  },
);

onBeforeUnmount(() => {
  mountPoint.value = null;
});
</script>

<style scoped>
.desktop-window-host {
  position: relative;
  width: 100%;
  height: 100%;
  min-height: 0;
  overflow: hidden;
}

.desktop-window-host__mount {
  width: 100%;
  height: 100%;
  min-height: 0;
  overflow-x: hidden;
  overflow-y: auto;
}

.desktop-window-host__mount :deep(> *) {
  width: 100%;
  min-height: 0;
}

.desktop-window-host__mount--chat {
  display: flex;
  flex-direction: column;
  overflow: hidden;
}

.desktop-window-host__mount--chat :deep(> *) {
  flex: 1 1 auto;
  min-height: 0;
}

.desktop-window-host__mount--chat :deep(> .settings-center-page) {
  min-height: 0;
  max-height: 100%;
  height: auto !important;
}

.desktop-window-host__error {
  position: absolute;
  inset: 0;
  display: grid;
  place-items: center;
  padding: 24px;
  color: #b42318;
  background: #fff7f6;
  text-align: center;
}
</style>
