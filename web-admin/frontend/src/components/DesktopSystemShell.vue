<template>
  <div class="desktop-system">
    <div
      class="desktop-system__wallpaper"
      :style="wallpaperStyle"
      aria-hidden="true"
    />
    <div
      class="desktop-system__ambient desktop-system__ambient--left"
      :style="ambientLeftStyle"
      aria-hidden="true"
    />
    <div
      class="desktop-system__ambient desktop-system__ambient--right"
      :style="ambientRightStyle"
      aria-hidden="true"
    />
    <div class="desktop-system__surface">
      <main class="desktop-system__workspace">
        <div
          v-if="showLauncher"
          class="desktop-system__launcher-backdrop"
          @click="$emit('toggle-launcher')"
        />
        <aside v-if="showLauncher" class="desktop-system__launcher" @click.stop>
          <div class="desktop-system__launcher-head">
            <div>
              <div class="desktop-system__launcher-eyebrow">All Apps</div>
              <h3>启动台</h3>
            </div>
            <button
              type="button"
              class="desktop-system__launcher-close"
              @click="$emit('toggle-launcher')"
            >
              收起
            </button>
          </div>

          <div class="desktop-system__launcher-actions">
            <button
              type="button"
              class="desktop-system__launcher-action desktop-system__launcher-action--danger"
              @click="$emit('clear-cache')"
            >
              清理当前缓存
            </button>
            <span>关闭窗口、清理桌面运行缓存，保留登录态、当前壁纸和已添加的 Dock 应用。</span>
          </div>

          <p class="desktop-system__launcher-note">
            底部 dock
            是常驻主应用。启动台是完整应用库，工作台和其他小应用都从这里打开。
          </p>

          <section
            v-for="section in launcherSections"
            :key="section.id"
            class="desktop-system__launcher-section"
          >
            <div class="desktop-system__launcher-section-head">
              <span>{{ section.label }}</span>
            </div>
            <div class="desktop-system__launcher-grid">
              <button
                v-for="item in section.items"
                :key="item.id"
                type="button"
                class="desktop-system__launcher-item"
                @click="$emit('launch-app', item)"
              >
                <span
                  class="desktop-system__launcher-icon"
                  :style="desktopIconStyle(item)"
                >{{ item.icon?.label || item.shortLabel }}</span>
                <strong>{{ item.label }}</strong>
                <small>{{ item.summary }}</small>
              </button>
            </div>
          </section>
        </aside>

        <section class="desktop-system__desktop">
          <div
            class="desktop-system__mesh"
            :style="meshStyle"
            aria-hidden="true"
          />
          <article
            v-for="window in visibleWindows"
            :key="window.id"
            :ref="(element) => setWindowElement(window.id, element)"
            :data-window-id="window.id"
            class="desktop-system__window"
            :class="{
              'is-active': window.id === activeWindowId,
              'is-minimized': window.minimized,
              'is-maximized': window.maximized,
              'is-dragging': draggingWindowId === window.id,
              'is-resizing': resizingWindowId === window.id,
            }"
            :style="windowStyle(window)"
            @pointerdown="handleWindowPointerDown(window)"
          >
            <div
              class="desktop-system__window-bar"
              @pointerdown="startWindowDrag($event, window)"
              @dblclick="handleWindowBarDoubleClick(window)"
            >
              <div class="desktop-system__traffic-group">
                <button
                  type="button"
                  class="desktop-system__traffic desktop-system__traffic--close"
                  @click.stop="$emit('close-window', window.id)"
                />
                <button
                  type="button"
                  class="desktop-system__traffic desktop-system__traffic--min"
                  @click.stop="$emit('minimize-window', window.id)"
                />
                <button
                  type="button"
                  class="desktop-system__traffic desktop-system__traffic--max"
                  @click.stop="$emit('maximize-window', window.id)"
                />
              </div>
              <div class="desktop-system__window-title-group">
                <div class="desktop-system__window-title">
                  {{ window.title }}
                </div>
                <div class="desktop-system__window-subtitle">
                  {{ window.eyebrow }}
                </div>
              </div>
              <div class="desktop-system__window-actions">
                <button
                  type="button"
                  class="desktop-system__window-action"
                  aria-label="刷新当前窗口"
                  title="刷新当前窗口"
                  @pointerdown.stop
                  @click.stop="$emit('refresh-window', window.id)"
                >
                  ↻
                </button>
                <slot name="toolbar" :window="window" />
              </div>
            </div>

            <div v-show="!window.minimized" class="desktop-system__window-body">
              <div class="desktop-system__window-summary">
                <p>{{ window.summary }}</p>
              </div>
              <div class="desktop-system__window-frame">
                <slot name="window" :window="window" />
              </div>
            </div>

            <template v-if="!window.maximized">
              <button
                v-for="direction in RESIZE_HANDLES"
                :key="`${window.id}-${direction}`"
                type="button"
                class="desktop-system__resize-handle"
                :class="`desktop-system__resize-handle--${direction}`"
                :aria-label="`Resize ${direction}`"
                @pointerdown.stop="startWindowResize($event, window, direction)"
              />
            </template>
          </article>
        </section>
      </main>

      <div
        v-if="hasMaximizedWindow"
        class="desktop-system__dock-trigger"
        aria-hidden="true"
        @pointerenter="revealDock"
      >
        <span class="desktop-system__dock-trigger-line" />
      </div>

      <nav
        ref="dockRef"
        class="desktop-system__dock"
        :class="{
          'is-auto-hidden': shouldAutoHideDock,
          'is-revealed': !shouldAutoHideDock,
          'is-dock-sorting': isDockSorting,
        }"
        :style="dockStyleVars"
        aria-label="桌面应用"
        @pointerenter="revealDock"
        @pointerleave="hideDock"
      >
        <span
          v-if="dockTooltipVisible"
          class="desktop-system__dock-tooltip"
          :style="dockTooltipStyle"
          role="tooltip"
        >
          {{ dockTooltipLabel }}
        </span>

        <div class="desktop-system__dock-scroll">
          <button
            type="button"
            class="desktop-system__dock-item desktop-system__dock-item--launcher"
            :class="{ 'is-active': showLauncher }"
            :style="dockLauncherStyle"
            aria-label="启动台"
            @pointerenter="showDockTooltip('启动台', $event)"
            @pointerleave="clearDockTooltip"
            @focus="showDockTooltip('启动台', $event)"
            @blur="clearDockTooltip"
            @click="$emit('toggle-launcher')"
          >
            <span class="desktop-system__dock-icon">+</span>
            <span class="desktop-system__dock-label">启动台</span>
          </button>

          <span
            v-for="item in dockItems"
            :key="item.id"
            class="desktop-system__dock-item-shell"
            :style="dockItemShellStyle(item)"
            :data-dock-app-id="item.id"
            :class="{
              'is-dock-dragging': draggingDockAppId === item.id,
              'is-dock-drop-target': dockDropTargetId === item.id && draggingDockAppId !== item.id,
            }"
            @pointerenter="showDockTooltip(item.label, $event)"
            @pointerleave="clearDockTooltip"
            @pointerdown="startDockDrag($event, item)"
          >
            <button
              type="button"
              class="desktop-system__dock-item"
              :class="{
                'is-active': activeWindow?.appId === item.id,
                'is-open': openAppIds.includes(item.id),
              }"
              :style="dockItemStyle(item)"
              :aria-label="item.label"
              @focus="showDockTooltip(item.label, $event)"
              @blur="clearDockTooltip"
              @click="handleDockItemClick(item)"
            >
              <span class="desktop-system__dock-icon" :style="desktopIconStyle(item)">{{
                item.icon?.label || item.shortLabel
              }}</span>
              <span class="desktop-system__dock-label">{{ item.label }}</span>
            </button>
            <button
              v-if="item.dockRemovable === true"
              type="button"
              class="desktop-system__dock-remove"
              aria-label="从 Dock 移除"
              @click.stop="$emit('unpin-dock-app', item)"
            >
              ×
            </button>
          </span>
        </div>
      </nav>
    </div>
  </div>
