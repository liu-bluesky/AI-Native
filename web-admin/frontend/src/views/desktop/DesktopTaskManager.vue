<template>
  <main class="desktop-task-manager">
    <header class="desktop-task-manager__header">
      <div>
        <div class="desktop-task-manager__eyebrow">Desktop System</div>
        <h1>任务管理器</h1>
        <p>显示当前真实打开的桌面窗口，可切换或单独关闭。</p>
      </div>
      <div class="desktop-task-manager__count">{{ orderedWindows.length }} 个窗口</div>
    </header>

    <section class="desktop-task-manager__panel" aria-labelledby="running-windows-title">
      <div class="desktop-task-manager__panel-head">
        <h2 id="running-windows-title">已启动窗口</h2>
        <span>实时状态</span>
      </div>

      <div v-if="orderedWindows.length" class="desktop-task-manager__list">
        <article
          v-for="windowItem in orderedWindows"
          :key="windowItem.id"
          class="desktop-task-manager__item"
          :class="{ 'is-active': windowItem.id === activeWindowId }"
        >
          <button
            type="button"
            class="desktop-task-manager__focus"
            @click="focusWindow(windowItem.id)"
          >
            <span class="desktop-task-manager__icon" :style="iconStyle(windowItem)">
              {{ appMeta(windowItem).icon?.label || appMeta(windowItem).shortLabel }}
            </span>
            <span class="desktop-task-manager__copy">
              <strong>{{ windowItem.title || appMeta(windowItem).label }}</strong>
              <small>{{ windowItem.eyebrow || appMeta(windowItem).eyebrow }}</small>
            </span>
          </button>
          <span class="desktop-task-manager__state">
            {{ windowItem.minimized ? "已最小化" : "运行中" }}
          </span>
          <button
            type="button"
            class="desktop-task-manager__close"
            :aria-label="`关闭${windowItem.title || appMeta(windowItem).label}`"
            @click="closeWindow(windowItem.id)"
          >
            关闭
          </button>
        </article>
      </div>
      <div v-else class="desktop-task-manager__empty">当前没有打开的桌面窗口。</div>
    </section>
  </main>
</template>

<script setup>
import { computed, onBeforeUnmount, onMounted, ref } from "vue";
import { getDesktopAppById } from "@/utils/desktop-shell.js";
import {
  DESKTOP_WINDOW_MANAGER_STATE_EVENT,
  readDesktopWindowManagerState,
  requestDesktopWindowManagerAction,
} from "@/utils/desktop-window-manager.js";

const desktopWindowState = ref(readDesktopWindowManagerState());

const activeWindowId = computed(
  () => String(desktopWindowState.value?.activeWindowId || "").trim(),
);
const orderedWindows = computed(() =>
  [...(Array.isArray(desktopWindowState.value?.windows)
    ? desktopWindowState.value.windows
    : [])].sort((left, right) => Number(right.zIndex || 0) - Number(left.zIndex || 0)),
);

function appMeta(windowItem) {
  return getDesktopAppById(windowItem?.appId);
}

function iconStyle(windowItem) {
  const icon = appMeta(windowItem)?.icon || {};
  return {
    "--task-manager-icon-top": icon.top || "#64748b",
    "--task-manager-icon-bottom": icon.bottom || "#334155",
    "--task-manager-icon-text": icon.text || "#ffffff",
  };
}

function focusWindow(windowId) {
  requestDesktopWindowManagerAction("focus", windowId);
}

function closeWindow(windowId) {
  requestDesktopWindowManagerAction("close", windowId);
}

function handleStateUpdate(event) {
  desktopWindowState.value = event?.detail || readDesktopWindowManagerState();
}

onMounted(() => {
  window.addEventListener(DESKTOP_WINDOW_MANAGER_STATE_EVENT, handleStateUpdate);
  desktopWindowState.value = readDesktopWindowManagerState();
});

onBeforeUnmount(() => {
  window.removeEventListener(DESKTOP_WINDOW_MANAGER_STATE_EVENT, handleStateUpdate);
});
</script>

