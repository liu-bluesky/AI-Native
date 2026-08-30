<template>
  <div class="desktop-window-host">
    <div
      ref="mountPoint"
      class="desktop-window-host__mount"
      :class="{
        'desktop-window-host__mount--chat': isChatRoute,
        'desktop-window-host__mount--settings': isSettingsRoute,
      }"
    />
    <div v-if="error" class="desktop-window-host__error">{{ error }}</div>
  </div>
</template>

<script setup>
import {
  computed,
  createApp,
  h,
  onBeforeUnmount,
  onMounted,
  ref,
  watch,
} from "vue";
import ElementPlus from "element-plus";
import zhCn from "element-plus/dist/locale/zh-cn.mjs";
import { RouterView } from "vue-router";
import { createDesktopWindowRouter } from "@/router";
import { normalizeDesktopBridgePath } from "@/utils/desktop-app-bridge.js";

const props = defineProps({
  windowId: {
    type: String,
    required: true,
  },
  sourcePath: {
    type: String,
    required: true,
  },
});

const emit = defineEmits(["route-change"]);

const mountPoint = ref(null);
const error = ref("");
const activeRoutePath = ref("");
const isChatRoute = computed(
  () =>
    String(activeRoutePath.value || props.sourcePath || "").trim() ===
    "/ai/chat",
);
const isSettingsRoute = computed(() =>
  String(activeRoutePath.value || props.sourcePath || "")
    .trim()
    .startsWith("/ai/chat/settings"),
);
let childApp = null;
let childRouter = null;
let removeAfterEach = null;
let disposed = false;

const DesktopWindowRoot = {
  name: "DesktopWindowRoot",
  render: () => h(RouterView),
};

function resolvePath(path) {
  return normalizeDesktopBridgePath(path) || "/workbench";
}

async function navigate(path) {
  if (!childRouter) return;
  const targetPath = resolvePath(path);
  if (childRouter.currentRoute.value.fullPath === targetPath) return;
  await childRouter.replace(targetPath);
  activeRoutePath.value = String(childRouter.currentRoute.value.path || "");
}

async function mountDesktopWindow() {
  try {
    childRouter = createDesktopWindowRouter(props.windowId);
    removeAfterEach = childRouter.afterEach((to) => {
      activeRoutePath.value = String(to.path || "");
      emit("route-change", {
        path: to.fullPath,
      });
    });
    await navigate(props.sourcePath);
    if (disposed || !mountPoint.value) return;

    childApp = createApp(DesktopWindowRoot);
    childApp.use(ElementPlus, { locale: zhCn });
    childApp.use(childRouter);
    childApp.mount(mountPoint.value);
  } catch (cause) {
    console.error("初始化桌面窗口组件失败", cause);
    error.value = String(cause?.message || cause || "窗口加载失败").trim();
  }
}

onMounted(() => {
  void mountDesktopWindow();
});

watch(
  () => props.sourcePath,
  (path) => {
    void navigate(path).catch((cause) => {
      console.error("切换桌面窗口路由失败", cause);
      error.value = String(cause?.message || cause || "窗口导航失败").trim();
    });
  },
);

onBeforeUnmount(() => {
  disposed = true;
  if (removeAfterEach) {
    removeAfterEach();
    removeAfterEach = null;
  }
  if (childApp) {
    childApp.unmount();
    childApp = null;
  }
  childRouter = null;
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

.desktop-window-host__mount--chat {
  display: flex;
  overflow: hidden;
}

.desktop-window-host__mount--settings {
  display: flex;
  min-height: 0;
  overflow-x: hidden;
  overflow-y: hidden;
}

.desktop-window-host__mount--settings :deep(> .settings-center-page) {
  width: 100%;
  height: 100% !important;
  min-height: 0;
  max-height: 100% !important;
  overflow: hidden;
}

.desktop-window-host__mount--chat :deep(> .chat-layout) {
  flex: 1 1 auto;
  width: 100%;
  min-height: 0;
  max-height: 100%;
  height: auto !important;
}

/* Allow desktop application content to extend and scroll inside its window. */
.desktop-window-host__mount :deep(> *) {
  width: 100%;
  min-height: 100%;
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
