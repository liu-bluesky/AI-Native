<template>
  <div class="desktop-window-host">
    <div ref="mountPoint" class="desktop-window-host__mount" />
    <div v-if="error" class="desktop-window-host__error">{{ error }}</div>
  </div>
</template>

<script setup>
import { createApp, h, onBeforeUnmount, onMounted, ref, watch } from "vue";
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
}

async function mountDesktopWindow() {
  try {
    childRouter = createDesktopWindowRouter(props.windowId);
    removeAfterEach = childRouter.afterEach((to) => {
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
  overflow: hidden;
}

/* Keep each child application's root constrained to its desktop window. */
.desktop-window-host__mount :deep(> *) {
  width: 100%;
  height: 100% !important;
  min-height: 0 !important;
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