</template>

<script setup>
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from "vue";

const props = defineProps({
  dockItems: {
    type: Array,
    default: () => [],
  },
  launcherItems: {
    type: Array,
    default: () => [],
  },
  windows: {
    type: Array,
    default: () => [],
  },
  activeWindowId: {
    type: String,
    default: "",
  },
  statusText: {
    type: String,
    default: "System Ready",
  },
  brandName: {
    type: String,
    default: "AI 员工工厂",
  },
  brandMeta: {
    type: String,
    default: "Desktop Workspace",
  },
  showLauncher: {
    type: Boolean,
    default: false,
  },
  wallpaperAppearance: {
    type: Object,
    default: () => ({
      background: "",
      ambientLeft: "",
      ambientRight: "",
      meshOpacity: 1,
    }),
  },
});

const emit = defineEmits([
  "launch-app",
  "focus-window",
  "close-window",
  "minimize-window",
  "maximize-window",
  "refresh-window",
  "toggle-launcher",
  "move-window",
  "resize-window",
  "clear-cache",
  "unpin-dock-app",
  "reorder-dock-apps",
]);

const RESIZE_HANDLES = ["n", "e", "s", "w", "ne", "nw", "se", "sw"];
const DESKTOP_WINDOW_MIN_WIDTH = 720;
const DESKTOP_WINDOW_MIN_HEIGHT = 480;

const activeWindow = computed(
  () => props.windows.find((item) => item.id === props.activeWindowId) || null,
);

const visibleWindows = computed(() => props.windows);

const openAppIds = computed(() => props.windows.map((item) => item.appId));
const hasMaximizedWindow = computed(() =>
  props.windows.some((item) => item?.maximized && !item?.minimized),
);
const launcherSections = computed(() => {
  const sections = [];
  const sectionMap = new Map();
  for (const item of props.launcherItems) {
    const sectionId =
      String(item.category || "workspace").trim() || "workspace";
    if (!sectionMap.has(sectionId)) {
      const nextSection = {
        id: sectionId,
        label: String(item.categoryLabel || "工作应用").trim() || "工作应用",
        items: [],
      };
      sectionMap.set(sectionId, nextSection);
      sections.push(nextSection);
    }
    sectionMap.get(sectionId).items.push(item);
  }
  return sections;
});
const draggingWindowId = ref("");
const resizingWindowId = ref("");
const draggingDockAppId = ref("");
const dockDropTargetId = ref("");
const dockDragPreparing = ref(false);
const suppressDockClickAppId = ref("");
const dockRevealed = ref(false);
const dockRef = ref(null);
const dockDragOffsetX = ref(0);
const dockDragOffsetY = ref(0);
const dockDragAnchorX = ref(0);
const dockDragAnchorY = ref(0);
const dockTooltipLabel = ref("");
const dockTooltipLeft = ref(0);
const dockTooltipVisible = ref(false);
const wallpaperStyle = computed(() => ({
  background:
    String(props.wallpaperAppearance?.background || "").trim() || undefined,
}));
const ambientLeftStyle = computed(() => ({
  background:
    String(props.wallpaperAppearance?.ambientLeft || "").trim() || undefined,
}));
const ambientRightStyle = computed(() => ({
  background:
    String(props.wallpaperAppearance?.ambientRight || "").trim() || undefined,
}));
const meshStyle = computed(() => ({
  opacity: `${Number(props.wallpaperAppearance?.meshOpacity ?? 1)}`,
}));
const dockTone = computed(() => props.wallpaperAppearance?.dockTone || {});
const dockStyleVars = computed(() => ({
  "--dock-surface-border": "rgba(255, 255, 255, 0.34)",
  "--dock-surface-top": "rgba(255, 255, 255, 0.24)",
  "--dock-surface-mid": "rgba(255, 255, 255, 0.18)",
  "--dock-surface-bottom": "rgba(255, 255, 255, 0.12)",
  "--dock-surface-shadow": "rgba(15, 23, 42, 0.12)",
  "--dock-ambient-shadow": "rgba(15, 23, 42, 0.08)",
  "--dock-inner-highlight": "rgba(255, 255, 255, 0.28)",
  "--dock-edge-shade": "rgba(15, 23, 42, 0.08)",
  "--dock-item-top": String(dockTone.value?.itemTop || "rgba(255, 255, 255, 0.14)"),
  "--dock-item-bottom": String(dockTone.value?.itemBottom || "rgba(255, 255, 255, 0.05)"),
  "--dock-item-hover-top": String(dockTone.value?.itemHoverTop || "rgba(255, 255, 255, 0.34)"),
  "--dock-item-hover-bottom": String(dockTone.value?.itemHoverBottom || "rgba(255, 255, 255, 0.16)"),
  "--dock-item-border": String(dockTone.value?.itemBorder || "rgba(255, 255, 255, 0.24)"),
  "--dock-label-color": String(dockTone.value?.labelColor || "#526071"),
  "--dock-icon-border": String(dockTone.value?.iconBorder || "rgba(255, 255, 255, 0.26)"),
  "--dock-icon-top": String(dockTone.value?.iconTop || "rgba(250, 252, 255, 0.96)"),
  "--dock-icon-bottom": String(dockTone.value?.iconBottom || "rgba(232, 238, 246, 0.74)"),
  "--dock-icon-text": String(dockTone.value?.iconText || "#0f172a"),
  "--dock-indicator": String(dockTone.value?.indicator || "rgba(15, 23, 42, 0.58)"),
}));
const shouldAutoHideDock = computed(
  () => hasMaximizedWindow.value && !dockRevealed.value && !props.showLauncher,
);
const isDockSorting = computed(
  () => dockDragPreparing.value || Boolean(draggingDockAppId.value),
);
const dockTooltipStyle = computed(() => ({
  left: `${dockTooltipLeft.value}px`,
}));

const windowElements = new Map();
const dragState = {
  pointerId: null,
  windowId: "",
  startX: 0,
  startY: 0,
  originX: 0,
  originY: 0,
  width: 0,
  height: 0,
  nextBounds: null,
  frameId: null,
};
const dockDragState = {
  pointerId: null,
  appId: "",
  startX: 0,
  startY: 0,
  shellElement: null,
  active: false,
  moved: false,
};
const DOCK_DRAG_THRESHOLD = 6;
const dockFlipAnimations = new Map();
let dockLayoutSnapshot = new Map();
const resizeState = {
  pointerId: null,
  windowId: "",
  direction: "",
  startX: 0,
  startY: 0,
  originX: 0,
  originY: 0,
  originWidth: 0,
  originHeight: 0,
  nextBounds: null,
  frameId: null,
};