<style scoped>
.desktop-task-manager {
  min-height: 100%;
  box-sizing: border-box;
  padding: 28px;
  background:
    radial-gradient(circle at top right, rgba(56, 189, 248, 0.14), transparent 30%),
    #f8fafc;
  color: #0f172a;
}

.desktop-task-manager__header,
.desktop-task-manager__panel-head,
.desktop-task-manager__item,
.desktop-task-manager__focus {
  display: flex;
  align-items: center;
}

.desktop-task-manager__header,
.desktop-task-manager__panel-head {
  justify-content: space-between;
  gap: 16px;
}

.desktop-task-manager__eyebrow {
  color: #64748b;
  font-size: 11px;
  font-weight: 800;
  letter-spacing: 0.16em;
  text-transform: uppercase;
}

h1,
h2,
p {
  margin: 0;
}

h1 {
  margin-top: 6px;
  font-size: 28px;
}

.desktop-task-manager__header p {
  margin-top: 8px;
  color: #64748b;
  font-size: 14px;
}

.desktop-task-manager__count {
  flex: 0 0 auto;
  padding: 8px 12px;
  border-radius: 999px;
  background: #e0f2fe;
  color: #0369a1;
  font-size: 13px;
  font-weight: 800;
}

.desktop-task-manager__panel {
  margin-top: 26px;
  padding: 18px;
  border: 1px solid #e2e8f0;
  border-radius: 22px;
  background: rgba(255, 255, 255, 0.9);
  box-shadow: 0 16px 32px rgba(15, 23, 42, 0.06);
}

.desktop-task-manager__panel-head {
  padding-bottom: 14px;
  border-bottom: 1px solid #e2e8f0;
}

h2 {
  font-size: 16px;
}

.desktop-task-manager__panel-head span,
.desktop-task-manager__copy small {
  color: #64748b;
  font-size: 12px;
}

.desktop-task-manager__list {
  display: grid;
  gap: 10px;
  margin-top: 14px;
}

.desktop-task-manager__item {
  gap: 12px;
  padding: 10px;
  border: 1px solid #e2e8f0;
  border-radius: 16px;
  background: #ffffff;
}

.desktop-task-manager__item.is-active {
  border-color: #7dd3fc;
  background: #f0f9ff;
}

.desktop-task-manager__focus {
  flex: 1;
  min-width: 0;
  gap: 12px;
  padding: 0;
  border: 0;
  background: transparent;
  text-align: left;
  cursor: pointer;
}

.desktop-task-manager__icon {
  display: grid;
  width: 40px;
  height: 40px;
  flex: 0 0 auto;
  place-items: center;
  border-radius: 12px;
  background: linear-gradient(160deg, var(--task-manager-icon-top), var(--task-manager-icon-bottom));
  color: var(--task-manager-icon-text);
  font-size: 11px;
  font-weight: 800;
}

.desktop-task-manager__copy {
  display: grid;
  min-width: 0;
  gap: 3px;
}

.desktop-task-manager__copy strong,
.desktop-task-manager__copy small {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.desktop-task-manager__state {
  color: #0369a1;
  font-size: 12px;
  font-weight: 700;
}

.desktop-task-manager__close {
  padding: 7px 11px;
  border: 0;
  border-radius: 10px;
  background: #fee2e2;
  color: #b91c1c;
  font: inherit;
  font-size: 12px;
  font-weight: 800;
  cursor: pointer;
}

.desktop-task-manager__close:hover {
  background: #fecaca;
}

.desktop-task-manager__empty {
  display: grid;
  min-height: 180px;
  place-items: center;
  color: #64748b;
  font-size: 14px;
}

@media (max-width: 640px) {
  .desktop-task-manager {
    padding: 18px;
  }

  .desktop-task-manager__header {
    align-items: flex-start;
    flex-direction: column;
  }

  .desktop-task-manager__state {
    display: none;
  }
}
</style>
