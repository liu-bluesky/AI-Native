<template>
  <section class="workbench-app">
    <div class="workbench-app__ambient" aria-hidden="true" />

    <header class="workbench-app__hero">
      <div>
        <div class="workbench-app__eyebrow">AI Desktop</div>
        <h1>从这里打开应用。</h1>
        <p>工作台不再跳去某个页面，它是桌面里的总控应用。项目、素材、市场和设置中心都会以窗口方式运行，平台菜单统一收进设置中心。</p>
      </div>
      <button type="button" class="workbench-app__primary" @click="openApp('/ai/chat', 'chat')">
        打开 AI 控制台
      </button>
    </header>

    <div class="workbench-app__grid">
      <article
        v-for="app in apps"
        :key="app.id"
        class="workbench-app__card"
      >
        <button
          type="button"
          class="workbench-app__card-main"
          @click="openApp(app.path, app.id)"
        >
          <span class="workbench-app__icon" :style="desktopIconStyle(app)">{{
            app.icon?.label || app.shortLabel
          }}</span>
          <strong>{{ app.label }}</strong>
          <small>{{ app.summary }}</small>
        </button>
        <button
          type="button"
          class="workbench-app__pin"
          @click="pinApp(app)"
        >
          加入 Dock
        </button>
      </article>
    </div>
  </section>
</template>

<script setup>
import { computed } from "vue";
import { useRouter } from "vue-router";
import {
  canAccessDesktopApp,
  DESKTOP_LAUNCHER_ITEMS,
  resolveDesktopLaunchPath,
} from "@/utils/desktop-shell.js";
import {
  openRouteInDesktop,
  requestDesktopPinApp,
} from "@/utils/desktop-app-bridge.js";

const router = useRouter();
const apps = computed(() =>
  DESKTOP_LAUNCHER_ITEMS.filter(
    (item) =>
      item.id !== "workbench"
      && (item.category !== "settings" || item.id === "settings-home")
      && canAccessDesktopApp(item),
  ),
);

function desktopIconStyle(app) {
  return {
    "--desktop-app-icon-top": String(app?.icon?.top || "").trim(),
    "--desktop-app-icon-bottom": String(app?.icon?.bottom || "").trim(),
    "--desktop-app-icon-text": String(app?.icon?.text || "").trim() || "#ffffff",
    "--desktop-app-icon-glow": String(app?.icon?.glow || "").trim() || "rgba(15, 23, 42, 0.12)",
  };
}

function openApp(path, appId) {
  const app = DESKTOP_LAUNCHER_ITEMS.find((item) => item.id === appId);
  if (app && !canAccessDesktopApp(app)) return;
  const launchPath = app ? resolveDesktopLaunchPath(app.id) : path;
  void openRouteInDesktop(router, launchPath, {
    mode: "focus-or-open",
    appId: app?.id || appId,
    title: app?.label || "AI 控制台",
    summary: app?.summary || "在桌面窗口中运行 AI 控制台。",
    eyebrow: app?.eyebrow || "AI Console",
  });
}

function pinApp(app) {
  requestDesktopPinApp(app.id, {
    title: app.label,
  });
}
</script>

<style scoped>
.workbench-app {
  position: relative;
  min-height: 100vh;
  padding: 34px;
  overflow: hidden;
  background:
    radial-gradient(circle at 12% 0%, rgba(125, 211, 252, 0.18), transparent 26%),
    radial-gradient(circle at 88% 14%, rgba(103, 232, 249, 0.14), transparent 22%),
    linear-gradient(180deg, #f5f4ef 0%, #f8fafc 42%, #edf2f7 100%);
  box-sizing: border-box;
}

.workbench-app__ambient {
  position: absolute;
  inset: 12% auto auto 50%;
  width: 32rem;
  height: 32rem;
  border-radius: 999px;
  background: rgba(56, 189, 248, 0.12);
  filter: blur(86px);
  pointer-events: none;
  transform: translateX(-50%);
}

.workbench-app__hero {
  position: relative;
  display: grid;
  grid-template-columns: minmax(0, 1fr) auto;
  align-items: end;
  gap: 24px;
  margin-bottom: 28px;
}

.workbench-app__eyebrow {
  font-size: 12px;
  font-weight: 800;
  letter-spacing: 0.18em;
  text-transform: uppercase;
  color: #64748b;
}

.workbench-app h1 {
  max-width: 10ch;
  margin: 10px 0 0;
  color: #0f172a;
  font-size: clamp(42px, 7vw, 78px);
  line-height: 0.96;
  letter-spacing: -0.06em;
}

.workbench-app p {
  max-width: 54ch;
  margin: 16px 0 0;
  color: #475569;
  font-size: 15px;
  line-height: 1.75;
}

.workbench-app__primary,
.workbench-app__card-main,
.workbench-app__pin {
  border: 0;
  cursor: pointer;
  font: inherit;
}

.workbench-app__primary {
  height: 46px;
  padding: 0 18px;
  border-radius: 999px;
  background: #0f172a;
  color: #fff;
  font-weight: 700;
  box-shadow: 0 18px 36px rgba(15, 23, 42, 0.16);
}

.workbench-app__grid {
  position: relative;
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 14px;
}

.workbench-app__card {
  position: relative;
  min-height: 190px;
  padding: 0;
  border: 1px solid rgba(255, 255, 255, 0.84);
  border-radius: 28px;
  background: rgba(255, 255, 255, 0.62);
  box-shadow: 0 14px 34px rgba(15, 23, 42, 0.06);
  backdrop-filter: blur(20px);
  text-align: left;
  transition:
    transform 0.18s ease,
    background-color 0.18s ease,
    box-shadow 0.18s ease;
}

.workbench-app__card-main {
  width: 100%;
  min-height: 188px;
  display: grid;
  align-content: start;
  justify-items: start;
  gap: 12px;
  padding: 18px;
  border-radius: 28px;
  background: transparent;
  color: inherit;
  text-align: left;
}

.workbench-app__card:hover {
  transform: translateY(-3px);
  background: rgba(255, 255, 255, 0.82);
  box-shadow: 0 20px 46px rgba(15, 23, 42, 0.09);
}

.workbench-app__pin {
  position: absolute;
  top: 14px;
  right: 14px;
  height: 30px;
  padding: 0 11px;
  border-radius: 999px;
  background: rgba(15, 23, 42, 0.88);
  color: #fff;
  font-size: 12px;
  font-weight: 800;
  opacity: 0;
  transform: translateY(-4px);
  transition:
    opacity 0.18s ease,
    transform 0.18s ease;
}

.workbench-app__card:hover .workbench-app__pin,
.workbench-app__pin:focus-visible {
  opacity: 1;
  transform: translateY(0);
}

.workbench-app__icon {
  width: 48px;
  height: 48px;
  border-radius: 16px;
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
  font-size: 12px;
  font-weight: 900;
}

.workbench-app__card strong {
  color: #0f172a;
  font-size: 20px;
}

.workbench-app__card small {
  color: #526071;
  font-size: 13px;
  line-height: 1.6;
}

@media (max-width: 960px) {
  .workbench-app {
    padding: 22px;
  }

  .workbench-app__hero {
    grid-template-columns: 1fr;
  }

  .workbench-app__grid {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }
}

@media (max-width: 620px) {
  .workbench-app__grid {
    grid-template-columns: 1fr;
  }
}
</style>