function windowStyle(window) {
  const zIndex = Number(window.zIndex || 1);
  const motionActive = Boolean(window?.motionActive);
  const motionTranslateX = Number(window?.motionTranslateX || 0);
  const motionTranslateY = Number(window?.motionTranslateY || 0);
  const motionScale = Number(window?.motionScale || 1);
  const motionOpacity = Number(window?.motionOpacity ?? 1);
  const motionBlur = Number(window?.motionBlur || 0);
  const motionDuration = Number(window?.motionDuration || 680);
  if (window?.maximized) {
    const style = {
      inset: "0",
      width: "100%",
      height: "100%",
      zIndex,
      transform: "none",
    };
    if (!motionActive) return style;
    return {
      ...style,
      transform: `translate(${motionTranslateX}px, ${motionTranslateY}px) scale(${motionScale})`,
      transformOrigin: "center center",
      opacity: motionOpacity,
      filter: `blur(${motionBlur}px)`,
      pointerEvents: window?.motionPhase === "minimize" ? "none" : undefined,
      transition: window?.motionTransitionEnabled
        ? `transform ${motionDuration}ms cubic-bezier(0.22, 0.82, 0.24, 1), opacity ${motionDuration}ms ease, filter ${motionDuration}ms ease`
        : "none",
    };
  }
  const width = Number(window.width || 1040);
  const height = Number(window.height || 720);
  const baseX = Number(window.x || 0);
  const baseY = Number(window.y || 0);
  const style = {
    zIndex,
    "--desktop-window-width": `${width}px`,
    "--desktop-window-height": `${height}px`,
    "--desktop-window-x": `${baseX}px`,
    "--desktop-window-y": `${baseY}px`,
  };
  if (!motionActive) return style;
  return {
    ...style,
    width: `${width}px`,
    height: `${height}px`,
    transform: `translate(${baseX + motionTranslateX}px, ${baseY + motionTranslateY}px) scale(${motionScale})`,
    transformOrigin: "center center",
    opacity: motionOpacity,
    filter: `blur(${motionBlur}px)`,
    pointerEvents: window?.motionPhase === "minimize" ? "none" : undefined,
    transition: window?.motionTransitionEnabled
      ? `transform ${motionDuration}ms cubic-bezier(0.22, 0.82, 0.24, 1), opacity ${motionDuration}ms ease, filter ${motionDuration}ms ease`
      : "none",
  };
}

function setWindowElement(windowId, element) {
  const targetId = String(windowId || "").trim();
  if (!targetId) return;
  if (!element) {
    windowElements.delete(targetId);
    return;
  }
  windowElements.set(targetId, element);
}

function getViewportBounds() {
  return {
    viewportWidth: globalThis.window?.innerWidth || 1440,
    viewportHeight: globalThis.window?.innerHeight || 900,
  };
}

function clampWindowBounds(bounds) {
  const { viewportWidth, viewportHeight } = getViewportBounds();
  const width = Math.min(
    Math.max(Number(bounds?.width || DESKTOP_WINDOW_MIN_WIDTH), DESKTOP_WINDOW_MIN_WIDTH),
    Math.max(DESKTOP_WINDOW_MIN_WIDTH, viewportWidth),
  );
  const height = Math.min(
    Math.max(Number(bounds?.height || DESKTOP_WINDOW_MIN_HEIGHT), DESKTOP_WINDOW_MIN_HEIGHT),
    Math.max(DESKTOP_WINDOW_MIN_HEIGHT, viewportHeight),
  );
  const x = Math.min(
    Math.max(Number(bounds?.x || 0), 0),
    Math.max(0, viewportWidth - width),
  );
  const y = Math.min(
    Math.max(Number(bounds?.y || 0), 0),
    Math.max(0, viewportHeight - height),
  );
  return { x, y, width, height };
}

function applyWindowPreviewBounds(windowId, bounds) {
  const element = windowElements.get(windowId);
  if (!element || !bounds) return;
  element.style.setProperty("--desktop-window-x", `${Number(bounds.x || 0)}px`);
  element.style.setProperty("--desktop-window-y", `${Number(bounds.y || 0)}px`);
  element.style.setProperty(
    "--desktop-window-width",
    `${Number(bounds.width || DESKTOP_WINDOW_MIN_WIDTH)}px`,
  );
  element.style.setProperty(
    "--desktop-window-height",
    `${Number(bounds.height || DESKTOP_WINDOW_MIN_HEIGHT)}px`,
  );
}

function clearWindowPreviewBounds(windowId) {
  const element = windowElements.get(windowId);
  if (!element) return;
  element.style.removeProperty("--desktop-window-x");
  element.style.removeProperty("--desktop-window-y");
  element.style.removeProperty("--desktop-window-width");
  element.style.removeProperty("--desktop-window-height");
}

function flushWindowDragPreview() {
  dragState.frameId = null;
  if (!dragState.windowId || !dragState.nextBounds) return;
  applyWindowPreviewBounds(dragState.windowId, dragState.nextBounds);
}

function flushWindowResizePreview() {
  resizeState.frameId = null;
  if (!resizeState.windowId || !resizeState.nextBounds) return;
  applyWindowPreviewBounds(resizeState.windowId, resizeState.nextBounds);
}

function scheduleWindowDragPreview(bounds) {
  dragState.nextBounds = bounds;
  if (dragState.frameId != null) return;
  dragState.frameId = globalThis.requestAnimationFrame(flushWindowDragPreview);
}

function scheduleWindowResizePreview(bounds) {
  resizeState.nextBounds = bounds;
  if (resizeState.frameId != null) return;
  resizeState.frameId = globalThis.requestAnimationFrame(flushWindowResizePreview);
}

function cancelWindowDragPreview() {
  if (dragState.frameId == null) return;
  globalThis.cancelAnimationFrame(dragState.frameId);
  dragState.frameId = null;
}

function cancelWindowResizePreview() {
  if (resizeState.frameId == null) return;
  globalThis.cancelAnimationFrame(resizeState.frameId);
  resizeState.frameId = null;
}

function dockItemShellStyle(item) {
  const appId = String(item?.id || "").trim();
  if (!appId || draggingDockAppId.value !== appId) return undefined;
  return {
    transform: `translate(${dockDragOffsetX.value}px, ${dockDragOffsetY.value}px)`,
    zIndex: 5,
    transition: "none",
  };
}

function desktopIconStyle(item) {
  const top = String(item?.icon?.top || "").trim();
  const bottom = String(item?.icon?.bottom || "").trim();
  const text = String(item?.icon?.text || "").trim() || "#ffffff";
  const glow = String(item?.icon?.glow || "").trim() || "rgba(15, 23, 42, 0.12)";
  return {
    "--desktop-app-icon-top": top,
    "--desktop-app-icon-bottom": bottom,
    "--desktop-app-icon-text": text,
    "--desktop-app-icon-glow": glow,
  };
}

function dockItemStyle(item) {
  const appId = String(item?.id || "").trim();
  if (!appId) return undefined;
  if (draggingDockAppId.value === appId) return undefined;
  return undefined;
}

const dockLauncherStyle = computed(() => undefined);

function measureDockLayout() {
  const positions = new Map();
  const dockElement = dockRef.value;
  if (!dockElement) return positions;
  const shells = dockElement.querySelectorAll(".desktop-system__dock-item-shell");
  for (const shell of shells) {
    const appId = String(shell?.dataset?.dockAppId || "").trim();
    if (!appId) continue;
    const rect = shell.getBoundingClientRect();
    positions.set(appId, {
      left: rect.left,
      top: rect.top,
    });
  }
  return positions;
}

