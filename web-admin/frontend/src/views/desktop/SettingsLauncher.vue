<template>
  <section class="settings-launcher">
    <div class="settings-launcher__ambient" aria-hidden="true" />

    <header class="settings-launcher__hero">
      <div>
        <div class="settings-launcher__eyebrow">Platform Settings</div>
        <h1>平台入口收进设置中心。</h1>
        <p>启动台和工作台只保留设置中心。用户、角色、系统、模型源和监控这些平台菜单，都从这里以独立窗口打开。</p>
      </div>
    </header>

    <div class="settings-launcher__grid">
      <article
        v-for="app in apps"
        :key="app.id"
        class="settings-launcher__card"
      >
        <button
          type="button"
          class="settings-launcher__card-main"
          @click="openApp(app)"
        >
          <span class="settings-launcher__icon" :style="desktopIconStyle(app)">{{
            app.icon?.label || app.shortLabel
          }}</span>
          <strong>{{ app.label }}</strong>
          <small>{{ app.summary }}</small>
        </button>
        <button
          type="button"
          class="settings-launcher__pin"
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
  DESKTOP_SETTINGS_ITEMS,
  resolveDesktopLaunchPath,
} from "@/utils/desktop-shell.js";
import {
  openRouteInDesktop,
  requestDesktopPinApp,
} from "@/utils/desktop-app-bridge.js";

const router = useRouter();
const apps = computed(() =>
  DESKTOP_SETTINGS_ITEMS.filter((item) => canAccessDesktopApp(item)),
);

function desktopIconStyle(app) {
  return {
    "--desktop-app-icon-top": String(app?.icon?.top || "").trim(),
    "--desktop-app-icon-bottom": String(app?.icon?.bottom || "").trim(),
    "--desktop-app-icon-text": String(app?.icon?.text || "").trim() || "#ffffff",
    "--desktop-app-icon-glow": String(app?.icon?.glow || "").trim() || "rgba(15, 23, 42, 0.12)",
  };
}

function openApp(app) {
  if (!canAccessDesktopApp(app)) return;
  const launchPath = resolveDesktopLaunchPath(app.id);
  void openRouteInDesktop(router, launchPath, {
    mode: "focus-or-open",
    appId: app.id,
    title: app.label,
    summary: app.summary,
    eyebrow: app.eyebrow,
  });
}

function pinApp(app) {
  requestDesktopPinApp(app.id, {
    title: app.label,
  });
}
</script>

<style scoped>
.settings-launcher {
  position: relative;
  min-height: 100vh;
  padding: 34px;
  overflow: hidden;
  box-sizing: border-box;
  background:
    radial-gradient(circle at 10% 0%, rgba(125, 211, 252, 0.18), transparent 24%),
    radial-gradient(circle at 88% 16%, rgba(103, 232, 249, 0.14), transparent 22%),
    linear-gradient(180deg, #f5f4ef 0%, #f8fafc 42%, #edf2f7 100%);
}

.settings-launcher__ambient {
  position: absolute;
  inset: 8% auto auto 50%;
  width: 28rem;
  height: 28rem;
  border-radius: 999px;
  background: rgba(103, 232, 249, 0.14);
  filter: blur(82px);
  pointer-events: none;
  transform: translateX(-50%);
}

.settings-launcher__hero {
  position: relative;
  margin-bottom: 28px;
}

.settings-launcher__eyebrow {
  font-size: 12px;
  font-weight: 800;
  letter-spacing: 0.18em;
  text-transform: uppercase;
  color: #64748b;
}

.settings-launcher h1 {
  max-width: 11ch;
  margin: 10px 0 0;
  color: #0f172a;
  font-size: clamp(40px, 6.8vw, 74px);
  line-height: 0.98;
  letter-spacing: -0.06em;
}

.settings-launcher p {
  max-width: 56ch;
  margin: 16px 0 0;
  color: #475569;
  font-size: 15px;
  line-height: 1.75;
}

.settings-launcher__grid {
  position: relative;
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 14px;
}

.settings-launcher__card {
  position: relative;
  min-height: 188px;
  padding: 0;
  border: 1px solid rgba(255, 255, 255, 0.84);
  border-radius: 28px;
  background: rgba(255, 255, 255, 0.66);
  box-shadow: 0 14px 34px rgba(15, 23, 42, 0.06);
  backdrop-filter: blur(20px);
  text-align: left;
  cursor: pointer;
  transition:
    transform 0.18s ease,
    background-color 0.18s ease,
    box-shadow 0.18s ease;
}

.settings-launcher__card-main {
  width: 100%;
  min-height: 188px;
  display: grid;
  align-content: start;
  justify-items: start;
  gap: 12px;
  padding: 18px;
  border: 0;
  border-radius: 28px;
  background: transparent;
  color: inherit;
  font: inherit;
  text-align: left;
  cursor: pointer;
}

.settings-launcher__card:hover {
  transform: translateY(-3px);
  background: rgba(255, 255, 255, 0.84);
  box-shadow: 0 20px 46px rgba(15, 23, 42, 0.09);
}

.settings-launcher__pin {
  position: absolute;
  top: 14px;
  right: 14px;
  height: 30px;
  padding: 0 11px;
  border: 0;
  border-radius: 999px;
  background: rgba(15, 23, 42, 0.88);
  color: #fff;
  font: inherit;
  font-size: 12px;
  font-weight: 800;
  cursor: pointer;
  opacity: 0;
  transform: translateY(-4px);
  transition:
    opacity 0.18s ease,
    transform 0.18s ease;
}

.settings-launcher__card:hover .settings-launcher__pin,
.settings-launcher__pin:focus-visible {
  opacity: 1;
  transform: translateY(0);
}

.settings-launcher__icon {
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

.settings-launcher__card strong {
  color: #0f172a;
  font-size: 20px;
}

.settings-launcher__card small {
  color: #526071;
  font-size: 13px;
  line-height: 1.6;
}

@media (max-width: 960px) {
  .settings-launcher {
    padding: 22px;
  }

  .settings-launcher__grid {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }
}

@media (max-width: 620px) {
  .settings-launcher__grid {
    grid-template-columns: 1fr;
  }
}
</style>