async function animateDockLayoutShift() {
  if (isDockSorting.value || dockDragState.pointerId != null) return;
  const previousLayout = dockLayoutSnapshot;
  await nextTick();
  const nextLayout = measureDockLayout();
  if (previousLayout.size > 0) {
    for (const [appId, nextPosition] of nextLayout.entries()) {
      const previousPosition = previousLayout.get(appId);
      if (!previousPosition) continue;
      if (draggingDockAppId.value === appId) continue;
      const deltaX = previousPosition.left - nextPosition.left;
      const deltaY = previousPosition.top - nextPosition.top;
      if (Math.abs(deltaX) < 1 && Math.abs(deltaY) < 1) continue;
      const element = dockRef.value?.querySelector(
        `[data-dock-app-id="${appId}"]`,
      );
      if (!element?.animate) continue;
      dockFlipAnimations.get(appId)?.cancel();
      const animation = element.animate(
        [
          { transform: `translate(${deltaX}px, ${deltaY}px)` },
          { transform: "translate(0px, 0px)" },
        ],
        {
          duration: 320,
          easing: "cubic-bezier(0.22, 1, 0.36, 1)",
        },
      );
      dockFlipAnimations.set(appId, animation);
      animation.finished
        .catch(() => {})
        .finally(() => {
          if (dockFlipAnimations.get(appId) === animation) {
            dockFlipAnimations.delete(appId);
          }
        });
    }
  }
  dockLayoutSnapshot = nextLayout;
}

function cancelDockFlipAnimations() {
  for (const animation of dockFlipAnimations.values()) {
    animation.cancel();
  }
  dockFlipAnimations.clear();
}

function updateDockTooltipPosition(event) {
  const dockRect = dockRef.value?.getBoundingClientRect?.();
  const currentTargetRect = event?.currentTarget?.getBoundingClientRect?.();
  const fallbackRect = event?.target?.closest?.(".desktop-system__dock-item, .desktop-system__dock-item-shell")?.getBoundingClientRect?.();
  const targetRect = currentTargetRect || fallbackRect;
  if (!dockRect || !targetRect) return;
  dockTooltipLeft.value = targetRect.left - dockRect.left + targetRect.width / 2;
}

function showDockTooltip(label, event) {
  if (isDockSorting.value) return;
  const nextLabel = String(label || "").trim();
  if (!nextLabel) return;
  dockTooltipLabel.value = nextLabel;
  updateDockTooltipPosition(event);
  dockTooltipVisible.value = true;
}

function clearDockTooltip() {
  dockTooltipVisible.value = false;
}

function handleWindowPointerDown(desktopWindow) {
  const targetId = String(desktopWindow?.id || "").trim();
  if (!targetId || targetId === props.activeWindowId) return;
  emit("focus-window", targetId);
}

function startWindowDrag(event, desktopWindow) {
  const target = event?.target;
  if (target?.closest?.("button, a, input, textarea, select, [role='button']"))
    return;
  if (!desktopWindow || desktopWindow.minimized || desktopWindow.maximized)
    return;
  const pointerId = Number(event?.pointerId);
  if (!Number.isFinite(pointerId)) return;
  draggingWindowId.value = desktopWindow.id;
  dragState.pointerId = pointerId;
  dragState.windowId = desktopWindow.id;
  dragState.startX = Number(event.clientX || 0);
  dragState.startY = Number(event.clientY || 0);
  dragState.originX = Number(desktopWindow.x || 0);
  dragState.originY = Number(desktopWindow.y || 0);
  dragState.width = Number(desktopWindow.width || 1040);
  dragState.height = Number(desktopWindow.height || 720);
  dragState.nextBounds = {
    x: dragState.originX,
    y: dragState.originY,
    width: dragState.width,
    height: dragState.height,
  };
  emit("focus-window", desktopWindow.id);
  if (event.currentTarget?.setPointerCapture) {
    event.currentTarget.setPointerCapture(pointerId);
  }
  globalThis.window?.addEventListener("pointermove", handleWindowDrag);
  globalThis.window?.addEventListener("pointerup", stopWindowDrag);
  globalThis.window?.addEventListener("pointercancel", stopWindowDrag);
}

function startWindowResize(event, desktopWindow, direction) {
  if (!desktopWindow || desktopWindow.minimized || desktopWindow.maximized)
    return;
  const pointerId = Number(event?.pointerId);
  if (!Number.isFinite(pointerId)) return;
  resizeState.pointerId = pointerId;
  resizeState.windowId = desktopWindow.id;
  resizeState.direction = String(direction || "").trim();
  resizeState.startX = Number(event.clientX || 0);
  resizeState.startY = Number(event.clientY || 0);
  resizeState.originX = Number(desktopWindow.x || 0);
  resizeState.originY = Number(desktopWindow.y || 0);
  resizeState.originWidth = Number(desktopWindow.width || 1040);
  resizeState.originHeight = Number(desktopWindow.height || 720);
  resizeState.nextBounds = {
    x: resizeState.originX,
    y: resizeState.originY,
    width: resizeState.originWidth,
    height: resizeState.originHeight,
  };
  resizingWindowId.value = desktopWindow.id;
  emit("focus-window", desktopWindow.id);
  if (event.currentTarget?.setPointerCapture) {
    event.currentTarget.setPointerCapture(pointerId);
  }
  globalThis.window?.addEventListener("pointermove", handleWindowResize);
  globalThis.window?.addEventListener("pointerup", stopWindowResize);
  globalThis.window?.addEventListener("pointercancel", stopWindowResize);
}

function handleWindowDrag(event) {
  if (dragState.pointerId == null || dragState.windowId === "") return;
  if (Number(event.pointerId) !== dragState.pointerId) return;
  const nextBounds = clampWindowBounds({
    x: dragState.originX + Number(event.clientX || 0) - dragState.startX,
    y: dragState.originY + Number(event.clientY || 0) - dragState.startY,
    width: dragState.width,
    height: dragState.height,
  });
  scheduleWindowDragPreview(nextBounds);
}

function handleWindowResize(event) {
  if (resizeState.pointerId == null || resizeState.windowId === "") return;
  if (Number(event.pointerId) !== resizeState.pointerId) return;
  const deltaX = Number(event.clientX || 0) - resizeState.startX;
  const deltaY = Number(event.clientY || 0) - resizeState.startY;
  let nextBounds = {
    x: resizeState.originX,
    y: resizeState.originY,
    width: resizeState.originWidth,
    height: resizeState.originHeight,
  };
  if (resizeState.direction.includes("e")) {
    nextBounds.width = resizeState.originWidth + deltaX;
  }
  if (resizeState.direction.includes("s")) {
    nextBounds.height = resizeState.originHeight + deltaY;
  }
  if (resizeState.direction.includes("w")) {
    nextBounds.x = resizeState.originX + deltaX;
    nextBounds.width = resizeState.originWidth - deltaX;
  }
  if (resizeState.direction.includes("n")) {
    nextBounds.y = resizeState.originY + deltaY;
    nextBounds.height = resizeState.originHeight - deltaY;
  }
  nextBounds = clampWindowBounds(nextBounds);
  const rightEdge = resizeState.originX + resizeState.originWidth;
  const bottomEdge = resizeState.originY + resizeState.originHeight;
  if (resizeState.direction.includes("w")) {
    nextBounds = {
      ...nextBounds,
      x: Math.max(0, rightEdge - nextBounds.width),
    };
  }
  if (resizeState.direction.includes("n")) {
    nextBounds = {
      ...nextBounds,
      y: Math.max(0, bottomEdge - nextBounds.height),
    };
  }
  scheduleWindowResizePreview(nextBounds);
}

function stopWindowDrag(event) {
  if (dragState.pointerId == null) return;
  if (event && Number(event.pointerId) !== dragState.pointerId) return;
  cancelWindowDragPreview();
  if (dragState.nextBounds) {
    applyWindowPreviewBounds(dragState.windowId, dragState.nextBounds);
    emit("move-window", {
      windowId: dragState.windowId,
      x: dragState.nextBounds.x,
      y: dragState.nextBounds.y,
    });
    void nextTick(() => {
      clearWindowPreviewBounds(dragState.windowId);
    });
  }
  draggingWindowId.value = "";
  dragState.pointerId = null;
  dragState.windowId = "";
  dragState.width = 0;
  dragState.height = 0;
  dragState.nextBounds = null;
  globalThis.window?.removeEventListener("pointermove", handleWindowDrag);
  globalThis.window?.removeEventListener("pointerup", stopWindowDrag);
  globalThis.window?.removeEventListener("pointercancel", stopWindowDrag);
}

function stopWindowResize(event) {
  if (resizeState.pointerId == null) return;
  if (event && Number(event.pointerId) !== resizeState.pointerId) return;
  cancelWindowResizePreview();
  if (resizeState.nextBounds) {
    applyWindowPreviewBounds(resizeState.windowId, resizeState.nextBounds);
    emit("resize-window", {
      windowId: resizeState.windowId,
      direction: resizeState.direction,
      ...resizeState.nextBounds,
    });
    void nextTick(() => {
      clearWindowPreviewBounds(resizeState.windowId);
    });
  }
  resizingWindowId.value = "";
  resizeState.pointerId = null;
  resizeState.windowId = "";
  resizeState.direction = "";
  resizeState.nextBounds = null;
  globalThis.window?.removeEventListener("pointermove", handleWindowResize);
  globalThis.window?.removeEventListener("pointerup", stopWindowResize);
  globalThis.window?.removeEventListener("pointercancel", stopWindowResize);
}

function handleWindowBarDoubleClick(desktopWindow) {
  if (!desktopWindow) return;
  emit("maximize-window", desktopWindow.id);
}

function reorderDockItems(appId, targetAppId) {
  const sourceId = String(appId || "").trim();
  const targetId = String(targetAppId || "").trim();
  if (!sourceId || !targetId || sourceId === targetId) return;
  const orderedIds = props.dockItems.map((item) => item.id);
  const sourceIndex = orderedIds.indexOf(sourceId);
  const targetIndex = orderedIds.indexOf(targetId);
  if (sourceIndex === -1 || targetIndex === -1 || sourceIndex === targetIndex) return;
  const nextOrder = [...orderedIds];
  nextOrder.splice(sourceIndex, 1);
  nextOrder.splice(targetIndex, 0, sourceId);
  emit("reorder-dock-apps", nextOrder);
}

function startDockDrag(event, item) {
  const target = event?.target;
  if (target?.closest?.(".desktop-system__dock-remove")) return;
  const pointerId = Number(event?.pointerId);
  const appId = String(item?.id || "").trim();
  if (!Number.isFinite(pointerId) || !appId) return;
  dockDragState.pointerId = pointerId;
  dockDragState.appId = appId;
  dockDragState.startX = Number(event.clientX || 0);
  dockDragState.startY = Number(event.clientY || 0);
  dockDragState.shellElement = event.currentTarget || null;
  const shellRect = dockDragState.shellElement?.getBoundingClientRect?.();
  dockDragAnchorX.value = shellRect ? Number(event.clientX || 0) - shellRect.left : 0;
  dockDragAnchorY.value = shellRect ? Number(event.clientY || 0) - shellRect.top : 0;
  dockDragState.active = false;
  dockDragState.moved = false;
  dockDragPreparing.value = true;
  draggingDockAppId.value = "";
  dockDropTargetId.value = "";
  dockDragOffsetX.value = 0;
  dockDragOffsetY.value = 0;
  clearDockTooltip();
  cancelDockFlipAnimations();
  globalThis.window?.addEventListener("pointermove", handleDockDragMove);
  globalThis.window?.addEventListener("pointerup", stopDockDrag);
  globalThis.window?.addEventListener("pointercancel", stopDockDrag);
}

function handleDockDragMove(event) {
  if (dockDragState.pointerId == null || !dockDragState.appId) return;
  if (Number(event.pointerId) !== dockDragState.pointerId) return;
  const deltaX = Number(event.clientX || 0) - dockDragState.startX;
  const deltaY = Number(event.clientY || 0) - dockDragState.startY;
  const exceededThreshold =
    Math.abs(deltaX) > DOCK_DRAG_THRESHOLD ||
    Math.abs(deltaY) > DOCK_DRAG_THRESHOLD;
  if (!dockDragState.active) {
    if (!exceededThreshold) return;
    dockDragState.active = true;
    dockDragState.moved = true;
    cancelDockFlipAnimations();
    if (dockDragState.shellElement?.setPointerCapture) {
      dockDragState.shellElement.setPointerCapture(dockDragState.pointerId);
    }
    draggingDockAppId.value = dockDragState.appId;
    dockDropTargetId.value = dockDragState.appId;
    dockLayoutSnapshot = measureDockLayout();
  }
  const shellRect = dockDragState.shellElement?.getBoundingClientRect?.();
  if (shellRect) {
    dockDragOffsetX.value =
      Number(event.clientX || 0) - shellRect.left - dockDragAnchorX.value;
    dockDragOffsetY.value =
      Number(event.clientY || 0) - shellRect.top - dockDragAnchorY.value;
  } else {
    dockDragOffsetX.value = deltaX;
    dockDragOffsetY.value = deltaY;
  }
  dockDragState.moved = true;
  const target = document.elementFromPoint(
    Number(event.clientX || 0),
    Number(event.clientY || 0),
  );
  const shell = target?.closest?.(".desktop-system__dock-item-shell");
  const targetId = String(shell?.dataset?.dockAppId || "").trim();
  if (!targetId) return;
  dockDropTargetId.value = targetId;
  reorderDockItems(dockDragState.appId, targetId);
}

function stopDockDrag(event) {
  if (dockDragState.pointerId == null) return;
  if (event && Number(event.pointerId) !== dockDragState.pointerId) return;
  const draggedAppId = dockDragState.appId;
  if (dockDragState.active && dockDragState.moved && draggedAppId) {
    suppressDockClickAppId.value = draggedAppId;
    globalThis.window?.setTimeout(() => {
      if (suppressDockClickAppId.value === draggedAppId) {
        suppressDockClickAppId.value = "";
      }
    }, 0);
  }
  draggingDockAppId.value = "";
  dockDropTargetId.value = "";
  dockDragPreparing.value = false;
  dockDragOffsetX.value = 0;
  dockDragOffsetY.value = 0;
  dockDragAnchorX.value = 0;
  dockDragAnchorY.value = 0;
  clearDockTooltip();
  if (dockDragState.shellElement?.releasePointerCapture && dockDragState.pointerId != null) {
    try {
      dockDragState.shellElement.releasePointerCapture(dockDragState.pointerId);
    } catch {}
  }
  dockDragState.pointerId = null;
  dockDragState.appId = "";
  dockDragState.startX = 0;
  dockDragState.startY = 0;
  dockDragState.shellElement = null;
  dockDragState.active = false;
  dockDragState.moved = false;
  void nextTick(() => {
    dockLayoutSnapshot = measureDockLayout();
  });
  globalThis.window?.removeEventListener("pointermove", handleDockDragMove);
  globalThis.window?.removeEventListener("pointerup", stopDockDrag);
  globalThis.window?.removeEventListener("pointercancel", stopDockDrag);
}

function handleDockItemClick(item) {
  const appId = String(item?.id || "").trim();
  if (appId && suppressDockClickAppId.value === appId) {
    suppressDockClickAppId.value = "";
    return;
  }
  emit("launch-app", item);
}

function revealDock() {
  if (!hasMaximizedWindow.value) return;
  dockRevealed.value = true;
}

function hideDock() {
  if (!hasMaximizedWindow.value || props.showLauncher) {
    dockRevealed.value = false;
    clearDockTooltip();
    return;
  }
  dockRevealed.value = false;
  clearDockTooltip();
}

watch(hasMaximizedWindow, (value) => {
  if (!value) {
    dockRevealed.value = false;
    clearDockTooltip();
  }
});

watch(
  () => props.dockItems.map((item) => item.id).join("|"),
  () => {
    void animateDockLayoutShift();
  },
);

watch(
  () => props.showLauncher,
  (value) => {
    if (value) {
      dockRevealed.value = true;
      return;
    }
    if (hasMaximizedWindow.value) {
      dockRevealed.value = false;
    }
  },
);

onMounted(() => {
  void nextTick(() => {
    dockLayoutSnapshot = measureDockLayout();
  });
});

onBeforeUnmount(() => {
  cancelWindowDragPreview();
  cancelWindowResizePreview();
  stopWindowDrag();
  stopWindowResize();
  stopDockDrag();
  cancelDockFlipAnimations();
});
</script>

<style scoped>
.desktop-system {
  position: relative;
  min-height: 100vh;
  height: 100vh;
  overflow: hidden;
  background: #f8fafc;
}

.desktop-system__wallpaper {
  position: absolute;
  inset: 0;
  background:
    radial-gradient(
      circle at 12% 0%,
      rgba(125, 211, 252, 0.18),
      transparent 26%
    ),
    radial-gradient(
      circle at 88% 10%,
      rgba(103, 232, 249, 0.14),
      transparent 22%
    ),
    linear-gradient(180deg, #f5f4ef 0%, #f8fafc 40%, #edf2f7 100%);
  background-size: cover;
  background-position: center;
}

.desktop-system__ambient {
  position: absolute;
  border-radius: 999px;
  filter: blur(72px);
  pointer-events: none;
  opacity: 0.68;
}

.desktop-system__ambient--left {
  width: 24rem;
  height: 24rem;
  top: -7rem;
  left: -8rem;
  background: rgba(125, 211, 252, 0.28);
}

.desktop-system__ambient--right {
  width: 20rem;
  height: 20rem;
  right: -6rem;
  top: 7rem;
  background: rgba(103, 232, 249, 0.2);
}

.desktop-system__mesh {
  position: absolute;
  inset: 0;
  z-index: 0;
  background:
    linear-gradient(rgba(15, 23, 42, 0.03) 1px, transparent 1px),
    linear-gradient(90deg, rgba(15, 23, 42, 0.02) 1px, transparent 1px);
  background-size: 56px 56px;
  mask-image: linear-gradient(180deg, rgba(0, 0, 0, 0.72), transparent 84%);
  pointer-events: none;
}

.desktop-system__surface {
  position: relative;
  z-index: 1;
  display: flex;
  flex-direction: column;
  min-height: 100%;
  height: 100%;
  box-sizing: border-box;
}

.desktop-system__launcher-eyebrow {
  font-size: 11px;
  color: #64748b;
}

.desktop-system__workspace {
  position: relative;
  flex: 1;
  min-height: 0;
  padding-bottom: 4px;
}

.desktop-system__launcher-backdrop {
  position: absolute;
  inset: 0;
  z-index: 19;
  border-radius: 26px;
  background: rgba(15, 23, 42, 0.08);
  backdrop-filter: blur(8px);
}

.desktop-system__launcher {
  position: absolute;
  top: 0;
  left: 0;
  z-index: 20;
  width: min(380px, calc(100vw - 28px));
  max-height: calc(100vh - 132px);
  overflow: auto;
  display: flex;
  flex-direction: column;
  gap: 16px;
  padding: 18px;
  border-radius: 28px;
  border: 1px solid rgba(255, 255, 255, 0.88);
  background: rgba(255, 255, 255, 0.74);
  box-shadow: 0 22px 58px rgba(15, 23, 42, 0.08);
  backdrop-filter: blur(20px);
}

.desktop-system__launcher-head {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 12px;
}

.desktop-system__launcher-head h3 {
  margin: 6px 0 0;
  color: #0f172a;
  font-size: 24px;
  line-height: 1.1;
}

.desktop-system__launcher-close {
  padding: 0;
  border: 0;
  background: transparent;
  color: #475569;
  font-size: 13px;
  font-weight: 600;
  cursor: pointer;
}

.desktop-system__launcher-actions {
  display: grid;
  gap: 8px;
  padding: 12px;
  border: 1px solid rgba(251, 113, 133, 0.22);
  border-radius: 20px;
  background: rgba(255, 255, 255, 0.62);
}

.desktop-system__launcher-actions span {
  color: #64748b;
  font-size: 12px;
  line-height: 1.55;
}

.desktop-system__launcher-action {
  justify-self: start;
  min-height: 34px;
  padding: 0 14px;
  border: 0;
  border-radius: 999px;
  font: inherit;
  font-size: 13px;
  font-weight: 800;
  cursor: pointer;
}

.desktop-system__launcher-action--danger {
  background: #0f172a;
  color: #fff;
  box-shadow: 0 12px 26px rgba(15, 23, 42, 0.14);
}

.desktop-system__launcher-section {
  display: grid;
  gap: 10px;
}

.desktop-system__launcher-section-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  color: #64748b;
  font-size: 11px;
  font-weight: 800;
  letter-spacing: 0.16em;
  text-transform: uppercase;
}

.desktop-system__launcher-grid {
  display: grid;
  gap: 12px;
}

.desktop-system__launcher-note {
  margin: 0;
  color: #526071;
  font-size: 13px;
  line-height: 1.6;
}

.desktop-system__launcher-item {
  display: grid;
  gap: 8px;
  justify-items: start;
  padding: 14px;
  border: 1px solid rgba(226, 232, 240, 0.86);
  border-radius: 22px;
  background: rgba(248, 250, 252, 0.86);
  text-align: left;
  cursor: pointer;
}

.desktop-system__launcher-icon {
  width: 42px;
  height: 42px;
  border-radius: 14px;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  background: linear-gradient(
    180deg,
    var(--desktop-app-icon-top, #94a3b8),
    var(--desktop-app-icon-bottom, #475569)
  );
  box-shadow: 0 14px 28px var(--desktop-app-icon-glow, rgba(15, 23, 42, 0.12));
  color: var(--desktop-app-icon-text, #ffffff);
  font-size: 11px;
  font-weight: 800;
  text-shadow: 0 1px 1px rgba(15, 23, 42, 0.18);
}

.desktop-system__launcher-item strong {
  color: #0f172a;
  font-size: 16px;
}

.desktop-system__launcher-item small {
  color: #526071;
  line-height: 1.55;
}

.desktop-system__desktop {
  position: relative;
  min-height: 0;
  height: 100vh;
  isolation: isolate;
  /* border-radius: 26px; */
  border: 0;
  background:
    radial-gradient(
      circle at 18% 18%,
      rgba(255, 255, 255, 0.38),
      transparent 28%
    ),
    rgba(255, 255, 255, 0.12);
  box-shadow: none;
  overflow: hidden;
}

.desktop-system__window {
  position: absolute;
  top: 0;
  left: 0;
  z-index: 1;
  width: var(--desktop-window-width, 1040px);
  height: var(--desktop-window-height, 720px);
  min-width: 720px;
  min-height: 480px;
  border-radius: 30px;
  border: 1px solid rgba(255, 255, 255, 0.9);
  background: rgba(255, 255, 255, 0.76);
  box-shadow:
    0 24px 64px rgba(15, 23, 42, 0.12),
    0 4px 14px rgba(15, 23, 42, 0.04);
  backdrop-filter: blur(20px);
  overflow: hidden;
  display: grid;
  grid-template-rows: auto minmax(0, 1fr);
  transform: translate3d(
    var(--desktop-window-x, 0px),
    var(--desktop-window-y, 0px),
    0
  );
  transition:
    box-shadow 0.18s ease,
    transform 0.18s ease,
    opacity 0.18s ease,
    filter 0.18s ease;
  will-change: transform, opacity, filter;
}

.desktop-system__resize-handle {
  position: absolute;
  z-index: 3;
  padding: 0;
  border: 0;
  background: transparent;
}

.desktop-system__resize-handle--n,
.desktop-system__resize-handle--s {
  left: 12px;
  right: 12px;
  height: 12px;
}

.desktop-system__resize-handle--n {
  top: -6px;
  cursor: ns-resize;
}

.desktop-system__resize-handle--s {
  bottom: -6px;
  cursor: ns-resize;
}

.desktop-system__resize-handle--e,
.desktop-system__resize-handle--w {
  top: 12px;
  bottom: 12px;
  width: 12px;
}

.desktop-system__resize-handle--e {
  right: -6px;
  cursor: ew-resize;
}

.desktop-system__resize-handle--w {
  left: -6px;
  cursor: ew-resize;
}

.desktop-system__resize-handle--ne,
.desktop-system__resize-handle--nw,
.desktop-system__resize-handle--se,
.desktop-system__resize-handle--sw {
  width: 18px;
  height: 18px;
}

.desktop-system__resize-handle--ne {
  top: -8px;
  right: -8px;
  cursor: nesw-resize;
}

.desktop-system__resize-handle--nw {
  top: -8px;
  left: -8px;
  cursor: nwse-resize;
}

.desktop-system__resize-handle--se {
  right: -8px;
  bottom: -8px;
  cursor: nwse-resize;
}

.desktop-system__resize-handle--sw {
  left: -8px;
  bottom: -8px;
  cursor: nesw-resize;
}

.desktop-system__window.is-active {
  box-shadow:
    0 30px 84px rgba(15, 23, 42, 0.16),
    0 8px 24px rgba(15, 23, 42, 0.08);
}

.desktop-system__window.is-minimized {
  opacity: 0;
  pointer-events: none;
  transition: none;
}

.desktop-system__window.is-maximized {
  inset: 0;
  width: 100%;
  height: 100%;
  border-radius: 0;
}

.desktop-system__window.is-dragging {
  transition: none;
}

.desktop-system__window.is-resizing {
  transition: none;
}

.desktop-system__window-bar {
  display: grid;
  grid-template-columns: auto minmax(0, 1fr) auto;
  align-items: center;
  gap: 12px;
  padding: 14px 18px;
  border-bottom: 1px solid rgba(226, 232, 240, 0.82);
  cursor: grab;
  user-select: none;
}

.desktop-system__window.is-dragging .desktop-system__window-bar,
.desktop-system__window-bar:active {
  cursor: grabbing;
}

.desktop-system__traffic-group {
  display: inline-flex;
  align-items: center;
  gap: 8px;
}

.desktop-system__traffic {
  width: 15px;
  height: 15px;
  padding: 0;
  border: 0;
  border-radius: 999px;
  cursor: pointer;
}

.desktop-system__traffic--close {
  background: #fb7185;
}

.desktop-system__traffic--min {
  background: #fbbf24;
}

.desktop-system__traffic--max {
  background: #4ade80;
}

.desktop-system__window-title-group {
  min-width: 0;
  pointer-events: none;
}

.desktop-system__window-title {
  font-size: 14px;
  font-weight: 700;
  color: #0f172a;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.desktop-system__window-subtitle {
  margin-top: 3px;
  font-size: 11px;
  color: #64748b;
  letter-spacing: 0.12em;
  text-transform: uppercase;
}

.desktop-system__window-actions {
  display: flex;
  align-items: center;
  justify-content: flex-end;
  gap: 10px;
}

.desktop-system__window-action {
  width: 32px;
  height: 32px;
  border: 1px solid rgba(226, 232, 240, 0.88);
  border-radius: 999px;
  background: rgba(255, 255, 255, 0.82);
  color: #475569;
  font-size: 16px;
  line-height: 1;
  cursor: pointer;
  transition:
    transform 180ms ease,
    border-color 180ms ease,
    box-shadow 180ms ease,
    color 180ms ease,
    background 180ms ease;
}

.desktop-system__window-action:hover {
  transform: translateY(-1px);
  color: #0f172a;
  border-color: rgba(56, 189, 248, 0.26);
  background: rgba(255, 255, 255, 0.92);
  box-shadow: 0 12px 26px rgba(15, 23, 42, 0.08);
}

.desktop-system__window-handle {
  height: 30px;
  padding: 0 10px;
  border: 1px solid rgba(226, 232, 240, 0.88);
  border-radius: 999px;
  background: rgba(255, 255, 255, 0.82);
  color: #475569;
  font-size: 12px;
  font-weight: 600;
  cursor: grab;
}

.desktop-system__window-handle:active {
  cursor: grabbing;
}

.desktop-system__window-body {
  min-height: 0;
  display: grid;
  grid-template-rows: auto minmax(0, 1fr);
}

.desktop-system__window-summary {
  padding: 14px 18px 10px;
  color: #526071;
  font-size: 13px;
  line-height: 1.6;
}

.desktop-system__window-summary p {
  margin: 0;
}

.desktop-system__window-frame {
  min-height: 0;
  padding: 0 14px 14px;
}

.desktop-system__dock-trigger {
  position: fixed;
  left: 0;
  right: 0;
  bottom: 0;
  z-index: 79;
  height: 22px;
  display: flex;
  align-items: flex-end;
  justify-content: center;
  pointer-events: auto;
}

.desktop-system__dock-trigger-line {
  width: 132px;
  height: 4px;
  margin-bottom: 5px;
  border-radius: 999px;
  background: rgba(255, 255, 255, 0.72);
  box-shadow:
    0 8px 18px rgba(15, 23, 42, 0.14),
    0 0 0 1px rgba(255, 255, 255, 0.42);
  opacity: 0.9;
  animation: desktop-dock-trigger-pulse 2.2s ease-in-out infinite;
}

.desktop-system__dock {
  position: fixed;
  left: 50%;
  bottom: max(12px, env(safe-area-inset-bottom));
  z-index: 80;
  transform: translateX(-50%);
  max-width: calc(100vw - 24px);
  display: block;
  padding: 9px 12px;
  border-radius: 999px;
  border: 1px solid var(--dock-surface-border);
  background: color-mix(in srgb, var(--dock-surface-top) 100%, transparent);
  box-shadow:
    0 18px 40px var(--dock-surface-shadow),
    0 8px 18px var(--dock-ambient-shadow),
    inset 0 1px 0 var(--dock-inner-highlight),
    inset 0 -1px 0 var(--dock-edge-shade);
  backdrop-filter: blur(26px) saturate(1.08);
  -webkit-backdrop-filter: blur(26px) saturate(1.08);
  transition:
    transform 0.26s cubic-bezier(0.22, 0.82, 0.24, 1),
    opacity 0.22s ease,
    box-shadow 0.22s ease;
  will-change: transform, opacity;
  overflow: visible;
  isolation: isolate;
}

.desktop-system__dock-scroll {
  position: relative;
  z-index: 1;
  display: inline-flex;
  align-items: center;
  gap: 10px;
  box-sizing: border-box;
  max-width: calc(100vw - 48px);
  margin: -8px;
  padding: 8px;
  overflow-x: auto;
  overflow-y: visible;
  scrollbar-width: none;
}

.desktop-system__dock-scroll::-webkit-scrollbar {
  display: none;
}

.desktop-system__dock::before,
.desktop-system__dock::after {
  content: "";
  position: absolute;
  inset: 0;
  border-radius: inherit;
  pointer-events: none;
}

.desktop-system__dock::before {
  inset: 1px;
  background: linear-gradient(
    180deg,
    rgba(255, 255, 255, 0.22) 0%,
    rgba(255, 255, 255, 0.08) 38%,
    rgba(255, 255, 255, 0.02) 100%
  );
  opacity: 0.9;
}

.desktop-system__dock::after {
  background: linear-gradient(
    180deg,
    rgba(255, 255, 255, 0.04) 0%,
    rgba(255, 255, 255, 0) 44%,
    rgba(15, 23, 42, 0.08) 100%
  );
  opacity: 0.65;
}

.desktop-system__dock.is-auto-hidden {
  transform: translateX(-50%) translateY(calc(100% - 10px));
  opacity: 0;
  pointer-events: none;
}

.desktop-system__dock.is-revealed {
  transform: translateX(-50%) translateY(0);
  opacity: 1;
}

.desktop-system__dock-tooltip {
  position: absolute;
  left: 0;
  bottom: calc(100% + 12px);
  transform: translateX(-50%);
  padding: 7px 12px;
  border: 1px solid rgba(255, 255, 255, 0.82);
  border-radius: 999px;
  background: rgba(255, 255, 255, 0.78);
  color: #0f172a;
  font-size: 12px;
  font-weight: 700;
  line-height: 1;
  white-space: nowrap;
  box-shadow:
    0 12px 24px rgba(15, 23, 42, 0.12),
    inset 0 1px 0 rgba(255, 255, 255, 0.7);
  backdrop-filter: blur(20px) saturate(1.04);
  -webkit-backdrop-filter: blur(20px) saturate(1.04);
  pointer-events: none;
  z-index: 12;
}

.desktop-system__dock-item-shell {
  position: relative;
  display: inline-grid;
  z-index: 1;
}

.desktop-system__dock.is-dock-sorting .desktop-system__dock-item-shell,
.desktop-system__dock.is-dock-sorting .desktop-system__dock-item {
  transition: none;
}

.desktop-system__dock-item-shell.is-dock-dragging {
  z-index: 5;
  pointer-events: none;
}

.desktop-system__dock-item-shell.is-dock-dragging .desktop-system__dock-item {
  transform: translateY(-6px);
  background: color-mix(in srgb, var(--dock-item-hover-top) 72%, transparent);
  box-shadow:
    0 18px 32px var(--dock-surface-shadow),
    inset 0 1px 0 var(--dock-inner-highlight);
}

.desktop-system__dock-item-shell.is-dock-drop-target:not(.is-dock-dragging) {
  transform: translateY(-1px);
}

.desktop-system__dock.is-dock-sorting
  .desktop-system__dock-item-shell.is-dock-drop-target:not(.is-dock-dragging) {
  transform: none;
}

.desktop-system__dock.is-dock-sorting
  .desktop-system__dock-item-shell.is-dock-drop-target:not(.is-dock-dragging)
  .desktop-system__dock-item {
  box-shadow:
    0 10px 24px rgba(15, 23, 42, 0.1),
    inset 0 1px 0 var(--dock-inner-highlight);
}

.desktop-system__dock-item {
  min-width: 76px;
  display: grid;
  gap: 5px;
  justify-items: center;
  padding: 8px 10px 13px;
  border: 0;
  border-radius: 16px;
  background: linear-gradient(
    180deg,
    var(--dock-item-top),
    var(--dock-item-bottom)
  );
  color: var(--dock-label-color);
  cursor: pointer;
  transition:
    background 0.24s ease,
    box-shadow 0.24s ease,
    border-color 0.24s ease;
  border: 1px solid transparent;
  position: relative;
  z-index: 1;
}

.desktop-system__dock-item:hover,
.desktop-system__dock-item.is-active {
  border-color: var(--dock-item-border);
  background:
    linear-gradient(
      180deg,
      var(--dock-item-hover-top),
      var(--dock-item-hover-bottom)
    );
  box-shadow:
    0 12px 28px var(--dock-surface-shadow),
    inset 0 1px 0 var(--dock-inner-highlight);
}

.desktop-system__dock-item.is-open::after {
  content: "";
  width: 6px;
  height: 6px;
  position: absolute;
  bottom: 3px;
  border-radius: 999px;
  background: var(--dock-indicator);
  opacity: 1;
}

.desktop-system__dock-item--launcher .desktop-system__dock-icon {
  font-size: 18px;
}

.desktop-system__dock-icon {
  width: 36px;
  height: 36px;
  border-radius: 13px;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  border: 1px solid color-mix(in srgb, var(--desktop-app-icon-bottom, #475569) 28%, white);
  background: linear-gradient(
    180deg,
    var(--desktop-app-icon-top, var(--dock-icon-top)),
    var(--desktop-app-icon-bottom, var(--dock-icon-bottom))
  );
  box-shadow:
    inset 0 1px 0 rgba(255, 255, 255, 0.22),
    0 10px 20px var(--desktop-app-icon-glow, color-mix(in srgb, var(--dock-ambient-shadow) 70%, transparent));
  font-size: 11px;
  font-weight: 800;
  color: var(--desktop-app-icon-text, var(--dock-icon-text));
  text-shadow: 0 1px 1px rgba(15, 23, 42, 0.18);
}

.desktop-system__dock-label {
  width: 100%;
  max-width: 72px;
  overflow: hidden;
  color: var(--dock-label-color);
  font-size: 11px;
  font-weight: 800;
  line-height: 1.15;
  text-align: center;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.desktop-system__dock-remove {
  position: absolute;
  top: -8px;
  right: -8px;
  z-index: 6;
  width: 20px;
  height: 20px;
  padding: 0;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  border: 1px solid rgba(255, 255, 255, 0.76);
  border-radius: 999px;
  background: rgba(15, 23, 42, 0.86);
  color: #fff;
  font-size: 13px;
  line-height: 1;
  cursor: pointer;
  opacity: 0;
  transform: scale(0.86);
  box-shadow:
    0 8px 18px rgba(15, 23, 42, 0.18),
    inset 0 1px 0 rgba(255, 255, 255, 0.26);
  transition:
    opacity 0.18s ease,
    transform 0.18s ease;
}

.desktop-system__dock-item-shell:hover .desktop-system__dock-remove {
  opacity: 1;
  transform: scale(1);
}

@keyframes desktop-dock-trigger-pulse {
  0%,
  100% {
    opacity: 0.4;
    transform: scaleX(0.94);
  }
  50% {
    opacity: 0.92;
    transform: scaleX(1);
  }
}

@media (max-width: 1200px) {
  .desktop-system__launcher {
    width: min(100%, calc(100vw - 20px));
  }
}

@media (max-width: 960px) {
  /* .desktop-system__surface {
    padding: 10px 10px 92px;
  } */

  .desktop-system__dock {
    width: calc(100% - 20px);
    padding: 8px 10px;
  }

  .desktop-system__dock-scroll {
    width: 100%;
    max-width: none;
    gap: 6px;
  }

  .desktop-system__dock-item {
    min-width: 0;
    width: 68px;
  }

  .desktop-system__window {
    min-width: 0;
    width: calc(100% - 16px) !important;
    height: calc(100% - 16px) !important;
    transform: translate(8px, 8px) !important;
  }
}
</style>
